"""Batch S4, "Small-file facts and challenge check" (ARCHITECT-SMALL-FILES-ADDENDUM-2026-10-31 Lever 7 and §3.1;
ARCHITECT-BUNDLE-DONTTRADE-TEST-2026-10-31 B3 and §2.3).

* small-facts.js (pure, in Node): each fact on small hand-made files: no losses, a single day, no winning day,
  a firm whose rules leave the best-day limit "not stated", ties (the first wins), a loss exactly at the daily
  limit, a firm with no daily limit, a dates-only file, closing order.
* The hand-built 30-trade file (tests/fixtures/paid/small-30.csv): every fact, the first breach in the real order
  (rule, day, trade), every breach day, the habits on breach days with their dollars, the best-day share.
* Wording: every fixed string and every sentence shape passes the site lint (no advice, recommend, should, must,
  fix, coach, improve, ...) and carries no hedge (may, might, maybe, possibly, perhaps, unclear, not clear,
  could be).
* Chromium, end to end: the 30-trade file read by the report page's engine, rendered by renderReport with a
  30-trade report whose habits show no sign (the small-file order: facts first, then the rule check, then the
  habits); a firm picked; the text, lint, no network request, no horizontal overflow at 390 px.
* The example report's page embeds the committed sample-report.csv and draws both sections from it."""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from lint import lint_text  # noqa: E402

# "May" the month (after a day number) is a date, not a hedge.
HEDGE = re.compile(r"\b(?:might|maybe|possibly|perhaps|unclear|could\s+be|not\s+clear)\b|(?<!\d )\bmay\b", re.IGNORECASE)

