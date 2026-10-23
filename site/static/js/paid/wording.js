// wording.js — the paid report's sentences, exactly as ARCHITECT-STATS-AMENDMENT-R2-2026-10-21 §9.1–9.2
// gives them (page 1, the per-habit lines, the method lines and the percent format), filled from
// Report / Habit fields of the R2 engine (method 2026-10-23.stats2b: Architect ruling R-D2, hold_gap is
// described, not tested, so it is always withheld / not_calibrated and V-launch replaces M2 and the
// verdict; the V-spread, V-spread0, V-few and M2 hold_gap lines stay for Option B, unreachable under
// stats2b). No DOM, no I/O: report.js
// renders them. Every sentence describes the file's past trades only, is printed only when its
// condition holds, and passes checks/lint.py (tests/test_paid_wording.py, W-1 and W-2).
//
// fmt: { money(x), duration(seconds), ratio(x), count(n) } — the page passes its own formatters
// (money as report.js formats it now); the defaults are plain, for tests.

export const METHOD_VERSION = '2026-10-23.stats2b';
// V-launch (R-D2 H-2, exact text): hold_gap under stats2b. Replaces M2 and the verdict.
export const V_LAUNCH = 'Not tested in this version of the report. In our tests on files built to have no real pattern, this test reported a gap in more than 1 file in 20, the rate it is designed for, when a large win or loss changed how long the next trades were held. So this pattern is described here without a verdict.';
// The fixed page-1 line (R-D2 H-2), on every stats2b report.
export const HOLD_GAP_COVERAGE = 'Holding losers longer than winners is described, not tested, in this version of the report.';
// V-spread0 (R-D1 D-1): hold_gap withheld for spread with spread_ratio null (an infinite ratio). Replaces M2 and the verdict.
export const V_SPREAD0 = "Not tested: the middle half of your losing trades, or of your winning trades, all sit at the same relative position when each trade's hold is ranked among trades of the same symbol, holding period and direction. This test cannot tell a gap in hold apart from a difference in how spread out the holds are.";

const DEFAULT_FMT = {
  money: (x) => String(x),
  duration: (s) => `${s} s`,
  ratio: (x) => x.toFixed(2),
  count: (n) => String(n),
};

// The habits a stats2b report can test (R-D2: hold_gap is not one of them), and the habits shown with
// sentences under their heading (hold_gap's are M1, V-launch and M3).
export const TESTED = Object.freeze(['revenge', 'size_up', 'tilt']);
export const SENTENCE_HABITS = Object.freeze(['hold_gap', 'revenge', 'size_up', 'tilt']);

function fmtOf(fmt) {
  return { ...DEFAULT_FMT, ...(fmt || {}) };
}

// The report must come from the engine these sentences describe: an older report would be described
// with the wrong comparison ("similar trades opened just before it"), so it is refused.
export function checkMethod(report) {
  if (!report || report.method_version !== METHOD_VERSION) {
    throw new Error(`wording: report method ${report && report.method_version} is not ${METHOD_VERSION}`);
  }
}

// R-D2: under stats2b hold_gap is never tested. Any other hold_gap state (a p-value, a verdict, the spread
// rule) means the report is not what these sentences describe, so nothing is printed.
export function checkHoldGap(report) {
  const h = report && Array.isArray(report.habits) ? report.habits.find((x) => x.id === 'hold_gap') : null;
  if (!h) throw new Error('wording: the report has no hold_gap entry');
  if (h.verdict !== 'withheld' || h.withheld !== 'not_calibrated' || h.p_raw !== null || h.p_holm !== null || h.n_perm !== null) {
    throw new Error(`wording: hold_gap is ${h.verdict}/${h.withheld} with p_raw ${h.p_raw}, but it is not tested in ${METHOD_VERSION} (R-D2)`);
  }
}

// Everything renderReport() needs to be true before it shows anything.
export function checkReport(report) {
  checkMethod(report);
  checkHoldGap(report);
}

// ---------------------------------------------------------------- percent format (§9.2)

const pct = (x, dp) => (100 * x).toFixed(dp);

