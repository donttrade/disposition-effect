// wording.js — the paid report's sentences for DT-2 of the donttrade test (method 2026-10-31.stats3a):
// ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §2.4 (steps, step lines, guard line), §2.5 (report fields), §3 (how
// sure), §5.2 (the catch line), §5.4 (report plus re-test), §10 (the wording audit) and
// ARCHITECT-SMALL-FILES-ADDENDUM-2026-10-31 §3 (the small-file layout) and §6 (the check needs 5).
//
// Every checked habit ends in three definite things: its dollar facts, one of three steps (No sign, Some sign,
// Clear sign) and a number for how sure. The verdict layer has no hedge word (checks/lint.py [verdict_hedges] holds
// VERDICT_STRINGS to that). Every number comes from the engine's report: the step cuts (step_cuts), the group
// minimum (min_group), the family size (n_family), each habit's step, chance_per_100 and catch figures. checkReport()
// recomputes each step and number from the report's own p-values and refuses a report that disagrees, so report.js
// shows nothing rather than a sentence that is not true of the report (REPORT_ERROR).
//
// A report of the previous method (2026-10-23.stats2f, DT-1) is worded by the frozen wording-stats2f.js for one
// release (report.js dispatches on method_version). No DOM, no I/O: report.js renders these.
//
// fmt: { money(x), amount(x) (unsigned), duration(seconds), ratio(x), count(n) }: the page passes its own formatters;
// the defaults are plain, for tests.

// DT-2 after the calibration fixes (F1).
export const METHOD_VERSION = '2026-10-31.stats3a';
export const METHOD_LABEL = 'DT-2';

// The published settings of this method (the corrections entry and the pages state them). Every sentence is filled
// from the report's own fields (step_cuts, min_group, some_min_group, n_family, promise_per_100); these values are used
// only to refuse a report that claims this method with other settings, so a page never states a promise its engine
// was not calibrated for (calibration fixes item 8: Clear at most 3 in 100 on one report, 5 across a report and its
// re-test; Some at most 20 on one report).
export const METHOD_SETTINGS = Object.freeze({ step_cuts: [0.029, 0.2], min_group: 5, some_min_group: 10, n_family: 3,
  promise_per_100: { clear_run: 3, clear_report_and_retest: 5, some_run: 20 } });

// The habits a DT-2 report checks against chance in this release (revenge, tilt); size after a loss is in the engine's
// family of 3 with p = 1 until it ships (owner: ship without it), and is shown as facts.
export const CHECKED = Object.freeze(['revenge', 'tilt']);
export const SENTENCE_HABITS = Object.freeze(['hold_gap', 'revenge', 'size_up', 'tilt']);
export const HABIT_ORDER = Object.freeze(['hold_gap', 'revenge', 'size_up', 'tilt', 'oversized_loss']);
const STATUSES = Object.freeze({ hold_gap: ['facts'], revenge: ['tested', 'too_few', 'dates_only'], size_up: ['not_shipped'],
  tilt: ['tested', 'too_few', 'dates_only'], oversized_loss: ['facts'] });

// The pill words (plan §10 row 31). site/build.py reads this map for the example-report card (hero_media_report.html)
// and fails on a step it does not hold.
export const STEP = Object.freeze({
  clear: 'Clear sign',
  some: 'Some sign',
  none: 'No sign',
  too_few: 'Too few trades',
  dates_only: 'No check on this file',
});
export const PILL = STEP;   // report.js's pill words, the same name in both wording modules
// The second layer's heading (plan §9.4 item 2).
export const CHECK_HEADING = 'Habit or chance?';

const DEFAULT_FMT = {
  money: (x) => String(x),
  amount: (x) => String(Math.abs(x)),
  duration: (s) => `${s} s`,
  ratio: (x) => x.toFixed(2),
  count: (n) => String(n),
};
function fmtOf(fmt) {
  return { ...DEFAULT_FMT, ...(fmt || {}) };
}
const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);
const byId = (report, id) => report.habits.find((h) => h.id === id);

// ---------------------------------------------------------------- the checks (plan §2.5: checkSteps, on the page too)

// The step a habit's adjusted p gives under the report's own cuts; a gap that does not run the habit's way (revenge,
// tilt: the habit's trades did worse, effect < 0) is No sign whatever its p.
const CUT_TOL = 1e-12;
// Calibration fixes item 2: a habit whose smaller group is under some_min_group (5-9 trades) is Clear sign or No sign,
// never Some sign.
export function stepOf(h, cuts, someMin = 0) {
  if (!(Number.isFinite(h.effect) && h.effect < 0)) return 'none';
  if (h.p_holm <= cuts[0] + CUT_TOL) return 'clear';
  return h.p_holm <= cuts[1] + CUT_TOL && Math.min(h.n_a, h.n_b) >= someMin ? 'some' : 'none';
}
// Item 8, one scale per run: Clear shows ceil(100 p_holm) (at most promise.clear_run); Some at least clear_run + 1.
export function chancePer100(p, step = null, promise = METHOD_SETTINGS.promise_per_100) {
  const c = Math.max(1, Math.ceil(100 * p - 1e-9));
  return step === 'some' ? Math.max(promise.clear_run + 1, c) : c;
}

