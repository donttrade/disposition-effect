"""Plan steps 28–29: the 20 pages that passed through from docs/ in the old design are lifted
into the v2 templates, word for word.

* the body of every lifted page equals the old docs/ page in visible text, ids, links, tables
  and citation meta (checks/compare.py), and the committed fragments are what lift_pages.py
  derives from docs/;
* no HTML page passes through any more; every old URL and in-page anchor still resolves;
  PDF and CSV links resolve;
* the head follows the v2 rules (one JSON-LD graph, canonical, CSP), no inline script, style
  or event handler survives, and the old design (serif font, cream, old header) is gone;
* lint: full rules outside the frozen body, passthrough rules + word-for-word inside it;
* no study finding sits next to an offer;
* axe 0 serious/critical and no overflow at 320/375/1280 in both themes, and the two old
  calculators still compute their worked examples under the CSP.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import compare as C  # noqa: E402
import lint as L  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402

OLD = ["/404.html", "/about/", "/code/", "/corrections/", "/for-researchers/", "/glossary/", "/independence/",
       "/plan-gap/", "/research/", "/research/disposition-effect/", "/research/insider-buying-edge/",
       "/research/portfolio-driven-disposition-effect/", "/research/strategy-tests/",
       "/research/swing-trading-strategies/", "/research/volatility-scaled-momentum/", "/sample-memo/",
       "/sample-report/", "/tools/disposition-calculator/", "/tools/pass-rate-calculator/", "/who-pays/"]
STUDIES = [p for p in OLD if p.startswith("/research/") and p != "/research/"]


def html_of(site, path):
    return (site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


def test_all_twenty_are_lifted_and_nothing_passes_through():
    assert sorted(B.LIFTED_PATHS) == sorted(OLD)
    owned = {os.path.relpath(B.out_file("/x", p["path"]), "/x") for p in B.PAGES if not p["requires_flag"]}
    assert B.passthrough_pages(owned) == []
    assert B.PASSTHROUGH_FIXES == {}


def test_compare_zero_differences(built_site):
    assert C.compare_site(str(built_site["out"])) == []
    assert len(C.baselines()) == 20


def test_fragments_are_what_docs_gives(tmp_path):
    # Since step 30 (b613c8b) docs/ is the v2 build: lift_pages.py refuses it (no old header),
    # and the committed fragments are proved against the pre-bundle docs/ exported from git.
    lift = [sys.executable, os.path.join(REPO, "checks", "lift_pages.py"), "--check"]
    r = subprocess.run(lift, capture_output=True, text=True)
    assert r.returncode == 1 and "no old header" in r.stderr, r.stdout + r.stderr
    from test_build import PRE_BUNDLE
    arc = subprocess.run(["git", "archive", PRE_BUNDLE, "docs"], cwd=REPO, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tmp_path)], input=arc, check=True)
    r = subprocess.run(lift + ["--docs", str(tmp_path / "docs")], capture_output=True, text=True)
    assert r.returncode == 0 and "lift check: PASS" in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("change", [
    ("76.1%", "76.2%"),                                     # a number
    ("Odean", "Odeon"),                                     # a citation
    ('id="robustness-update"', 'id="robustness"'),          # an anchor
    ("/data/disposition-pgr-plr.csv", "/data/x.csv"),      # a data link
])
def test_compare_and_lint_catch_a_changed_body(built_site, tmp_path, change):
    html = html_of(built_site, "/research/disposition-effect/")
    head, body = html.split("<!--frozen:start-->", 1)
    assert change[0] in body
    bad = head + "<!--frozen:start-->" + body.replace(change[0], change[1], 1)
    base = C.baselines()["/research/disposition-effect/"]
    assert C.diff_page(base, bad) != []
    probs = L.lifted_problems(bad, "/research/disposition-effect/", "/research/disposition-effect/",
                              False, False, L.allowed_amounts(), [], False, False)
    assert any(p[0].startswith("frozen:") for p in probs), probs


def test_compare_catches_a_changed_citation_pdf(built_site):
    html = html_of(built_site, "/research/disposition-effect/")
    bad = html.replace("donttrade-disposition-effect.pdf", "x.pdf", 1)
    assert ("citation", ) == tuple(w for w, _ in C.diff_page(C.baselines()["/research/disposition-effect/"], bad))


def test_lint_full_rules_outside_the_frozen_body(built_site):
    html = html_of(built_site, "/about/")
    assert L.lifted_problems(html, "/about/", "/about/", False, False, L.allowed_amounts(), [], False, False) == []
    planted = html.replace("<!--frozen:end-->", "<!--frozen:end--><p>We recommend this.</p>")
    probs = L.lifted_problems(planted, "/about/", "/about/", False, False, L.allowed_amounts(), [], False, False)
    assert any(p[0].startswith("banned:") for p in probs), probs
    # a frozen marker on a page that is not lifted is refused
    tmp = str(built_site["out"]) + "-frozen-planted"
    shutil.copytree(built_site["out"], tmp)
    try:
        fp = B.out_file(tmp, "/pricing/")
        orig = open(fp, encoding="utf-8").read()
        with open(fp, "w", encoding="utf-8") as f:
            f.write(orig.replace("<main", "<!--frozen:start--><!--frozen:end--><main", 1))
        probs = L.lint_build(tmp)
    finally:
        shutil.rmtree(tmp)
    assert any(p[0] == "frozen" and p[1] == "/pricing/" for p in probs), probs


@pytest.mark.parametrize("path", OLD)
def test_v2_page_not_old_design(built_site, path):
    html = html_of(built_site, path)
    assert re.search(r'<link rel="stylesheet" href="/static/css/site\.css\?v=[0-9a-f]{8}">', html)  # N5: versioned
    assert '<main id="main" class="lifted">' in html
    assert '<header class="site-header">' in html and '<footer class="site-footer">' in html
    for old in ('<header class="site">', '<footer class="site">', "dt-serif", "#FBF8F3", "Who it’s for"):
        assert old not in html, old
    assert not re.search(r'<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>', html), "inline script"
    assert "<style" not in html and not re.search(r"\sstyle=\"", html)
    assert not re.search(r"\son[a-z]+=\"", html), "inline event handler"
    assert html.count("<!--frozen:start-->") == 1 and html.count("<!--frozen:end-->") == 1


@pytest.mark.parametrize("path", OLD)
def test_head_rules(built_site, path):
    html = html_of(built_site, path)
    page = next(p for p in B.PAGES if p["path"] == path)
    assert html.count('<meta http-equiv="Content-Security-Policy"') == 1
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "script-src &#39;self&#39;;" in csp and "style-src &#39;self&#39;;" in csp
    assert ("donttrade.substack.com" in csp) == ('action="https://donttrade.substack.com/subscribe"' in html)
    g = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))["@graph"]
    types = [n["@type"] for n in g]
    crumbs = next(n for n in g if n["@type"] == "BreadcrumbList")["itemListElement"]
    assert crumbs[0]["name"] == "Home" and crumbs[-1]["name"] == page["crumb"]
    if path in STUDIES:
        assert crumbs[1]["name"] == "Research" and "Article" in types
        art = next(n for n in g if n["@type"] == "Article")
        assert art["author"] == {"@id": "https://donttrade.ca/#org"} and art["url"] == "https://donttrade.ca" + path
    assert ('<meta name="robots" content="noindex">' in html) == (path in ("/404.html", "/who-pays/"))
    if path == "/who-pays/":
        assert '<meta http-equiv="refresh" content="0; url=/independence/">' in html


@pytest.mark.parametrize("path", STUDIES)
def test_citation_meta_and_pdfs(built_site, path):
    html = html_of(built_site, path)
    base = C.baselines()[path]
    assert C.citation_of(html) == base["citation"]
    for href in re.findall(r'href="(/[^"#?]+\.(?:pdf|csv|svg))"', html) + \
            [c.replace("https://donttrade.ca", "") for n, c in base["citation"] if n == "citation_pdf_url"]:
        assert (built_site["out"] / href.lstrip("/")).exists(), href


def test_every_internal_link_and_anchor_resolves(built_site):
    """Every link on every built page, to every page and id (old anchors included)."""
    out = built_site["out"]
    bad = []
    for fp in sorted(out.rglob("*.html")):
        html = fp.read_text(encoding="utf-8")
        ids = set(re.findall(r'\sid="([^"]+)"', html))
        for h in re.findall(r'\s(?:href|src|action)="([^"]+)"', html):
            h = h.replace("&amp;", "&")
            if h.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            target, _, frag = h.partition("#")
            target = target.split("?")[0]
            if target == "":
                if frag and frag not in ids:
                    bad.append((str(fp.relative_to(out)), h))
                continue
            t = out / target.lstrip("/")
            if target.endswith("/"):
                t = t / "index.html"
            if not t.exists():
                bad.append((str(fp.relative_to(out)), h))
            elif frag and t.suffix == ".html" and not re.search(r'\sid="' + re.escape(frag) + '"',
                                                                 t.read_text(encoding="utf-8")):
                bad.append((str(fp.relative_to(out)), h))
    assert bad == []


OFFER = re.compile(r"Start a Pilot|start a trial|waitlist|founding price|\$745|\$39\b|buy\.stripe\.com|"
                   r'href="/(?:pricing|start)/', re.I)


@pytest.mark.parametrize("path", STUDIES + ["/research/"])
def test_no_study_finding_next_to_an_offer(built_site, path):
    html = html_of(built_site, path)
    body = C.frozen_of(html)
    assert not OFFER.search(body), OFFER.search(body).group(0)
    header = re.search(r"(?s)<header class=\"site-header\">.*?</header>", html).group(0)
    # the old header carried a "Firms: start a Pilot" button above every finding; the v2 one has none.
    # v3 (ARCHITECT-V3-PLAN D3, owner decision Q3, Tester N2): the nav's one offer is the plain text link
    # "Start a Pilot" at the foot of the For firms panel: no price, no button, in each of the nav's two lists
    # (desktop panel, phone accordion). Exactly that link is taken out; anything else still fails.
    foot = r'<ul class="nav-foot">\s*<li><a href="/start/\?product=pilot#pilot">Start a Pilot</a></li>\s*</ul>'
    rest, n = re.subn(foot, "", header)
    assert n == 0, "25 Oct sweep: the nav holds no offer (no For firms panel, no Start a Pilot)"
    assert 'class="btn' not in header and not re.search(r"Start a Pilot|start a trial|\$\d|\d\s*%", rest, re.I)


def test_evidence_reads_the_lifted_pages():
    ev = B.evidence()
    assert ev["studies"] == 6 and ev["corrections"] >= 1 and ev["finding"]["pct"] == "76.1%"


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
@pytest.mark.parametrize("path", OLD)
def test_axe_and_overflow(browser, built_site, path, width, scheme):
    if path == "/who-pays/":
        pytest.skip("a redirect stub: the browser lands on /independence/")
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == []
    if width != 320:
        assert axe_violations(pg) == []
    ctx.close()


@pytest.mark.parametrize("path", OLD)
def test_no_console_or_csp_errors(browser, built_site, path):
    """Without bypassing the CSP: a leftover inline script, style or handler shows up here."""
    ctx = browser.new_context(viewport={"width": 375, "height": 900})
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    errs = [e for e in errs if not (path == "/404.html" and "404" in e)]
    assert errs == []
    ctx.close()


def test_calculators_still_compute_under_the_csp(browser, built_site):
    """The v1 worked examples (checks/tests/test_site_functional.py), on the lifted pages, CSP on."""
    import math
    ctx = browser.new_context(viewport={"width": 375, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/tools/disposition-calculator/")
    pg.click("#dc-example")
    got = {k: pg.inner_text(f"#dc-{k}") for k in ("pgr", "plr", "ratio", "diff", "se", "t")}
    rg, pgn, rl, pl = 420, 1780, 260, 2240
    pgr, plr = rg / (rg + pgn), rl / (rl + pl)
    se = math.sqrt(pgr * (1 - pgr) / (rg + pgn) + plr * (1 - plr) / (rl + pl))
    assert got == {"pgr": f"{pgr:.4f}", "plr": f"{plr:.4f}", "ratio": f"{pgr/plr:.2f}",
                   "diff": f"{pgr-plr:.4f}", "se": f"{se:.4f}", "t": f"{(pgr-plr)/se:.2f}"}
    pg.goto(built_site["url"] + "/tools/pass-rate-calculator/")
    pg.click("#pr-example")
    got = {k: pg.inner_text(f"#pr-{k}") for k in ("rate", "range", "perEval", "perFunded", "perTrader")}
    assert got == {"rate": "20.0%", "range": "17.0% to 32.0%", "perEval": "4.0%",
                   "perFunded": "23.5%", "perTrader": "1.25"}
    # the form never submits (it had onsubmit="return false"): Enter keeps the URL
    url = pg.url
    pg.press("#pr-started", "Enter")
    pg.wait_for_timeout(200)
    assert pg.url == url
    ctx.close()


def test_scroll_hint_and_copy_button_wired(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/corrections/")
    pg.wait_for_load_state("networkidle")
    hints = pg.eval_on_selector_all(".scroll-hint", "els => els.map(e => e.classList.contains('fits'))")
    assert hints and all(hints)   # at 1280 the tables fit, so the hints are hidden
    ctx.close()
