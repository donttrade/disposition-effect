"""Functional regression checks for the donttrade static site.

Re-checks the link, anchor, overflow, console-error and calculator findings from
the T1 functional audit (2026-10-19). Read-only: it never submits a form.

Run:
    pip install --break-system-packages pytest requests beautifulsoup4 playwright
    pytest -q test_site_functional.py                    # against https://donttrade.ca
    DT_BASE=http://localhost:8000 pytest -q test_site_functional.py
    DT_SKIP_EXTERNAL=1 pytest -q ...                     # offline / CI without egress

Polite by design: every HTTP request is spaced at least DT_DELAY seconds (default 1.0).
Chromium: set PW_CHROMIUM=/opt/pw-browsers/chromium (or any path) to override.
"""
import os
import re
import time
from functools import lru_cache
from urllib.parse import urljoin, urldefrag, urlparse

import pytest
import requests
from bs4 import BeautifulSoup

BASE = os.environ.get("DT_BASE", "https://donttrade.ca").rstrip("/")
DELAY = float(os.environ.get("DT_DELAY", "1.0"))
SKIP_EXTERNAL = os.environ.get("DT_SKIP_EXTERNAL") == "1"
INTERNAL_HOSTS = {urlparse(BASE).netloc, "donttrade.ca", "www.donttrade.ca"}
VIEWPORTS = [(375, 812), (768, 1024), (1440, 900)]

# Hosts that block scripted clients (403/202 challenge) even when the page is fine.
# A failure on these is "unverifiable", not "broken".
BOT_BLOCKING_HOSTS = {
    "github.com",  # org/user pages 403 behind some proxies; repo-file URLs are checked via a 404 only
    "academic.oup.com",
    "onlinelibrary.wiley.com",
    "www.fxstreet.com",
    "dataverse.harvard.edu",
    "laws-lois.justice.gc.ca",
}

_session = requests.Session()
_session.headers["User-Agent"] = "donttrade-site-tests/1.0 (+read-only QA)"
_last = [0.0]


def _get(url, method="GET", allow_redirects=False):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    return _session.request(method, url, allow_redirects=allow_redirects, timeout=25)


def _is_internal(url):
    return urlparse(url).netloc in INTERNAL_HOSTS


def _localise(url):
    """Map an absolute donttrade.ca URL onto DT_BASE so the suite can run against a local build."""
    p = urlparse(url)
    if p.netloc in INTERNAL_HOSTS:
        return BASE + (p.path or "/") + (("?" + p.query) if p.query else "")
    return url


@lru_cache(maxsize=1)
def crawl():
    """BFS over internal pages seeded from / and sitemap.xml. Returns (pages, links, ids)."""
    seeds = [BASE + "/"]
    r = _get(BASE + "/sitemap.xml")
    if r.status_code == 200:
        seeds += [_localise(u) for u in re.findall(r"<loc>(.*?)</loc>", r.text)]
    queue, seen = list(dict.fromkeys(seeds)), set(seeds)
    pages, links, ids = {}, [], {}
    while queue:
        u = queue.pop(0)
        resp = _get(u)
        pages[u] = resp.status_code
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        ids[u] = {t.get("id") for t in soup.find_all(id=True)} | {
            a.get("name") for a in soup.find_all("a", attrs={"name": True})
        }
        for tag, attr in (("a", "href"), ("link", "href"), ("script", "src"), ("img", "src"), ("form", "action")):
            for t in soup.find_all(tag):
                h = t.get(attr)
                if not h or h.startswith(("mailto:", "tel:", "javascript:", "data:")):
                    continue
                a = _localise(urljoin(u, h))
                links.append((u, h, a))
                d = urldefrag(a)[0]
                if tag == "a" and _is_internal(d) and d not in seen and not re.search(r"\.(svg|csv|txt|png|xml|pdf)$", d):
                    seen.add(d)
                    queue.append(d)
    return pages, links, ids


def html_pages():
    pages, _, ids = crawl()
    return sorted(ids)


# ---------------------------------------------------------------- links

def test_every_crawled_page_returns_200():
    pages, _, _ = crawl()
    bad = {u: s for u, s in pages.items() if s != 200}
    assert not bad, f"internal pages not 200: {bad}"