function fail(why) {
  throw new Error(`wording: ${why} (DT-2)`);
}

export function checkMethod(report) {
  if (!report || report.method_version !== METHOD_VERSION) fail(`report method ${report && report.method_version} is not ${METHOD_VERSION}`);
  if (report.method_label !== METHOD_LABEL) fail(`report label ${report.method_label} is not ${METHOD_LABEL}`);
  const c = report.step_cuts, M = METHOD_SETTINGS;
  if (!Array.isArray(c) || c.length !== 2 || c.some((x, i) => Math.abs(x - M.step_cuts[i]) > CUT_TOL)) fail(`step cuts ${JSON.stringify(c)} are not this method's ${JSON.stringify(M.step_cuts)}`);
  for (const k of ['min_group', 'some_min_group', 'n_family']) if (report[k] !== M[k]) fail(`${k} ${report[k]} is not this method's ${M[k]}`);
  const pr = report.promise_per_100;
  if (!pr || Object.keys(M.promise_per_100).some((k) => pr[k] !== M.promise_per_100[k])) fail(`promise_per_100 ${JSON.stringify(pr)} is not this method's`);
  if (pr.clear_run !== Math.ceil(100 * c[0] - 1e-9) || pr.some_run !== Math.ceil(100 * c[1] - 1e-9)) fail('promise_per_100 does not follow the cuts');
  const b = report.blocks;
  if (!b || b.rule !== 'session' || typeof b.clock_guard !== 'boolean' || ![b.gap_min, b.cap_min, b.clock_band_min].every((x) => Number.isInteger(x) && x > 0)) fail(`blocks ${JSON.stringify(b)}`);
  if (!Number.isInteger(report.catch_max_trades) || report.catch_max_trades < 1) fail(`catch_max_trades ${report.catch_max_trades}`);
}

// The row counts (R-D3 addendum I-5 and addendum 3, unchanged in DT-2).
export function checkRows(report) {
  const r = report.n_rows, t = report.n_trades, k = report.n_date_only_rows;
  if (!Number.isInteger(r) || !Number.isInteger(t) || t < 1 || t > r) fail(`n_rows ${r} and n_trades ${t}`);
  if (typeof report.dates_only !== 'boolean' || !Number.isInteger(k) || k < 0 || k > r || (report.dates_only && (r !== t || 20 * k < r))
    || (!report.dates_only && 20 * k >= r)) {
    fail(`dates_only ${report.dates_only}, ${k} date-only rows, ${r} rows and ${t} trades`);
  }
}

// The reasons a habit has no catch figure (dt-private catch_reason), each with a definite line (catchReasonLine).
export const CATCH_REASONS = Object.freeze(['same_result', 'over_limit', 'dates_only', 'no_trades', 'off']);
function checkCatch(h, report) {
  const c = h.catch, why = h.catch_reason;
  if (!CHECKED.includes(h.id)) {
    if (c !== null || why !== null) fail(`${h.id} has a catch figure or reason it cannot have`);
    return;
  }
  if (c === null) {
    if (!CATCH_REASONS.includes(why)) fail(`${h.id} has no catch figure and the reason ${why}`);
    if ((why === 'dates_only') !== report.dates_only) fail(`${h.id} has the catch reason ${why} in a ${report.dates_only ? 'dates-only' : 'timed'} file`);
    if ((why === 'over_limit') !== (report.n_trades > report.catch_max_trades) && !report.dates_only) fail(`${h.id} has the catch reason ${why} on ${report.n_trades} trades`);
    return;
  }
  if (why !== null) fail(`${h.id} has a catch figure and the reason ${why}`);
  if (report.dates_only || report.n_trades > report.catch_max_trades) fail(`${h.id} has a catch figure it cannot have`);
  const ok = c && Array.isArray(c.sizes) && c.sizes.length >= 1 && c.sizes.length <= 3 && c.sizes[0] === report.n_trades
    && c.sizes.every((s, j) => Number.isInteger(s) && (j === 0 || s > c.sizes[j - 1]))
    && Array.isArray(c.at_least_10ths) && c.at_least_10ths.length === c.sizes.length
    && c.at_least_10ths.every((t) => Number.isInteger(t) && t >= 0 && t <= 10)
    && Array.isArray(c.caught) && c.caught.length === c.sizes.length && Number.isInteger(c.reps) && c.reps >= 1
    && c.caught.every((x, j) => Number.isInteger(x) && x >= 0 && x <= c.reps && c.at_least_10ths[j] <= Math.floor((10 * x) / c.reps))
    && Number.isInteger(c.n_perm) && c.effect && Number.isFinite(c.effect.amount) && c.effect.amount > 0 && c.effect.unit === report.currency;
  if (!ok) fail(`${h.id} has a malformed catch figure ${JSON.stringify(c)}`);
}

