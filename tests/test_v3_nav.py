"""v3 nav (ARCHITECT-V3-PLAN 2026-10-21 §c.2, steps A1-A2): Tester invariants N1-N8.

29 Oct (owner): Sample report · Free tools · Pricing · For firms as four plain links (no drop-down: /tools/ shows
every tool), one compact "Take the test — $39" button in paid builds (it opens the pay dialog; a link to
/pricing/#last-step without JS), the theme icon, all in a slim sticky bar. Below 900 px the links and the button sit
in one "Menu" <details>. The [[nav]] labels never show a price, a % or a study number (D3); the only price in the
header is the button's own.
"""
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import build as B  # noqa: E402

ORDER = ["Example report", "Free tools", "Pricing", "For firms"]
HEADER_H = "Math.round(document.querySelector('.site-header').getBoundingClientRect().height)"
CTA_RE = re.compile(r'<a class="btn[^"]*" href="/pricing/#last-step" data-pay>Take the test — \$39</a>')


def _ctx(browser, width, scheme="light", js=True, **kw):
    return browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, java_script_enabled=js,
                               bypass_csp=True, **kw)


def _header(built_site, rel="index.html"):
    html = (built_site["out"] / rel).read_text(encoding="utf-8")
    return re.search(r"(?s)<header class=\"site-header\">.*?</header>", html).group(0)


def _cfg():
    import tomllib
    with open(os.path.join(REPO, "site", "config", "site.toml"), "rb") as f:
        return tomllib.load(f)