// {share_a%} and {share_b%}: 1 decimal; if the two print the same while the values differ, 2, then 3.
export function sharePair(a, b) {
  for (const dp of [1, 2, 3]) {
    const pa = pct(a, dp), pb = pct(b, dp);
    if (pa !== pb || a === b || dp === 3) return [pa + '%', pb + '%'];
  }
  throw new Error('unreachable');
}

// {share%}: exactly 0.5 prints "50%"; else 1 decimal, and 2 then 3 while it would print "50.0" (etc.).
export function shareOne(s) {
  if (s === 0.5) return '50%';
  for (const dp of [1, 2, 3]) {
    const p = pct(s, dp);
    if (Number(p) !== 50 || dp === 3) return p + '%';
  }
  throw new Error('unreachable');
}

// ---------------------------------------------------------------- per-habit lines (§9.2)

const V_HAB = (n) => `This gap is distinguishable from noise, after adjusting for the ${n} patterns tested.`;
const V_OPP = (n) => `${V_HAB(n)} It runs the opposite way to this pattern's name.`;
export const V_NO = 'A gap this size is within what chance alone produces in files with no pattern, so this file cannot tell it apart from noise.';

// The verdict line of a tested habit (distinguishable / not distinguishable), any habit.
function verdictLine(h, report) {
  if (h.verdict === 'distinguishable') {
    if (h.direction === 'habit') return V_HAB(report.n_tested);
    if (h.direction === 'opposite') return V_OPP(report.n_tested);
    throw new Error(`wording: ${h.id} is distinguishable with direction ${h.direction} (R2-3)`);
  }
  if (h.verdict === 'not_distinguishable') return V_NO;
  throw new Error(`wording: ${h.id} has no verdict line for ${h.verdict}`);
}

function needCounts(h) {
  if (!Number.isInteger(h.n_a_compared) || !Number.isInteger(h.n_b_compared)) throw new Error(`wording: ${h.id} ${h.verdict} without compared counts`);
}

function holdGapLines(h, report, f) {
  const out = [];
  if (h.measure_a !== null && h.measure_b !== null) {
    out.push(`Your losing trades were held a median of ${f.duration(h.measure_a)}; your winning trades a median of ${f.duration(h.measure_b)}.`);   // M1
  }
  if (h.verdict === 'withheld' && h.withheld === 'not_calibrated') {
    out.push(V_LAUNCH);   // R-D2 (stats2b): replaces M2 and the verdict
  } else if (h.verdict === 'withheld') {
    if (h.withheld !== 'spread') throw new Error(`wording: hold_gap withheld for ${h.withheld}`);
    // V-spread (replaces M2 and the verdict). spread_ratio is null when the ratio is infinite: one
    // group's middle half of holds (or both groups') has no spread at all. "Spread very differently"
    // would then be false when both have none, so that case has its own sentence (V-spread0, text fixed by
    // the Architect's ruling R-D1.1 / D-1: the spread is of each hold's rank inside its symbol x holding
    // period x direction group, so the sentence speaks of that rank, never of equal hold lengths).
    if (h.spread_ratio === null) {
      out.push(V_SPREAD0);
    } else {
      out.push(`Not tested: the holds of your losing and winning trades are spread very differently (the middle half of one group covers ${h.spread_ratio.toFixed(1)}× the range of the other's), and this test cannot tell a gap in hold apart from that difference.`);
    }
  } else if (h.verdict === 'too_few') {
    needCounts(h);
    out.push(`Not enough trades to tell: each trade is compared only with similar trades opened just before it, and only ${h.n_a_compared} losing and ${h.n_b_compared} winning trades have such a comparison in a group holding both kinds; the test needs at least 30 of each.`);   // V-few
  } else if (h.share_a !== null && h.share_b !== null && h.p_raw !== null) {
    const [a, b] = sharePair(h.share_a, h.share_b);
    out.push(`Compared with similar trades opened just before it, a losing trade's hold came out longer in ${a} of comparisons; a winning trade's in ${b}. With no link between hold and outcome, the two figures would be about equal.`);   // M2
  }
  if (h.n_long_a + h.n_long_b >= 1) {
    out.push(`Held 12 hours or more: ${h.n_long_a} of your ${h.n_a} losing trades and ${h.n_long_b} of your ${h.n_b} winning trades. This count is not part of the test: trades held 12 hours or more are only compared with each other.`);   // M3
  }
  if (h.verdict === 'distinguishable' || h.verdict === 'not_distinguishable') out.push(verdictLine(h, report));
  return out;
}