// Everything the page needs to be true before it shows anything (the site's half of the engine's checkSteps).
export function checkReport(report) {
  checkMethod(report);
  checkRows(report);
  if (!Array.isArray(report.habits) || report.habits.map((h) => h.id).join() !== HABIT_ORDER.join()) fail('the habits are not the five in order');
  const cuts = report.step_cuts;
  for (const h of report.habits) {
    if (!STATUSES[h.id].includes(h.status)) fail(`${h.id} has status ${h.status}`);
    const tested = h.status === 'tested';
    for (const k of ['p_raw', 'p_holm', 'step', 'chance_per_100', 'chance_below_1', 'small_group']) {
      if (tested !== (h[k] !== null && h[k] !== undefined)) fail(`${h.id} has status ${h.status} and ${k} ${h[k]}`);
    }
    if (h.status === 'dates_only' && (!report.dates_only || h.dollars !== null || h.measure_a !== null || h.measure_b !== null)) fail(`${h.id} is dates_only with a figure or in a timed file`);
    if (CHECKED.includes(h.id) && report.dates_only && h.status !== 'dates_only') fail(`${h.id} is ${h.status} in a dates-only file`);
    if (h.status === 'too_few' && Math.min(h.n_a, h.n_b) >= report.min_group) fail(`${h.id} is too_few with groups ${h.n_a} and ${h.n_b}`);
    if (h.id === 'size_up' && report.dates_only && (h.measure_a !== null || h.dollars !== null)) fail('size_up has a figure in a dates-only file');
    if (tested) {
      if (Math.min(h.n_a, h.n_b) < report.min_group) fail(`${h.id} is checked with groups ${h.n_a} and ${h.n_b}`);
      if (!(h.p_raw > 0 && h.p_raw <= 1) || !(h.p_holm >= h.p_raw - 1e-15 && h.p_holm <= 1)) fail(`${h.id} has p_raw ${h.p_raw} and p_holm ${h.p_holm}`);
      if (!Number.isInteger(h.n_perm) || h.n_perm < 1) fail(`${h.id} has n_perm ${h.n_perm}`);
      if (!['none', 'some', 'clear'].includes(h.step) || h.step !== stepOf(h, cuts, report.some_min_group)) fail(`${h.id} has step ${h.step} but p_holm ${h.p_holm} and effect ${h.effect}`);
      const pr = report.promise_per_100;
      if (h.chance_per_100 !== chancePer100(h.p_holm, h.step, pr)) fail(`${h.id} has chance ${h.chance_per_100} but p_holm ${h.p_holm}`);
      if ((h.step === 'clear' && h.chance_per_100 > pr.clear_run) || (h.step === 'some' && h.chance_per_100 <= pr.clear_run)) fail(`${h.id} is ${h.step} with chance ${h.chance_per_100}`);
      if (h.small_group !== (Math.min(h.n_a, h.n_b) < report.some_min_group)) fail(`${h.id} has small_group ${h.small_group} with groups ${h.n_a} and ${h.n_b}`);
      if (h.small_group && h.step === 'some') fail(`${h.id} is Some sign with a smaller group under ${report.some_min_group}`);
      if (h.chance_below_1 !== (h.step === 'clear' && h.p_holm < 0.01)) fail(`${h.id} has chance_below_1 ${h.chance_below_1}`);
      if (h.measure_a === null || h.measure_b === null || !h.dollars) fail(`${h.id} is checked with no figure`);
    }
    checkCatch(h, report);
  }
  const tested = report.habits.filter((h) => h.status === 'tested');
  if (report.n_tested !== tested.length) fail(`n_tested ${report.n_tested} but ${tested.length} habits are checked`);
  for (const [k, st] of [['n_clear', 'clear'], ['n_some', 'some']]) {
    const n = tested.filter((h) => h.step === st).length;
    if (report[k] !== n) fail(`${k} ${report[k]} but ${n} habits are ${st}`);
  }
  // the focus: the Clear sign with the most negative dollar total (ties to the first), or none when no Clear is a loss
  let best = null;
  for (const h of tested) if (h.step === 'clear' && h.dollars.amount < 0 && (best === null || h.dollars.amount < best.dollars.amount)) best = h;
  if ((best ? best.id : null) !== report.focus) fail(`focus ${report.focus} but the Clear loss is ${best && best.id}`);
}

