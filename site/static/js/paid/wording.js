// wording.js — the paid report's sentences for DT-2 of the donttrade test (method 2026-10-30.stats3):
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

export const METHOD_VERSION = '2026-10-30.stats3';
export const METHOD_LABEL = 'DT-2';

// The promise the engine's Clear cut is set for (addendum Lever 6, owner decision §7: the two-look line). With Clear at
// this cut on both runs, a Clear sign on any habit turns up at most PER_100 in 100 times across a first report and its
// re-test together, on histories with no real habit. The page states that promise only for a report whose Clear cut is
// this one; a report with another cut is refused (checkReport), so the promise can never drift from the engine.
export const TWO_LOOK = Object.freeze({ clear_cut: 0.029, per_100: 5 });

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
export function stepOf(h, cuts) {
  if (!(Number.isFinite(h.effect) && h.effect < 0)) return 'none';
  return h.p_holm <= cuts[0] + CUT_TOL ? 'clear' : h.p_holm <= cuts[1] + CUT_TOL ? 'some' : 'none';
}
export const chancePer100 = (p) => Math.max(1, Math.ceil(100 * p - 1e-9));

function fail(why) {
  throw new Error(`wording: ${why} (DT-2)`);
}

export function checkMethod(report) {
  if (!report || report.method_version !== METHOD_VERSION) fail(`report method ${report && report.method_version} is not ${METHOD_VERSION}`);
  if (report.method_label !== METHOD_LABEL) fail(`report label ${report.method_label} is not ${METHOD_LABEL}`);
  const c = report.step_cuts;
  if (!Array.isArray(c) || c.length !== 2 || !(c[0] > 0 && c[0] < c[1] && c[1] < 1)) fail(`step cuts ${JSON.stringify(c)}`);
  if (Math.abs(c[0] - TWO_LOOK.clear_cut) > CUT_TOL) fail(`the Clear cut ${c[0]} is not the two-look cut ${TWO_LOOK.clear_cut} the page's promise is for`);
  if (!Number.isInteger(report.n_family) || report.n_family < CHECKED.length) fail(`n_family ${report.n_family}`);
  if (!Number.isInteger(report.min_group) || report.min_group < 1) fail(`min_group ${report.min_group}`);
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

function checkCatch(h, report) {
  const c = h.catch;
  if (c === null) {
    if (h.status === 'tested' && report.n_trades <= report.catch_max_trades) fail(`${h.id} is checked on ${report.n_trades} trades with no catch figure`);
    return;
  }
  if (!CHECKED.includes(h.id) || report.dates_only || report.n_trades > report.catch_max_trades) fail(`${h.id} has a catch figure it cannot have`);
  const ok = c && Array.isArray(c.sizes) && c.sizes.length >= 1 && c.sizes.length <= 3 && c.sizes[0] === report.n_trades
    && c.sizes.every((s, j) => Number.isInteger(s) && (j === 0 || s > c.sizes[j - 1]))
    && Array.isArray(c.at_least_10ths) && c.at_least_10ths.length === c.sizes.length
    && c.at_least_10ths.every((t) => Number.isInteger(t) && t >= 0 && t <= 10)
    && Array.isArray(c.caught) && c.caught.length === c.sizes.length && Number.isInteger(c.reps) && c.reps >= 1
    && c.caught.every((x, j) => Number.isInteger(x) && x >= 0 && x <= c.reps && c.at_least_10ths[j] <= Math.floor((10 * x) / c.reps))
    && Number.isInteger(c.n_perm) && c.effect && Number.isFinite(c.effect.amount) && c.effect.amount >= 0 && c.effect.unit === report.currency;
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
    for (const k of ['p_raw', 'p_holm', 'step', 'chance_per_100']) {
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
      if (!['none', 'some', 'clear'].includes(h.step) || h.step !== stepOf(h, cuts)) fail(`${h.id} has step ${h.step} but p_holm ${h.p_holm} and effect ${h.effect}`);
      if (h.chance_per_100 !== chancePer100(h.p_holm)) fail(`${h.id} has chance ${h.chance_per_100} but p_holm ${h.p_holm}`);
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

// §2.4 step lines. N is the habit's chance_per_100 (rounded up, so "at most" stays true); below 1 in 100 it says so.
const chancePhrase = (h) => (h.p_holm < 0.01 ? 'fewer than 1 in 100 times' : `at most ${h.chance_per_100} in 100 times`);
export function stepLine(h, report, fmt) {
  const n = fmtOf(fmt).count(report.n_trades), m = report.n_family;
  const tail = `In files with no real habit, a result this strong turns up ${chancePhrase(h)}, allowing for all ${m} habits at once.`;
  if (h.step === 'clear') return `Clear sign of this habit in these ${n} trades. ${tail}`;
  if (h.step === 'some') return `Some sign of this habit in these ${n} trades, short of clear. ${tail}`;
  if (h.step === 'none') return `No sign of this habit in these ${n} trades.`;
  return fail(`${h.id} has no step line for ${h.step}`);
}
// §2.4 guard line, under every Some sign and Clear sign number.
export const GUARD_LINE = 'This counts how often chance alone does this. It is not the chance your habit is real.';

// §5.2 the catch line, under every No sign and Some sign.
const CATCH_CLAUSE = { revenge: 'trades soon after a loss end', tilt: 'trades after 2 or more losses in a row end' };
const tenths = (t) => (t >= 1 ? `at least ${t} in 10` : 'fewer than 1 in 10');
export function catchLine(h, report, fmt) {
  const f = fmtOf(fmt), c = h.catch;
  if (c === null) {
    if (report.n_trades > report.catch_max_trades) return catchOver(f.count(report.catch_max_trades));
    return fail(`${h.id} has no catch figure`);
  }
  if (!(c.effect.amount > 0)) return CATCH_FLAT;
  const rows = c.sizes.map((s, j) => (j === 0 ? `files of ${f.count(s)} trades show it as a Clear sign ${tenths(c.at_least_10ths[j])} times`
    : `${f.count(s)} trades ${tenths(c.at_least_10ths[j])}`));
  const list = rows.length === 1 ? rows[0] : rows.length === 2 ? `${rows[0]}, and ${rows[1]}` : `${rows[0]}, ${rows[1]}, and ${rows[2]}`;
  return `If your next trades look like these: when ${CATCH_CLAUSE[h.id]} ${f.amount(c.effect.amount)} worse each, ${list}.`;
}
export const catchOver = (max) => `Files over ${max} trades get no catch figure.`;
export const CATCH_FLAT = 'Every trade in this file has the same result, so it gets no catch figure.';

// §5.2 Expert text: the premise in full, and the counts behind each figure.
export function catchHow(h, fmt) {
  const f = fmtOf(fmt), c = h.catch;
  if (!c || !(c.effect.amount > 0)) return null;
  return `How the catch figure is worked out: we reshuffled your own results so no habit was left in them, added a habit of ${f.amount(c.effect.amount)} a trade (half the spread of your results), and extended the file by repeating its own trading days. Each figure is the lowest share that ${f.count(c.reps)} such files support at 95% confidence, with ${f.count(c.n_perm)} reshuffles each, at the strictest level a Clear sign can need.`;
}

// Plan §10 row 37 (Expert): the raw reshuffle count and the adjusted p.
export function expertLine(h, report, fmt) {
  if (h.status !== 'tested') return null;
  const f = fmtOf(fmt), N = h.n_perm, c = Math.max(0, Math.round(h.p_raw * (N + 1)) - 1);
  return `${f.count(c)} of ${f.count(N)} reshuffles of your own results came out at least this one-sided (one-sided p = ${h.p_raw.toPrecision(3)}). Allowing for ${report.n_family} habits (Holm): ${h.p_holm.toPrecision(3)}.`;
}

// Plan §10 row 19: the method line, with the habit's own permutation count.
export function methodLine(h, fmt) {
  if (h.status !== 'tested') return null;
  const n = fmtOf(fmt).count(h.n_perm);
  const tail = 'It counts as a sign only when both the average result and how often a result was the worse one point the habit’s way.';
  if (h.id === 'revenge') return `Compared with your other trades from the same day, matched on whether another trade had closed in the 15 minutes before it opened and whether another trade opened in the 15 minutes after it closed. The results were reshuffled within each day ${n} times (days with a single trade are grouped with nearby such days). ${tail}`;
  if (h.id === 'tilt') return `Compared with your other trades from the same day. The results were reshuffled within each day ${n} times (days with a single trade are grouped with nearby such days). ${tail}`;
  return fail(`methodLine: ${h.id} is not checked`);
}

// T-3 T3-C (kept): in a dates-only file, holds are counted from dates.
export function holdDays(s) {
  const d = s / 86400;
  const t = Number.isInteger(d) ? String(d) : d.toFixed(1);
  return t === '1' ? '1 day' : `${t} days`;
}
export const SAME_DATE_LINE = 'In this file, a trade with dates but no times that opened and closed on the same date counts as 0 days.';

// The lines of one habit, split by layer: what (under "What happened", the fact line first) and check (under
// "Habit or chance?": the step line, the guard line, the catch line; or the too-few or dates-only line).
export function habitLines(h, report, fmt) {
  checkReport(report);
  const f = fmtOf(fmt), what = [], check = [];
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
      if (h.step !== 'clear') check.push(catchLine(h, report, f));
    }
  } else if (h.id !== 'oversized_loss') {   // large losses: report.js shows its measures list
    fail(`habitLines: ${h.id} has no sentences`);
  }
  return { what, check };
}

// ---------------------------------------------------------------- page 1 (plan §10 rows 22–28)

export const noneChecked = (min) => `Too few trades to check any habit in this file: each check needs at least ${min} trades in both groups it compares.`;
export function noSignLine(nTested, n) {
  if (nTested === 1) return `No sign of the habit checked in these ${n} trades.`;
  if (nTested === 2) return `No sign of either habit checked in these ${n} trades.`;
  return `No sign of any of the ${nTested} habits checked in these ${n} trades.`;
}
export const CATCH_INTRO = 'Each habit below shows how often files of this size catch a habit of a stated dollar size.';
export const stepsLine = (k, j, m) => `Clear sign on ${k} of ${m} habits, some sign on ${j}. The steps allow for all ${m} habits at once: in files with no real habit, a Clear sign on any habit turns up at most ${TWO_LOOK.per_100} in 100 times, counting a first report and its re-test together.`;
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
  const lines = [stepsLine(k, j, m)];
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

export const RETEST_TWO_LOOK = `This re-test checks a longer history that includes your first file. Across a first report and its re-test, a Clear sign on a history with no real habit turns up at most ${TWO_LOOK.per_100} in 100 times.`;
export const STEPS_MOVE = 'Steps can move between runs by chance alone.';
export const RETEST_DT1 = 'A first report made with DT-1 of the donttrade test gave two results per habit; this re-test uses the three steps of DT-2, so the two are not directly comparable.';
export const retestLines = () => [RETEST_TWO_LOOK, STEPS_MOVE, RETEST_DT1];

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
  catch: { sizes: [120, 240, 480], at_least_10ths: [0, 3, 5], caught: [8, 27, 39], reps: 60, n_perm: 199, effect: { unit: 'USD', amount: 7.2 } } };
