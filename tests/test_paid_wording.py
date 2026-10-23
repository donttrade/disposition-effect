"""Paid report wording R2 (ARCHITECT-STATS-AMENDMENT-R2-2026-10-21 sections 9.1-9.2), site/static/js/paid/wording.js.

W-1: every string, filled from synthetic and real (dt-private golden) reports, passes checks/lint.py in
plain and in paid mode. W-2: page 1 driven through the 9 truth-table cases of section 9.1 prints exactly
the ticked lines. The per-habit lines, the method lines and the percent format read exactly as 9.2 gives
them. NO_LOSS_ONE / NO_LOSS_MANY no longer exist (S-B2).

R-D2 (method 2026-10-23.stats2b): hold_gap is described, not tested. The 9 truth-table cases are re-based on
revenge, size_up and tilt; hold_gap is always withheld / not_calibrated and prints M1, V-launch and M3; any
other hold_gap state, a stats2 report, a forged hold_gap p or verdict throws."""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "paid-reports")

JS = r"""
import * as W from './site/static/js/paid/wording.js';
import { readFileSync, readdirSync } from 'node:fs';
const names = { hold_gap: 'Holding losers longer than winners', revenge: 'Re-entering soon after a loss',
  size_up: 'Size after a loss', tilt: 'Trading after a losing streak', oversized_loss: 'Losses much larger than your usual loss' };
const labels = { hold_gap: 'Losing trades held longer than your median winning hold', revenge: "Trades opened within 15 minutes of a losing trade's close",
  size_up: 'Trades after a loss at 1.5 times your usual size or more', tilt: 'Trades taken after 2 or more losses in a row', oversized_loss: 'Losses more than twice your median loss' };
const MED = ['hold_gap', 'size_up'];
// stats2b hold_gap (R-D2): withheld / not_calibrated, every test field null
const LAUNCH = { verdict: 'withheld', withheld: 'not_calibrated', p_raw: null, p_holm: null, n_perm: null, direction: null,
  share_a: null, share_b: null, n_a_compared: null, n_b_compared: null, spread_ratio: null };
const H = (id, o) => ({ id, name: names[id], n_a: 40, n_b: 90, measure_a: id === 'hold_gap' ? 5400 : id === 'size_up' ? 1.6 : -12.5,
  measure_b: id === 'hold_gap' ? 1800 : id === 'size_up' ? 1.0 : 3.25, effect: MED.includes(id) ? 1.5 : -15.75,
  p_raw: 0.001, p_holm: 0.004, verdict: 'distinguishable', direction: 'habit', n_perm: 10000,
  n_a_compared: MED.includes(id) ? 38 : null, n_b_compared: MED.includes(id) ? 85 : null,
  ...(id === 'hold_gap' ? { share_a: 0.61, share_b: 0.47, n_long_a: 0, n_long_b: 0, spread_ratio: 1.1, withheld: null } : {}),
  ...(id === 'size_up' ? { share: 0.58 } : {}), ...(id === 'revenge' || id === 'tilt' ? { p_mean: 0.001, p_rank: 0.0008 } : {}),
  dollars: { label: labels[id], amount: -500, n_trades: 40 }, ...o });
const ND = { verdict: 'not_distinguishable', p_raw: 0.4, p_holm: 1 };
const R = (over, o) => {
  const habits = [H('hold_gap', { ...LAUNCH, ...(over.hold_gap || {}) })].concat(W.TESTED.map((id) => H(id, over[id] || ND)))
    .concat([H('oversized_loss', { verdict: 'descriptive', direction: null, p_raw: null, p_holm: null, n_perm: null })]);
  return { method_version: W.METHOD_VERSION, n_tested: habits.filter((h) => h.p_raw !== null).length,
    n_distinguishable: habits.filter((h) => h.verdict === 'distinguishable').length, focus: null, habits, ...o };
};
const fmt = { money: (x) => (x < 0 ? '−$' + (-x).toFixed(2) : '$' + x.toFixed(2)), duration: (s) => Math.round(s / 60) + ' min', ratio: (x) => x.toFixed(2), count: (n) => n.toLocaleString('en-US') };
const run = (f) => { try { return f(); } catch (e) { return 'THROW: ' + e.message; } };
const out = { cases: {}, coverage: {}, habit: {}, method: {}, pct: {}, real: {}, exports: Object.keys(W).sort(), tested: W.TESTED, v_launch: W.V_LAUNCH };
const nodollar = (id) => ({ dollars: { label: labels[id], amount: 0, n_trades: 0 } });
const gain = (id) => ({ dollars: { label: labels[id], amount: 120, n_trades: 40 } });
const opp = { direction: 'opposite' };
// The 9 truth-table cases of section 9.1, re-based on revenge, size_up and tilt (R-D2); hold_gap is withheld
const C = {
  1: [{}],
  2: [{ revenge: {} }, { focus: 'revenge' }],
  3: [{ tilt: opp }],
  4: [{ size_up: nodollar('size_up') }],
  5: [{ revenge: gain('revenge') }],
  6: [{ size_up: { dollars: { label: labels.size_up, amount: -200, n_trades: 9 } }, revenge: {}, tilt: opp }, { focus: 'revenge' }],
  7: [{ revenge: gain('revenge'), size_up: nodollar('size_up'), tilt: opp }],
  8: [{ size_up: { direction: null } }],
};
for (const [k, [over, o]] of Object.entries(C)) {
  out.cases[k] = run(() => W.page1Lines(R(over, o), fmt));
  out.coverage[k] = run(() => W.coverageLines(R(over, o)));
}
const dirnull = JSON.parse(readFileSync('tests/fixtures/paid-reports/stats-r2__32-probe-dirnull.report.json', 'utf8'));
out.cases[9] = run(() => W.page1Lines(dirnull, fmt));
out.coverage[9] = run(() => W.coverageLines(dirnull));
out.case9_hold_gap = dirnull.habits[0].verdict + '/' + dirnull.habits[0].withheld;
// guards
out.guard_inconsistent = run(() => W.page1Lines(R({ revenge: {} }), fmt));
out.guard_count = run(() => W.page1Lines(R({ revenge: {} }, { focus: 'revenge', n_distinguishable: 2 }), fmt));
out.guard_method = run(() => W.page1Lines(R({}, { method_version: '2026-10-21.stats1' }), fmt));
out.guard_stats2 = run(() => W.page1Lines(R({}, { method_version: '2026-10-21.stats2' }), fmt));
out.guard_habit_dirnull = run(() => W.habitSentences(H('size_up', { direction: null }), R({}), fmt));
// R-D2: a forged hold_gap p or verdict throws on page 1, in the coverage lines and in every habit's lines
const forged = {
  p_raw: { p_raw: 0.001, p_holm: 0.003, n_perm: 10000 },
  distinguishable: { verdict: 'distinguishable', direction: 'habit', withheld: null, p_raw: 0.001, p_holm: 0.003, n_perm: 10000, share_a: 0.6, share_b: 0.4, n_a_compared: 40, n_b_compared: 80 },
  spread: { withheld: 'spread', spread_ratio: 1.9 },
  too_few: { verdict: 'too_few', withheld: null },
};
out.forged = {};
for (const [k, o] of Object.entries(forged)) {
  const rep = R({ hold_gap: o });
  rep.n_tested = rep.habits.filter((h) => h.p_raw !== null).length;
  rep.n_distinguishable = rep.habits.filter((h) => h.verdict === 'distinguishable').length;
  out.forged[k] = [run(() => W.page1Lines(rep, fmt)), run(() => W.coverageLines(rep)), run(() => W.habitSentences(rep.habits[0], rep, fmt)), run(() => W.habitSentences(rep.habits[1], rep, fmt))];
}
// per-habit lines
const r4 = R({});
const lines = (h) => run(() => W.habitSentences(h, r4, fmt));
out.habit.hold_launch = lines(H('hold_gap', LAUNCH));
out.habit.hold_launch_m3 = lines(H('hold_gap', { ...LAUNCH, n_long_a: 3, n_long_b: 5 }));
out.habit.hold_launch_nomed = lines(H('hold_gap', { ...LAUNCH, measure_b: null }));
// the stats2 hold_gap lines (Option B) are unreachable under stats2b: each input throws
out.habit.hold_dist = lines(H('hold_gap', {}));
out.habit.hold_spread = lines(H('hold_gap', { verdict: 'withheld', withheld: 'spread', spread_ratio: 1.8974358974358976, p_raw: null, p_holm: null, n_perm: null, direction: null, n_long_a: 2, n_long_b: 0 }));
out.habit.hold_spread0 = lines(H('hold_gap', { verdict: 'withheld', withheld: 'spread', spread_ratio: null, p_raw: null, p_holm: null, n_perm: null, direction: null }));
out.habit.hold_few = lines(H('hold_gap', { verdict: 'too_few', p_raw: null, p_holm: null, n_perm: null, direction: null, n_a_compared: 9, n_b_compared: 6, share_a: 0.5, share_b: 0.6 }));
out.habit.size_dist = lines(H('size_up', {}));
out.habit.size_no = lines(H('size_up', { ...ND, share: 0.5 }));
out.habit.size_few = lines(H('size_up', { verdict: 'too_few', p_raw: null, p_holm: null, n_perm: null, direction: null, n_a_compared: 15, n_b_compared: 8 }));
out.habit.rev_dist = lines(H('revenge', {}));
out.habit.rev_few = lines(H('revenge', { verdict: 'too_few', p_raw: null, p_holm: null, n_perm: null, n_a: 12 }));
out.habit.tilt_opp = lines(H('tilt', { direction: 'opposite' }));
for (const id of W.SENTENCE_HABITS) out.method[id] = W.methodLine(H(id, { n_perm: 5000 }), fmt);
out.method.none = W.methodLine(H('hold_gap', LAUNCH), fmt);
// percent format
out.pct.pair = [W.sharePair(0.5243464052287582, 0.5), W.sharePair(0.52441, 0.52449), W.sharePair(0.524441, 0.524449), W.sharePair(0.5244441, 0.5244449), W.sharePair(0.6, 0.6)];
out.pct.one = [W.shareOne(0.5), W.shareOne(0.58), W.shareOne(0.5002), W.shareOne(0.50002), W.shareOne(0.499996)];
// the real reports (dt-private goldens): page 1, every habit's lines and method line
for (const f of readdirSync('tests/fixtures/paid-reports').filter((x) => x.endsWith('.report.json')).sort()) {
  const rep = JSON.parse(readFileSync('tests/fixtures/paid-reports/' + f, 'utf8'));
  out.real[f] = run(() => ({ method_version: rep.method_version, page1: W.page1Lines(rep, fmt), coverage: W.coverageLines(rep),
    habits: Object.fromEntries(rep.habits.filter((h) => W.SENTENCE_HABITS.includes(h.id)).map((h) => [h.id, [...W.habitSentences(h, rep, fmt), W.methodLine(h, fmt)].filter(Boolean)])) }));
}
process.stdout.write(JSON.stringify(out));
"""