// ---------------------------------------------------------------- the pill (never a digit) and the small-file layout

// The pill key of a habit: its step, 'too_few', 'dates_only', or null for a facts-only habit (no pill).
export function pillOf(h) {
  if (h.status === 'tested') return h.step;
  if (h.status === 'too_few' || h.status === 'dates_only') return h.status;
  return null;
}
export const factsOnly = (h) => h.status === 'facts' || h.status === 'not_shipped';
export const isClear = (h) => h.step === 'clear';

// Addendum §3.1: the small-file layout, for a file under 100 trades where every checked habit shows No sign or
// Too few trades.
export const SMALL_FILE_TRADES = 100;
export function smallFile(report) {
  return report.n_trades < SMALL_FILE_TRADES && !report.habits.some((h) => h.step === 'some' || h.step === 'clear');
}

// ---------------------------------------------------------------- the lines of one habit

const DATED = 'open at exactly 00:00 and were held a whole number of days, as in exports with dates but no times';
export function datesSubject(report, fmt) {
  const f = fmtOf(fmt);
  return report.n_date_only_rows === report.n_rows ? `All ${f.count(report.n_rows)} trades in this file`
    : `${f.count(report.n_date_only_rows)} of the ${f.count(report.n_rows)} trades in this file`;
}
// Plan §10 rows 6 and 8.
export const vDatesOnly = (T) => `No check on this file: ${lowerFirst(T)} ${DATED}; this habit depends on the order of trades within a day, which these rows do not show.`;
export const datesP1 = (T, m) => `${T} ${DATED}, so the ${m} habits that depend on the order of trades within a day get no check on this file.`;
// Row 18 (the minimum is the engine's min_group).
export const tooFewLine = (a, b, min) => `Too few trades to check: this habit compares two groups of at least ${min} trades each, and this file has ${a} and ${b}.`;

// §2.4 step lines. N is the engine's chance_per_100 (rounded up, so "at most" stays true; calibration fixes item 8: a
// Clear sign at most promise.clear_run, a Some sign at least one more); chance_below_1 says "fewer than 1 in 100".
const chancePhrase = (h) => (h.chance_below_1 ? 'fewer than 1 in 100 times' : `at most ${h.chance_per_100} in 100 times`);
export function stepLine(h, report, fmt) {
  const n = fmtOf(fmt).count(report.n_trades), m = report.n_family;
  const tail = `In files with no real habit, a result this strong turns up ${chancePhrase(h)}, allowing for all ${m} habits at once.`;
  if (h.step === 'clear') return `Clear sign of this habit in these ${n} trades. ${tail}`;
  if (h.step === 'some') return `Some sign of this habit in these ${n} trades, short of clear. ${tail}`;
  // Buyer read-through (31 Oct): the No sign line agrees with the gap the card shows. A gap the habit's way is within
  // what chance gives (adjusted p over the Some cut); a gap the other way is not the habit at all.
  if (h.step === 'none') return !inHabitWay(h) ? noSignOther(h.id, n) : h.small_group ? noSignSmall(n) : noSignChance(n);
  return fail(`${h.id} has no step line for ${h.step}`);
}
const inHabitWay = (h) => Number.isFinite(h.effect) && h.effect < 0;
const NO_WORSE = { revenge: 'trades soon after a loss did not do worse than your other trades', tilt: 'trades after 2 or more losses in a row did not do worse than your other trades' };
export const noSignChance = (n) => `No sign beyond chance in these ${n} trades: a gap this size is common in files with no habit.`;
export const noSignOther = (id, n) => `No sign in these ${n} trades: ${NO_WORSE[id]}.`;
export const noSignSmall = (n) => `No sign beyond chance in these ${n} trades.`;
// Calibration fixes item 2: under the No sign line when the smaller group has 5-9 trades (small_group).
export const smallGroupLine = (a) => `With ${a} trades in the smaller group, this check shows a Clear sign or no sign.`;
// §2.4 guard line, under every Some sign and Clear sign number.
export const GUARD_LINE = 'This counts how often chance alone does this. It is not the chance your habit is real.';