# ------------------------------------------------------------------ N1: order, plain links, the journal flag
def test_n1_order_plain_links_and_no_journal(built_site):
    head = _header(built_site)
    row = head[head.index('<ul class="nav-row">'):head.index('<details class="nav-menu"')]
    assert [re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<li><a [^>]*>(.*?)</a></li>", row)] == ORDER
    assert "<details" not in row and "nav-dd" not in head and "nav-pop" not in head
    menu = head[head.index('<details class="nav-menu"'):]
    links = re.findall(r'class="nav-links">(.*?)</ul>', menu, re.S)[0]   # the home page: no Home link (a)
    assert [re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<li><a [^>]*>(.*?)</a></li>", links)] == ORDER
    assert head.count("<details") == 1   # the phone Menu only
    assert _cfg()["flags"]["journal"] is False
    for root, _, files in os.walk(built_site["out"]):
        for name in files:
            if name.endswith((".html", ".xml", ".js")):
                s = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
                assert 'href="/journal/' not in s and "donttrade.ca/journal/" not in s, name
    assert all(not g["items"] and not g["foot"] for g in B.nav_for(_cfg()["nav"], {"journal": True, "paid_report": True}))


# ------------------------------------------------------------------ N2: no price, %, number or banned word in the nav text
def test_n2_build_guard_refuses_numbers_prices_and_banned_words():
    good = _cfg()["nav"]
    assert B.nav_problem(good) is None
    for bad in ("Pilot from $745", "76.1% of traders", "Five habits in 5 minutes", "Our best advice", "Unlock your edge",
                "Get a free trial"):
        nav = json.loads(json.dumps(good))
        nav[1]["label"] = bad
        assert B.nav_problem(nav), bad
    item = {"label": "Trade stats", "href": "/tools/trade-stats/", "desc": "Totals from your trade file", "icon": "stats"}
    nav = json.loads(json.dumps(good))
    nav[1]["items"] = [dict(item, requires_flag="jornal")]
    assert "not a flag" in B.nav_problem(nav)
    nav[1]["items"] = [dict(item, icon="rocket")]
    assert "icon" in B.nav_problem(nav)


def test_n2_only_the_buy_button_holds_a_price(built_site):
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    for rel in ("index.html", "pricing/index.html", "for-firms/index.html", "research/disposition-effect/index.html"):
        head = _header(built_site, rel)
        # the bar's button and the Menu's; none on the research pages (no study finding next to an offer)
        assert len(CTA_RE.findall(head)) == (0 if rel.startswith("research/") else 2), rel
        rest = CTA_RE.sub("", head)
        text = re.sub(r"<[^>]+>", " ", rest)
        assert not re.search(r"\d\s*%|\$", text), rel
        for p in prices["products"]:
            assert B.usd(p["price_usd"]) not in text, rel
        assert set(re.findall(r'aria-label="([^"]+)"', head)) == {"Main"}, rel   # ask_box = false (launch, 25 Oct)
        assert 'class="btn' not in rest
        assert "Start a Pilot" not in head


# ------------------------------------------------------------------ N3: JS off: the button is a link to the pay step
def test_n3_no_js_the_button_is_a_link_to_the_pay_step(browser, built_site):
    ctx = _ctx(browser, 1280, js=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/about/")
    pg.click(".hdr-cta")
    pg.wait_for_load_state()
    assert pg.url.endswith("/pricing/#last-step")
    ctx.close()


# ------------------------------------------------------------------ N4: phone, targets, axe
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 390])
def test_n4_phone_menu_no_overflow_targets_axe(browser, built_site, width, scheme):
    ctx = _ctx(browser, width, scheme)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_load_state("networkidle")
    assert not pg.is_visible(".hdr-cta")
    pg.click(".nav-menu > summary")
    assert horizontal_overflow(pg) == []
    sizes = pg.eval_on_selector_all(".nav-panel a:visible", "es => es.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; })")
    assert len(sizes) == 5 and all(h >= 44 and w >= 44 for w, h in sizes)
    assert pg.inner_text(".nav-panel a[data-pay]") == "Take the test — $39"
    assert axe_violations(pg) == [], (width, scheme)
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_n4_desktop_axe_clean_and_keyboard_order(browser, built_site, scheme):
    for width in (900, 1280):
        ctx = _ctx(browser, width, scheme)
        pg = ctx.new_page()
        pg.goto(built_site["url"] + "/pricing/")
        pg.wait_for_load_state("networkidle")
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == [], (width, scheme)
        seen = []
        pg.keyboard.press("Tab")   # the skip link
        for _ in range(7):
            pg.keyboard.press("Tab")
            seen.append(pg.evaluate("document.activeElement.textContent.trim()"))
        assert seen[:6] == ["donttrade"] + ORDER + ["Take the test — $39"], seen
        assert pg.evaluate("document.activeElement.matches('[data-theme-toggle]')")
        ctx.close()


# ------------------------------------------------------------------ N8: slim, sticky, no layout shift
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_n8_header_slim_sticky_and_scrolling_shifts_nothing(browser, built_site, scheme):
    for width in (390, 900, 1280):
        ctx = _ctx(browser, width, scheme)
        ctx.add_init_script("window.__cls = 0; new PerformanceObserver(l => l.getEntries().forEach(e => { __cls += e.value; }))"
                            ".observe({type: 'layout-shift', buffered: true});")
        pg = ctx.new_page()
        pg.goto(built_site["url"] + "/about/")
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(300)
        assert pg.evaluate(HEADER_H) <= 58
        before = pg.evaluate("__cls")
        pg.mouse.wheel(0, 1200)
        pg.wait_for_timeout(300)
        assert abs(pg.evaluate("document.querySelector('.site-header').getBoundingClientRect().top")) < 1, width
        assert pg.evaluate("__cls") == before, width
        # a focused element is never left under the bar (scroll-padding)
        pg.focus("footer a")
        top = pg.evaluate("document.activeElement.getBoundingClientRect().top")
        assert top >= pg.evaluate(HEADER_H) - 1, (width, top)
        ctx.close()


# ------------------------------------------------------------------ N7: motion (the phone menu)
PANEL_ANIMS = """() => document.getAnimations().filter(a => a.effect.target && a.effect.target.closest('.nav-panel') && !a.transitionProperty).map(a => {
  const t = a.effect.getComputedTiming();
  const props = a.transitionProperty ? [a.transitionProperty]
    : a.effect.getKeyframes().flatMap(k => Object.keys(k).filter(x => !['offset', 'computedOffset', 'easing', 'composite'].includes(x)));
  return {props, end: t.delay + t.duration, iter: t.iterations};
})"""


@pytest.mark.parametrize("motion", ["reduce", "no-preference"])
def test_n7_menu_motion(browser, built_site, motion):
    ctx = _ctx(browser, 390, reduced_motion=motion)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/pricing/")
    pg.wait_for_load_state("networkidle")
    pg.focus(".nav-menu > summary")
    pg.keyboard.press("Enter")
    anims = pg.evaluate(PANEL_ANIMS)
    if motion == "reduce":
        assert anims == [], anims
    else:
        # 29 Oct: the phone menu opens at once (an entrance animation made a click on its links wait for it);
        # anything that does animate there may move only transform and opacity
        for a in anims:
            assert set(a["props"]) <= {"opacity", "transform"} and a["iter"] == 1 and a["end"] <= 240, a
    ctx.close()


def test_a2_nav_js_budget():
    assert os.path.getsize(os.path.join(REPO, "site", "static", "js", "nav.js")) <= 3072