const SAMPLE_REPORT = { n_trades: 120, n_family: 3, catch_max_trades: 5000 };
const SAMPLE_FMT = { amount: (x) => `$${x.toFixed(2)}`, count: (n) => n.toLocaleString('en-US') };
export const VERDICT_STRINGS = Object.freeze([
  ...Object.values(STEP), CHECK_HEADING,
  stepLine({ ...SAMPLE, step: 'clear', chance_per_100: 3, p_holm: 0.025 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'clear', chance_per_100: 1, p_holm: 0.004 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'some', chance_per_100: 14, p_holm: 0.14 }, SAMPLE_REPORT, SAMPLE_FMT),
  stepLine({ ...SAMPLE, step: 'none', chance_per_100: 100, p_holm: 1 }, SAMPLE_REPORT, SAMPLE_FMT),
  GUARD_LINE,
  catchLine(SAMPLE, SAMPLE_REPORT, SAMPLE_FMT),
  catchLine({ ...SAMPLE, id: 'tilt', catch: { ...SAMPLE.catch, sizes: [2000, 4000], at_least_10ths: [4, 7], caught: [30, 50] } }, SAMPLE_REPORT, SAMPLE_FMT),
  catchLine({ ...SAMPLE, catch: { ...SAMPLE.catch, sizes: [3000], at_least_10ths: [6], caught: [45] } }, SAMPLE_REPORT, SAMPLE_FMT),
  catchOver('5,000'), CATCH_FLAT, catchHow(SAMPLE, SAMPLE_FMT), expertLine(SAMPLE, SAMPLE_REPORT, SAMPLE_FMT),
  methodLine(SAMPLE, SAMPLE_FMT), methodLine({ ...SAMPLE, id: 'tilt' }, SAMPLE_FMT),
  tooFewLine('3', '116', 5), vDatesOnly('All 200 trades in this file'), datesP1('12 of the 200 trades in this file', 3),
  noneChecked(5), noSignLine(1, '120'), noSignLine(2, '120'), noSignLine(3, '120'), CATCH_INTRO, stepsLine(1, 0, 3), stepsLine(0, 2, 3),
  NO_FOCUS, focusLine('Re-entering soon after a loss', "Trades opened within 15 minutes of a losing trade's close", '−$500.00'),
  focusNone('Re-entering soon after a loss', "trades opened within 15 minutes of a losing trade's close"),
  focusGain('Re-entering soon after a loss', "trades opened within 15 minutes of a losing trade's close", '+$120.00'),
  coverageHead(2, 3, 5), tooFewNames(['Trading after a losing streak']), SIZE_UP_FACTS, FACTS_LINE,
  fewJoin([fewPart('Trading after a losing streak', 'tilt', '4', '26', 5), fewPart('Re-entering soon after a loss', 'revenge', '0', '30', 5)]),
  retestRow(CATCH_CLAUSE.tilt, '$7.20', ['60 trades show it as a Clear sign at least 2 in 10 times', '120 trades show it as a Clear sign fewer than 1 in 10 times']),
  ...retestLines(),
].filter(Boolean));