// §5.2 the catch figure, under every No sign and Some sign (buyer read-through, 31 Oct: one short lead line, then one
// row per file size, drawn by report.js as a labelled table with a bar). Each row is the engine's Wilson lower bound
// in tenths ("at least N in 10", or "fewer than 1 in 10" for 0), so no row overstates the catch rate; the lead keeps
// the premise ("if your next trades look like these").
const CATCH_CLAUSE = { revenge: 'trades soon after a loss end', tilt: 'trades after 2 or more losses in a row end' };
const tenths = (t) => (t >= 1 ? `at least ${t} in 10` : 'fewer than 1 in 10');
export const catchLead = (amount) => `If the habit is real at ${amount} a trade and your next trades look like these, a file shows it as a Clear sign:`;
export const CATCH_CAPTION = 'How often a file of each size shows this habit as a Clear sign';
export const CATCH_HEAD = Object.freeze(['File size', 'Shown as a Clear sign']);
export const catchSize = (count, own) => `${count} trades${own ? ' (this file)' : ''}`;
// { lead, rows: [{ size, value, tenths }] }, or { line } (a fixed line) when the file gets no figure.
export function catchFigure(h, report, fmt) {
  const f = fmtOf(fmt), c = h.catch;
  if (c === null) return { line: catchReasonLine(h.catch_reason, f.count(report.catch_max_trades)) };
  return { lead: catchLead(f.amount(c.effect.amount)),
    rows: c.sizes.map((sz, j) => ({ size: catchSize(f.count(sz), j === 0), value: tenths(c.at_least_10ths[j]), tenths: c.at_least_10ths[j] })) };
}
// The figure as plain lines (lead, then "size: value" rows), for tests and the lint.
export function catchLines(h, report, fmt) {
  const g = catchFigure(h, report, fmt);
  return g.line ? [g.line] : [g.lead, ...g.rows.map((r) => `${r.size}: ${r.value}`)];
}
// One definite line per catch_reason (calibration fixes item 4.3 for same_result).
export const catchOver = (max) => `No catch figure: files over ${max} trades get none.`;
export const CATCH_FLAT = 'No catch figure: every trade in this file has the same result.';
const CATCH_REASON_LINES = { same_result: () => CATCH_FLAT, over_limit: catchOver,
  dates_only: () => 'No catch figure: this file has dates but no times of day.',
  no_trades: () => 'No catch figure: this file has no trades to build one from.',
  off: () => 'No catch figure: this report was made without one.' };
export function catchReasonLine(why, max) {
  if (!CATCH_REASON_LINES[why]) return fail(`no line for the catch reason ${why}`);
  return CATCH_REASON_LINES[why](max);
}

// §5.2 Expert text: the premise in full, and the counts behind each figure.
export function catchHow(h, fmt) {
  const f = fmtOf(fmt), c = h.catch;
  if (!c) return null;
  return `How the catch figure is worked out: we reshuffled your own results so no habit was left in them, added a habit of ${f.amount(c.effect.amount)} a trade (half the spread of your results), and built files of each size from your own trading days, drawn at random with repeats. Each figure is the lowest share that ${f.count(c.reps)} such files support at 95% confidence, with ${f.count(c.n_perm)} reshuffles each, at a level at least as strict as any Clear sign needs.`;
}

// Plan §10 row 37 (Expert): the raw reshuffle count and the adjusted p.
export function expertLine(h, report, fmt) {
  if (h.status !== 'tested') return null;
  const f = fmtOf(fmt), N = h.n_perm, c = Math.max(0, Math.round(h.p_raw * (N + 1)) - 1);
  return `${f.count(c)} of ${f.count(N)} reshuffles of your own results came out at least this one-sided (one-sided p = ${h.p_raw.toPrecision(3)}). Allowing for ${report.n_family} habits (Holm): ${h.p_holm.toPrecision(3)}.`;
}

// Plan §10 row 19: the method line, with the habit's own permutation count. Calibration fixes item 1: the shuffle runs
// within trading sessions found from the file's own opens (report.blocks), and, when the clock guard fired, within
// each band of the clock too.
const hours = (min) => { const h = min / 60; return `${Number.isInteger(h) ? h : h.toFixed(1)} hour${h === 1 ? '' : 's'}`; };
const hourBand = (min) => `${Number.isInteger(min / 60) ? min / 60 : (min / 60).toFixed(1)}-hour`;
export const sessionRule = (b) => `A session ends at a gap of ${hours(b.gap_min)} or more between opens and lasts at most ${hours(b.cap_min)}.`;
export const clockGuardLine = (b) => `In this file, wins and losses differ sharply by time of day, so each trade was also kept within its ${hourBand(b.clock_band_min)} band of the clock when the results were reshuffled.`;
export function methodLine(h, fmt, report) {
  if (h.status !== 'tested') return null;
  const n = fmtOf(fmt).count(h.n_perm), b = report.blocks;
  const tail = 'It counts as a sign only when both the average result and how often a result was the worse one point the habit’s way.';
  const shuffle = `The results were reshuffled within each trading session ${n} times (sessions with a single trade are grouped with nearby such sessions). ${sessionRule(b)}${b.clock_guard ? ' ' + clockGuardLine(b) : ''} ${tail}`;
  if (h.id === 'revenge') return `Compared with your other trades from the same session, matched on whether another trade had closed in the 15 minutes before it opened and whether another trade opened in the 15 minutes after it closed. ${shuffle}`;
  if (h.id === 'tilt') return `Compared with your other trades from the same session. ${shuffle}`;
  return fail(`methodLine: ${h.id} is not checked`);
}

