// wording.js — the paid report's sentences, exactly as ARCHITECT-STATS-AMENDMENT-R2-2026-10-21 §9.1–9.2
// gives them (page 1, the per-habit lines, the method lines and the percent format), filled from
// Report / Habit fields of the R2 engine (method 2026-10-23.stats2b: Architect ruling R-D2, hold_gap is
// described, not tested, so it is always withheld / not_calibrated and V-launch replaces M2 and the
// verdict; the V-spread, V-spread0, V-few and M2 hold_gap lines stay for Option B, unreachable under
// stats2b). Method 2026-10-23.stats2c (Architect ruling R-D3): size_up is described, not tested, too, so it
// is always withheld / not_calibrated and V-launch-size follows its M1; its M2, verdict and too_few lines
// stay for a later size method, unreachable under stats2c. Method 2026-10-23.stats2d (R-D3 addendum I-5): the
// server merges rows with the same open minute, symbol and direction into one trade; the report carries n_rows
// and n_trades, and page 1 says so when they differ (mergedLine). Method 2026-10-23.stats2f (R-D3 addendum 3
// I-9, replacing addendum 2's stats2e): a dates-only file (5% or more of its rows open at 00:00 and are held
// whole days) is not merged and its order-based habits carry no figure: revenge and tilt print vDatesOnly,
// size_up prints sizeNotDescribed, page 1 prints NONE_TESTED and datesP1, and the size-up coverage line becomes
// SIZE_UP_NONE. NONE_TESTED also replaces H0a/H0b whenever n_tested is 0. {T} is "All {n} trades in this
// file" when every row is date-only and "{k} of the {n} trades in this file" otherwise, so each line stays
// true for a file whose other rows have times.
// No DOM, no I/O: report.js
// renders them. Every sentence describes the file's past trades only, is printed only when its
// condition holds, and passes checks/lint.py (tests/test_paid_wording.py, W-1 and W-2).
//
// fmt: { money(x), duration(seconds), ratio(x), count(n) } — the page passes its own formatters
// (money as report.js formats it now); the defaults are plain, for tests.

import { POWER_TABLE } from './power-table.js?v=fed358b0';

export const METHOD_VERSION = '2026-10-23.stats2f';
// V-launch (R-D2 H-2, exact text): hold_gap under stats2b. Replaces M2 and the verdict.
export const V_LAUNCH = 'In our tests on files built to have no real pattern, this test reported a gap in more than 1 file in 20, the rate it is designed for, when a large win or loss changed how long the next trades were held. So this pattern is described here without a verdict.';
// The fixed page-1 line (R-D2 H-2), on every stats2b and stats2c report.
export const HOLD_GAP_COVERAGE = 'Holding losers longer than winners is described, not tested, in this version of the report.';
// V-launch-size (R-D3.2, exact text): size_up under stats2c. Follows M1; replaces M2 and the verdict.
export const V_LAUNCH_SIZE = 'In our tests on files built to have no real pattern, this test reported a gap in more than 1 file in 20, the rate it is designed for, in files that mix several symbols whose sizes and results both follow the time of day. So this pattern is described here without a verdict.';
// R-D3 addendum 3 I-9, exact texts ({T}: datesSubject).
export const NONE_TESTED = 'None of the patterns could be tested in this file. Some are described below without a verdict.';
export const SIZE_UP_NONE = 'Size after a loss is not described or tested for this file.';
export function datesSubject(report, fmt) {
  const f = fmtOf(fmt);
  return report.n_date_only_rows === report.n_rows ? `All ${f.count(report.n_rows)} trades in this file`
    : `${f.count(report.n_date_only_rows)} of the ${f.count(report.n_rows)} trades in this file`;
}
const DATED = 'open at exactly 00:00 and were held a whole number of days, as in exports with dates but no times';
// House style: lower case after a colon ("Not tested: the holds ..."), so {T} starts lower case there.
export const vDatesOnly = (T) => `Not tested: ${lowerFirst(T)} ${DATED}; this pattern depends on the timing of trades within a day, so it is not tested on files like that.`;
export const sizeNotDescribed = (T) => `Not described: ${lowerFirst(T)} ${DATED}; this pattern depends on which trade came after a loss, so it is not described for files like that.`;
export const datesP1 = (T) => `${T} ${DATED}, so the patterns that depend on the order and timing of trades within a day are not tested, and size after a loss is not described.`;
// The fixed page-1 line (R-D3.2), on every stats2c report, after HOLD_GAP_COVERAGE.
export const SIZE_UP_COVERAGE = 'Size after a loss is described, not tested, in this version of the report.';
// V-spread0 (R-D1 D-1): hold_gap withheld for spread with spread_ratio null (an infinite ratio). Replaces M2 and the verdict.
export const V_SPREAD0 = "Not tested: the middle half of your losing trades, or of your winning trades, all sit at the same relative position when each trade's hold is ranked among trades of the same symbol, holding period and direction. This test cannot tell a gap in hold apart from a difference in how spread out the holds are.";

