"""The shared header (Manager V3, 21 Oct 2026): one 64 px line at every width.

Below 900 px: brand · "Menu" (<details>) · theme toggle as a 44 px icon button; from 900 px:
brand · nav row · theme toggle. Checked on template pages and lifted pages, light and dark:
  * the header is at most 66 px tall at 320, 375, 768, 1024, 1280 and 1440, with no overflow;
  * one list of links is shown at a time; the menu works with JavaScript off;
  * keyboard: Tab reaches Menu, Enter/Space opens it, Tab enters the links, Escape closes it and
    focus returns to Menu; a click outside closes it; the expanded state is exposed;
  * axe: 0 serious/critical with the menu open; every target at least 44 px;
  * the toggle keeps its name "Dark mode" (aria-pressed), the header holds no button and one plain
    text offer link ("Start a Pilot", For firms panel; ARCHITECT-V3 Q3). v3 nav tests: test_v3_nav.py.
"""
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402

PAGES = ["/", "/research/disposition-effect/", "/pricing/", "/for-firms/", "/about/", "/corrections/",
         "/tools/disposition-calculator/", "/tools/trade-stats/", "/404.html"]
HEADER_H = "Math.round(document.querySelector('.site-header').getBoundingClientRect().height)"


def _ctx(browser, width, scheme="light", js=True):
    # bypass_csp: axe is injected as a script (the pages allow only 'self'), as in test_oldpages
    return browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, java_script_enabled=js,
                               bypass_csp=True)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 768, 900, 1024, 1280, 1440])
def test_header_is_one_line_at_every_width(browser, built_site, width, scheme):
    ctx = _ctx(browser, width, scheme)
    pg = ctx.new_page()
    for path in PAGES:
        pg.goto(built_site["url"] + path)
        pg.wait_for_load_state("networkidle")
        assert pg.evaluate(HEADER_H) <= 66, (path, width, pg.evaluate(HEADER_H))
        assert horizontal_overflow(pg) == [], (path, width)
        compact = width < 900
        assert pg.is_visible(".nav-menu > summary") == compact, (path, width)
        assert pg.is_visible(".site-nav .nav-row") == (not compact), (path, width)
        assert not pg.is_visible(".site-nav .nav-panel"), "the menu starts closed"
        box = pg.locator("[data-theme-toggle]").bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44
        if compact:
            s = pg.locator(".nav-menu > summary").bounding_box()
            assert s["height"] >= 44 and s["width"] >= 44
    ctx.close()


def _expanded(cdp):
    nodes = cdp.send("Accessibility.getFullAXTree")["nodes"]
    for n in nodes:
        if (n.get("role") or {}).get("value") == "DisclosureTriangle" and (n.get("name") or {}).get("value") == "Menu":
            props = {p["name"]: p["value"].get("value") for p in n.get("properties", [])}
            return props.get("expanded")
    raise AssertionError("no disclosure in the accessibility tree")


