"""DT-2: "more trades" is the in-file catch line (ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §5.2, §5.3; batch S1
deletes the static power table, SHOW_MORE_TRADES and every MORE_TRADES_* string).

* The catch line (wording.js catchLine): under every No sign and Some sign, never under a Clear sign, a too-few,
  dates-only or facts-only habit. Its figures are the engine's (report catch: sizes, at_least_10ths, effect), so two
  reports that differ only in the file's own gap print the same line; a bound of 0 says "fewer than 1 in 10"; one,
  two or three sizes; a file over the engine's catch_max_trades gets the fixed line; a forged bound is refused.
* The pay step's expectation line: in pay_facts (dialog and /pricing/), definite (no hedge word), lint-clean, no
  digits, at most 14 words, and it names "No sign".
* The power table and its builder are gone; B7: teaserText (a luck result next to the offer) is gone."""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text, verdict_hedge_hits  # noqa: E402

JS = r"""
import { readFileSync } from 'node:fs';
const W = await import('./site/static/js/paid/wording.js');
const base = JSON.parse(readFileSync('tests/fixtures/paid-reports-dt2/stats__07-dayvol-trend_right_skew-220.report.json', 'utf8'));
const clone = () => JSON.parse(JSON.stringify(base));
const by = (r, id) => r.habits.find((h) => h.id === id);
const fmt = { money: (x) => (x < 0 ? '−$' : '+$') + Math.abs(x).toFixed(2), amount: (x) => '$' + Math.abs(x).toFixed(2), count: (n) => n.toLocaleString('en-US') };
const run = (f) => { try { return f(); } catch (e) { return 'THROW: ' + e.message; } };
const out = {};
out.check = Object.fromEntries(base.habits.map((h) => [h.id, W.habitLines(h, base, fmt).check]));
// the file's own gap never moves the catch line
const a = clone(), b = clone();
Object.assign(by(b, 'revenge'), { measure_a: -60, effect: -61.5 }); by(b, 'revenge').dollars.amount = -9999;
out.same = W.catchLine(by(a, 'revenge'), a, fmt) === W.catchLine(by(b, 'revenge'), b, fmt);
// sizes and bounds
const withCatch = (sizes, t) => { const r = clone(); const h = by(r, 'tilt'); r.n_trades = sizes[0]; r.n_rows = sizes[0];
  h.catch = { ...h.catch, sizes, at_least_10ths: t, caught: t.map((x) => Math.ceil(6 * x) + 6) }; return [h, r]; };
out.three = W.catchLine(...withCatch([220, 440, 880], [0, 4, 10]), fmt);
out.two = W.catchLine(...withCatch([1500, 3000], [6, 9]), fmt);
out.one = W.catchLine(...withCatch([4500], [7]), fmt);
// over the engine's limit, and every result the same size
const big = clone(); big.n_trades = 6000; big.n_rows = 6000; by(big, 'revenge').catch = null;
out.over = W.catchLine(by(big, 'revenge'), big, fmt);
const flat = clone(); by(flat, 'revenge').catch.effect.amount = 0;
out.flat = W.catchLine(by(flat, 'revenge'), flat, fmt);
// a forged bound (more than the caught count allows) is refused
const forged = clone(); by(forged, 'revenge').catch.at_least_10ths = [0, 0, 9];
out.forged = run(() => W.checkReport(forged));
const missing = clone(); by(missing, 'tilt').catch = null;
out.missing = run(() => W.checkReport(missing));
out.strings = W.VERDICT_STRINGS;
out.exports = Object.keys(W);
console.log(JSON.stringify(out));
"""