const DEFAULT_FMT = {
  money: (x) => String(x),
  duration: (s) => `${s} s`,
  ratio: (x) => x.toFixed(2),
  count: (n) => String(n),
};

// The habits a stats2c report can test (R-D2: hold_gap is not one of them; R-D3: nor is size_up), and the
// habits shown with sentences under their heading (hold_gap's are M1, V-launch and M3; size_up's M1 and
// V-launch-size).
export const TESTED = Object.freeze(['revenge', 'tilt']);
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

// R-D3: under stats2c size_up is never tested either; any other size_up state means nothing is printed.
export function checkSizeUp(report) {
  const h = report && Array.isArray(report.habits) ? report.habits.find((x) => x.id === 'size_up') : null;
  if (!h) throw new Error('wording: the report has no size_up entry');
  if (h.verdict !== 'withheld' || h.withheld !== 'not_calibrated' || h.p_raw !== null || h.p_holm !== null || h.n_perm !== null) {
    throw new Error(`wording: size_up is ${h.verdict}/${h.withheld} with p_raw ${h.p_raw}, but it is not tested in ${METHOD_VERSION} (R-D3)`);
  }
}

// R-D3 addendum I-5: a stats2d report counts the rows it received and the trades it analysed.
export function checkRows(report) {
  const r = report && report.n_rows, t = report && report.n_trades;
  if (!Number.isInteger(r) || !Number.isInteger(t) || t < 1 || t > r) {
    throw new Error(`wording: the report has n_rows ${r} and n_trades ${t} (R-D3 addendum)`);
  }
  const k = report.n_date_only_rows;
  if (typeof report.dates_only !== 'boolean' || !Number.isInteger(k) || k < 0 || k > r || (report.dates_only && (r !== t || 20 * k < r))
    || (!report.dates_only && 20 * k >= r)) {
    throw new Error(`wording: the report has dates_only ${report.dates_only}, ${k} date-only rows, ${r} rows and ${t} trades (R-D3 addendum 3)`);
  }
}

// R-D3 addendum 3: a dates-only report carries no figure for revenge, tilt or size_up and tests nothing; any
// other report has no "dates_only" habit.
export function checkCoarse(report) {
  for (const h of report.habits) {
    const blankSeq = h.verdict === 'withheld' && h.withheld === 'dates_only' && h.p_raw === null && h.p_holm === null
      && h.measure_a === null && h.measure_b === null && h.effect === null && h.dollars === null;
    if (report.dates_only && (h.id === 'revenge' || h.id === 'tilt') && !blankSeq) {
      throw new Error(`wording: ${h.id} has a figure in a dates-only report (R-D3 addendum 3)`);
    }
    if (report.dates_only && h.id === 'size_up' && (h.measure_a !== null || h.measure_b !== null || h.effect !== null || h.dollars !== null)) {
      throw new Error('wording: size_up is described in a dates-only report (R-D3 addendum 3)');
    }
    if (!report.dates_only && h.withheld === 'dates_only') throw new Error(`wording: ${h.id} is dates_only in a report that is not (R-D3 addendum 3)`);
  }
  if (report.dates_only && (report.n_tested !== 0 || report.focus !== null)) throw new Error('wording: a dates-only report with a test or a focus (R-D3 addendum 3)');
}

// Everything renderReport() needs to be true before it shows anything.
export function checkReport(report) {
  checkMethod(report);
  checkHoldGap(report);
  checkSizeUp(report);
  checkRows(report);
  checkCoarse(report);
}

// Page 1, only when the server merged rows (R-D3 addendum I-5, exact text); null otherwise.
export function mergedLine(report, fmt) {
  checkReport(report);
  if (report.dates_only || report.n_rows === report.n_trades) return null;
  const f = fmtOf(fmt);
  // T-3 T3-F: date-only rows are never merged; say so when the file has any
  const kept = report.n_date_only_rows > 0 ? '; rows that open at 00:00 with whole-day holds are kept separate' : '';
  return `Rows with the same open minute, symbol and direction were counted as one trade (for example, a position closed in parts${kept}): ${f.count(report.n_rows)} rows became ${f.count(report.n_trades)} trades.`;
}

// ---------------------------------------------------------------- related research (R-D3 addendum I-6)