@pytest.mark.parametrize("width", [320, 375])
def test_menu_keyboard_escape_and_click_outside(browser, built_site, width):
    ctx = _ctx(browser, width)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/research/disposition-effect/")
    pg.wait_for_load_state("networkidle")
    cdp = pg.context.new_cdp_session(pg)   # one session: the tree it returns follows the page
    assert _expanded(cdp) is False
    for _ in range(6):   # skip link, brand, then Menu
        pg.keyboard.press("Tab")
        if pg.evaluate("document.activeElement.matches('.nav-menu > summary')"):
            break
    assert pg.evaluate("document.activeElement.matches('.nav-menu > summary')")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(100)   # the accessibility tree updates after the toggle event
    assert pg.is_visible(".nav-panel") and _expanded(cdp) is True
    pg.keyboard.press("Tab")   # v3 (ARCHITECT-V3 §c.2): the menu holds 3 accordion groups, then Pricing and About
    assert pg.evaluate("document.activeElement.matches('.nav-acc > summary')")
    assert pg.evaluate("document.activeElement.textContent") == "Free tools"
    groups = pg.eval_on_selector_all(".nav-panel .nav-acc > summary", "ss => ss.map(s => [s.textContent, s.classList.contains('is-current'), s.getBoundingClientRect().height])")
    assert [t for t, _, _ in groups] == ["Free tools", "Research, current section", "For firms"]
    assert [t for t, c, _ in groups if c] == ["Research, current section"]   # a study is in the Research section
    links = pg.eval_on_selector_all(".nav-panel .nav-links a", "as => as.map(a => [a.textContent, a.getBoundingClientRect().height])")
    assert [t for t, _ in links] == ["Home", "Pricing", "About", "Ask a question"]   # Home link (a): first in .nav-links off the homepage
    assert all(h >= 44 for _, _, h in groups) and all(h >= 44 for _, h in links)
    pg.click(".nav-acc:nth-of-type(2) > summary")
    items = pg.eval_on_selector_all(".nav-acc[open] a", "as => as.map(a => a.getBoundingClientRect().height)")
    assert len(items) == 4 and all(h >= 48 for h in items)   # 25 Oct: Code, Corrections moved to the footer
    assert axe_violations(pg) == []
    pg.keyboard.press("Escape")
    assert not pg.is_visible(".nav-panel")
    assert pg.evaluate("document.activeElement.matches('.nav-menu > summary')")
    pg.keyboard.press(" ")
    assert pg.is_visible(".nav-panel")
    pg.mouse.click(width // 2, 700)
    assert not pg.is_visible(".nav-panel")
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 768])
def test_menu_open_axe_and_overflow(browser, built_site, width, scheme):
    ctx = _ctx(browser, width, scheme)
    pg = ctx.new_page()
    for path in ("/", "/pricing/", "/research/disposition-effect/"):
        pg.goto(built_site["url"] + path)
        pg.wait_for_load_state("networkidle")
        pg.click(".nav-menu > summary")
        assert pg.is_visible(".nav-panel")
        assert pg.evaluate(HEADER_H) <= 66, "the open menu lies over the page; the header does not grow"
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == [], (path, width, scheme)
    ctx.close()


def test_menu_works_without_javascript(browser, built_site):
    ctx = _ctx(browser, 375, js=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/about/")
    assert not pg.is_visible("[data-theme-toggle]"), "the toggle needs JS, so it stays hidden"
    pg.click(".nav-menu > summary")
    assert pg.is_visible(".nav-panel a[href='/pricing/']")
    pg.click(".nav-panel a[href='/pricing/']")
    pg.wait_for_load_state()
    assert pg.url.endswith("/pricing/")
    box = pg.locator(".site-header").bounding_box()
    assert box["height"] <= 66
    ctx.close()


def test_theme_toggle_keeps_its_name_and_state(browser, built_site):
    ctx = _ctx(browser, 375)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    btn = pg.get_by_role("button", name="Dark mode")
    assert btn.count() == 1 and btn.is_visible()
    label = pg.locator(".theme-toggle .tt-label").bounding_box()
    assert label["width"] <= 1 and label["height"] <= 1, "icon only on a phone; the name stays for screen readers"
    btn.click()
    assert pg.evaluate("document.documentElement.dataset.theme") == "dark"
    assert btn.get_attribute("aria-pressed") == "true"
    ctx.close()


def test_header_markup(built_site):
    for path in PAGES:
        f = built_site["out"] / (os.path.join(path.strip("/"), "index.html") if path.endswith("/") else path.strip("/"))
        html = f.read_text(encoding="utf-8")
        header = re.search(r"(?s)<header class=\"site-header\">.*?</header>", html).group(0)
        # v3: 3 drop-downs + the phone Menu + its 3 accordion groups; one offer, the plain text link
        # "Start a Pilot" at the foot of For firms, once in each list (CSS shows one list at a time)
        assert header.count("<nav ") == 1 and header.count("<details") == 8, path   # + the "Ask" popover (§c.5)
        assert 'class="btn' not in header and not re.search(r"\$\d", header), path
        assert header.count("Start a Pilot") == 2 == header.count('<li><a href="/start/?product=pilot#pilot">Start a Pilot</a></li>'), path
        assert re.search(r'<script src="/static/js/nav\.js\?v=[0-9a-f]{8}" defer></script>', html), path  # N5: versioned