JS_UNITS = r"""
import { readFileSync } from 'node:fs';
const SF = await import('./site/static/js/paid/small-facts.js');
const { NOT_STATED } = await import('./site/static/js/tools/challenge-presets.js');
const lib = JSON.parse(readFileSync('site/config/challenge_rules.json', 'utf8'));
const P = (id) => lib.presets.find((p) => p.id === id);
// T(day of June 2026, 'hh:mm' open, hold in minutes, P&L, qty)
const T = (d, hm, hold, pnl, qty = 1) => {
  const [h, m] = hm.split(':').map(Number);
  const o = Date.UTC(2026, 5, d, h, m);
  return { symbol: 'A', dir: 'long', open_ts: o, close_ts: o + hold * 60000, hold_s: hold * 60, qty, pnl, pnl_unit: 'USD' };
};
const out = {};
out.no_losses = SF.fileFacts([T(1, '09:30', 5, 10), T(2, '09:30', 5, 20)]);
out.no_losses_cons = SF.consistencyShare([10, 20], 0.5);
out.single_up = SF.fileFacts([T(1, '09:30', 5, 10), T(1, '09:40', 5, -5), T(1, '09:50', 5, -7), T(1, '10:00', 5, 3)]);
out.single_up_cons = SF.consistencyShare([1], 0.5);
out.single_down = SF.fileFacts([T(1, '09:30', 5, -10), T(1, '09:40', 5, 3)]);
out.no_win_day = SF.fileFacts([T(1, '09:30', 5, -10), T(2, '09:30', 5, -5), T(2, '09:40', 5, 2)]);
out.no_win_day_cons = SF.consistencyShare([-10, -3], 0.3);
out.no_profit_cons = SF.consistencyShare([50, -80], 0.3);
out.ties = SF.fileFacts([T(1, '09:30', 5, -10), T(1, '09:40', 5, -30), T(1, '09:50', 5, 20),   // day 1: -20, run of 2
  T(2, '09:30', 5, -30), T(2, '09:40', 5, -10), T(2, '09:50', 5, 20),                          // day 2: -20, run of 2
  T(3, '09:30', 5, 50), T(4, '09:30', 5, 50)]);
out.ties_cons = SF.consistencyShare([-20, -20, 50, 50], 0.5);
out.ties_day1 = T(1, '09:30', 5, 0).close_ts;
out.flat_breaks_run = SF.fileFacts([T(1, '09:30', 5, -1), T(1, '09:40', 5, 0), T(1, '09:50', 5, -1), T(1, '10:00', 5, -1)]);
out.last_run = SF.fileFacts([T(1, '09:30', 5, 5), T(1, '09:40', 5, -1), T(1, '09:50', 5, -2)]);
out.two_losses = SF.fileFacts([T(1, '09:30', 5, -4), T(1, '09:40', 5, -6), T(1, '09:50', 5, 1)]);
// closing order, whatever the input order: the facts number trades by close
out.order = SF.fileFacts([T(2, '09:30', 5, -9), T(1, '09:30', 5, 4)]);
// "not stated": Alpha Capital Group's page states no best-day limit
const alpha = SF.challengeCheck([T(1, '09:30', 5, 300), T(2, '09:30', 5, 100)], P('alpha-capital-group-alpha-pro-10-phase-1'), { accountSize: 100000, fileTz: 'UTC' });
out.alpha = { cons: alpha.consistency, ns: alpha.not_stated, ns_marker: NOT_STATED, first: alpha.first };
// a loss that reaches the daily limit exactly counts (prop-sim-core: reaching is a breach); 3% of 10,000 = 300
const exact = SF.challengeCheck([T(1, '09:30', 5, -100), T(1, '09:40', 5, -200), T(1, '09:50', 5, 50), T(2, '09:30', 5, -299.99)], P('ftmo-1-step'), { accountSize: 10000, fileTz: 'UTC' });
out.exact = { first: exact.first, breaches: exact.breaches.map((b) => [b.day, b.trade.n, b.running]) };
// no daily limit (Topstep): no breach days; the max loss (2,000, trailing end of day) breaks first
const top = SF.challengeCheck([T(1, '09:30', 5, -1500), T(1, '09:40', 5, -600), T(2, '09:30', 5, 10)], P('topstep-50k-trading-combine'), { fileTz: 'UTC' });
out.topstep = { first: top.first, breaches: top.breaches, daily: top.rules.daily_loss, habits: top.habits.map((h) => h.n_trades), cons: top.consistency };
// a dates-only file: re-entry and size after a loss need times
const D = (d, pnl) => { const o = Date.UTC(2026, 5, d); return { symbol: 'A', dir: 'long', open_ts: o, close_ts: o + 86400000, hold_s: 86400, qty: 1, pnl, pnl_unit: 'USD' }; };
const dates = SF.challengeCheck([D(1, -400), D(3, -200), D(5, 50)], P('ftmo-1-step'), { accountSize: 10000, fileTz: 'UTC' });
out.dates = { dates_only: dates.dates_only, needs: dates.habits.filter((h) => h.needs_times).map((h) => h.id), breaches: dates.breaches.length };
// the 30-trade fixture through the engine
const { runFile } = await import('./site/static/js/engine/index.js');
const r = runFile(new Uint8Array(readFileSync('tests/fixtures/paid/small-30.csv')));
const t30 = r.result.trades;
out.f30 = SF.fileFacts(t30);
const c30 = SF.challengeCheck(t30, P('ftmo-1-step'), { accountSize: 10000, fileTz: 'UTC' });
out.c30 = { first: c30.first, breaches: c30.breaches.map((b) => ({ day: b.day, trade: b.trade.n, running: b.running })), habits: c30.habits,
  cons: c30.consistency, ns: c30.not_stated, n: c30.n_trades };
// the real-order replay is the free Readiness Check's own sequence mode on the same days and rules
const core = await import('./site/static/js/tools/prop-sim-core.js');
const pr = (await import('./site/static/js/tools/challenge-presets.js')).presetRules(P('ftmo-1-step'), 10000);
const seq = core.simulate({ mode: 'sequence', days: core.groupDays(t30, { fileTz: 'UTC', dayStart: pr.dayStart }).days, rules: pr.rules });
out.parity = { outcome: seq.outcome, why: seq.why, day: seq.day };
// every preset the library can quote runs on the 30-trade file
out.all = SF.usablePresets(lib).map((p) => { const c = SF.challengeCheck(t30, p, { fileTz: 'UTC' }); return [p.id, c.first.outcome, c.breaches.length]; });
out.tz = [SF.defaultFileTz('mt5'), SF.defaultFileTz('mt4'), SF.defaultFileTz('generic'), SF.defaultFileTz('generic', true)];
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def units():
    r = subprocess.run(["node", "--input-type=module", "-e", JS_UNITS], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_no_losses(units):
    f = units["no_losses"]
    assert (f["n"], f["n_loss"], f["net"], f["loss_total"]) == (2, 0, 30, 0)
    assert f["worst_day"] is None and f["run"] is None and f["largest_loss"] is None and f["top"] is None
    c = units["no_losses_cons"]
    assert c["kind"] == "share" and c["best"] == 20 and c["best_day"] == 2 and abs(c["share"] - 20 / 30) < 1e-12 and c["over"] is True


def test_single_day(units):
    f = units["single_up"]
    assert f["n_days"] == 1 and f["worst_day"] is None   # the only day ended at +1: no losing day
    assert f["run"] == {"length": 2, "total": -12, "from": 2, "to": 3, "same_length": 1, "next": {"n": 4, "pnl": 3}}
    assert units["single_up_cons"]["share"] == 1 and units["single_up_cons"]["over"] is True
    d = units["single_down"]
    assert d["worst_day"]["total"] == -7 and d["worst_day"]["n_trades"] == 2 and d["worst_day"]["loss_share"] == 1


def test_no_winning_day(units):
    f = units["no_win_day"]
    assert f["worst_day"]["total"] == -10 and f["n_days"] == 2
    assert units["no_win_day_cons"]["kind"] == "no_win_day" and units["no_win_day_cons"]["best"] is None
    c = units["no_profit_cons"]
    assert c["kind"] == "no_profit" and c["best"] == 50 and c["net"] == -30 and "share" not in c


def test_ties_go_to_the_first(units):
    f = units["ties"]
    assert f["worst_day"]["total"] == -20 and f["worst_day"]["date_ts"] == units["ties_day1"]   # day 1, its first close
    assert f["run"]["from"] == 1 and f["run"]["length"] == 2 and f["run"]["same_length"] == 2
    assert f["largest_loss"] == {"n": 2, "pnl": -30, "close_ts": f["largest_loss"]["close_ts"], "share": 0.375}
    assert f["top"] == {"k": 3, "of": 4, "total": -70, "share": 0.875}
    c = units["ties_cons"]
    assert c["best_day"] == 3 and c["best"] == 50 and c["share"] == 50 / 60


def test_runs_and_closing_order(units):
    assert units["flat_breaks_run"]["run"]["length"] == 2 and units["flat_breaks_run"]["run"]["from"] == 3   # break-even ends a run
    assert units["flat_breaks_run"]["n_flat"] == 1
    assert units["last_run"]["run"]["next"] is None
    t = units["two_losses"]["top"]
    assert t == {"k": 2, "of": 2, "total": -10, "share": 1}
    o = units["order"]
    assert o["largest_loss"]["n"] == 2 and o["run"]["from"] == 2   # the June 2 loss closed second


def test_not_stated_firm(units):
    a = units["alpha"]
    assert "consistency" in a["ns"] and a["cons"]["limit"] == a["ns_marker"] == "not stated" and a["cons"]["over"] is None
    assert a["cons"]["kind"] == "share" and a["cons"]["share"] == 0.75


def test_exact_limit_and_no_daily_limit(units):
    e = units["exact"]
    assert e["first"]["outcome"] == "bust" and e["first"]["why"] == "daily" and e["first"]["trade"]["n"] == 2 and e["first"]["day"] == 1
    assert e["breaches"] == [[1, 2, -300]]   # day 2's -299.99 does not reach it
    t = units["topstep"]
    assert t["daily"] is None and t["breaches"] == [] and t["habits"] == [0, 0, 0, 0]
    assert t["first"]["outcome"] == "bust" and t["first"]["why"] == "max" and t["first"]["trade"]["n"] == 2
    d = units["dates"]
    assert d["dates_only"] is True and d["needs"] == ["reentry", "size_after_loss"] and d["breaches"] == 1


# The 30-trade file's facts, worked out by hand (tests/fixtures/paid/make_small_30.py).
def test_thirty_trade_file_facts(units):
    f = units["f30"]
    assert (f["n"], f["n_win"], f["n_loss"], f["n_days"]) == (30, 14, 16, 5)
    assert (f["net"], f["win_total"], f["loss_total"]) == (580, 1460, -880)
    w = f["worst_day"]
    assert (w["total"], w["n_trades"], w["loss"]) == (-330, 6, -350) and round(100 * w["loss_share"]) == 40
    assert f["run"] == {"length": 5, "total": -350, "from": 7, "to": 11, "same_length": 1, "next": {"n": 12, "pnl": 20}}
    assert f["largest_loss"]["n"] == 26 and f["largest_loss"]["pnl"] == -120
    assert f["top"]["total"] == -310 and round(100 * f["top"]["share"]) == 35


def test_thirty_trade_file_against_ftmo(units):
    c = units["c30"]
    assert c["n"] == 30
    f = c["first"]
    assert (f["outcome"], f["why"], f["day"], f["trade"]["n"], f["day_at"]) == ("bust", "daily", 2, 11, -350)
    assert units["parity"] == {"outcome": "bust", "why": "daily", "day": 2}
    assert c["breaches"] == [{"day": 2, "trade": 11, "running": -350}, {"day": 5, "trade": 28, "running": -300}]
    h = {x["id"]: (x["on_breach"], x["n_breach"], x["on_other_losing"], x["n_other_losing"], x["n_trades"], x["total"]) for x in c["habits"]}
    assert [x["id"] for x in c["habits"]] == ["reentry", "streak", "size_after_loss", "large_loss"]   # fixed order
    assert h == {"reentry": (2, 2, 1, 1, 6, -490), "streak": (2, 2, 1, 1, 5, -320), "size_after_loss": (0, 2, 0, 1, 0, 0),
                 "large_loss": (1, 2, 0, 1, 2, -220)}
    k = c["cons"]
    assert k["kind"] == "share" and k["best"] == 480 and k["net"] == 580 and k["limit"] == 0.5 and k["over"] is True
    assert c["ns"] == ["min_days", "time_limit"]
    assert len(units["all"]) >= 8 and all(o in ("bust", "pass", "timeout", "end") for _, o, _ in units["all"])
    assert units["tz"] == ["broker", "broker", "local", "UTC"]


JS_STRINGS = r"""
const V = await import('./site/static/js/paid/small-facts-view.js');
const L = V.SF_LINES, m = '−$1,234.50', p = '+$80.00';
const shapes = [];
for (const [k, f] of Object.entries(L)) {
  if (typeof f === 'string') { shapes.push(f); continue; }
  const args = { facts_h: [[1], [30]], won: [[p, 1], [p, 14]], lost: [[m, 1], [m, 16]], flat: [[1], [3]], worst_sub: [['Tue 2 Jun', 6]],
    top_label: [[3, 16], [2, 2], [1, 1]], largest: [[m, 26]], run_value: [[1], [5]], run_trades: [[7, 11], [4, 4]], run_next: [[p]],
    run_ties: [[2]], first_bust: [['daily loss limit', 'Tue 2 Jun', 2, 11, 30], ['maximum loss', 'Fri 5 Jun', 5, 28, 30]],
    bust_sub_daily: [['Closed at 10:40', m]], bust_sub_max: [['Closed Tue 2 Jun 2026', m]], closed_at: [['10:40']], closed_on: [['Tue 2 Jun 2026']],
    first_pass: [[9]], first_pass_held: [[7, 9]], first_end: [[1], [5]], first_time: [[30]], rules_for: [['FTMO', 'FTMO Challenge: 1-Step', '$10,000.00']],
    max_kind: [['$1,000.00', 'fixed']], not_stated: [['FTMO', 'time limit (the check uses none)']], not_stated_one: [['FTMO']],
    ns_part: [['time limit', 'none']], breach_count: [[2, 5], [1, 1]], no_breach: [['$300.00']], breach_row: [['Tue 2 Jun', 2, 11]],
    breach_more: [[1], [4]], cons_line: [[p, p]], cons_over: [['FTMO', '50%']], cons_within: [['FTMO', '50%']], cons_no_profit: [[m, p]],
    habit_days: [[2, 2, 1, 1], [0, 2, 0, 0]], habit_money: [[1, m], [6, m]], read_on: [['FTMO', '29 Oct 2026']], strip_label: [[5, 2], [1, 0]] }[k];
  if (!args) throw new Error('no sample arguments for SF_LINES.' + k);
  for (const a of args) shapes.push(f(...a));
}
console.log(JSON.stringify({ text: Object.values(V.SF_TEXT), names: Object.values(V.HABIT_NAMES), shapes }));
"""


def test_every_new_string_is_lint_clean_and_definite():
    r = subprocess.run(["node", "--input-type=module", "-e", JS_STRINGS], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    every = s["text"] + s["names"] + s["shapes"]
    assert len(s["shapes"]) >= 50
    for x in every:
        assert lint_text(x, "small-facts", paid=True) == [], x
        assert not HEDGE.search(x), x
        assert "NaN" not in x and "undefined" not in x, x


# ------------------------------------------------------------------ Chromium, end to end

RENDER = r"""
async ({ csv, presets }) => {
  const tag = document.createElement('script');
  tag.type = 'application/json'; tag.id = 'sf-presets'; tag.textContent = presets;
  document.body.append(tag);
  const { runFile } = await import('/site/static/js/engine/index.js');
  const { renderReport } = await import('/site/static/js/paid/report.js');
  const parsed = runFile(new TextEncoder().encode(csv));
  const trades = parsed.result.trades;
  const H = (id, name, verdict, n, amt) => ({ id, name, question: name + '?', n_a: 6, n_b: 24, measure_a: -40, measure_b: 30, effect: -70,
    p_raw: verdict === 'not_distinguishable' ? 0.4 : null, p_holm: verdict === 'not_distinguishable' ? 0.8 : null, verdict, direction: null,
    method: 'within-day sequence shuffle (mean and rank)', n_perm: 999, n_a_compared: null, n_b_compared: null, p_mean: 0.4, p_rank: 0.4,
    detail: id === 'tilt' ? { streak3_n: 3, streak3_mean: -30 } : null, research_ref: null,
    dollars: { label: name + ' trades', amount: amt, n_trades: n },
    ...(id === 'hold_gap' || id === 'size_up' ? { verdict: 'withheld', withheld: 'not_calibrated', p_raw: null, p_holm: null, n_perm: null,
      share: null, share_a: null, share_b: null, spread_ratio: null, n_long_a: 0, n_long_b: 0 } : {}) });
  const report = { v: 1, currency: 'USD', disclaimer: 'donttrade measures your own past trades. It is not investment advice, does not recommend any security, trade, size or exit, and is not registered as an adviser. Past results do not predict future results.',
    engine_commit: 'test', rule_library_version: 'test', rule_library: ['Rule one.'], method_version: '2026-10-23.stats2f', n_rows: 30, dates_only: false,
    n_date_only_rows: 0, n_trades: 30, period_weeks: 1, pgr_plr: null, focus: null,
    habits: [H('hold_gap', 'Holding losers longer than winners', 'withheld', 8, -200), H('revenge', 'Re-entering soon after a loss', 'not_distinguishable', 14, -490),
      H('size_up', 'Size after a loss', 'withheld', 0, 0), H('tilt', 'Trading after a losing streak', 'too_few', 9, -320),
      { id: 'oversized_loss', name: 'Losses much larger than your usual loss', question: 'Q?', n_a: 2, n_b: null, measure_a: 0.07, measure_b: 0.25, effect: -45,
        p_raw: null, p_holm: null, verdict: 'descriptive', direction: null, method: null, n_perm: null, n_a_compared: null, n_b_compared: null, detail: null,
        research_ref: null, dollars: { label: 'Large losses', amount: -220, n_trades: 2 } }] };
  report.habits.find((h) => h.id === 'tilt').p_raw = null; report.habits.find((h) => h.id === 'tilt').p_holm = null;
  report.n_tested = report.habits.filter((h) => h.p_raw !== null).length; report.n_distinguishable = 0;
  const out = document.createElement('div');
  out.id = 'rp-out';
  document.body.append(out);
  renderReport(report, out, { trades, format: parsed.result.format });
  const order = [...out.querySelectorAll(':scope > section')].map((s) => s.id || s.querySelector('h2').id);
  const before = out.querySelector('#rule-check').innerText;
  const sel = out.querySelector('#sf-preset');
  sel.value = 'ftmo-1-step'; sel.dispatchEvent(new Event('change'));
  const acc = out.querySelector('#sf-account');
  acc.value = '10000'; acc.dispatchEvent(new Event('change'));
  const tz = out.querySelector('#sf-tz');
  tz.value = 'UTC'; tz.dispatchEvent(new Event('change'));
  const texts = {};
  for (const id of usable(JSON.parse(presets))) {
    sel.value = id; sel.dispatchEvent(new Event('change'));
    out.querySelectorAll('#rule-check details').forEach((d) => { d.open = true; });
    texts[id] = out.querySelector('#rule-check').innerText;
  }
  sel.value = 'alpha-capital-group-alpha-pro-10-phase-1'; sel.dispatchEvent(new Event('change'));
  const alpha = out.querySelector('#sf-consistency').innerText;
  sel.value = 'ftmo-1-step'; sel.dispatchEvent(new Event('change'));
  acc.value = '10000'; acc.dispatchEvent(new Event('change'));
  return { order, facts: out.querySelector('#file-facts').innerText, before, ftmo: out.querySelector('#rule-check').innerText, texts, alpha,
    first: out.querySelector('#sf-first').textContent, all: out.innerText,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth };
  function usable(lib) { return lib.presets.filter((p) => p.status !== 'not_quotable' && p.rules).map((p) => p.id); }
}
"""


@pytest.fixture(scope="module")
def rendered(browser, repo_server):
    import build as B
    os.environ.setdefault("DT_TODAY", "2026-10-30")
    presets = json.dumps(B.challenge_presets(), sort_keys=True, ensure_ascii=False)
    csv = open(os.path.join(HERE, "fixtures", "paid", "small-30.csv"), encoding="utf-8").read()
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/tests/harness.html")
    page.wait_for_function("document.getElementById('status').textContent !== 'loading'")
    # the modules load first; from then on, drawing and using the sections makes no request at all
    page.evaluate("Promise.all([import('/site/static/js/engine/index.js'), import('/site/static/js/paid/report.js')]).then(() => 1)")
    page.on("request", lambda r: requests.append(r.url))
    res = page.evaluate(RENDER, {"csv": csv, "presets": presets})
    ctx.close()
    res["errors"], res["requests"] = errors, requests
    return res


def test_small_file_order_and_facts(rendered):
    assert rendered["errors"] == []
    o = rendered["order"]
    assert o[:4] == ["file-facts", "rule-check", "focus", "all-habits"], o   # §3.1: facts, rules, then the habits
    t = rendered["facts"]
    for want in ("Your 30 trades, in dollars", "Net total", "+$580.00", "+$1,460.00 won in 14 trades", "−$880.00 lost in 16 trades",
                 "Worst day", "−$330.00", "Tue 2 Jun · 6 trades", "40% of your loss dollars", "3 largest losses", "35%",
                 "Largest: −$120.00, trade 26", "Longest losing run", "5 in a row", "−$350.00", "trades 7–11", "Next trade: +$20.00"):
        assert want in t, want


def test_rule_check_on_the_thirty_trade_file(rendered):
    assert "Choose a firm to replay your trades against its rules." in rendered["before"]
    assert rendered["first"] == "In the real order, your trades broke the daily loss limit on Tue 2 Jun (day 2), at trade 11 of 30."
    t = rendered["ftmo"]
    for want in ("Closed at 10:40 · the day stood at −$350.00 at that trade.", "FTMO, FTMO Challenge: 1-Step · $10,000.00 account",
                 "$300.00", "50%", "2 of 5 days", "Tue 2 Jun · day 2 · trade 11 · the day at −$350.00",
                 "Fri 5 Jun · day 5 · trade 28 · the day at −$300.00", "83%", "Best day +$480.00 of total profit +$580.00.",
                 "FTMO’s limit: 50%. This file is over it.", "Re-entering soon after a loss", "On 2 of 2 breach days · 1 of 1 other losing day",
                 "6 trades on breach days, totalling −$490.00", "5 trades on breach days, totalling −$320.00",
                 "2 trades on breach days, totalling −$220.00", "Not stated by FTMO: time limit (the check uses none).",
                 "Rules as published by FTMO, read on 29 Oct 2026."):
        assert want in t, want
    assert "Not stated by Alpha Capital Group." in rendered["alpha"]


def test_rendered_text_is_lint_clean_definite_and_local(rendered):
    assert rendered["requests"] == []   # nothing is fetched or sent while the sections are drawn and used
    assert not rendered["overflow"]
    for k in ["facts", "before", "ftmo", "alpha"] + list(rendered["texts"]):
        x = rendered[k] if k in rendered else rendered["texts"][k]
        assert lint_text(x, k, paid=True) == [], (k, lint_text(x, k, paid=True))
        assert not HEDGE.search(x), (k, HEDGE.search(x).group(0))
        assert "NaN" not in x and "undefined" not in x and "Infinity" not in x, k


def test_example_page_embeds_the_committed_file(paid_site, browser):
    html = (paid_site["out"] / "sample-report" / "index.html").read_text(encoding="utf-8")
    csv = open(os.path.join(HERE, "fixtures", "paid", "sample-report.csv"), encoding="utf-8").read()
    assert f'<script type="text/csv" id="sample-trades">{csv}</script>' in html
    assert 'id="sf-presets"' in html and 'id="sf-presets"' in (paid_site["out"] / "report" / "index.html").read_text(encoding="utf-8")
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(paid_site["url"] + "/sample-report/")
    page.wait_for_selector("#sample-out #file-facts")
    order = page.evaluate("[...document.querySelectorAll('#sample-out > section')].map((s) => s.id || s.querySelector('h2').id)")
    facts = page.locator("#file-facts").inner_text()
    page.select_option("#sf-preset", "ftmo-1-step")
    first = page.locator("#sf-first").inner_text()
    ctx.close()
    assert errors == []
    assert order.index("all-habits") < order.index("file-facts") < order.index("rule-check") < order.index("rules")   # 304 trades: the plan's order
    assert "Your 304 trades, in dollars" in facts
    assert first.startswith("In the real order, your trades")


@pytest.fixture(scope="module")
def paid_site(tmp_path_factory):
    """The default build (paid_report is on in site.toml), served locally."""
    import functools
    import http.server
    import threading
    out = tmp_path_factory.mktemp("sf") / "_site"
    env = {**os.environ, "DT_OUT": str(out)}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    class Q(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()