def data():
    if not hasattr(data, "cache"):
        r = subprocess.run(["node", "--input-type=module", "-e", JS], cwd=REPO, capture_output=True, text=True, check=True)
        data.cache = json.loads(r.stdout)
    return data.cache


def flat(x):
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for v in x for s in flat(v)]
    if isinstance(x, dict):
        return [s for v in x.values() for s in flat(v)]
    return []


H1 = ("{k} of the {n} patterns tested in this file {v} distinguishable from noise. Each verdict is adjusted for testing {n} "
      "patterns at once. In our tests on files built to have no real pattern, at least one pattern showed as "
      "distinguishable in about 1 report in 20 or fewer.")
H0 = ["No pattern in this file is distinguishable from noise.",
      "That does not show the patterns are absent; it means this file cannot tell them apart from chance."]
N0 = ("No pattern is shown first. A pattern is shown first only when its gap is distinguishable from noise, runs the way "
      "its name describes, and its dollar figure is a loss.")


# R-D2 H-2 exact texts
V_LAUNCH = ("Not tested in this version of the report. In our tests on files built to have no real pattern, this test reported "
            "a gap in more than 1 file in 20, the rate it is designed for, when a large win or loss changed how long the next "
            "trades were held. So this pattern is described here without a verdict.")
HG_LINE = "Holding losers longer than winners is described, not tested, in this version of the report."
COV3 = "3 of the 3 patterns could be tested. Each one compares two groups of at least 30 trades."