// Each line claims only what the paper's abstract shows (Tester T-4) and says the report's test is a different
// one. The page renders these, never the report's research_ref; oversized_loss has none. Bibliography as T-4
// checked it against Crossref (volume, issue, pages, DOI).
export const RESEARCH_PREFIX = "Related research (a different test from this report's): ";
const ODEAN = { cite: 'Odean, T. (1998). Are investors reluctant to realize their losses? Journal of Finance 53(5), 1775–1798.',
  url: 'https://doi.org/10.1111/0022-1082.00072' };
const COVAL = { cite: 'Coval, J. D. & Shumway, T. (2005). Do behavioral biases affect prices? Journal of Finance 60(1), 1–34.',
  url: 'https://doi.org/10.1111/j.1540-6261.2005.00723.x' };
const CS_FOUND = 'Coval and Shumway (2005) found that Chicago Board of Trade traders who lost money in the morning took above-average risk in the afternoon';
export const RESEARCH = Object.freeze({
  hold_gap: { line: 'Odean (1998) found that investors at a discount brokerage realised gains more readily than losses; that study counted sales, not holding times.', ...ODEAN },
  revenge: { line: `${CS_FOUND}; this report's 15-minute window is not from that study.`, ...COVAL },
  size_up: { line: `${CS_FOUND}.`, ...COVAL },
  tilt: { line: `${CS_FOUND}; this report's rule of 2 or more losses in a row is not from that study.`, ...COVAL },
});

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

// T-3 T3-C: in a dates-only file, holds are counted from dates (a trade opened and closed on the same date has
// h = 0, not a known 0-minute hold), so they are shown in days with that said, never as minutes.
export function holdDays(s) {
  const d = s / 86400;
  const t = Number.isInteger(d) ? String(d) : d.toFixed(1);
  return t === '1' ? '1 day' : `${t} days`;
}
export const SAME_DATE_LINE = 'In this file, a trade with dates but no times that opened and closed on the same date counts as 0 days.';

function holdGapLines(h, report, f) {
  const out = [];
  if (h.measure_a !== null && h.measure_b !== null) {
    if (report.dates_only) {
      out.push(`Your losing trades were held a median of ${holdDays(h.measure_a)}; your winning trades a median of ${holdDays(h.measure_b)}. ${SAME_DATE_LINE}`);   // M1, T3-C
    } else {
      out.push(`Your losing trades were held a median of ${f.duration(h.measure_a)}; your winning trades a median of ${f.duration(h.measure_b)}.`);   // M1
    }
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
    out.push(`${report.dates_only ? 'Held 12 hours or more, or closed on a later date' : 'Held 12 hours or more'}: ${h.n_long_a} of your ${h.n_a} losing trades and ${h.n_long_b} of your ${h.n_b} winning trades.`);   // M3 (T-3 T3-D: no hold-gap test runs, so the old "not part of the test" clause is dropped)
  }
  if (h.verdict === 'distinguishable' || h.verdict === 'not_distinguishable') out.push(verdictLine(h, report));
  return out;
}

function sizeUpLines(h, report, f) {
  const out = [];
  if (report.dates_only) return [sizeNotDescribed(datesSubject(report, f))];   // R-D3 addendum 3: replaces M1 and V-launch-size
  if (h.effect !== null) out.push(`Your median size after a loss was ${f.ratio(h.effect)}× your median size after a win.`);   // M1
  if (h.verdict === 'withheld' && h.withheld === 'not_calibrated') {
    out.push(V_LAUNCH_SIZE);   // R-D3 (stats2c): replaces M2 and the verdict
    return out;
  }
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
  if (h.verdict === 'withheld' && h.withheld === 'dates_only') return [vDatesOnly(datesSubject(report, f))];   // R-D3 addendum 3
  if (h.verdict === 'too_few') return [`Not enough trades to tell: this pattern compares two groups of at least 30 trades each, and this file has ${h.n_a} and ${h.n_b}.`];
  const m = h.id === 'revenge'
    ? `Trades opened within 15 minutes of a losing trade's close averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`
    : `Trades taken after 2 or more losses in a row averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`;
  return [m, verdictLine(h, report)];
}

