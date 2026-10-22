"""Owner-approved Home link (basis: NN/g "Homepage links").

(a) the mobile Menu's links start with Home on every page but the homepage; (b) the desktop row has no Home
item (the logo is the home link); (c) the interior pages named in the brief carry a "Home >" breadcrumb;
(d) every non-home page has the breadcrumb or the Menu's Home link, and the homepage has no live self-link.
"""
import re

import pytest

NAMED = ["/tools/", "/tools/trade-stats/", "/tools/prop-challenge-simulator/", "/tools/disposition-calculator/", "/tools/pass-rate-calculator/", "/tools/lot-size-calculator/",
         "/start/", "/pricing/", "/help/", "/about/", "/for-traders/", "/for-firms/", "/for-platforms/", "/privacy/", "/terms/",
         "/research/", "/research/disposition-effect/"]


def pages(out):
    for f in sorted(out.rglob("index.html")):
        rel = "/" + str(f.parent.relative_to(out)).replace("\\", "/").strip(".") + "/"
        yield ("/" if rel in ("//", "/./") else rel.replace("//", "/")), f.read_text(encoding="utf-8")


def menu_links(html):
    m = re.search(r'<ul class="nav-links">(.*?)</ul>', html, re.S)
    return m.group(1) if m else ""


def crumbs(html):
    m = re.search(r'<nav class="crumb small" aria-label="Breadcrumb"><ol class="crumbs">(.*?)</ol></nav>', html, re.S)
    return m.group(1) if m else None


def test_home_has_no_live_self_link_and_no_crumb(built_site):
    html = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    assert '<a href="/">Home</a>' not in html and crumbs(html) is None
    assert ">Home<" not in menu_links(html)


def test_desktop_row_has_no_home_item(built_site):
    html = (built_site["out"] / "pricing" / "index.html").read_text(encoding="utf-8")
    row = html[:html.index('<details class="nav-menu"')]
    assert ">Home<" not in row.split('<ul', 1)[-1]


@pytest.mark.parametrize("path", NAMED)
def test_named_interior_pages_have_home_breadcrumbs(built_site, path):
    out = built_site["out"] / path.strip("/") / "index.html"
    if not out.exists():
        pytest.skip(path + " is not in this build")
    c = crumbs(out.read_text(encoding="utf-8"))
    assert c and c.startswith('<li><a href="/">Home</a>') and 'aria-current="page"' in c, (path, c)


def test_journal_has_home_breadcrumbs(journal_site):
    c = crumbs((journal_site["out"] / "journal" / "index.html").read_text(encoding="utf-8"))
    assert c and c.startswith('<li><a href="/">Home</a>') and '<a href="/tools/">Free tools</a>' in c


def test_every_non_home_page_reaches_home(built_site):
    bad = []
    for path, html in pages(built_site["out"]):
        if path == "/" or "nav-links" not in html:
            continue   # redirect stubs and pages without the site header
        first = re.search(r"<li>(.*?)</li>", menu_links(html), re.S)
        if not (crumbs(html) or (first and first.group(1) == '<a href="/">Home</a>')):
            bad.append(path)
    assert not bad, bad


def test_breadcrumb_layout_phone(browser, built_site):
    ctx = browser.new_context(viewport={"width": 320, "height": 700})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/tools/trade-stats/")
    box = pg.locator("nav.crumb").bounding_box()
    sw = pg.evaluate("document.documentElement.scrollWidth")
    ctx.close()
    assert box and box["x"] >= 0 and box["x"] + box["width"] <= 320 and sw <= 320, (box, sw)


@pytest.mark.parametrize("path", ["/research/disposition-effect/", "/tools/trade-stats/", "/for-firms/"])
def test_breadcrumb_same_on_lifted_and_new_pages_phone(browser, built_site, path):
    """The lifted pages' list rules (.lifted ol/li padding) must not indent the crumb, and its links get the
    site's 44 px touch target, the same as on the new pages."""
    ctx = browser.new_context(viewport={"width": 320, "height": 700})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + path)
    ol = pg.locator("nav.crumb ol").bounding_box()
    h1 = pg.locator("main h1").first.bounding_box()
    links = pg.eval_on_selector_all("nav.crumb a", "as => as.map(a => a.getBoundingClientRect().height)")
    ctx.close()
    assert abs(ol["x"] - h1["x"]) <= 1, (ol, h1)
    assert links and all(h >= 44 for h in links), links