// T-3 T3-C (kept): in a dates-only file, holds are counted from dates.
export function holdDays(s) {
  const d = s / 86400;
  const t = Number.isInteger(d) ? String(d) : d.toFixed(1);
  return t === '1' ? '1 day' : `${t} days`;
}
export const SAME_DATE_LINE = 'In this file, a trade with dates but no times that opened and closed on the same date counts as 0 days.';

// The lines of one habit, split by layer: what (under "What happened", the fact line first), check (under
// "Habit or chance?": the step line and the guard line, or the too-few or dates-only line, or a fixed no-figure line)
// and figure (the catch figure: { lead, rows }, drawn after the check lines), or null.
export function habitLines(h, report, fmt) {
  checkReport(report);
  const f = fmtOf(fmt), what = [], check = [];
  let figure = null;
  if (h.id === 'hold_gap') {
    if (h.measure_a !== null && h.measure_b !== null) {
      what.push(report.dates_only ? `Your losing trades were held a median of ${holdDays(h.measure_a)}; your winning trades a median of ${holdDays(h.measure_b)}. ${SAME_DATE_LINE}`
        : `Your losing trades were held a median of ${f.duration(h.measure_a)}; your winning trades a median of ${f.duration(h.measure_b)}.`);
    }
    if (h.n_long_a + h.n_long_b >= 1) {
      what.push(`${report.dates_only ? 'Held 12 hours or more, or closed on a later date' : 'Held 12 hours or more'}: ${h.n_long_a} of your ${h.n_a} losing trades and ${h.n_long_b} of your ${h.n_b} winning trades.`);
    }
  } else if (h.id === 'size_up') {
    if (report.dates_only) what.push(vDatesOnly(datesSubject(report, f)));
    else if (h.effect !== null) what.push(`Your median size after a loss was ${f.ratio(h.effect)}× your median size after a win.`);
  } else if (h.id === 'revenge' || h.id === 'tilt') {
    if (h.status === 'dates_only') check.push(vDatesOnly(datesSubject(report, f)));
    else if (h.status === 'too_few') check.push(tooFewLine(f.count(h.n_a), f.count(h.n_b), report.min_group));
    else {
      what.push(h.id === 'revenge'
        ? `Trades opened within 15 minutes of a losing trade's close averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`
        : `Trades taken after 2 or more losses in a row averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`);
      check.push(stepLine(h, report, f));
      if (h.step !== 'none') check.push(GUARD_LINE);
      else if (h.small_group) check.push(smallGroupLine(f.count(Math.min(h.n_a, h.n_b))));
      if (h.step !== 'clear') {
        const g = catchFigure(h, report, f);
        if (g.line) check.push(g.line); else figure = g;
      }
    }
  } else if (h.id !== 'oversized_loss') {   // large losses: report.js shows its measures list
    fail(`habitLines: ${h.id} has no sentences`);
  }
  return { what, check, figure };
}

// ---------------------------------------------------------------- page 1 (plan §10 rows 22–28)

export const noneChecked = (min) => `Too few trades to check any habit in this file: each check needs at least ${min} trades in both groups it compares.`;
export function noSignLine(nTested, n) {
  if (nTested === 1) return `No sign of the habit checked in these ${n} trades.`;
  if (nTested === 2) return `No sign of either habit checked in these ${n} trades.`;
  return `No sign of any of the ${nTested} habits checked in these ${n} trades.`;
}
export const CATCH_INTRO = 'Each habit below shows how often files of this size catch a habit of a stated dollar size.';
export const stepsLine = (k, j, m, pr) => `Clear sign on ${k} of ${m} habits, some sign on ${j}. The steps allow for all ${m} habits at once: in files with no real habit, a Clear sign on any habit turns up at most ${pr.clear_report_and_retest} in 100 times, counting a first report and its re-test together.`;
// Calibration fixes item 8: the step definitions, shown once, per run and across two runs on one scale.
export const stepDefs = (pr, someMin) => `Clear sign: on one report, a result this strong turns up at most ${pr.clear_run} in 100 times in files with no real habit, and at most ${pr.clear_report_and_retest} in 100 across a report and its re-test. Some sign: at most ${pr.some_run} in 100 on one report, and only when the smaller group has ${someMin} trades or more.`;
export const NO_FOCUS = 'No habit is shown first. A habit is shown first only when it has a Clear sign and its dollar total is a loss.';