def test_w1_every_string_passes_the_lint_plain_and_paid():
    d = data()
    texts = [t for t in flat({k: v for k, v in d.items() if k not in ("exports", "case9_hold_gap", "tested")})
             if not t.startswith("THROW:") and not t.startswith("2026-10-2") and not t.endswith(".report.json")]
    assert V_LAUNCH in texts and HG_LINE in texts
    assert len(texts) > 60
    for t in texts:
        assert lint_text(t) == [], (t, lint_text(t))
        assert lint_text(t, "paid-report", paid=True) == [], (t, lint_text(t, "paid-report", paid=True))


def test_w2_page1_truth_table_prints_exactly_the_ticked_lines():
    c = data()["cases"]
    assert data()["tested"] == ["revenge", "size_up", "tilt"]
    assert c["1"] == H0                                                              # case 1: H0a, H0b
    assert c["2"] == [H1.format(k=1, v="is", n=3),                                  # case 2: H1, F
                      "Shown first: Re-entering soon after a loss. Trades opened within 15 minutes of a losing trade's close "
                      "totalled −$500.00 (historical)."]
    assert c["3"] == [H1.format(k=1, v="is", n=3), N0,                                   # case 3: H1, N0, N-opp
                      "Trading after a losing streak: trades taken after 2 or more losses in a row did better than your other "
                      "trades, the other way round from the pattern's name."]
    assert c["4"] == [H1.format(k=1, v="is", n=3), N0,                                   # case 4: H1, N0, N-none
                      "Size after a loss: within groups of comparable trades, size after a loss was larger than size after a "
                      "win, but no trade in this file is in its dollar figure (trades after a loss at 1.5 times your usual "
                      "size or more)."]
    assert c["5"] == [H1.format(k=1, v="is", n=3), N0,                                   # case 5: H1, N0, N-gain
                      "Re-entering soon after a loss: trades opened within 15 minutes of a losing trade's close did worse than "
                      "your other trades, but its dollar figure (trades opened within 15 minutes of a losing trade's close) "
                      "totalled $120.00 (historical), which is not a loss."]
    assert c["6"] == [H1.format(k=3, v="are", n=3),                                 # case 6: H1, F (the most negative)
                      "Shown first: Re-entering soon after a loss. Trades opened within 15 minutes of a losing trade's close "
                      "totalled −$500.00 (historical)."]
    assert c["7"] == [H1.format(k=3, v="are", n=3), N0,                             # case 7: one line per habit, fixed order
                      "Re-entering soon after a loss: trades opened within 15 minutes of a losing trade's close did worse than "
                      "your other trades, but its dollar figure (trades opened within 15 minutes of a losing trade's close) "
                      "totalled $120.00 (historical), which is not a loss.",
                      "Size after a loss: within groups of comparable trades, size after a loss was larger than size after a "
                      "win, but no trade in this file is in its dollar figure (trades after a loss at 1.5 times your usual "
                      "size or more).",
                      "Trading after a losing streak: trades taken after 2 or more losses in a row did better than your other "
                      "trades, the other way round from the pattern's name."]
    assert c["8"] == "THROW: page1Lines: size_up is distinguishable with direction null (R2-3)"   # case 8: throw
    # case 9: the Tester's S-B2 file, now on stats2b: hold_gap withheld; page 1 follows cases 1-7 for the others (case 1)
    assert data()["case9_hold_gap"] == "withheld/not_calibrated" and c["9"] == H0
    # every stats2b page 1 carries the fixed hold-gap line exactly once (the coverage block follows the headline)
    cov = data()["coverage"]
    for k in [str(i) for i in range(1, 10) if i != 8]:
        page1 = c[k] + cov[k]
        assert page1.count(HG_LINE) == 1 and cov[k][-1] == HG_LINE, k
        assert cov[k][0].endswith(" of the 3 patterns could be tested. Each one compares two groups of at least 30 trades."), k
    assert cov["1"] == [COV3, HG_LINE]
    assert cov["9"] == ["1 of the 3 patterns could be tested. Each one compares two groups of at least 30 trades.",
                        "Not tested: Size after a loss, Trading after a losing streak.", HG_LINE]