function sizeUpLines(h, report, f) {
  const out = [];
  if (h.effect !== null) out.push(`Your median size after a loss was ${f.ratio(h.effect)}× your median size after a win.`);   // M1
  if (h.verdict === 'too_few') {
    needCounts(h);
    out.push(`Not enough trades to tell: trades after a loss and trades after a win are compared only within groups of comparable trades, and only ${h.n_a_compared} and ${h.n_b_compared} of them share a group with the other kind; the test needs at least 30 of each.`);   // V-few
    return out;
  }
  if (h.share !== null && h.p_raw !== null) {
    out.push(`Compared with trades after a win in the same group of comparable trades, a trade after a loss had the larger size rank in ${shareOne(h.share)} of pairs; 50% would mean no difference.`);   // M2
  }
  out.push(verdictLine(h, report));
  return out;
}

// revenge and tilt keep R1's sentences (§9.2).
function seqLines(h, report, f) {
  if (h.verdict === 'too_few') return [`Not enough trades to tell: this pattern compares two groups of at least 30 trades each, and this file has ${h.n_a} and ${h.n_b}.`];
  const m = h.id === 'revenge'
    ? `Trades opened within 15 minutes of a losing trade's close averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`
    : `Trades taken after 2 or more losses in a row averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`;
  return [m, verdictLine(h, report)];
}

// Every line of a tested habit as shown under its heading, in order.
export function habitSentences(h, report, fmt) {
  checkHoldGap(report);
  if (h.id === 'hold_gap') checkHoldGap({ habits: [h] });
  const f = fmtOf(fmt);
  switch (h.id) {
    case 'hold_gap': return holdGapLines(h, report, f);
    case 'size_up': return sizeUpLines(h, report, f);
    case 'revenge': case 'tilt': return seqLines(h, report, f);
    default: throw new Error(`habitSentences: ${h.id} is not a tested habit`);
  }
}

// The method line (small text under each tested habit that has a p). {n_perm} is the habit's own
// permutation count (it scales with the file size), never a fixed number.
export function methodLine(h, fmt) {
  if (h.n_perm === null || h.n_perm === undefined) return null;
  const n = fmtOf(fmt).count(h.n_perm);
  switch (h.id) {
    case 'hold_gap': return `How this is compared: each trade's hold is first ranked against the 20 trades of the same symbol, holding period (under or over 12 hours) and direction opened nearest to it in time of day on other days. It is then compared with up to 8 such trades opened just before it on the same day, with no break in the file's trading hours between them. Win and loss labels were reshuffled within groups of about 8 neighbouring trades ${n} times to see how large a gap chance alone produces.`;
    case 'size_up': return `How this is compared: each trade's size is first ranked against the 20 trades of the same symbol, holding period (under or over 12 hours) and direction opened nearest to it in time of day on other days. Groups of comparable trades are then about 8 such trades opened on the same day with no break in the file's trading hours between them. The labels were reshuffled within each group ${n} times to see how large a gap chance alone produces.`;
    case 'revenge': return `Compared with your other trades from the same day, matched on whether another trade had closed in the 15 minutes before it opened and whether another trade opened in the 15 minutes after it closed. The results were reshuffled within each day ${n} times (days with a single trade are grouped with nearby such days). The gap counts as distinguishable only when both the average result and how often a result was the worse one are distinguishable, in the same direction.`;
    case 'tilt': return `Compared with your other trades from the same day. The results were reshuffled within each day ${n} times (days with a single trade are grouped with nearby such days). The gap counts as distinguishable only when both the average result and how often a result was the worse one are distinguishable, in the same direction.`;
    default: throw new Error(`methodLine: ${h.id} is not a tested habit`);
  }
}

// ---------------------------------------------------------------- page 1 (§9.1)