export const focusLine = (name, label, money) => `Shown first: ${name}. ${label} totalled ${money} (historical).`;
export const focusNone = (name, label) => `${name}: Clear sign, but no trade in this file is in its dollar total (${label}).`;
export const focusGain = (name, label, money) => `${name}: Clear sign, but its dollar total (${label}) was ${money} (historical), not a loss.`;

export function page1Lines(report, fmt) {
  checkReport(report);
  const f = fmtOf(fmt), n = f.count(report.n_trades), m = report.n_family;
  if (report.dates_only) return [datesP1(datesSubject(report, f), m)];
  if (report.n_tested === 0) return [noneChecked(report.min_group)];
  const k = report.n_clear, j = report.n_some;
  if (k + j === 0) {
    const lines = [noSignLine(report.n_tested, n)];
    if (report.habits.some((h) => h.status === 'tested' && h.catch !== null)) lines.push(CATCH_INTRO);
    return lines;
  }
  const lines = [stepsLine(k, j, m, report.promise_per_100)];
  if (report.focus !== null) {
    const h = byId(report, report.focus);
    lines.push(focusLine(h.name, h.dollars.label, f.money(h.dollars.amount)));
    return lines;
  }
  lines.push(NO_FOCUS);
  for (const h of report.habits.filter((x) => x.step === 'clear')) {
    const label = lowerFirst(h.dollars.label);
    lines.push(h.dollars.n_trades === 0 ? focusNone(h.name, label) : focusGain(h.name, label, f.money(h.dollars.amount)));
  }
  return lines;
}

export const SIZE_UP_FACTS = 'Size after a loss is shown as facts from your file, with no check against chance in this version.';
export const coverageHead = (n, m, min) => `${n} of ${m} habits checked against chance. Each check needs at least ${min} trades in both groups it compares.`;
export const tooFewNames = (names) => `Too few trades to check: ${names.join(', ')}.`;
export function coverageLines(report) {
  checkReport(report);
  const lines = [coverageHead(report.n_tested, report.n_family, report.min_group)];
  if (report.n_tested > 0) lines.push(stepDefs(report.promise_per_100, report.some_min_group));
  const few = report.habits.filter((h) => h.status === 'too_few').map((h) => h.name);
  if (few.length) lines.push(tooFewNames(few));
  lines.push(SIZE_UP_FACTS);
  return lines;
}

// Page 1, only when the server merged rows (R-D3 addendum I-5, unchanged).
export function mergedLine(report, fmt) {
  checkReport(report);
  if (report.dates_only || report.n_rows === report.n_trades) return null;
  const f = fmtOf(fmt);
  const kept = report.n_date_only_rows > 0 ? '; rows that open at 00:00 with whole-day holds are kept separate' : '';
  return `Rows with the same open minute, symbol and direction were counted as one trade (for example, a position closed in parts${kept}): ${f.count(report.n_rows)} rows became ${f.count(report.n_trades)} trades.`;
}

// Facts-only habits (the hold gap, large losses, size after a loss in this release): plan §10 row 29.
export const FACTS_LINE = 'Facts from your file. No check against chance exists for these habits in this version.';

// ---------------------------------------------------------------- the small-file layout (addendum §3.1 items 3–4)

const FEW_GROUPS = { revenge: (a, b) => `${a} trades soon after a loss, ${b} others`, tilt: (a, b) => `${a} trades after 2 or more losses in a row, ${b} others` };
export const fewPart = (name, id, a, b, min) => `${lowerFirst(name)} (${FEW_GROUPS[id](a, b)}; the check needs ${min} of each)`;
export const fewJoin = (parts) => `Too few trades to check: ${parts.join('; ')}.`;
// All "Too few trades" habits in one line (§3.1 item 3); null when there is none.
export function tooFewCollapsed(report, nameOf, fmt) {
  checkReport(report);
  const f = fmtOf(fmt);
  const parts = report.habits.filter((h) => h.status === 'too_few').map((h) => fewPart(nameOf(h), h.id, f.count(h.n_a), f.count(h.n_b), report.min_group));
  return parts.length ? fewJoin(parts) : null;
}
// The re-test reason (§3.1 item 4): the catch line's larger sizes, one line per No sign habit that has them.
export const retestRow = (clause, amount, rows) => `For your re-test: when ${clause} ${amount} worse each, files of ${rows.join(', and ')}.`;
export function retestReasons(report, fmt) {
  checkReport(report);
  const f = fmtOf(fmt);
  return report.habits.filter((h) => h.status === 'tested' && h.step === 'none' && h.catch && h.catch.sizes.length > 1 && h.catch.effect.amount > 0)
    .map((h) => retestRow(CATCH_CLAUSE[h.id], f.amount(h.catch.effect.amount),
      h.catch.sizes.slice(1).map((s, j) => `${f.count(s)} trades show it as a Clear sign ${tenths(h.catch.at_least_10ths[j + 1])} times`)));
}