// Every line of a tested habit as shown under its heading, in order.
export function habitSentences(h, report, fmt) {
  checkHoldGap(report);
  checkSizeUp(report);
  if (h.id === 'hold_gap') checkHoldGap({ habits: [h] });
  if (h.id === 'size_up') checkSizeUp({ habits: [h] });
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
    // R-D3 addendum 2: when nothing was tested, "no pattern is distinguishable" is not a fair summary
    if (n === 0) return report.dates_only ? [NONE_TESTED, datesP1(datesSubject(report, f))] : [NONE_TESTED];
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

// Coverage lines (page 1, always). R-D3: two habits can be tested (revenge, tilt); the hold-gap and
// size-up lines are fixed.
export function coverageLines(report) {
  checkReport(report);
  const lines = [`${report.n_tested} of the 2 habits could be tested. Each one compares two groups of at least 30 trades.`];
  if (report.n_tested < 2) {
    const names = report.habits.filter((h) => TESTED.includes(h.id) && h.p_raw === null).map((h) => h.name);
    lines.push(`Not tested: ${names.join(', ')}.`);
  }
  lines.push(HOLD_GAP_COVERAGE, report.dates_only ? SIZE_UP_NONE : SIZE_UP_COVERAGE);   // R-D3 addendum 3
  return lines;
}

// ---------------------------------------------------------------- "N more trades to tell" (bundle plan §2.2, slice 1)
// New strings only; nothing above changes. Shown for a tested habit whose verdict is "could be luck"
// (not_distinguishable) and never for "unlikely to be luck", a facts-only habit, too_few or a habit that was not tested.
// N comes from the static table power-table.js (checks/power_table/build_power_table.mjs), built offline on the
// shipped engine with a FIXED moderate pattern (0.5 sd): it never uses the file's own gap (plan R9, post-hoc power).
// The table carries the engine method it was built on; a report from another method is refused.
export const MORE_TRADES_ODDS = 0.5;
export const MORE_TRADES_CAP = 1000;
export const moreTradesLine = (N) => `About ${N} more trades would give this check even odds of telling a moderate pattern from luck.`;
export const MORE_TRADES_OVER = 'More than 1,000 more trades would give this check even odds of telling a moderate pattern from luck.';
export const moreTradesEnough = (n) => `The ${n} trades in this file already give this check even odds of telling a moderate pattern from luck.`;
export const moreTradesBar = (have, of) => `${have} of about ${of} trades`;
export const MORE_TRADES_CAVEAT = 'Assumes your next trades look like these.';
export const moreTradesHow = (built) => `How "more trades" is worked out: a moderate pattern (the matching trades' results 0.5 standard deviations worse, a fixed size, never your file's own gap) was planted in generated test files of each size, and the share of files in which this check told it apart from luck was counted, at the first Holm step for the habits tested. "Even odds" is the size at which that share reaches one half. The table is fixed (built ${built}).`;

function checkTable(report, table) {
  if (!table || table.method_version !== report.method_version) {
    throw new Error(`wording: the more-trades table is for method ${table && table.method_version}, the report is ${report.method_version}`);
  }
  if (table.reference_effect_sd !== 0.5) throw new Error('wording: the more-trades table is not built on the fixed moderate pattern');
}

// Trades for even odds (a whole file's trade count, rounded up to 10), by log-n interpolation; Infinity off the table.
export function tradesForEvenOdds(id, table = POWER_TABLE) {
  const t = table.habits[id];
  if (!t) throw new Error(`wording: no more-trades row for ${id}`);
  const n = table.n, p = t.power;
  for (let i = 1; i < p.length; i++) if (p[i] < p[i - 1]) throw new Error(`wording: more-trades row ${id} is not monotone`);
  const i = p.findIndex((x) => x >= MORE_TRADES_ODDS);
  if (i < 0) return Infinity;
  if (i === 0) return n[0];
  const f = (MORE_TRADES_ODDS - p[i - 1]) / (p[i] - p[i - 1]);
  return Math.ceil(Math.exp(Math.log(n[i - 1]) + f * (Math.log(n[i]) - Math.log(n[i - 1]))) / 10) * 10;
}

// { line, bar: {have, of, label} | null, caveat, how } or null when no N is shown for this habit.
export function moreTrades(h, report, fmt, table = POWER_TABLE) {
  checkReport(report);
  if (!TESTED.includes(h.id) || h.verdict !== 'not_distinguishable' || h.p_raw === null) return null;
  checkTable(report, table);
  const f = fmtOf(fmt), have = report.n_trades, of = tradesForEvenOdds(h.id, table);
  const how = moreTradesHow(table.built);
  if (of - have <= 0) return { line: moreTradesEnough(f.count(have)), bar: null, caveat: MORE_TRADES_CAVEAT, how };
  if (!Number.isFinite(of) || of - have > MORE_TRADES_CAP) return { line: MORE_TRADES_OVER, bar: null, caveat: MORE_TRADES_CAVEAT, how };
  return { line: moreTradesLine(f.count(of - have)), bar: { have, of, label: moreTradesBar(f.count(have), f.count(of)) }, caveat: MORE_TRADES_CAVEAT, how };
}

// Every new string, filled with sample values, for the lint and the word budgets (plan §6, BUNDLE_STRINGS).
export const BUNDLE_STRINGS = Object.freeze([moreTradesLine('120'), MORE_TRADES_OVER, moreTradesEnough('304'), moreTradesBar('180', '300'),
  MORE_TRADES_CAVEAT, moreTradesHow('2026-10-30')]);
