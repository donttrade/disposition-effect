"""Step 12: lot-size calculator and the rebuilt /tools/ index.

Plan checks: output matches hand arithmetic on 3 cases; zero or negative inputs give named
errors; no default risk % (every input starts blank); ambiguous separators refused; never
NaN; lint clean. The /tools/ index lists every tool as a row (8 since tools batch 2).
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402

PATH = "/tools/lot-size-calculator/"


def open_tool(browser, built_site, width=1280, scheme="light", path=PATH, **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    pg = ctx.new_page()
    log = {"requests": [], "console": []}
    pg.on("request", lambda r: log["requests"].append(r.url))
    pg.on("console", lambda m: log["console"].append(m.text))
    pg.on("pageerror", lambda e: log["console"].append(str(e)))
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def calc(pg, mode, **vals):
    pg.check(f"#ls-mode-{mode}")
    for k in ("balance", "risk", "stop", "vpp", "step"):
        pg.fill(f"#ls-{k}", vals.get(k, ""))
    pg.click("#ls-form button[type=submit]")


# Hand arithmetic (worked out here, not by the code under test):
#  1. amount 200, stop 40 points, 1 per point per lot: 200 / (40 × 1) = 5 lots.
#  2. 0.5% of 25,000 = 125; stop 25, 10 per point: 125 / 250 = 0.5 lots.
#  3. amount 100, stop 30, 10 per point: 100 / 300 = 0.3333 lots; step 0.01 → 0.33 lots,
#     loss at the stop 0.33 × 300 = 99.00 (rounded down, never above 100).
HAND = [
    ("amount", {"risk": "200", "stop": "40", "vpp": "1"}, {"lots": "5.0000 lots", "risk_at": "200.00"}),
    ("pct", {"balance": "25000", "risk": "0.5", "stop": "25", "vpp": "10"}, {"lots": "0.5000 lots", "risk_at": "125.00", "risk_pct": "0.50%"}),
    ("amount", {"risk": "100", "stop": "30", "vpp": "10", "step": "0.01"}, {"lots": "0.3333 lots", "rounded": "0.33 lots", "risk_at": "99.00"}),
]


def test_inputs_start_blank_with_no_default_risk(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    for k in ("balance", "risk", "stop", "vpp", "step"):
        assert pg.input_value(f"#ls-{k}") == "", k
    html = (built_site["out"] / "tools" / "lot-size-calculator" / "index.html").read_text()
    assert not re.search(r'id="ls-[a-z]+"[^>]*\svalue="', html)
    ctx.close()


@pytest.mark.parametrize("mode,vals,want", HAND)
def test_hand_arithmetic(browser, built_site, mode, vals, want):
    ctx, pg, log = open_tool(browser, built_site)
    log["requests"].clear()
    calc(pg, mode, **vals)
    pg.wait_for_selector("#ls-out:not([hidden])")
    for k, v in want.items():
        assert pg.inner_text(f'[data-k="{k}"]') == v, k
    body = pg.inner_text("main")
    assert "Arithmetic on the numbers you entered" in body and "not a suggestion" in body
    assert not re.search(r"\b(NaN|Infinity|undefined|null)\b", body)
    assert L.lint_text(body, PATH) == []
    assert all(u.startswith(built_site["url"] + "/static/") for u in log["requests"]), log["requests"]
    assert log["console"] == [] and ctx.cookies() == []
    assert pg.evaluate("localStorage.length + sessionStorage.length") == 0
    ctx.close()


def test_below_one_lot_step_is_said_not_rounded_up(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    calc(pg, "amount", risk="5", stop="50", vpp="10", step="0.01")  # 5 / 500 = 0.01 lots... at exactly one step
    assert pg.inner_text('[data-k="rounded"]') == "0.01 lots"
    calc(pg, "amount", risk="4", stop="50", vpp="10", step="0.01")  # 0.008 lots: below one step
    assert pg.inner_text('[data-k="rounded"]') == "0.00 lots"
    assert "Smaller than one lot step" in pg.inner_text("#ls-belowmin")
    ctx.close()


@pytest.mark.parametrize("field,value,needle", [
    ("risk", "0", "has to be more than zero"),
    ("stop", "-10", "has to be more than zero"),
    ("vpp", "", "Enter the value per point for one lot."),
    ("risk", "1,5", "use a decimal point"),
    ("stop", "1,500", "could mean 1500 or 1.500"),
    ("vpp", "4 2", "remove the spaces"),
    ("vpp", "1,0,0", "not a number this page can read"),
])
def test_bad_inputs_get_named_errors(browser, built_site, field, value, needle):
    ctx, pg, _ = open_tool(browser, built_site)
    vals = {"risk": "200", "stop": "40", "vpp": "1", field: value}
    calc(pg, "amount", **vals)
    assert pg.is_visible("#ls-errors")
    assert needle in pg.inner_text(f"#ls-{field}-err")
    assert pg.get_attribute(f"#ls-{field}", "aria-invalid") == "true"
    assert pg.is_hidden("#ls-out")
    ctx.close()


def test_pct_mode_needs_a_balance_and_at_most_100(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    calc(pg, "pct", risk="1", stop="10", vpp="1")
    assert "Enter the account balance." in pg.inner_text("#ls-balance-err")
    calc(pg, "pct", balance="1000", risk="150", stop="10", vpp="1")
    assert "cannot be more than 100" in pg.inner_text("#ls-risk-err")
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 1280])
def test_axe_and_overflow(browser, built_site, scheme, width):
    ctx, pg, _ = open_tool(browser, built_site, width=width, scheme=scheme, bypass_csp=True)
    calc(pg, "amount", risk="100", stop="30", vpp="10", step="0.01")
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == [] and axe_violations(pg) == []
    calc(pg, "amount", risk="0")
    assert axe_violations(pg) == []
    ctx.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_tools_index_lists_eight_tools(browser, built_site, width):
    # tools batch 2 added the heatmap, the drawdown calculator and the risk-reward calculator
    ctx, pg, _ = open_tool(browser, built_site, width=width, path="/tools/", bypass_csp=True)
    links = pg.locator("ul.tool-cards > li > a.tool-card-link")   # 25 Oct sweep: one link per card
    assert links.count() == 8
    hrefs = [links.nth(i).get_attribute("href") for i in range(8)]
    assert hrefs == ["/tools/trade-stats/", "/tools/trading-heatmap/", "/tools/drawdown-calculator/",
                     "/tools/prop-challenge-simulator/", "/tools/lot-size-calculator/", "/tools/risk-reward-calculator/",
                     "/tools/disposition-calculator/", "/tools/pass-rate-calculator/"]
    for h in hrefs:
        assert (built_site["out"] / h.strip("/") / "index.html").exists(), h
    assert axe_violations(pg) == [] and horizontal_overflow(pg) == []
    ctx.close()