def test_page1_guards_throw_instead_of_printing():
    d = data()
    assert d["guard_inconsistent"] == "THROW: page1Lines: focus is null but a habit-direction gap totalled a loss"
    assert d["guard_count"].startswith("THROW: page1Lines: n_distinguishable 2 but 1")
    assert d["guard_method"] == "THROW: wording: report method 2026-10-21.stats1 is not 2026-10-23.stats2b"
    assert d["guard_stats2"] == "THROW: wording: report method 2026-10-21.stats2 is not 2026-10-23.stats2b"
    assert d["guard_habit_dirnull"] == "THROW: wording: size_up is distinguishable with direction null (R2-3)"


def test_r_d2_forged_hold_gap_throws_everywhere():
    """H-2 acceptance 4 (the wording half; the page half is test_report_error_line.py): a stats2b report whose
    hold_gap has a p, a verdict, or the spread rule's withhold prints nothing."""
    f = data()["forged"]
    assert sorted(f) == ["distinguishable", "p_raw", "spread", "too_few"]
    for k, outs in f.items():
        assert len(outs) == 4
        for o in outs:
            assert isinstance(o, str) and o.startswith("THROW: wording: hold_gap is ") and o.endswith(
                "but it is not tested in 2026-10-23.stats2b (R-D2)"), (k, o)