export const CLAUSES = Object.freeze({
  hold_gap: ['losing trades were held longer than winning trades, each compared with similar trades opened just before it',
    'losing trades were held shorter than winning trades, each compared with similar trades opened just before it'],
  revenge: ["trades opened within 15 minutes of a losing trade's close did worse than your other trades",
    "trades opened within 15 minutes of a losing trade's close did better than your other trades"],
  size_up: ['within groups of comparable trades, size after a loss was larger than size after a win',
    'within groups of comparable trades, size after a loss was smaller than size after a win'],
  tilt: ['trades taken after 2 or more losses in a row did worse than your other trades',
    'trades taken after 2 or more losses in a row did better than your other trades'],
});

const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);

// Page 1: the headline lines (H0a/H0b, or H1 then F, or H1, N0 and one reason line per
// distinguishable habit). Throws on an inconsistent report rather than print a false line.
export function page1Lines(report, fmt) {
  checkReport(report);
  const f = fmtOf(fmt);
  const D = TESTED.map((id) => report.habits.find((h) => h.id === id)).filter((h) => h && h.verdict === 'distinguishable');
  for (const h of D) if (h.direction !== 'habit' && h.direction !== 'opposite') throw new Error(`page1Lines: ${h.id} is distinguishable with direction ${h.direction} (R2-3)`);
  const k = D.length, n = report.n_tested;
  if (report.n_distinguishable !== k) throw new Error(`page1Lines: n_distinguishable ${report.n_distinguishable} but ${k} habits are distinguishable`);
  if (k === 0) {
    if (report.focus !== null) throw new Error('page1Lines: a focus with no distinguishable habit');
    return ['No pattern in this file is distinguishable from noise.',                                                  // H0a
      'That does not show the patterns are absent; it means this file cannot tell them apart from chance.'];     // H0b
  }
  const lines = [`${k} of the ${n} patterns tested in this file ${k === 1 ? 'is' : 'are'} distinguishable from noise. Each verdict is adjusted for testing ${n} patterns at once. In our tests on files built to have no real pattern, at least one pattern showed as distinguishable in about 1 report in 20 or fewer.`];   // H1
  if (report.focus !== null) {
    const h = D.find((x) => x.id === report.focus);
    if (!h) throw new Error(`page1Lines: focus ${report.focus} is not a distinguishable habit`);
    if (!(h.direction === 'habit' && h.dollars.amount < 0)) throw new Error(`page1Lines: focus ${h.id} is not a loss in the habit's own direction`);
    lines.push(`Shown first: ${h.name}. ${h.dollars.label} totalled ${f.money(h.dollars.amount)} (historical).`);   // F
    return lines;
  }
  if (D.some((h) => h.direction === 'habit' && h.dollars.n_trades >= 1 && h.dollars.amount < 0)) {
    throw new Error('page1Lines: focus is null but a habit-direction gap totalled a loss');
  }
  lines.push('No pattern is shown first. A pattern is shown first only when its gap is distinguishable from noise, runs the way its name describes, and its dollar figure is a loss.');   // N0
  for (const h of D) {
    const [habitClause, oppClause] = CLAUSES[h.id];
    const label = lowerFirst(h.dollars.label);
    if (h.direction === 'opposite') lines.push(`${h.name}: ${oppClause}, the other way round from the pattern's name.`);   // N-opp
    else if (h.dollars.n_trades === 0) lines.push(`${h.name}: ${habitClause}, but no trade in this file is in its dollar figure (${label}).`);   // N-none
    else lines.push(`${h.name}: ${habitClause}, but its dollar figure (${label}) totalled ${f.money(h.dollars.amount)} (historical), which is not a loss.`);   // N-gain
  }
  return lines;
}

// Coverage lines (page 1, always). R-D2 H-2: three patterns can be tested; the hold-gap line is fixed.
export function coverageLines(report) {
  checkReport(report);
  const lines = [`${report.n_tested} of the 3 patterns could be tested. Each one compares two groups of at least 30 trades.`];
  if (report.n_tested < 3) {
    const names = report.habits.filter((h) => TESTED.includes(h.id) && h.p_raw === null).map((h) => h.name);
    lines.push(`Not tested: ${names.join(', ')}.`);
  }
  lines.push(HOLD_GAP_COVERAGE);
  return lines;
}
