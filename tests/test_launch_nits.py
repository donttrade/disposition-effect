"""Free-launch tester NITs (TESTER-REPORT-FREE-LAUNCH-2026-10-21.md), fixed 21 Oct 2026.

N1 singular counts ("1 closed trade from 4 fills", "1 day", "1 trading day");
N3 the disposition calculator's own example "1,780" is accepted (tests/test_calc_numbers.py);
N4 the two old calculators say they need JavaScript when it is off;
N5 they carry the Free tools breadcrumb;
N6 /terms/ no longer shows "The anchor of this section is unchanged."
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_tool_prop_sim import fill, open_tool, run_ui  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
CALCS = ["/tools/disposition-calculator/", "/tools/pass-rate-calculator/"]


def test_n1_trade_stats_one_closed_trade(browser, built_site):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.set_input_files("#ts-file", os.path.join(FIX, "mt5", "deals_hedging.htm"))
    page.wait_for_selector("#ts-noise", timeout=60000)
    text = page.inner_text("#ts-out")
    ctx.close()
    assert "1 closed trade from 4 fills" in text and "1 closed trades" not in text, text[:400]
    assert "n = 1 closed trade," in text


def test_n1_prop_sim_one_day(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    pg.set_input_files("#ps-file", os.path.join(FIX, "tradovate", "orders.csv"))
    pg.wait_for_selector("#ps-file-status:not([hidden])")
    fill(pg, {"#ps-target": "1000", "#ps-maxloss": "2000", "#ps-days": "30"})
    run_ui(pg)
    text = pg.inner_text("#ps-out")
    ctx.close()
    assert "(1 day, 2 trades)" in text and "Your file has 1 trading day," in text, text[:600]
    assert "1 days" not in text and "1 trading days" not in text


@pytest.mark.parametrize("path", CALCS)
def test_n4_n5_breadcrumb_and_noscript(browser, built_site, path):
    html = (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
    pre = html[:html.index("<!--frozen:start-->")]
    assert '<nav class="crumb small" aria-label="Breadcrumb">' in pre and '<a href="/">Home</a>' in pre
    assert '<a href="/tools/">Free tools</a>' in pre   # Home > Free tools > this calculator (Home link (c))
    assert "<noscript>" in pre and "needs JavaScript turned on" in pre
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 800})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + path)
    note = pg.locator(".lifted-pre .notice")
    assert note.count() == 1 and note.is_visible() and "needs JavaScript turned on" in note.inner_text()
    crumb, h1 = pg.locator(".crumb").bounding_box(), pg.locator("h1").bounding_box()
    ctx.close()
    assert 0 < h1["y"] - (crumb["y"] + crumb["height"]) < 120, (crumb, h1)
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(built_site["url"] + path)
    assert pg.locator(".lifted-pre .notice").count() == 0   # with JS on, <noscript> shows nothing
    ctx.close()


def test_n6_terms_has_no_developer_note(built_site):
    html = (built_site["out"] / "terms" / "index.html").read_text(encoding="utf-8")
    assert "anchor of this section" not in html
    assert "(called “Trial” before" in html
