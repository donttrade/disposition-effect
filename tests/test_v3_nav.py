"""v3 nav (ARCHITECT-V3-PLAN 2026-10-21 §c.2, steps A1-A2): Tester invariants N1-N8.

Free tools ▾ · Research ▾ · For firms ▾ · Pricing · About. Each ▾ is a <details name="nav"> disclosure
(no ARIA menu role) that works with JS off; nav.js adds Escape, focus-out, click-outside and hover intent.
The nav never shows a price, a % or a study number; its one offer is the text link "Start a Pilot".
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

ORDER = ["Free tools", "Research", "For firms", "Pricing", "About"]
HEADER_H = "Math.round(document.querySelector('.site-header').getBoundingClientRect().height)"
OPEN = "() => [...document.querySelectorAll('details.nav-dd')].map(d => d.open)"


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


# ------------------------------------------------------------------ N1: order and the journal flag
def test_n1_order_and_journal_item_only_with_its_flag(built_site):
    head = _header(built_site)
    row = head[head.index('<ul class="nav-row">'):head.index('<details class="nav-menu"')]
    tops = [re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<summary[^>]*>(.*?)<svg", row)]
    tops += re.findall(r'<li><a href="/(?:pricing|about)/"[^>]*>([^<]+)</a></li>', row)
    assert tops == ORDER
    menu = head[head.index('<details class="nav-menu"'):]
    acc = [re.sub(r"<[^>]+>", "", t) for t in re.findall(r"<summary[^>]*>([^<]*)<svg class=\"chev\"", menu)]
    assert acc == ORDER[:3] and re.findall(r'class="nav-links">.*?</ul>', menu, re.S)
    # journal = false (committed): the journal is nowhere in the build
    assert _cfg()["flags"]["journal"] is False
    for root, _, files in os.walk(built_site["out"]):
        for name in files:
            if name.endswith((".html", ".xml", ".js")):
                s = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
                assert 'href="/journal/' not in s and "donttrade.ca/journal/" not in s, name
    # with the flag on, the journal row is the first Free tools item (data level; the page arrives in J3)
    nav = B.nav_for(_cfg()["nav"], {"journal": True, "paid_report": False})
    assert nav[0]["items"][0]["href"] == "/journal/"
    nav = B.nav_for(_cfg()["nav"], {"journal": False, "paid_report": False})
    assert all(i["href"] != "/journal/" for g in nav for i in g["items"])


def test_n1_label_if_paid_drops_the_waitlist_word():
    on = B.nav_for(_cfg()["nav"], {"journal": False, "paid_report": True})
    off = B.nav_for(_cfg()["nav"], {"journal": False, "paid_report": False})
    assert "For traders: the habit report (waitlist)" in [i["label"] for i in off[0]["foot"]]
    assert "For traders: the habit report" in [i["label"] for i in on[0]["foot"]]
    assert not any("waitlist" in i["label"] for g in on for i in g["items"] + g["foot"])


# ------------------------------------------------------------------ N2: no price, %, number or banned word
def test_n2_build_guard_refuses_numbers_prices_and_banned_words():
    good = _cfg()["nav"]
    assert B.nav_problem(good) is None
    for bad in ("Pilot from $745", "76.1% of traders", "Five habits in 5 minutes", "Our best advice", "Unlock your edge",
                "Get a free trial"):
        nav = json.loads(json.dumps(good))
        nav[2]["items"][0]["desc"] = bad
        assert B.nav_problem(nav), bad
    nav = json.loads(json.dumps(good))
    nav[0]["items"][0]["requires_flag"] = "jornal"
    assert "not a flag" in B.nav_problem(nav)
    nav = json.loads(json.dumps(good))
    nav[1]["items"][0]["icon"] = "rocket"
    assert "icon" in B.nav_problem(nav)


def test_n2_nav_text_has_no_price_and_one_text_offer(built_site):
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    for rel in ("index.html", "pricing/index.html", "for-firms/index.html", "research/disposition-effect/index.html"):
        head = _header(built_site, rel)
        text = re.sub(r"<[^>]+>", " ", head)
        assert not re.search(r"\d\s*%|\$", text), rel
        for p in prices["products"]:
            assert B.usd(p["price_usd"]) not in text, rel
        assert "aria-label" not in head.replace('aria-label="Main"', ""), rel   # no hidden text to check apart from Main
        assert 'class="btn' not in head
        assert head.count("Start a Pilot") == 2   # once per list: desktop panel, phone accordion


@pytest.mark.parametrize("width", [375, 1280])
def test_n2_start_a_pilot_shows_once_as_a_link(browser, built_site, width):
    ctx = _ctx(browser, width)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    if width < 900:
        pg.click(".nav-menu > summary")
        pg.click(".nav-acc:nth-of-type(3) > summary")
    else:
        pg.click(".nav-dd-li:nth-child(3) summary")
    vis = pg.locator(".site-header a:visible", has_text="Start a Pilot")
    assert vis.count() == 1
    assert vis.evaluate("a => a.tagName") == "A" and "btn" not in (vis.get_attribute("class") or "")
    assert vis.get_attribute("href") == "/start/?product=pilot#pilot"
    ctx.close()


# ------------------------------------------------------------------ N3: JS off
def test_n3_no_js_groups_open_by_click_one_at_a_time_and_links_tab(browser, built_site):
    ctx = _ctx(browser, 1280, js=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/about/")
    for i in range(3):
        pg.click(f".nav-dd-li:nth-child({i + 1}) summary")
        state = pg.evaluate(OPEN)
        assert state == [j == i for j in range(3)], state   # name="nav": opening one closes the other
        assert pg.is_visible(f".nav-dd-li:nth-child({i + 1}) .nav-pop")
    # Tab from the open For firms summary walks its links in order
    pg.focus(".nav-dd-li:nth-child(3) summary")
    seen = []
    for _ in range(6):
        pg.keyboard.press("Tab")
        seen.append(pg.evaluate("document.activeElement.getAttribute('href')"))
    assert seen == ["/for-firms/", "/for-firms/#copy-leader", "/for-platforms/", "/tools/pass-rate-calculator/",
                    "/independence/", "/start/?product=pilot#pilot"]
    pg.click(".nav-dd-li:nth-child(3) a[href='/independence/']")
    pg.wait_for_load_state()
    assert pg.url.endswith("/independence/")
    ctx.close()


# ------------------------------------------------------------------ N4: phone, targets, axe
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375])
def test_n4_phone_each_group_open_no_overflow_targets_axe(browser, built_site, width, scheme):
    ctx = _ctx(browser, width, scheme)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_load_state("networkidle")
    pg.click(".nav-menu > summary")
    for i in range(3):
        pg.click(f".nav-acc:nth-of-type({i + 1}) > summary")
        assert pg.evaluate("[...document.querySelectorAll('.nav-acc')].map(d => d.open)") == [j == i for j in range(3)]
        assert horizontal_overflow(pg) == []
        sizes = pg.eval_on_selector_all(".nav-panel a:visible, .nav-panel summary:visible",
                                        "es => es.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height, e.closest('.nav-acc[open]') ? 1 : 0]; })")
        assert all(h >= 44 and w >= 44 for w, h, _ in sizes)
        assert all(h >= 48 for w, h, inside in sizes if inside)
        assert axe_violations(pg) == [], (i, width, scheme)
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_n4_desktop_each_panel_axe_clean_and_inside_the_viewport(browser, built_site, scheme):
    for width in (900, 1280):
        ctx = _ctx(browser, width, scheme)
        pg = ctx.new_page()
        pg.goto(built_site["url"] + "/pricing/")
        pg.wait_for_load_state("networkidle")
        for i in range(3):
            pg.click(f".nav-dd-li:nth-child({i + 1}) summary")
            box = pg.locator(f".nav-dd-li:nth-child({i + 1}) .nav-pop").bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width, (width, i, box)
            assert horizontal_overflow(pg) == []
            assert axe_violations(pg) == [], (width, i, scheme)
        ctx.close()


# ------------------------------------------------------------------ N8: one line, no layout shift
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_n8_header_one_line_and_opening_a_panel_shifts_nothing(browser, built_site, scheme):
    for width in (900, 1024, 1280, 1440):
        ctx = _ctx(browser, width, scheme)
        ctx.add_init_script("window.__cls = 0; new PerformanceObserver(l => l.getEntries().forEach(e => { __cls += e.value; }))"
                            ".observe({type: 'layout-shift', buffered: true});")
        pg = ctx.new_page()
        pg.goto(built_site["url"] + "/about/")
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(300)
        assert pg.evaluate(HEADER_H) <= 66
        tops = pg.eval_on_selector_all(".nav-row > li", "ls => ls.map(l => Math.round(l.getBoundingClientRect().top))")
        assert len(set(tops)) == 1, (width, tops)
        before = pg.evaluate("__cls")
        main_top = pg.evaluate("document.querySelector('main').getBoundingClientRect().top")
        for i in range(3):
            pg.click(f".nav-dd-li:nth-child({i + 1}) summary")
            pg.wait_for_timeout(250)
            assert pg.evaluate(HEADER_H) <= 66
            assert pg.evaluate("document.querySelector('main').getBoundingClientRect().top") == main_top
        assert pg.evaluate("__cls") == before, width
        ctx.close()
