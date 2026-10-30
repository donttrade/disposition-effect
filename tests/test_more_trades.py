"""Bundle slice 1 (ARCHITECT-BUNDLE-DONTTRADE-TEST-2026-10-31 §2.2, §4, B7).

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
// small file: a bar with real counts
const s = clone(); s.n_trades = 120; s.n_rows = 120;
out.small = W.moreTrades(by(s, 'tilt'), s);
const t = { ...POWER_TABLE, habits: { ...POWER_TABLE.habits, tilt: { ...POWER_TABLE.habits.tilt, power: POWER_TABLE.n.map(() => 0.1) } } };
out.cap = W.moreTrades(by(s, 'tilt'), s, undefined, t);
try { W.moreTrades(by(s, 'tilt'), s, undefined, { ...POWER_TABLE, method_version: 'x' }); out.mismatch = 'no throw'; } catch (e) { out.mismatch = 'threw'; }
out.even = { revenge: W.tradesForEvenOdds('revenge'), tilt: W.tradesForEvenOdds('tilt') };
out.strings = W.BUNDLE_STRINGS;
out.table = { mv: POWER_TABLE.method_version, k: POWER_TABLE.reference_effect_sd };
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
    assert s["tilt"]["line"] == "The 304 trades in this file already give this check even odds of telling a moderate pattern from luck."
    assert s["tilt"]["bar"] is None and s["tilt"]["caveat"] == "Assumes your next trades look like these."
    assert o["same"] is True
    sm = o["small"]
    n = o["even"]["tilt"] - 120
    assert sm["line"] == f"About {n} more trades would give this check even odds of telling a moderate pattern from luck."
    assert sm["bar"] == {"have": 120, "of": o["even"]["tilt"], "label": f"120 of about {o['even']['tilt']} trades"}
    assert o["cap"]["line"].startswith("More than 1,000 more trades") and o["cap"]["bar"] is None
    assert o["mismatch"] == "threw"
    assert o["table"] == {"mv": o["method"], "k": 0.5}
    assert 40 <= o["even"]["tilt"] <= 2000 and 40 <= o["even"]["revenge"] <= 2000


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
    assert lint_text(line, "pricing/index.html", paid=True, analytics=True) == []
    banned = ["advice", "recommend", "should", "fix", "coach", "must", "need to", "signal", "improve", "mentor", "certified",
              "verified", "audited", "seal"]
    assert not [w for w in banned if w in line.lower()]


def test_teaser_text_deleted():
    for p in ("site/static/js/tools/trade-stats-badges.js", "site/static/js/tools/trade-stats.js"):
        assert "teaserText" not in re.sub(r"//.*", "", open(os.path.join(REPO, p), encoding="utf-8").read())
