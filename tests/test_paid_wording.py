"""Paid report wording (ARCHITECT-STATS-AMENDMENT-2026-10-21 section 7.1), site/static/js/paid/wording.js.

Every branch is filled from synthetic Report objects and must (a) read exactly as the amendment
gives it and (b) pass checks/lint.py with the current banned.toml (F-7 for the paid page)."""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text  # noqa: E402

JS = r"""
import * as W from './site/static/js/paid/wording.js';
const names = { hold_gap: 'Holding losers longer than winners', revenge: 'Re-entering soon after a loss',
  size_up: 'Size after a loss', tilt: 'Trading after a losing streak', oversized_loss: 'Losses much larger than your usual loss' };
const labels = { hold_gap: 'Losing trades held longer than your median winning hold', revenge: "Trades opened within 15 minutes of a losing trade's close",
  size_up: 'Trades after a loss at 1.5 times your usual size or more', tilt: 'Trades taken after 2 or more losses in a row', oversized_loss: 'Losses more than twice your median loss' };
const H = (id, o) => ({ id, name: names[id], n_a: 40, n_b: 90, measure_a: -12.5, measure_b: 3.25, effect: id === 'hold_gap' || id === 'size_up' ? 1.5 : -15.75,
  p_raw: 0.001, p_holm: 0.004, verdict: 'distinguishable', direction: 'habit', n_perm: 10000, n_a_compared: id === 'hold_gap' || id === 'size_up' ? 38 : null,
  n_b_compared: id === 'hold_gap' || id === 'size_up' ? 85 : null, dollars: { label: labels[id], amount: -500, n_trades: 40 }, ...o });
const R = (habits, o) => ({ n_tested: habits.filter((h) => h.p_raw !== null).length, n_distinguishable: habits.filter((h) => h.verdict === 'distinguishable').length,
  focus: null, habits: [...habits, H('oversized_loss', { verdict: 'descriptive', direction: null, p_raw: null, n_perm: null, method: null })], ...o });
const fmt = { money: (x) => (x < 0 ? '−$' + (-x).toFixed(2) : '$' + x.toFixed(2)), duration: (s) => Math.round(s / 60) + ' min', ratio: (x) => x.toFixed(2) };
const out = {};
const all = ['hold_gap', 'revenge', 'size_up', 'tilt'];
const rFocus = R(all.map((id) => H(id, id === 'revenge' ? {} : { verdict: 'not_distinguishable' })), { focus: 'revenge' });
out.focus = W.page1Lines(rFocus, fmt);
out.opp1 = W.page1Lines(R(all.map((id) => H(id, id === 'tilt' ? { direction: 'opposite', effect: 4 } : { verdict: 'not_distinguishable' }))), fmt);
out.opp2 = W.page1Lines(R(all.map((id) => H(id, id === 'tilt' || id === 'size_up' ? { direction: 'opposite' } : { verdict: 'not_distinguishable' }))), fmt);
out.uncovered = W.page1Lines(R(all.map((id) => H(id, id === 'revenge' ? { dollars: { label: labels[id], amount: 120, n_trades: 40 } } : { verdict: 'not_distinguishable' }))), fmt);
const gain = (id) => ({ dollars: { label: labels[id], amount: 120, n_trades: 40 } });
out.uncovered2 = W.page1Lines(R(all.map((id) => H(id, id === 'revenge' || id === 'tilt' ? gain(id) : { verdict: 'not_distinguishable' }))), fmt);
out.mixed = W.page1Lines(R(all.map((id) => H(id, id === 'revenge' ? gain(id) : id === 'tilt' ? { direction: 'opposite' } : { verdict: 'not_distinguishable' }))), fmt);
try { W.page1Lines(R(all.map((id) => H(id, id === 'revenge' ? {} : { verdict: 'not_distinguishable' }))), fmt); out.inconsistent = 'no error'; }
catch (e) { out.inconsistent = e.message; }
out.pending = [W.NO_LOSS_ONE, W.NO_LOSS_MANY];
out.none = W.page1Lines(R(all.map((id) => H(id, { verdict: 'not_distinguishable' }))), fmt);
const tf = R(all.map((id) => H(id, id === 'revenge' || id === 'size_up' ? { verdict: 'too_few', p_raw: null, p_holm: null, n_perm: null, n_a: 12, n_a_compared: id === 'size_up' ? 9 : null } : {})));
out.coverage = W.coverageLines(tf);
out.coverage4 = W.coverageLines(rFocus);
out.habit = {};
for (const h of tf.habits.slice(0, 4).concat(rFocus.habits.slice(0, 4)).concat(R(all.map((id) => H(id, { direction: 'opposite' }))).habits.slice(0, 4))) {
  (out.habit[h.id] = out.habit[h.id] || []).push(...W.habitSentences(h, tf, fmt));
  const m = W.methodLine(h); if (m) out.habit[h.id].push(m);
}
out.notdist = W.verdictSentence(H('tilt', { verdict: 'not_distinguishable' }), tf);
process.stdout.write(JSON.stringify(out));
"""


