"""Free tools, batch 2: /tools/risk-reward-calculator/, /tools/drawdown-calculator/, /tools/trading-heatmap/.

Checks: math golden values worked out by hand (comments below, not by the code under test); the
file tools against an independent Python mirror on the synthetic sample (tests/reference engine);
JS off shows the "needs JavaScript" note (and the static recovery table still works); nothing but
the page's own /static/ files is requested, nothing is stored, no console output; the rendered text
passes the wording lint; axe and no page overflow at 375 and 1280 px, light and dark; teasers state
only computed figures and follow the offer state (waitlist / paid); no "real or noise" wording in any
build (these pages are descriptive in every flag combination); analytics wording switches with its flag.
"""
import datetime as dt
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
import engine_ref as E  # noqa: E402
import build as B  # noqa: E402

RR, DD, HM = "/tools/risk-reward-calculator/", "/tools/drawdown-calculator/", "/tools/trading-heatmap/"
PATHS = (RR, DD, HM)
FIX = os.path.join(HERE, "fixtures", "tools2")
DEMO = os.path.join(REPO, "site", "static", "samples", "example-trades.csv")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MINUS = "−"


def open_page(browser, site, path, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    pg = ctx.new_page()
    log = {"requests": [], "console": []}
    pg.on("request", lambda r: log["requests"].append(r.url))
    pg.on("console", lambda m: log["console"].append(m.text))
    pg.on("pageerror", lambda e: log["console"].append(str(e)))
    pg.goto(site["url"] + path)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def assert_clean(ctx, pg, log, site, path):
    """Only this site's /static/ files were requested; no console output, cookie or storage; the
    rendered text passes the wording lint and never shows NaN/Infinity/undefined/null."""
    assert all(u.startswith(site["url"] + "/static/") for u in log["requests"]), log["requests"]
    assert log["console"] == [], log["console"]
    assert ctx.cookies() == []
    assert pg.evaluate("localStorage.length + sessionStorage.length") == 0
    body = pg.inner_text("main")
    assert not re.search(r"\b(NaN|Infinity|undefined|null)\b", body)
    assert L.lint_text(body, path) == []
    for s in L.FREE_BADGE_STRINGS:
        assert s not in body, s


def k(pg, key, scope=""):
    return pg.inner_text(f'{scope} [data-k="{key}"]'.strip())


def money(x):
    return ("+" if x > 0 else MINUS if x < 0 else "") + "$" + f"{abs(x):,.2f}"


# ================================================================== risk-reward calculator
def rr(pg, mode="prices", **vals):
    pg.check(f"#rr-mode-{mode}")
    for f in ("entry", "stop", "target", "ratio", "winrate"):
        if pg.is_visible(f"#rr-{f}"):
            pg.fill(f"#rr-{f}", vals.get(f, ""))
    pg.click("#rr-form button[type=submit]")


# Hand arithmetic:
#  1. long: entry 100, stop 98, target 106: risk 2, reward 6, R = 3; break-even 1/4 = 25.0%;
#     at 40%: 0.4 × 3 − 0.6 = +0.60R.
#  2. short: entry 50, stop 52, target 45: risk 2, reward 5, R = 2.5; break-even 1/3.5 = 28.57…%;
#     at 30%: 0.3 × 2.5 − 0.7 = +0.05R.
#  3. forex prices, no win rate: 1.08500 / 1.08300 / 1.09100: risk 0.002, reward 0.006, R = 3.
#  4. ratio 2 typed in, 25%: break-even 1/3 = 33.3%; 0.25 × 2 − 0.75 = −0.25R.
#  5. ratio 1 at 50%: break-even 50.0%; 0.5 − 0.5 = 0.00R (no sign).
RR_HAND = [
    ("prices", {"entry": "100", "stop": "98", "target": "106", "winrate": "40"},
     {"side": "Long", "r": "3.00R", "break_even": "25.0%", "expectancy": "+0.60R"}, "6.00 ÷ 2.00 = 3.00"),
    ("prices", {"entry": "50", "stop": "52", "target": "45", "winrate": "30"},
     {"side": "Short", "r": "2.50R", "break_even": "28.6%", "expectancy": "+0.05R"}, "5.00 ÷ 2.00 = 2.50"),
    ("prices", {"entry": "1.08500", "stop": "1.08300", "target": "1.09100"},
     {"side": "Long", "r": "3.00R", "break_even": "25.0%"}, "0.00600 ÷ 0.00200 = 3.00"),
    ("ratio", {"ratio": "2", "winrate": "25"}, {"r": "2.00R", "break_even": "33.3%", "expectancy": MINUS + "0.25R"}, "1 ÷ (1 + 2.00) = 33.3%"),
    ("ratio", {"ratio": "1", "winrate": "50"}, {"r": "1.00R", "break_even": "50.0%", "expectancy": "0.00R"}, "50.0% × 1.00R − 50.0% × 1R = 0.00R"),
]


@pytest.mark.parametrize("mode,vals,want,formula", RR_HAND)
def test_rr_hand_arithmetic(browser, built_site, mode, vals, want, formula):
    ctx, pg, log = open_page(browser, built_site, RR)
    log["requests"].clear()
    rr(pg, mode, **vals)
    pg.wait_for_selector("#rr-out:not([hidden])")
    for key, v in want.items():
        assert k(pg, key, "#rr-out") == v, key
    assert ("expectancy" in want) == (pg.locator('#rr-out [data-k="expectancy"]').count() == 1)
    assert formula in pg.inner_text("#rr-out pre.formula")
    assert "It is not a suggestion" in pg.inner_text("#rr-out")
    assert_clean(ctx, pg, log, built_site, RR)
    ctx.close()


def test_rr_core_exports(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, RR)
    got = pg.evaluate("""async () => {
        const m = await import('/static/js/tools/risk-reward.js');
        const a = m.riskReward({mode: 'ratio', ratio: 3, winRate: 0.25});
        const b = m.riskReward({mode: 'prices', entry: 10, stop: 11, target: 7});
        let err = null; try { m.riskReward({mode: 'prices', entry: 10, stop: 9, target: 8}); } catch (e) { err = [e.name, e.id]; }
        return {a, b, err}; }""")
    assert got["a"]["breakEven"] == 0.25 and got["a"]["expectancy"] == 0     # at break-even, exactly 0
    assert got["b"]["side"] == "short" and got["b"]["r"] == 3 and got["b"]["expectancy"] is None
    assert got["err"] == ["RiskRewardError", "rr-target"]
    ctx.close()


def test_rr_inputs_start_blank(browser, built_site):
    html = (built_site["out"] / "tools" / "risk-reward-calculator" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'id="rr-[a-z]+"[^>]*\svalue="', html)
    ctx, pg, _ = open_page(browser, built_site, RR)
    for f in ("entry", "stop", "target", "winrate"):
        assert pg.input_value(f"#rr-{f}") == "", f
    ctx.close()


@pytest.mark.parametrize("mode,vals,field,needle", [
    ("prices", {"entry": "100", "stop": "98", "target": "97"}, "target", "on the same side of the entry"),
    ("prices", {"entry": "100", "stop": "100", "target": "106"}, "stop", "at the entry price"),
    ("prices", {"entry": "100", "stop": "98", "target": "100"}, "target", "at the entry price"),
    ("prices", {"entry": "1,500", "stop": "98", "target": "106"}, "entry", "could mean 1500 or 1.500"),
    ("prices", {"entry": "100", "stop": "98"}, "target", "Enter the target price."),
    ("prices", {"entry": "100", "stop": "-98", "target": "106"}, "stop", "has to be more than zero"),
    ("prices", {"entry": "100", "stop": "98", "target": "106", "winrate": "120"}, "winrate", "cannot be more than 100"),
    ("ratio", {"ratio": "0"}, "ratio", "has to be more than zero"),
    ("ratio", {"ratio": "2", "winrate": "4 0"}, "winrate", "remove the spaces"),
])
def test_rr_bad_inputs_get_named_errors(browser, built_site, mode, vals, field, needle):
    ctx, pg, _ = open_page(browser, built_site, RR)
    rr(pg, mode, **vals)
    assert pg.is_visible("#rr-errors")
    assert needle in pg.inner_text(f"#rr-{field}-err")
    assert pg.get_attribute(f"#rr-{field}", "aria-invalid") == "true"
    assert pg.is_hidden("#rr-out")
    assert L.lint_text(pg.inner_text("main"), RR) == []
    ctx.close()


# ================================================================== drawdown calculator
# Recovery gain = d ÷ (1 − d): 10% → 11.11…%, 20% → 25%, 30% → 42.857…%, 50% → 100%, 90% → 900%.
def test_dd_static_table_works_without_javascript(built_site):
    html = (built_site["out"] / "tools" / "drawdown-calculator" / "index.html").read_text(encoding="utf-8")
    want = {"5": "5.3%", "10": "11.1%", "20": "25.0%", "25": "33.3%", "30": "42.9%", "50": "100.0%", "75": "300.0%", "90": "900.0%"}
    for d, g in want.items():
        assert f'data-dd="{d}">{g}</td>' in html, d


@pytest.mark.parametrize("d,gain", [("10", "11.11%"), ("20", "25.00%"), ("50", "100.00%"), ("33.3", "49.93%"), ("0.5", "0.50%")])
def test_dd_quick_calculator(browser, built_site, d, gain):
    # 33.3%: 0.333 / 0.667 = 0.49925… → 49.93% ; 0.5%: 0.005 / 0.995 = 0.005025… → 0.50%
    ctx, pg, log = open_page(browser, built_site, DD)
    log["requests"].clear()
    pg.fill("#dd-pct", d)
    pg.click("#dd-q-form button[type=submit]")
    assert k(pg, "gain", "#dd-q-out") == gain
    assert "Arithmetic on the number you entered" in pg.inner_text("#dd-q-out")
    assert_clean(ctx, pg, log, built_site, DD)
    ctx.close()


@pytest.mark.parametrize("d,needle", [("100", "less than 100%"), ("0", "more than zero"), ("abc", "not a number"), ("", "Enter the drawdown.")])
def test_dd_quick_calculator_errors(browser, built_site, d, needle):
    ctx, pg, _ = open_page(browser, built_site, DD)
    pg.fill("#dd-pct", d)
    pg.click("#dd-q-form button[type=submit]")
    assert needle in pg.inner_text("#dd-pct-err") and pg.is_hidden("#dd-q-out")
    assert pg.get_attribute("#dd-pct", "aria-invalid") == "true"
    ctx.close()


def test_dd_recovery_gain_core(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, DD)
    got = pg.evaluate("""async () => { const m = await import('/static/js/tools/drawdown-core.js');
        return [0, 0.2, 0.5, 0.75, 1, -0.1].map(m.recoveryGain); }""")
    assert got == [0, 0.25, 1, 3, None, None]
    ctx.close()


def upload(pg, prefix, name):
    pg.set_input_files(f"#{prefix}-file", os.path.join(FIX, name))
    pg.wait_for_selector(f"#{prefix}-out:not([hidden])")


# drawdown_hand.csv, results +100, −50, −30, +40, +60, −120, +20 (closes 1, 2, 3, 4, 5, 8, 8 June):
#   equity 100, 50, 20, 60, 120, 0, 20; highs 100 (trade 1) then 120 (trade 5).
#   Drawdown 1: high at trade 1 (1 Jun), low at trade 3 (depth 80), recovered at trade 5 (5 Jun):
#               2 trades to the low, 4 trades in the drawdown, 4 calendar days.
#   Drawdown 2: high at trade 5 (5 Jun), low at trade 6 (depth 120), not recovered; to trade 7 (8 Jun):
#               1 trade to the low, 2 trades, 3 calendar days. Current drawdown 120 − 20 = 100.
#   Balance 1000: 80 / 1100 = 7.27%, 120 / 1120 = 10.71% (the largest), gain 120 / 1000 = 12.00%;
#                 drawdown 1's gain 80 / 1020 = 7.84%.
#   Trade 7 opened 10:40, 10 minutes after trade 6 (a loss) closed at 10:30.
def test_dd_hand_file(browser, built_site):
    ctx, pg, log = open_page(browser, built_site, DD)
    log["requests"].clear()
    upload(pg, "dd", "drawdown_hand.csv")
    s = "#dd-out"
    assert k(pg, "max_abs", s) == MINUS + "$120.00"
    assert k(pg, "max_pct", s) == "—" and k(pg, "recovery_gain", s) == "—"
    assert k(pg, "longest_trades", s) == "4 trades"
    assert k(pg, "longest_days", s) == "4 calendar days"
    assert k(pg, "current", s) == MINUS + "$100.00"
    assert k(pg, "deep_depth", s) == MINUS + "$120.00" and k(pg, "deep_trades", s) == "2" and k(pg, "deep_days", s) == "3"
    assert k(pg, "summary", s) == "2 drawdowns in 7 closed trades; 1 recovered to the previous high."
    words = pg.inner_text("#dd-out")
    assert ("The largest fell $120.00 from the high set at 2026-06-05, reached its low 1 trade later, on 2026-06-08, "
            "and has not recovered by the last trade in the file (2 trades and 3 calendar days so far).") in words
    assert "The median recovered drawdown took 4 trades from high to high." in words
    rows = pg.locator("#dd-out table").last.locator("tbody tr")
    assert rows.count() == 2
    assert rows.nth(1).inner_text().split("\t") == ["2", "2026-06-01", "2026-06-03", "2026-06-05", MINUS + "$80.00", "2", "4", "4"]
    # the starting balance re-draws the same file
    pg.fill("#dd-balance", "1000")
    pg.dispatch_event("#dd-balance", "change")
    pg.wait_for_function("document.querySelector('#dd-out [data-k=max_pct]').textContent !== '—'")
    assert k(pg, "max_pct", s) == "10.71%" and k(pg, "recovery_gain", s) == "12.00%"
    rows = pg.locator("#dd-out table").last.locator("tbody tr")
    assert rows.nth(0).inner_text().split("\t")[4:7] == [MINUS + "$120.00", "10.71%", "12.00%"]
    assert rows.nth(1).inner_text().split("\t")[4:7] == [MINUS + "$80.00", "7.27%", "7.84%"]
    # 7 trades: under 30, so the teaser keeps its fallback line
    t = pg.inner_text("#dd-teaser-text")
    assert t == "We're building a habit report that looks at what you do after a loss and after a run of losses, in your own trade file."
    assert pg.get_attribute("#dd-teaser-text", "data-live") is None
    assert_clean(ctx, pg, log, built_site, DD)
    ctx.close()


def test_dd_core_on_hand_trades(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, DD)
    got = pg.evaluate("""async () => { const m = await import('/static/js/tools/drawdown-core.js');
        const day = (d, hh, mm) => Date.UTC(2026, 5, d, hh, mm);
        const t = (d, oh, om, ch, cm, pnl) => ({pnl, close_ts: day(d, ch, cm), hold_s: (day(d, ch, cm) - day(d, oh, om)) / 1000});
        const trades = [t(1,10,0,10,30,100), t(2,10,0,10,20,-50), t(3,10,0,10,5,-30), t(4,10,0,10,30,40),
                        t(5,10,0,10,30,60), t(8,10,0,10,30,-120), t(8,10,40,11,0,20)];
        const r = m.drawdowns(trades, 1000);
        return {eps: r.episodes.map(e => [e.peak_i, e.trough_i, e.end_i, e.depth, e.trades, e.days, e.recovered]),
                max_pct: r.max_pct, after: m.openedAfterLoss(trades, r.deepest), first: m.openedAfterLoss(trades, r.episodes[0])}; }""")
    assert got["eps"] == [[0, 2, 4, 80, 4, 4, True], [4, 5, 6, 120, 2, 3, False]]
    assert abs(got["max_pct"] - 120 / 1120) < 1e-12
    assert got["after"] == {"n": 2, "hits": 1}      # trade 7, 10 minutes after trade 6
    assert got["first"] == {"n": 4, "hits": 0}      # each opened a day after the last loss
    ctx.close()


def test_dd_no_drawdown(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, DD)
    upload(pg, "dd", "no_drawdown.csv")
    assert "No drawdown in this file" in pg.inner_text("#dd-none")
    assert k(pg, "max_abs", "#dd-out") == "$0.00" and k(pg, "current", "#dd-out") == "none: at the high"
    assert L.lint_text(pg.inner_text("main"), DD) == []
    ctx.close()


def demo_trades():
    return E.parse_file(open(DEMO, "rb").read())["trades"]


def dd_mirror(trades):
    """Written from the definitions in the page's "How the numbers are counted", not from drawdown-core.js."""
    eps, eq, high, high_i, cur = [], 0.0, 0.0, -1, None
    for i, t in enumerate(trades):
        eq += t["pnl"]
        if eq >= high:
            if cur:
                cur["end"], cur["recovered"] = i, True
                eps.append(cur)
                cur = None
            high, high_i = eq, i
        elif cur is None:
            cur = {"high_i": high_i, "high": high, "low_i": i, "depth": high - eq}
        elif high - eq > cur["depth"]:
            cur["low_i"], cur["depth"] = i, high - eq
    if cur:
        cur["end"], cur["recovered"] = len(trades) - 1, False
        eps.append(cur)
    for e in eps:
        e["trades"] = e["end"] - e["high_i"]
        start = trades[0]["open_ts"] if e["high_i"] < 0 else trades[e["high_i"]]["close_ts"]
        e["days"] = trades[e["end"]]["close_ts"] // 86400000 - start // 86400000
    return eps, eq


def test_dd_sample_equals_python_mirror_and_teaser(browser, built_site):
    trades = demo_trades()
    eps, final = dd_mirror(trades)
    deep = max(eps, key=lambda e: e["depth"])     # max() keeps the first on ties, as the page does
    longest = max(eps, key=lambda e: e["trades"])
    longest_d = max(eps, key=lambda e: e["days"])
    losses = [t["close_ts"] for t in trades if t["pnl"] < 0]
    inside = trades[deep["high_i"] + 1: deep["end"] + 1]
    def after_loss(t):
        prev = [c for c in losses if c <= t["open_ts"]]
        return bool(prev) and t["open_ts"] - max(prev) <= 15 * 60 * 1000
    hits = sum(after_loss(t) for t in inside)
    ctx, pg, log = open_page(browser, built_site, DD)
    log["requests"].clear()
    pg.click("#dd-sample-btn")
    pg.wait_for_selector("#dd-out:not([hidden])")
    s = "#dd-out"
    assert k(pg, "max_abs", s) == money(-deep["depth"])
    assert k(pg, "longest_trades", s) == f"{longest['trades']} trades"
    assert k(pg, "longest_days", s) == f"{longest_d['days']} calendar days"
    assert k(pg, "summary", s).startswith(f"{len(eps)} drawdowns in {len(trades)} closed trades; {sum(e['recovered'] for e in eps)} recovered")
    cur = eps[-1]
    assert k(pg, "current", s) == ("none: at the high" if cur["recovered"] else money(-(cur["high"] - final)))
    assert "Example data" in pg.inner_text(s)   # 29 Oct (owner)
    assert hits > 0
    want = (f"Your deepest drawdown ran {len(inside)} trades, and {round(100 * hits / len(inside))}% of the trades inside it "
            "were opened within 15 minutes of a loss. We're building a habit report that tests whether trades opened within "
            "15 minutes of a loss turned out differently from the rest, and what they totalled in your file.")
    assert pg.inner_text("#dd-teaser-text") == want
    assert pg.get_attribute("#dd-teaser-text", "data-live") == "true"
    # the underwater chart has a table fallback and an SVG title
    assert pg.locator("#dd-out figure.chart svg title").count() == 1
    assert pg.locator("#dd-out figure.chart details table").count() == 1
    assert_clean(ctx, pg, log, built_site, DD)
    ctx.close()


# ================================================================== heatmap
# heatmap_hand.csv (opened → closed, result):
#   A Mon 1 Jun 09:30 → 09:45  +10    B Mon 1 Jun 09:50 → 10:10  −4
#   C Tue 2 Jun 14:05 → 15:30  +6     D Sat 6 Jun 23:30 → Sun 7 Jun 00:10  −2
# No shift: Mon 09:00 = A + B = +6 (2 trades, average +3, win rate 50%); Tue 14:00 = +6; Sat 23:00 = −2.
# +2 h: A, B open 11:30, 11:50 → Mon 11:00 (+6); D opens Sun 01:30 → Sun 01:00 (−2).
# −10 h: A, B open Sun 31 May 23:30, 23:50 → Sun 23:00 (+6); C → Tue 04:00; D → Sat 13:00.
# 4-hour blocks: Mon 08:00–12:00 (block 2) = +6.
def cell(pg, wd, b):
    return pg.inner_text(f'#hm-grid td[data-cell="{wd}-{b}"]').split("\n")


def test_hm_hand_file(browser, built_site):
    ctx, pg, log = open_page(browser, built_site, HM)
    log["requests"].clear()
    upload(pg, "hm", "heatmap_hand.csv")
    assert cell(pg, 0, 9) == ["+$6.00", "2 trades"]
    assert cell(pg, 1, 14) == ["+$6.00", "1 trade"]
    assert cell(pg, 5, 23) == [MINUS + "$2.00", "1 trade"]
    assert pg.locator("#hm-grid td.heat-empty").count() > 0 and "heat-l" in pg.get_attribute('#hm-grid td[data-cell="5-23"]', "class")
    assert "heat-g4" in pg.get_attribute('#hm-grid td[data-cell="0-9"]', "class")
    heads = pg.locator("#hm-grid thead th").all_inner_texts()
    assert heads == ["Opened", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows = pg.locator("#hm-grid tbody th").all_inner_texts()
    assert rows == ["09:00–10:00", "14:00–15:00", "23:00–24:00"]
    assert k(pg, "range", "#hm-out") == ("Open times as written in the file: first trade opened Monday 2026-06-01 09:30, last opened "
                                         "Saturday 2026-06-06 23:30. If these do not match what you remember, change the shift above.")
    mon = pg.locator("#hm-out table").nth(1).locator("tbody tr").first.inner_text().split("\t")
    assert mon == ["Monday", "2", "+$6.00", "+$3.00", "50.0%"]
    assert "This grid has 3 cells with trades." in pg.inner_text("#hm-many")
    assert k(pg, "n_small", "#hm-many").startswith("All 3 cells hold fewer than 30 trades")
    assert pg.inner_text("#hm-teaser-text") == ("None of your cells has 30 or more trades yet. We're building a habit report that "
                                                "looks at what you do after a loss rather than at the clock.")
    pg.select_option("#hm-shift", "2")
    assert cell(pg, 0, 11) == ["+$6.00", "2 trades"] and cell(pg, 6, 1) == [MINUS + "$2.00", "1 trade"]
    assert "shifted +2 h from the file" in k(pg, "range", "#hm-out")
    pg.select_option("#hm-shift", "-10")
    assert cell(pg, 6, 23) == ["+$6.00", "2 trades"] and cell(pg, 1, 4) == ["+$6.00", "1 trade"] and cell(pg, 5, 13) == [MINUS + "$2.00", "1 trade"]
    pg.select_option("#hm-shift", "0")
    pg.select_option("#hm-block", "4")
    assert cell(pg, 0, 2) == ["+$6.00", "2 trades"]
    assert pg.locator("#hm-grid tbody th").all_inner_texts() == ["08:00–12:00", "12:00–16:00", "20:00–24:00"]
    assert_clean(ctx, pg, log, built_site, HM)
    ctx.close()


def test_hm_core(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, HM)
    got = pg.evaluate("""async () => { const m = await import('/static/js/tools/heatmap-core.js');
        return {lv: [[0, 10], [1, 10], [2.5, 10], [2.6, 10], [-10, 10], [-7.6, 10], [5, 0]].map(([t, x]) => m.level(t, x)),
                labels: [m.blockLabel(0, 1), m.blockLabel(23, 1), m.blockLabel(5, 4), m.blockLabel(3, 3)]}; }""")
    assert got["lv"] == [0, 1, 1, 2, -4, -4, 0]
    assert got["labels"] == ["00:00–01:00", "23:00–24:00", "20:00–24:00", "09:00–12:00"]
    ctx.close()


def hm_mirror(trades, block=1, shift=0):
    grid = {}
    for t in trades:
        o = dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=t["open_ts"] + shift * 3600000)
        key = (o.weekday(), o.hour // block)
        c = grid.setdefault(key, {"n": 0, "total": 0.0})
        c["n"] += 1
        c["total"] += t["pnl"]
    return grid


def test_hm_sample_equals_python_mirror_and_teaser(browser, built_site):
    trades = demo_trades()
    ctx, pg, log = open_page(browser, built_site, HM)
    log["requests"].clear()
    pg.click("#hm-sample-btn")
    pg.wait_for_selector("#hm-out:not([hidden])")
    for block in (1, 2, 4):
        pg.select_option("#hm-block", str(block))
        grid = hm_mirror(trades, block)
        for (wd, b), c in grid.items():
            assert cell(pg, wd, b) == [money(c["total"]), f"{c['n']} trade{'s' if c['n'] != 1 else ''}"], (block, wd, b)
        assert pg.locator("#hm-grid td.heat:not(.heat-empty)").count() == len(grid)
        big = [(wd, b, c) for (wd, b), c in sorted(grid.items()) if c["n"] >= 30]
        teaser = pg.inner_text("#hm-teaser-text")
        if big:
            wd, b, c = min(big, key=lambda x: x[2]["total"])
            lab = f"{b * block:02d}:00–{(b + 1) * block:02d}:00"
            assert teaser == (f"Your {WEEKDAYS[wd]} {lab} trades ({c['n']} of them) closed at {money(c['total'])} in total. We're building a "
                              "habit report that looks at what you do after a loss, such as trades opened within 15 minutes of one, rather than at the clock.")
        else:
            assert teaser.startswith("None of your cells has 30 or more trades yet.")
    assert block == 4 and big, "the 4-hour grid of the sample has cells of 30+ trades, so the live line is tested"
    assert_clean(ctx, pg, log, built_site, HM)
    ctx.close()


# ================================================================== every page
@pytest.mark.parametrize("path,notices,hidden", [
    (RR, ["#rr-js-needed"], ["#rr-form"]),
    (DD, ["#dd-q-js-needed", "#dd-js-needed"], ["#dd-q-form", "#dd-controls"]),
    (HM, ["#hm-js-needed"], ["#hm-controls"]),
])
def test_js_off_says_so(browser, built_site, path, notices, hidden):
    ctx, pg, _ = open_page(browser, built_site, path, java_script_enabled=False)
    for n in notices:
        assert pg.is_visible(n) and "needs JavaScript" in pg.inner_text(n)
    for h in hidden:
        assert pg.is_hidden(h)
    assert pg.is_visible(".teaser") and "Join the waitlist — $39 founding price" in pg.inner_text(".teaser")
    if path == DD:
        assert pg.is_visible("#dd-table") and "25.0%" in pg.inner_text("#dd-table")
    assert L.lint_text(pg.inner_text("main"), path) == []
    ctx.close()


@pytest.mark.parametrize("path", PATHS)
def test_csp_and_head(built_site, path):
    import html as H
    page = next(p for p in B.PAGES if p["path"] == path)
    text = (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
    csp = H.unescape(re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', text).group(1))
    d = dict((x.split(" ", 1) + [""])[:2] for x in (y.strip() for y in csp.split(";")))
    assert d["connect-src"] == "'none'" and d["script-src"] == "'self'" and d["style-src"] == "'self'"
    assert "<script>" not in text and " style=" not in text and "onclick" not in text   # no inline script or style
    assert f"<title>{page['title']}</title>" in text and f'<link rel="canonical" href="https://donttrade.ca{path}">' in text
    assert '"@type": "WebApplication"' in text and '"@type": "FAQPage"' in text and '"@type": "BreadcrumbList"' in text
    sm = (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>https://donttrade.ca{path}</loc><lastmod>2026-10-21</lastmod>" in sm


def run_sample(pg, path):
    if path == RR:
        rr(pg, "prices", entry="100", stop="98", target="106", winrate="40")
        pg.wait_for_selector("#rr-out:not([hidden])")
    elif path == DD:
        pg.fill("#dd-pct", "20")
        pg.click("#dd-q-form button[type=submit]")
        pg.fill("#dd-balance", "10000")
        pg.click("#dd-sample-btn")
        pg.wait_for_selector("#dd-out:not([hidden])")
    else:
        pg.click("#hm-sample-btn")
        pg.wait_for_selector("#hm-out:not([hidden])")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 1280])
@pytest.mark.parametrize("path", PATHS)
def test_axe_and_overflow(browser, built_site, path, scheme, width):
    ctx, pg, _ = open_page(browser, built_site, path, width=width, scheme=scheme, bypass_csp=True)
    run_sample(pg, path)
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == [] and axe_violations(pg) == []
    ctx.close()


def test_heat_cell_text_contrast(browser, built_site):
    """The darkest tints keep the cell text at >= 4.5:1 in both themes (color-mix is resolved by the browser)."""
    for scheme in ("light", "dark"):
        ctx, pg, _ = open_page(browser, built_site, HM, scheme=scheme)
        ratios = pg.evaluate("""() => {
            const lum = (c) => { const m = c.match(/[\\d.]+/g).slice(0, 3).map(Number);
                const v = (c.startsWith('color(') ? m : m.map(x => x / 255)).map(x => x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4);
                return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
            const out = {};
            for (const cls of ['heat-g4', 'heat-l4', 'heat-g1', 'heat-l1']) {
                const td = document.createElement('td'); td.className = 'heat ' + cls; td.textContent = 'x';
                const t = document.createElement('table'); t.className = 'heatmap'; t.append(document.createElement('tr')); t.firstChild.append(td);
                document.querySelector('main').append(t);
                const s = getComputedStyle(td); const a = lum(s.color), b = lum(s.backgroundColor);
                out[cls] = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05); t.remove(); }
            return out; }""")
        assert min(ratios.values()) >= 4.5, (scheme, ratios)
        ctx.close()


# ------------------------------------------------------------------ flags: badges, paid, analytics
def test_badges_build_changes_nothing_on_these_pages(built_site, badges_site):
    for path in PATHS:
        a = (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
        b = (badges_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
        strip = lambda h: re.sub(r"\?v=[0-9a-f]{8}", "", h)
        assert strip(a) == strip(b), path
        assert not L.free_badge_problems(a, path)
    for js in ("risk-reward.js", "drawdown.js", "drawdown-core.js", "heatmap.js", "heatmap-core.js", "file-tool.js"):
        src = (built_site["out"] / "static" / "js" / "tools" / js).read_text(encoding="utf-8")
        assert not L.free_badge_problems(src, "/static/js/tools/" + js), js
        assert "fetch(" not in src and "localStorage" not in src and "console." not in src and "sendBeacon" not in src, js


@pytest.fixture(scope="module")
def paid_tools_site(tmp_path_factory):
    import functools
    import http.server
    import threading
    from conftest import _Quiet
    from test_legal import build, paid_env
    tmp = tmp_path_factory.mktemp("tools2-paid")
    r, out = build(tmp, "on", **paid_env(tmp))
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


def test_paid_build_sells_and_teasers_follow(browser, paid_tools_site):
    # owner, 25 Oct: the paid build's one offer is partials/tool_next_step.html, right after the result
    # container; the teaser box (which quoted the visitor's figures) is gone, and a run changes nothing in it.
    for path in PATHS:
        h = (paid_tools_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
        assert 'href="/pricing/#last-step">Get the habit report — $39</a>' in h and "/for-traders/#waitlist" not in h, path
        assert h.count('class="notice notice-gap next-step"') == 1 and "notice-gap teaser" not in h, path
        assert not L.not_on_sale_claims(L.readable_text(h), path), path
    ctx, pg, _ = open_page(browser, paid_tools_site, DD)
    before = pg.inner_text(".next-step")
    pg.click("#dd-sample-btn")
    pg.wait_for_selector("#dd-out:not([hidden])")
    assert pg.inner_text(".next-step") == before and "reads your trade file" in before
    pg.goto(paid_tools_site["url"] + HM)
    before = pg.inner_text(".next-step")
    pg.click("#hm-sample-btn")
    pg.wait_for_selector("#hm-out:not([hidden])")
    assert pg.inner_text(".next-step") == before and "reads this same file" in before
    ctx.close()


def test_analytics_build_switches_the_privacy_sentence(tmp_path):
    from test_merge_oldpages import _flag_build
    out, _ = _flag_build(tmp_path, "a", launch="2026-10-21", analytics=True)
    # 29 Oct (Tester sweep 3 #5): one sentence on every file tool, in the FAQ and in "How it works"
    # 29 Oct (owner): one sentence wherever the analytics line appears, the Readiness Check included
    one = "Only anonymous counts of visits and finished steps are sent; your file is never sent."
    for path, sentence in ((DD, one), (HM, one), ("/tools/trade-stats/", one), ("/tools/prop-challenge-simulator/", one)):
        h = (out / path.strip("/") / "index.html").read_text(encoding="utf-8")
        assert sentence in h, path
        assert "blocks every outgoing network request" not in h and "blocks it from making network requests" not in h, path


def test_tools_index_lists_the_new_tools(built_site):
    h = (built_site["out"] / "tools" / "index.html").read_text(encoding="utf-8")
    for path in PATHS:
        assert f'<a class="tool-card-link" href="{path}">' in h and f'"url": "https://donttrade.ca{path}"' in h, path   # 25 Oct sweep: one link per card