def test_internal_links_resolve_without_redirect():
    pages, links, _ = crawl()
    problems = []
    checked = {}
    for src, href, a in links:
        d = urldefrag(a)[0]
        if not _is_internal(d):
            continue
        if d not in checked:
            checked[d] = pages.get(d) or _get(d).status_code
        if checked[d] != 200:
            problems.append(f"{src} -> {href}: HTTP {checked[d]}")
    assert not problems, "\n".join(problems)


def test_in_page_anchors_exist():
    _, links, ids = crawl()
    broken = []
    for src, href, a in links:
        u, frag = urldefrag(a)
        if frag and u in ids and frag not in ids[u]:
            broken.append(f"{src} -> {href} (no id='{frag}')")
    assert not broken, "\n".join(broken)


@pytest.mark.skipif(SKIP_EXTERNAL, reason="DT_SKIP_EXTERNAL=1")
def test_external_links_not_404():
    """Fails on definite breakage (404/410/5xx/DNS). Bot-blocked hosts are reported, not failed."""
    _, links, _ = crawl()
    targets = sorted({urldefrag(a)[0] for _, _, a in links if not _is_internal(a) and a.startswith("http")})
    hard, soft = [], []
    for t in targets:
        try:
            r = _get(t, "HEAD", allow_redirects=True)
            if r.status_code in (403, 405, 404, 400, 429):
                r = _get(t, "GET", allow_redirects=True)
            code = r.status_code
            final_host = urlparse(r.url).netloc
        except requests.RequestException as e:
            code, final_host = type(e).__name__, urlparse(t).netloc
        if code in (404, 410) or (isinstance(code, int) and code >= 500) or isinstance(code, str):
            (soft if final_host in BOT_BLOCKING_HOSTS and code != 404 else hard).append(f"{t}: {code}")
        elif code != 200:
            (soft if final_host in BOT_BLOCKING_HOSTS else hard).append(f"{t}: {code}")
    if soft:
        print("UNVERIFIABLE (bot-blocking hosts):\n  " + "\n  ".join(soft))
    assert not hard, "broken external links:\n" + "\n".join(hard)


@pytest.mark.skipif(SKIP_EXTERNAL, reason="DT_SKIP_EXTERNAL=1")
def test_sample_report_script_exists_on_github():
    """T1 BREAK-1: /sample-report/ and /code/ link to a script that was never pushed."""
    url = "https://github.com/donttrade/disposition-effect/blob/main/samples/sample_trader_report.py"
    r = _get(url, allow_redirects=True)
    assert r.status_code == 200, f"{url} -> HTTP {r.status_code}"


# ---------------------------------------------------------------- browser checks

@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        kw = {}
        exe = os.environ.get("PW_CHROMIUM")
        if exe:
            kw["executable_path"] = exe
        b = p.chromium.launch(**kw)
        yield b
        b.close()


OVERFLOW_JS = """() => {
  const vw = window.innerWidth;
  function inScroller(el){let p=el.parentElement;while(p&&p!==document.body){const o=getComputedStyle(p).overflowX;
    if(['auto','scroll','hidden','clip'].includes(o))return true;p=p.parentElement;}return false;}
  const off=[];
  for (const el of document.querySelectorAll('body *')) {
    if (el.checkVisibility && !el.checkVisibility()) continue;
    const r = el.getBoundingClientRect();
    if (r.width && r.right > vw + 1 && !inScroller(el)) off.push(el.tagName.toLowerCase()+(el.className?'.'+String(el.className).split(' ').join('.'):'')+' right='+Math.round(r.right));
    if (off.length > 5) break;
  }
  return {scrollW: document.documentElement.scrollWidth, vw, off};
}"""


@pytest.mark.parametrize("vp", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
def test_no_horizontal_overflow_or_console_errors(browser, vp):
    failures = []
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]})
    for url in html_pages():
        page = ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
        page.goto(url, wait_until="load")
        page.wait_for_timeout(300)
        o = page.evaluate(OVERFLOW_JS)
        if o["scrollW"] > o["vw"] or o["off"]:
            failures.append(f"{url} @{vp[0]}: scrollWidth={o['scrollW']} > {o['vw']} {o['off']}")
        if errs:
            failures.append(f"{url} @{vp[0]}: console/network errors {errs}")
        page.close()
        time.sleep(DELAY)
    ctx.close()
    assert not failures, "\n".join(failures)