def run():
    r = subprocess.run(["node", "--input-type=module", "-e", JS], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_the_catch_line_sits_under_no_sign_and_some_sign_only():
    o = run()
    c = o["check"]
    # stats__07: revenge and tilt both Some sign (11 in 100), so each has its step line, the guard and the catch line
    for hid in ("revenge", "tilt"):
        assert len(c[hid]) == 3 and c[hid][0].startswith("Some sign of this habit in these 220 trades, short of clear.")
        assert c[hid][2].startswith("If your next trades look like these: when ")
    assert c["revenge"][2] == ("If your next trades look like these: when trades soon after a loss end $48.00 worse each, files of 220 trades show "
                               "it as a Clear sign fewer than 1 in 10 times, 440 trades fewer than 1 in 10, and 880 trades at least 3 in 10.")
    for hid in ("hold_gap", "size_up", "oversized_loss"):
        assert c[hid] == []
    assert o["same"] is True


def test_catch_line_sizes_bounds_and_fixed_lines():
    o = run()
    assert o["three"] == ("If your next trades look like these: when trades after 2 or more losses in a row end $48.00 worse each, files of 220 "
                          "trades show it as a Clear sign fewer than 1 in 10 times, 440 trades at least 4 in 10, and 880 trades at least 10 in 10.")
    assert o["two"].endswith("files of 1,500 trades show it as a Clear sign at least 6 in 10 times, and 3,000 trades at least 9 in 10.")
    assert o["one"].endswith("files of 4,500 trades show it as a Clear sign at least 7 in 10 times.")
    assert o["over"] == "Files over 5,000 trades get no catch figure."
    assert o["flat"] == "Every trade in this file has the same result, so it gets no catch figure."
    assert o["forged"].startswith("THROW: wording: revenge has a malformed catch figure")
    assert o["missing"].startswith("THROW: wording: tilt is checked on 220 trades with no catch figure")


def test_the_power_table_and_its_strings_are_gone():
    o = run()
    for gone in ("moreTrades", "BUNDLE_STRINGS", "bandFor", "tradesForEvenOdds", "MORE_TRADES_ODDS", "MORE_TRADES_CAVEAT", "moreTradesHow"):
        assert gone not in o["exports"], gone
    assert not os.path.exists(os.path.join(REPO, "site/static/js/paid/power-table.js"))
    assert not os.path.exists(os.path.join(REPO, "checks/power_table"))
    src = open(os.path.join(REPO, "site/static/js/paid/report.js"), encoding="utf-8").read()
    for gone in ("SHOW_MORE_TRADES", "moreTrades", "more-trades", "even odds"):
        assert gone not in src, gone


def test_new_strings_lint_clean():
    for s in run()["strings"]:
        assert lint_text(s, "report/index.html", paid=True, analytics=True) == [], s
        assert verdict_hedge_hits(s, "report/index.html") == [], s


def test_pay_expectation_line():
    sys.path.insert(0, os.path.join(REPO, "site"))
    import build as B
    src = open(os.path.join(REPO, "site", "templates", "partials", "pay_facts.html"), encoding="utf-8").read()
    m = re.search(r'<p class="pay-expect small" data-lint="verdict">([^<]+)</p>', src)
    assert m
    line = m.group(1).replace("{{ verdict.steps.none }}", B.step_labels()["none"])
    assert line == "Small files often show “No sign”. Every dollar total and rule check is included."
    assert not re.search(r"\d", line)
    assert len(re.findall(r"[A-Za-z’']+", line)) <= 14
    assert "would tell" not in line and "not clear" not in line.lower()
    assert lint_text(line, "pricing/index.html", paid=True, analytics=True) == []
    assert verdict_hedge_hits(line, "pricing/index.html") == []
    banned = ["advice", "recommend", "should", "fix", "coach", "must", "need to", "signal", "improve", "mentor", "certified",
              "verified", "audited", "seal"]
    assert not [w for w in banned if w in line.lower()]


def test_teaser_text_deleted():
    for p in ("site/static/js/tools/trade-stats-badges.js", "site/static/js/tools/trade-stats.js"):
        assert "teaserText" not in re.sub(r"//.*", "", open(os.path.join(REPO, p), encoding="utf-8").read())