// ---------------------------------------------------------------- the re-test (plan §5.4, §2.4 item 5, §11)

export const retestTwoLook = (pr) => `This re-test checks a longer history that includes your first file. Across a first report and its re-test, a Clear sign on a history with no real habit turns up at most ${pr.clear_report_and_retest} in 100 times.`;
export const STEPS_MOVE = 'Steps can move between runs by chance alone.';
export const RETEST_DT1 = 'A first report made with DT-1 of the donttrade test gave two results per habit; this re-test uses the three steps of DT-2, so the two are not directly comparable.';
export const retestLines = (report) => [retestTwoLook(report.promise_per_100), STEPS_MOVE, RETEST_DT1];

// ---------------------------------------------------------------- related research (R-D3 addendum I-6, unchanged)

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

// ---------------------------------------------------------------- every verdict-layer string, for the lint

// Filled with sample values (checks/lint.py [verdict_hedges] and the word rules; tests/test_dt2_wording.py).
const SAMPLE = { id: 'revenge', status: 'tested', n_a: 40, n_b: 90, effect: -12, p_raw: 0.01, p_holm: 0.03, n_perm: 10000,
  catch: { sizes: [120, 240, 480], at_least_10ths: [0, 3, 5], caught: [8, 27, 39], reps: 60, n_perm: 399, effect: { unit: 'USD', amount: 7.2 } } };
const SAMPLE_PROMISE = METHOD_SETTINGS.promise_per_100;
const SAMPLE_BLOCKS = { rule: 'session', gap_min: 180, cap_min: 1440, clock_band_min: 120, clock_guard: true };
const SAMPLE_REPORT = { n_trades: 120, n_family: 3, catch_max_trades: 5000, promise_per_100: SAMPLE_PROMISE, blocks: SAMPLE_BLOCKS };
const SAMPLE_FMT = { amount: (x) => `$${x.toFixed(2)}`, count: (n) => n.toLocaleString('en-US') };
export const VERDICT_STRINGS = Object.freeze([
  ...Object.values(STEP), CHECK_HEADING,
  stepLine({ ...SAMPLE, step: 'clear', chance_per_100: 3, p_holm: 0.025 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'clear', chance_per_100: 1, p_holm: 0.004 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'some', chance_per_100: 14, p_holm: 0.14 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'none', chance_per_100: 100, p_holm: 1 }, SAMPLE_REPORT, SAMPLE_FMT),
  noSignOther('revenge', '120'), noSignOther('tilt', '120'),
  GUARD_LINE,
  ...catchLines(SAMPLE, SAMPLE_REPORT, SAMPLE_FMT), CATCH_CAPTION, ...CATCH_HEAD,
  ...CATCH_REASONS.map((why) => catchReasonLine(why, '5,000')), catchHow(SAMPLE, SAMPLE_FMT), expertLine(SAMPLE, SAMPLE_REPORT, SAMPLE_FMT),
  methodLine(SAMPLE, SAMPLE_FMT, SAMPLE_REPORT), methodLine({ ...SAMPLE, id: 'tilt' }, SAMPLE_FMT, { ...SAMPLE_REPORT, blocks: { ...SAMPLE_BLOCKS, clock_guard: false } }),
  noSignSmall('30'), smallGroupLine('8'), stepDefs(SAMPLE_PROMISE, 10),
  tooFewLine('3', '116', 5), vDatesOnly('All 200 trades in this file'), datesP1('12 of the 200 trades in this file', 3),
  noneChecked(5), noSignLine(1, '120'), noSignLine(2, '120'), noSignLine(3, '120'), CATCH_INTRO, stepsLine(1, 0, 3, SAMPLE_PROMISE), stepsLine(0, 2, 3, SAMPLE_PROMISE),
  NO_FOCUS, focusLine('Re-entering soon after a loss', "Trades opened within 15 minutes of a losing trade's close", '−$500.00'),
  focusNone('Re-entering soon after a loss', "trades opened within 15 minutes of a losing trade's close"),
  focusGain('Re-entering soon after a loss', "trades opened within 15 minutes of a losing trade's close", '+$120.00'),
  coverageHead(2, 3, 5), tooFewNames(['Trading after a losing streak']), SIZE_UP_FACTS, FACTS_LINE,
  fewJoin([fewPart('Trading after a losing streak', 'tilt', '4', '26', 5), fewPart('Re-entering soon after a loss', 'revenge', '0', '30', 5)]),
  retestRow(CATCH_CLAUSE.tilt, '$7.20', ['60 trades show it as a Clear sign at least 2 in 10 times', '120 trades show it as a Clear sign fewer than 1 in 10 times']),
  ...retestLines(SAMPLE_REPORT),
].filter(Boolean));
