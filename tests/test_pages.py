"""Steps 13–17: the template-owned pages (home, for-traders, for-firms, pricing, start,
for-platforms, thank-you pages, privacy, terms).

Shared checks for every page: axe 0 serious/critical in both themes with every <details>
open, no horizontal overflow at 320/375/1280, every internal link and #anchor resolves
in the build, no console errors, title 10–70 and description 50–160 characters, one h1.
Page-specific checks follow below.
"""
import os
import re
import sys
from html.parser import HTMLParser

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import build as B  # noqa: E402

PAGES = ["/"]
# Links to anchors that the NEXT step builds. Each step that builds one removes it here.
FORWARD = {"/for-traders/#waitlist"}  # built in step 14


def html_of(site, path):
    return (site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs, self.ids, self.h1 = [], set(), 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "h1":
            self.h1 += 1
        for k in ("href", "src", "srcset", "action"):
            if a.get(k):
                self.hrefs.append(a[k])


def parse(html):
    p = _Links()
    p.feed(html)
    return p


@pytest.mark.parametrize("path", PAGES)
def test_internal_links_and_anchors_resolve(built_site, path):
    page = parse(html_of(built_site, path))
    assert page.h1 == 1
    bad = []
    for h in page.hrefs:
        if h.startswith(("http://", "https://", "mailto:", "data:")) or h in FORWARD:
            continue
        target, _, frag = h.partition("#")
        target = target.split("?")[0]
        if target == "":
            if frag and frag not in page.ids:
                bad.append(h)
            continue
        fp = built_site["out"] / target.lstrip("/")
        if target.endswith("/"):
            fp = fp / "index.html"
        if not fp.exists():
            bad.append(h)
        elif frag and fp.suffix == ".html" and not re.search(r'\sid="' + re.escape(frag) + '"', fp.read_text(encoding="utf-8")):
            bad.append(h)
    assert bad == []


@pytest.mark.parametrize("path", PAGES)
def test_title_description_lengths(built_site, path):
    html = html_of(built_site, path)
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert 10 <= len(title) <= 70 and 50 <= len(desc) <= 160, (len(title), len(desc))


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
@pytest.mark.parametrize("path", PAGES)
def test_axe_overflow_console(browser, built_site, path, width, scheme):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == []
    if width != 320:  # axe once per theme per layout is enough; 320 is checked for overflow
        assert axe_violations(pg) == []
    assert errs == []
    ctx.close()


# ------------------------------------------------------------------ step 13: home
def test_home_numbers_come_from_data(built_site):
    html = html_of(built_site, "/")
    ev = B.evidence()
    assert f"{ev['studies']} published studies" in html
    assert f"Scripts public for {ev['scripts_public']} of {ev['studies']}" in html
    assert f"{ev['corrections']} corrections, dated and logged" in html
    study = (built_site["out"] / "research" / "disposition-effect" / "index.html").read_text(encoding="utf-8")
    finding = ev["finding"]["pct"] + " " + ev["finding"]["rest"]
    assert finding in study  # word for word on the study page
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert ev["finding"]["pct"] in text and ev["finding"]["rest"] in text


def test_home_has_no_firm_prices_and_the_trader_cta(built_site):
    html = html_of(built_site, "/")
    prices = __import__("json").load(open(os.path.join(REPO, "site", "config", "prices.json")))
    for p in prices["products"]:
        if p["audience"] == "firm":
            assert B.usd(p["price_usd"]) not in html, p["id"]
    assert "Join the waitlist — $39 founding price" in html
    assert not re.search(r"\btrial\b", re.sub(r"<[^>]+>", " ", html), re.I)
    assert "standard" not in html.lower() or "after launch" not in html.lower()


def test_home_hero_is_a_real_screenshot_within_budget(built_site):
    html = html_of(built_site, "/")
    for scheme in ("light", "dark"):
        f = built_site["out"] / "static" / "img" / f"hero-trade-stats-{scheme}.webp"
        assert f.exists() and f.stat().st_size <= 120 * 1024
        assert f"/static/img/hero-trade-stats-{scheme}.webp" in html
    assert re.search(r'<img src="/static/img/hero-trade-stats-light.webp" width="\d+" height="\d+"', html)
    assert "Sample data, not a real trader." in html