def test_s_b2_the_pending_sentences_are_gone():
    assert "NO_LOSS_ONE" not in data()["exports"] and "NO_LOSS_MANY" not in data()["exports"]
    for path in glob.glob(os.path.join(REPO, "site", "**", "*.*"), recursive=True):
        if path.endswith((".js", ".html", ".toml", ".py")):
            s = open(path, encoding="utf-8", errors="replace").read()
            assert "NO_LOSS_ONE" not in s and "did not total a loss, so no pattern is shown first" not in s, path


M1 = "Your losing trades were held a median of 90 min; your winning trades a median of 30 min."
VH = "This gap is distinguishable from noise, after adjusting for the 3 patterns tested."
VNO = ("A gap this size is within what chance alone produces in files with no pattern, so this file cannot tell it apart "
       "from noise.")


def test_hold_gap_lines_are_the_ruling_r_d2():
    h = data()["habit"]
    # M1, then V-launch, then M3 only when a trade was held 12 hours or more
    assert h["hold_launch"] == [M1, V_LAUNCH]
    assert h["hold_launch_m3"] == [M1, V_LAUNCH,
                                   "Held 12 hours or more: 3 of your 40 losing trades and 5 of your 90 winning trades. This count "
                                   "is not part of the test: trades held 12 hours or more are only compared with each other."]
    assert h["hold_launch_nomed"] == [V_LAUNCH]
    assert data()["v_launch"] == V_LAUNCH
    # the stats2 lines (M2, the verdict, V-spread, V-spread0, V-few) stay in the code for Option B but are unreachable
    for k in ("hold_dist", "hold_spread", "hold_spread0", "hold_few"):
        assert isinstance(h[k], str) and h[k].startswith("THROW: wording: hold_gap is ") and h[k].endswith("(R-D2)"), (k, h[k])


def test_size_up_and_sequence_lines_are_the_amendments():
    h = data()["habit"]
    assert h["size_dist"] == ["Your median size after a loss was 1.50× your median size after a win.",
                              "Compared with trades after a win in the same group of comparable trades, a trade after a loss had "
                              "the larger size rank in 58.0% of pairs; 50% would mean no difference.", VH]
    assert h["size_no"][1].endswith("the larger size rank in 50% of pairs; 50% would mean no difference.") and h["size_no"][2] == VNO
    assert h["size_few"] == ["Your median size after a loss was 1.50× your median size after a win.",
                             "Not enough trades to tell: trades after a loss and trades after a win are compared only within groups "
                             "of comparable trades, and only 15 and 8 of them share a group with the other kind; the test needs at "
                             "least 30 of each."]
    assert h["rev_dist"] == ["Trades opened within 15 minutes of a losing trade's close averaged −$12.50 per trade; your other "
                             "trades averaged $3.25.", VH]
    assert h["rev_few"] == ["Not enough trades to tell: this pattern compares two groups of at least 30 trades each, and this file "
                            "has 12 and 90."]
    assert h["tilt_opp"] == ["Trades taken after 2 or more losses in a row averaged −$12.50 per trade; your other trades averaged "
                             "$3.25.", VH + " It runs the opposite way to this pattern's name."]