def sentences():
    r = subprocess.run(["node", "--input-type=module", "-e", JS], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def flat(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for v in x for s in flat(v)]
    return [s for v in x.values() for s in flat(v)]


def test_every_paid_sentence_passes_the_lint():
    texts = flat(sentences())
    assert len(texts) > 30
    for t in texts:
        assert lint_text(t) == [], (t, lint_text(t))


def test_page1_and_coverage_wording_is_the_amendments():
    s = sentences()
    assert s["focus"] == [
        "1 of the 4 patterns tested in this file is distinguishable from noise. Each verdict is adjusted for testing 4 "
        "patterns at once, so in files with no real pattern, at least one shows as distinguishable in about 1 report in 20 "
        "or fewer.",
        "Shown first: Re-entering soon after a loss. Trades opened within 15 minutes of a losing trade's close totalled "
        "−$500.00 (historical)."]
    assert s["opp1"][1] == "The distinguishable gap runs the opposite way to its pattern name, so no pattern is shown first."
    assert s["opp2"][0].startswith("2 of the 4 patterns tested in this file are distinguishable")
    assert s["opp2"][1] == "The distinguishable gaps run the opposite way to their pattern names, so no pattern is shown first."
    # PLAN CONFLICT §7.1 (pending Architect sign-off): a gap in the habit's own direction that did not
    # total a loss. The stats Coder's sentence, word for word; never the false "opposite way" line.
    assert s["uncovered"] == [s["focus"][0], "The distinguishable gap in this pattern's direction did not total a loss, so no "
                              "pattern is shown first."]
    assert s["uncovered2"][0].startswith("2 of the 4 patterns tested in this file are distinguishable")
    assert s["uncovered2"][1] == ("The distinguishable gaps in these patterns' directions did not total a loss, so no pattern "
                                  "is shown first.")
    assert s["mixed"][1] == s["uncovered"][1] and len(s["mixed"]) == 2
    assert "opposite way" not in " ".join(s["uncovered"] + s["uncovered2"] + s["mixed"])
    assert s["inconsistent"] == "page1Lines: focus is null but a habit-direction gap totalled a loss (D-6)"
    for t in s["pending"]:
        assert lint_text(t) == [] and lint_text(t, "pending", paid=True) == [], t
    assert s["none"] == ["No pattern in this file is distinguishable from noise.",
                         "That does not show the patterns are absent; it means this file cannot tell them apart from chance."]
    assert s["coverage"] == ["2 of the 4 patterns could be tested. Each one compares two groups of at least 30 trades.",
                             "Not tested: Re-entering soon after a loss, Size after a loss."]
    assert s["coverage4"] == ["4 of the 4 patterns could be tested. Each one compares two groups of at least 30 trades."]


def test_habit_wording_is_the_amendments():
    s = sentences()["habit"]
    assert s["revenge"][0] == ("Not enough trades to tell: this pattern compares two groups of at least 30 trades each, "
                               "and this file has 12 and 90.")
    assert s["size_up"][0] == ("Not enough trades to tell: this pattern compares two groups of at least 30 trades each, "
                               "counted on days that have both, and this file has 9 and 85.")
    assert s["hold_gap"][:3] == [
        "Your losing trades were held a median of 0 min; your winning trades a median of 0 min.",
        "This gap is distinguishable from noise, after adjusting for the 2 patterns tested.",
        "Compared within the same days: the labels were reshuffled within each day 10000 times to see how large a gap "
        "chance alone produces."]
    assert ("Trades opened within 15 minutes of a losing trade's close averaged −$12.50 per trade; your other trades "
            "averaged $3.25.") in s["revenge"]
    assert ("Compared with your other trades from the same days, matched on whether another trade had just closed: the "
            "results were reshuffled within each day 10000 times to see how large a gap chance alone produces.") in s["revenge"]
    assert ("Compared with your other trades from the same days: the results were reshuffled within each day 10000 times "
            "to see how large a gap chance alone produces.") in s["tilt"]
    assert "Your median size after a loss was 1.50× your median size after a win." in s["size_up"]
    assert ("This gap is distinguishable from noise, after adjusting for the 2 patterns tested. It runs the opposite way "
            "to this pattern's name.") in s["tilt"]
    assert sentences()["notdist"] == ("A gap this size is within what chance alone produces in files with no pattern, so "
                                      "this file cannot tell it apart from noise.")
