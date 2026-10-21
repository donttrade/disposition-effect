"""Step 11: the prop-firm challenge simulator at /tools/prop-challenge-simulator/.

Plan checks: the hand-checkable cases (100% win rate passes 100%; one loss larger than
the max-loss limit busts 100%), the three shares sum to 1, identical results across runs,
an empty network log. Plus: the JS core equals an independent Python mirror run by run
(same mulberry32 as the reference), input errors are named, axe and overflow, lint.
"""
import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
import engine_ref as E  # noqa: E402

PATH = "/tools/prop-challenge-simulator/"
DEMO = os.path.join(REPO, "site", "static", "samples", "demo-trades.csv")
FIX = os.path.join(HERE, "fixtures")


# ------------------------------------------------------------------ Python mirror of prop-sim-core.js
def simulate_py(p):
    """Written from the rules in prop-sim-core.js's header, not from its code."""
    rand = E.mulberry32(p["seed"])
    r = p["rules"]
    out = {"pass": 0, "bust": 0, "timeout": 0, "bust_daily": 0, "bust_max": 0, "bust_after_streak": 0}
    pass_days = []
    for _ in range(p["runs"]):
        eq, peak, floor, run_l, outcome = 0.0, 0.0, -r["max_loss"], 0, "timeout"
        for d in range(1, r["time_limit"] + 1):
            start = eq
            if p["mode"] == "file":
                trades = p["days"][math.floor(rand() * len(p["days"]))]
                draws = iter(trades)
                n = len(trades)
            else:
                n = p["trades_per_day"]
                draws = None
            busted = False
            for _i in range(n):
                pnl = next(draws) if draws else (p["avg_win"] if rand() < p["win_rate"] else -p["avg_loss"])
                before = run_l
                eq += pnl
                run_l = run_l + 1 if pnl < 0 else 0
                why = "daily" if (r["daily_loss"] is not None and eq <= start - r["daily_loss"]) else ("max" if eq <= floor else None)
                if why:
                    out["bust_" + why] += 1
                    out["bust_after_streak"] += before >= 2
                    outcome, busted = "bust", True
                    break
            if busted:
                break
            if r["trailing"]:
                peak = max(peak, eq)
                floor = peak - r["max_loss"]
            if eq >= r["target"] and d >= r["min_days"]:
                outcome = "pass"
                pass_days.append(d)
                break
        out[outcome] += 1
    pass_days.sort()
    n = len(pass_days)
    out["median_pass_days"] = None if not n else (pass_days[(n - 1) // 2] if n % 2 else (pass_days[n // 2 - 1] + pass_days[n // 2]) / 2)
    return out


def demo_days():
    trades = E.parse_file(open(DEMO, "rb").read())["trades"]
    days, key = [], None
    for t in trades:
        k = t["close_ts"] // 86400000
        if k != key:
            days.append([])
            key = k
        days[-1].append(t["pnl"])
    return days


def js_simulate(page, params):
    return page.evaluate("""async (p) => {
        const m = await import('/static/js/tools/prop-sim-core.js');
        return m.simulate(p);
    }""", params)


@pytest.fixture(scope="module")
def page(browser, built_site):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(built_site["url"] + PATH)
    yield pg
    ctx.close()


RULES = [
    {"target": 600, "daily_loss": 250, "max_loss": 500, "trailing": False, "time_limit": 60, "min_days": 5},
    {"target": 400, "daily_loss": None, "max_loss": 300, "trailing": True, "time_limit": 30, "min_days": 0},
    {"target": 1000, "daily_loss": 120, "max_loss": 400, "trailing": True, "time_limit": 90, "min_days": 10},
]


@pytest.mark.parametrize("rules", RULES)
def test_file_mode_equals_python_mirror(page, rules):
    p = {"mode": "file", "days": demo_days(), "rules": rules, "seed": 20261022, "runs": 10000}
    js = js_simulate(page, p)
    py = simulate_py(p)
    for k, v in py.items():
        assert js[k] == v, (k, js[k], v)
    assert js["pass"] + js["bust"] + js["timeout"] == 10000
    assert js["bust_daily"] + js["bust_max"] == js["bust"]


def test_manual_mode_equals_python_mirror(page):
    p = {"mode": "manual", "win_rate": 0.48, "avg_win": 90, "avg_loss": 70, "trades_per_day": 3,
         "rules": RULES[0], "seed": 7, "runs": 10000}
    js, py = js_simulate(page, p), simulate_py(p)
    for k, v in py.items():
        assert js[k] == v, (k, js[k], v)


def test_python_and_js_trading_days_agree(page, built_site):
    js = page.evaluate("""async (csv) => {
        const e = await import('/static/js/engine/index.js');
        const c = await import('/static/js/tools/prop-sim-core.js');
        return c.tradingDays(e.parseFile(new TextEncoder().encode(csv)).trades);
    }""", open(DEMO, encoding="utf-8").read())
    assert js == demo_days()


# ------------------------------------------------------------------ the page
def fill(page, values):
    for k, v in values.items():
        page.fill(k, v)


def run_ui(page):
    page.click("#ps-run")
    page.wait_for_selector("#ps-out:not([hidden])", timeout=60000)
    return {k: page.inner_text(f'tr[data-outcome="{k}"] td:nth-child(2)') for k in ("pass", "bust", "timeout")}


def open_tool(browser, built_site, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    pg = ctx.new_page()
    log = {"requests": [], "console": []}
    pg.on("request", lambda r: log["requests"].append((r.method, r.url)))
    pg.on("console", lambda m: log["console"].append(m.text))
    pg.on("pageerror", lambda e: log["console"].append(str(e)))
    pg.goto(built_site["url"] + PATH)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def test_hand_checks_in_the_page(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    pg.check("#ps-mode-manual")
    # every trade wins 100: a 500 target is reached on day 5 in every run
    fill(pg, {"#ps-wr": "100", "#ps-avgwin": "100", "#ps-avgloss": "50", "#ps-tpd": "1",
              "#ps-target": "500", "#ps-maxloss": "1000", "#ps-days": "30"})
    res = run_ui(pg)
    assert res == {"pass": "10,000", "bust": "0", "timeout": "0"}
    assert pg.inner_text('[data-k="median_pass_days"]') == "5"
    # every trade loses 2,000 against a 1,000 maximum loss: every run busts on its first trade
    fill(pg, {"#ps-wr": "0", "#ps-avgloss": "2000"})
    res = run_ui(pg)
    assert res == {"pass": "0", "bust": "10,000", "timeout": "0"}
    assert pg.inner_text('[data-k="bust_max"]') == "10,000"
    # the first trade has no losses before it, so none of these busts came after a streak
    assert "0 of 10,000" in pg.inner_text("#ps-streak")
    ctx.close()


def test_sample_run_is_repeatable_local_and_clean(browser, built_site):
    ctx, pg, log = open_tool(browser, built_site)
    pg.click("#ps-sample-btn")
    fill(pg, {"#ps-target": "600", "#ps-daily": "250", "#ps-maxloss": "500", "#ps-days": "60", "#ps-mindays": "5"})
    log["requests"].clear()
    first = run_ui(pg)
    text1 = pg.inner_text("#ps-out")
    second = run_ui(pg)
    assert first == second and pg.inner_text("#ps-out") == text1
    py = simulate_py({"mode": "file", "days": demo_days(), "rules": RULES[0], "seed": 20261022, "runs": 10000})
    assert first == {k: f"{py[k]:,}" for k in ("pass", "bust", "timeout")}
    for method, url in log["requests"]:
        assert method == "GET" and url.startswith(built_site["url"] + "/static/"), url  # same-origin static only
    assert ctx.cookies() == [] and pg.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0
    body = pg.inner_text("main")
    assert not re.search(r"\b(NaN|Infinity|undefined|null)\b", body)
    assert L.lint_text(body, PATH) == []
    assert log["console"] == []
    assert "not a prediction" in body
    assert pg.is_visible("#ps-teaser") and "Join the waitlist — $39 founding price" in pg.inner_text("#ps-teaser")
    ctx.close()


def test_input_errors_are_named(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    pg.click("#ps-run")  # no file, no rules
    assert pg.is_visible("#ps-errors")
    errs = pg.inner_text("#ps-errors")
    assert "Choose a trade file" in errs and "Enter the profit target." in errs and "Enter the maximum loss." in errs
    assert pg.get_attribute("#ps-target", "aria-invalid") == "true"
    fill(pg, {"#ps-target": "1,500", "#ps-maxloss": "-5", "#ps-days": "400"})
    pg.click("#ps-run")
    assert "could mean 1500 or 1.500" in pg.inner_text("#ps-target-err")
    assert "more than zero" in pg.inner_text("#ps-maxloss-err")
    assert "between 1 and 365" in pg.inner_text("#ps-days-err")
    assert pg.is_hidden("#ps-out")
    ctx.close()


def test_short_file_warns(browser, built_site):
    ctx, pg, _ = open_tool(browser, built_site)
    pg.set_input_files("#ps-file", os.path.join(FIX, "generic", "basic.csv"))
    pg.wait_for_selector("#ps-file-status:not([hidden])")
    fill(pg, {"#ps-target": "100", "#ps-maxloss": "100", "#ps-days": "10"})
    run_ui(pg)
    assert "lean heavily on a few days" in pg.inner_text("#ps-out")
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 1280])
def test_axe_and_overflow(browser, built_site, scheme, width):
    ctx, pg, _ = open_tool(browser, built_site, width=width, scheme=scheme, bypass_csp=True)
    pg.click("#ps-sample-btn")
    fill(pg, {"#ps-target": "600", "#ps-maxloss": "500", "#ps-days": "60"})
    run_ui(pg)
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == []
    assert axe_violations(pg) == []
    # also with the manual fields and the error summary showing
    pg.check("#ps-mode-manual")
    pg.click("#ps-run")
    assert axe_violations(pg) == []
    ctx.close()