def test_method_lines_are_the_amendments():
    m = data()["method"]
    assert m["hold_gap"] == ("How this is compared: each trade's hold is first ranked against the 20 trades of the same symbol, "
                             "holding period (under or over 12 hours) and direction opened nearest to it in time of day on other "
                             "days. It is then compared with up to 8 such trades opened just before it on the same day, with no "
                             "break in the file's trading hours between them. Win and loss labels were reshuffled within groups "
                             "of about 8 neighbouring trades 5,000 times to see how large a gap chance alone produces.")
    assert m["size_up"] == ("How this is compared: each trade's size is first ranked against the 20 trades of the same symbol, "
                            "holding period (under or over 12 hours) and direction opened nearest to it in time of day on other "
                            "days. Groups of comparable trades are then about 8 such trades opened on the same day with no break "
                            "in the file's trading hours between them. The labels were reshuffled within each group 5,000 times "
                            "to see how large a gap chance alone produces.")
    assert m["revenge"] == ("Compared with your other trades from the same day, matched on whether another trade had closed in "
                            "the 15 minutes before it opened and whether another trade opened in the 15 minutes after it closed. "
                            "The results were reshuffled within each day 5,000 times (days with a single trade are grouped with "
                            "nearby such days). The gap counts as distinguishable only when both the average result and how "
                            "often a result was the worse one are distinguishable, in the same direction.")
    assert m["tilt"] == ("Compared with your other trades from the same day. The results were reshuffled within each day 5,000 "
                         "times (days with a single trade are grouped with nearby such days). The gap counts as distinguishable "
                         "only when both the average result and how often a result was the worse one are distinguishable, in "
                         "the same direction.")
    assert m["none"] is None


def test_percent_format():
    p = data()["pct"]
    # 1 decimal; 2 then 3 while the two print the same but differ; section 9.2 stops at 3 decimals
    assert p["pair"] == [["52.4%", "50.0%"], ["52.44%", "52.45%"], ["52.444%", "52.445%"], ["52.444%", "52.444%"], ["60.0%", "60.0%"]]
    assert p["one"] == ["50%", "58.0%", "50.02%", "50.002%", "50.000%"]


# R-D1 D-1: the exact V-spread0 text (the rank position, not hold lengths).
V_SPREAD0 = ("Not tested: the middle half of your losing trades, or of your winning trades, all sit at the same relative position "
             "when each trade's hold is ranked among trades of the same symbol, holding period and direction. This test cannot "
             "tell a gap in hold apart from a difference in how spread out the holds are.")


def test_r_d2_supersedes_d1_the_sizeup0_probe_renders_v_launch():
    """R-D2.2: the D-1 item "33-probe-sizeup0 renders V-spread0" is superseded; that fixture now renders V-launch."""
    real = data()["real"]
    for f in ("stats-r2__33-probe-sizeup0.report.json", "stats__02-spread-trend_right_skew-200.report.json"):
        lines = real[f]["habits"]["hold_gap"]
        assert V_LAUNCH in lines, (f, lines)
        assert V_SPREAD0 not in lines and not any("spread very differently" in s for s in lines), (f, lines)
        assert not any("same length" in s for s in lines)
    for paid in (False, True):   # V-spread0 stays for Option B and still passes the lint
        assert lint_text(V_SPREAD0, "V-spread0", paid=paid) == []
        assert lint_text(V_LAUNCH, "V-launch", paid=paid) == [] and lint_text(HG_LINE, "hg-line", paid=paid) == []


def test_cross_repo_reports_render_without_a_throw_and_are_method_stats2b():
    real = data()["real"]
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(FIX, "*.report.json")))
    assert len(files) >= 3 and sorted(real) == files
    for f, r in real.items():
        assert isinstance(r, dict), (f, r)                     # no throw
        assert r["method_version"] == "2026-10-23.stats2b", f
        assert r["coverage"].count(HG_LINE) == 1 and r["habits"]["hold_gap"].count(V_LAUNCH) == 1, f
        assert not any("reshuffled" in s for s in r["habits"]["hold_gap"]), f   # no hold_gap method line
    # random.json's hold_gap was the stats2 focus (case 2); under stats2b nothing is distinguishable (case 1)
    assert real["random.report.json"]["page1"] == H0
    assert real["random.report.json"]["coverage"] == ["2 of the 3 patterns could be tested. Each one compares two groups of "
                                                      "at least 30 trades.", "Not tested: Re-entering soon after a loss.", HG_LINE]
    s4 = real["stats-r2__33-probe-sizeup0.report.json"]
    assert s4["page1"][0] == H1.format(k=1, v="is", n=2)
    assert s4["page1"][1] == N0 and s4["page1"][2].startswith("Size after a loss: within groups of comparable trades, size after a "
                                                              "loss was larger than size after a win, but no trade in this file")
    assert s4["habits"]["hold_gap"][-1] == V_LAUNCH
    pr = real["planted_revenge.report.json"]["page1"]
    assert pr[0] == H1.format(k=2, v="are", n=3) and pr[1].startswith("Shown first: Re-entering soon after a loss.")
    assert real["stats-r2__32-probe-dirnull.report.json"]["page1"] == H0