def test_pages_have_unique_title_and_description(browser):
    page = browser.new_page()
    titles, problems = {}, []
    for url in html_pages():
        page.goto(url)
        t = page.title()
        d = page.evaluate("(document.querySelector('meta[name=description]')||{}).content||''")
        if not t or not d:
            problems.append(f"{url}: title={t!r} description={d!r}")
        if t in titles:
            problems.append(f"duplicate title {t!r}: {titles[t]} and {url}")
        titles[t] = url
        time.sleep(DELAY)
    page.close()
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------- calculators

DC = BASE + "/tools/disposition-calculator/"
PR = BASE + "/tools/pass-rate-calculator/"


def _fill(page, values):
    for sel, v in values.items():
        page.fill(sel, v)


def test_disposition_example_matches_hand_arithmetic(browser):
    import math
    page = browser.new_page()
    page.goto(DC)
    page.click("#dc-example")
    got = {k: page.inner_text(f"#dc-{k}") for k in ("pgr", "plr", "ratio", "diff", "se", "t")}
    rg, pg, rl, pl = 420, 1780, 260, 2240
    pgr, plr = rg / (rg + pg), rl / (rl + pl)
    se = math.sqrt(pgr * (1 - pgr) / (rg + pg) + plr * (1 - plr) / (rl + pl))
    want = {"pgr": f"{pgr:.4f}", "plr": f"{plr:.4f}", "ratio": f"{pgr/plr:.2f}",
            "diff": f"{pgr-plr:.4f}", "se": f"{se:.4f}", "t": f"{(pgr-plr)/se:.2f}"}
    page.close()
    assert got == want


def test_pass_rate_example_matches_hand_arithmetic(browser):
    page = browser.new_page()
    page.goto(PR)
    page.click("#pr-example")
    got = {k: page.inner_text(f"#pr-{k}") for k in ("rate", "range", "perEval", "perFunded", "perTrader")}
    page.close()
    assert got == {"rate": "20.0%", "range": "17.0% to 32.0%", "perEval": "4.0%",
                   "perFunded": "23.5%", "perTrader": "1.25"}


@pytest.mark.parametrize("url,sel", [(DC, "#dc-form input"), (PR, "#pr-form input")])
def test_pristine_calculator_fields_not_marked_invalid(browser, url, sel):
    """T1 DEGRADE: on first load every empty required field carries aria-invalid=true (red border)."""
    page = browser.new_page()
    page.goto(url)
    invalid = page.evaluate(f"[...document.querySelectorAll('{sel}')].filter(i=>i.getAttribute('aria-invalid')==='true').map(i=>i.id)")
    page.close()
    assert invalid == [], f"pristine fields marked invalid: {invalid}"


@pytest.mark.parametrize("raw", ["1,5", "4 2", "1,0,0"])
def test_ambiguous_separators_are_rejected_not_silently_merged(browser, raw):
    """T1 DEGRADE: '1,5' is read as 15, '4 2' as 42, '1,0,0' as 100 with no warning."""
    page = browser.new_page()
    page.goto(DC)
    _fill(page, {"#dc-rg": raw, "#dc-pg": "10", "#dc-rl": "2", "#dc-pl": "10"})
    shown = not page.evaluate("document.getElementById('dc-results').hidden")
    msg = page.inner_text("#dc-msg")
    page.close()
    assert not shown or msg, f"input {raw!r} silently produced a result"


def test_pass_rate_never_rounds_to_100_when_some_failed(browser):
    """T1 DEGRADE: 19,999 passed of 20,000 finished shows '100.0%'."""
    page = browser.new_page()
    page.goto(PR)
    _fill(page, {"#pr-started": "20000", "#pr-open": "0", "#pr-passed": "19999", "#pr-paid": "0"})
    rate = page.inner_text("#pr-rate")
    page.close()
    assert rate != "100.0%", "pass rate shown as 100.0% although 1 evaluation failed"


def test_too_large_input_gets_specific_message(browser):
    """T1 NIT: 1000000000001 is a whole number but the message says it isn't."""
    page = browser.new_page()
    page.goto(DC)
    _fill(page, {"#dc-rg": "1000000000001", "#dc-pg": "10", "#dc-rl": "2", "#dc-pl": "10"})
    msg = page.inner_text("#dc-msg")
    page.close()
    assert "whole number of zero or more" not in msg or "large" in msg.lower(), msg
