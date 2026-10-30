"""Bundle slice 1 (and the Tester's slice 1 fixes: group-share bands, rounding up, a floor of 10) (ARCHITECT-BUNDLE-DONTTRADE-TEST-2026-10-31 §2.2, §4, B7).

* "N more trades to tell" (wording.js moreTrades, power-table.js): only for a tested habit whose verdict is "could be
  luck"; never for "unlikely to be luck", facts-only habits, too_few or untested habits; N comes from the fixed
  moderate-pattern table, so two reports that differ only in the file's own gap print the same line; a table from
  another engine method is refused; the 1,000 cap and the "already" case; every new string passes the lint.
* The pay step's expectation line: in pay_facts (dialog and /pricing/), lint-clean, no digits, ≤ 14 words.
* B7: teaserText (a luck result next to the offer) is gone."""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text  # noqa: E402

JS = r"""
import { readFileSync } from 'node:fs';
const W = await import('./site/static/js/paid/wording.js');
const { POWER_TABLE } = await import('./site/static/js/paid/power-table.js');
const base = JSON.parse(readFileSync('site/config/sample-report.report.json', 'utf8'));
const clone = () => JSON.parse(JSON.stringify(base));
const out = {};
const by = (r, id) => r.habits.find((h) => h.id === id);
out.sample = Object.fromEntries(base.habits.map((h) => [h.id, W.moreTrades(h, base)]));
// the file's own gap never moves N
const a = clone(), b = clone();
by(b, 'tilt').effect = -50; by(b, 'tilt').measure_a = -60; by(b, 'tilt').dollars.amount = -9999;
out.same = JSON.stringify(W.moreTrades(by(a, 'tilt'), a)) === JSON.stringify(W.moreTrades(by(b, 'tilt'), b));
// a hand-made table: band 0 never reaches even odds, band 1 not simulated, band 2 reaches it at 170 trades
const N = POWER_TABLE.n;
const row = (p) => ({ share: [0, 1], power: p, worlds: ['x'], cells: {} });
const T = { ...POWER_TABLE, bands: { tilt: [[0, 0.15], [0.15, 0.25], [0.25, 0.35], [0.35, 0.5], [0.5, 1]] }, habits: { tilt: [
  row(N.map(() => 0.2)), row(null), row([0, 0, 0.25, 0.45, 0.6, 0.8, 0.9, 1, 1]), row(N.map(() => 1)), row(null)] } };
const at = (n, na, table = T) => { const r = clone(); r.n_trades = n; r.n_rows = n; by(r, 'tilt').n_a = na; return W.moreTrades(by(r, 'tilt'), r, undefined, table); };
out.even = W.tradesForEvenOdds(T.habits.tilt[2], T);
out.low = at(300, 30); out.unknown = at(300, 60); out.near = at(out.even - 1, Math.round(0.3 * (out.even - 1)));
out.small = at(120, 36); out.past = at(400, 120); out.high = at(120, 48);
out.share = [at(300, 30).line, at(300, 90).line];
// N never below the table's size, whatever the file size
out.floor = [];
for (let n = 40; n <= 2000; n += 7) { const m = at(n, Math.round(0.3 * n)); if (m.bar) out.floor.push([n, m.bar.of, m.bar.of - n]); }
try { W.moreTrades(by(base, 'tilt'), base, undefined, { ...POWER_TABLE, method_version: 'x' }); out.mismatch = 'no throw'; } catch (e) { out.mismatch = 'threw'; }
out.real = Object.fromEntries(Object.entries(POWER_TABLE.habits).map(([id, rows]) => [id, rows.map((r) => r.power)]));
out.strings = W.BUNDLE_STRINGS;
out.table = { mv: POWER_TABLE.method_version, k: POWER_TABLE.reference_effect_sd, bands: POWER_TABLE.bands.tilt.length };
out.method = W.METHOD_VERSION;
console.log(JSON.stringify(out));
"""


def run():
    r = subprocess.run(["node", "--input-type=module", "-e", JS], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def test_more_trades_rules():
    o = run()
    s = o["sample"]
    assert s["revenge"] is None                       # unlikely to be luck: no N
    assert s["hold_gap"] is None and s["size_up"] is None and s["oversized_loss"] is None
    assert s["tilt"] is not None
    assert o["same"] is True
    assert o["mismatch"] == "threw"
    assert o["table"] == {"mv": o["method"], "k": 0.5, "bands": 5}
    assert o["even"] == 170
    assert o["low"]["line"].startswith("More trades may not settle this.") and o["low"]["bar"] is None
    assert o["unknown"]["line"].startswith("We can’t say how many more trades") and o["unknown"]["bar"] is None
    assert o["near"]["line"] == "About 10 more trades would give this check even odds of telling a moderate pattern from luck."
    assert o["small"]["line"] == "About 50 more trades would give this check even odds of telling a moderate pattern from luck."
    assert o["small"]["bar"] == {"have": 120, "of": 170, "label": "120 of about 170 trades"}
    assert o["small"]["caveat"] == "Assumes your next trades look like these."
    assert o["past"]["line"].startswith("The 400 trades in this file already") and o["past"]["caveat"] is None
    assert o["high"]["line"].startswith("The 120 trades in this file already")   # share band 0.35-0.5 is at even odds from 40
    assert o["share"][0] != o["share"][1]             # same size, different share, different answer
    assert o["floor"] and all(of >= 170 and more >= 10 and more % 10 == 0 for _, of, more in o["floor"])


def test_real_table_is_monotone_and_banded():
    o = run()
    for id_, rows in o["real"].items():
        assert len(rows) == 5
        for p in rows:
            if p is not None:
                assert len(p) == 9 and all(p[i] <= p[i + 1] for i in range(8)), (id_, p)


def test_new_strings_lint_clean():
    for s in run()["strings"]:
        assert lint_text(s, "report/index.html", paid=True, analytics=True) == [], s


def test_pay_expectation_line():
    src = open(os.path.join(REPO, "site", "templates", "partials", "pay_facts.html"), encoding="utf-8").read()
    m = re.search(r'<p class="pay-expect small">([^<]+)</p>', src)
    assert m
    line = m.group(1)
    assert not re.search(r"\d", line)
    assert len(re.findall(r"[A-Za-z’']+", line)) <= 14
    assert "would tell" not in line   # Tester slice 1: the report gives even odds, not a promise
    assert lint_text(line, "pricing/index.html", paid=True, analytics=True) == []
    banned = ["advice", "recommend", "should", "fix", "coach", "must", "need to", "signal", "improve", "mentor", "certified",
              "verified", "audited", "seal"]
    assert not [w for w in banned if w in line.lower()]


def test_teaser_text_deleted():
    for p in ("site/static/js/tools/trade-stats-badges.js", "site/static/js/tools/trade-stats.js"):
        assert "teaserText" not in re.sub(r"//.*", "", open(os.path.join(REPO, p), encoding="utf-8").read())
