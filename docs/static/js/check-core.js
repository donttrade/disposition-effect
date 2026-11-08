// check-core.js: the free check's COUNTS, nothing else. Pure (no DOM, no network, no storage).
// A port of the report server's grouping (dt2-private src/core/habits.mjs, method 2026-10-23.stats2f) so the count shown
// before payment is the count the report uses: mergeRows (rows with one symbol, direction and open minute are one trade),
// date-only detection, the groups of the five habits, the size of each set the report totals, MIN_GROUP, the 20,000-row cap
// and the 10-year span (those two are paid/strip.js toRows, the same function the report sends rows with).
// It has no test against chance, no verdict and no money function, on purpose: tests/test_check_core.py checks that.
// Every figure is a whole number of trades.

import { toRows } from './paid/strip.js?v=ae765086';

export const MIN_GROUP = 30;
export const MIN_ROWS = 30;
const REVENGE_S = 900;
export const HABIT_IDS = Object.freeze(['hold_gap', 'revenge', 'size_up', 'tilt', 'oversized_loss']);
const isDateOnlyRow = (r) => r.o % 1440 === 0 && r.h % 86400 === 0;

function med(xs) {
  const n = xs.length;
  if (!n) return null;
  const a = Float64Array.from(xs).sort();
  const k = n >> 1;
  return n % 2 ? a[k] : (a[k - 1] + a[k]) / 2;
}

function bisectRight(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (x < arr[m]) hi = m; else lo = m + 1; } return lo; }
function bisectLeft(arr, x) { let lo = 0, hi = arr.length; while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] < x) lo = m + 1; else hi = m; } return lo; }

// rows sharing (s, d, o) become one trade; a date-only row never merges. Sums in integer cents and thousandths.
function mergeRows(rows) {
  const at = new Map(), groups = [];
  for (const [i, r] of rows.entries()) {
    const k = isDateOnlyRow(r) ? 'date-only:' + i : r.s + ':' + r.d + ':' + r.o;
    const j = at.get(k);
    if (j === undefined) { at.set(k, groups.length); groups.push([r]); } else groups[j].push(r);
  }
  return groups.map((g) => {
    if (g.length === 1) return g[0];
    let cents = 0, thou = 0, h = g[0].h;
    for (const r of g) { cents += Math.round(r.p * 100); thou += Math.round(r.q * 1000); if (r.h > h) h = r.h; }
    return { o: g[0].o, h, d: g[0].d, q: thou / 1000, p: cents / 100, s: g[0].s };
  });
}

function prepare(rows) {
  const items = rows.map((r, i) => ({ i, open: 60 * r.o, close: 60 * r.o + r.h, h: r.h, q: r.q, p: r.p }));
  const byClose = items.slice().sort((a, b) => (a.close - b.close) || (a.open - b.open) || (a.i - b.i));
  const byOpen = items.slice().sort((a, b) => (a.open - b.open) || (a.close - b.close) || (a.i - b.i));
  const closes = byClose.map((t) => t.close);
  const streak = [];
  let run = 0;
  for (const t of byClose) { run = t.p < 0 ? run + 1 : 0; streak.push(run); }
  return { byClose, byOpen, closes, streak };
}

function priorIndex(t, byClose, closes) {
  let k = bisectRight(closes, t.open) - 1;
  while (k >= 0 && byClose[k].i === t.i) k--;
  return k;
}

const cell = (a, b, set) => ({ n_a: a, n_b: b, n_set: set, enough: Math.min(a, b) >= MIN_GROUP });

function holdGap(byClose) {
  const losers = byClose.filter((t) => t.p < 0);
  const winners = byClose.filter((t) => t.p > 0);
  const mb = med(winners.map((t) => t.h));
  return cell(losers.length, winners.length, losers.filter((t) => mb !== null && t.h > mb).length);
}

function revenge(byOpen, byClose) {
  const lossCloses = byClose.filter((t) => t.p < 0);
  const lc = lossCloses.map((t) => t.close);
  let a = 0, b = 0;
  byOpen.forEach((t, k) => {
    if (k === 0) return;
    let m = bisectLeft(lc, t.open - REVENGE_S);
    let hit = false;
    while (m < lc.length && lc[m] <= t.open) {
      if (lossCloses[m].i !== t.i) { hit = true; break; }
      m++;
    }
    if (hit) a++; else b++;
  });
  return cell(a, b, a);
}

function sizeUp(byOpen, byClose, closes) {
  let a = 0, b = 0, set = 0;
  for (const t of byOpen) {
    const k = priorIndex(t, byClose, closes);
    if (k < 0) continue;
    const pp = byClose[k].p;
    if (pp < 0) { a++; if (t.q >= 1.5) set++; } else if (pp > 0) b++;
  }
  return cell(a, b, set);
}

function tilt(byOpen, byClose, closes, streak) {
  let a = 0, b = 0;
  for (const t of byOpen) {
    const k = priorIndex(t, byClose, closes);
    if (k < 0) continue;
    if (streak[k] >= 2) a++; else b++;
  }
  return cell(a, b, a);
}

function oversized(byClose) {
  const losses = byClose.filter((t) => t.p < 0);
  const m = med(losses.map((t) => -t.p));
  const big = losses.filter((t) => m !== null && -t.p > 2 * m).length;
  return cell(big, losses.length, big);
}

// rows: toRows(trades).rows (fields o, h, d, q, p, s). Returns whole numbers of trades only:
//   n_rows, n_trades, n_merged (rows folded into another), dates_only, n_date_only, below_min_rows,
//   habits[id] = {n_a, n_b, n_set, enough}: the two groups the report compares, the size of the set the report totals, and
//   whether both groups reach MIN_GROUP. A dates-only file has no merge, and revenge, tilt and size_up have no set (null).
// Which habits the report tests is a separate fact: testable[] lists those with enough trades in both groups (never in a
// dates-only file).
export function countRows(rows) {
  const nDate = rows.reduce((k, r) => k + (isDateOnlyRow(r) ? 1 : 0), 0);
  const datesOnly = rows.length > 0 && 20 * nDate >= rows.length;
  const used = datesOnly ? rows : mergeRows(rows);
  const { byClose, byOpen, closes, streak } = prepare(used);
  const habits = {
    hold_gap: holdGap(byClose),
    revenge: revenge(byOpen, byClose),
    size_up: sizeUp(byOpen, byClose, closes),
    tilt: tilt(byOpen, byClose, closes, streak),
    oversized_loss: oversized(byClose),
  };
  if (datesOnly) for (const id of ['revenge', 'tilt', 'size_up']) habits[id].n_set = null;
  const testable = datesOnly ? [] : ['revenge', 'tilt'].filter((id) => habits[id].enough);
  return { n_rows: rows.length, n_trades: used.length, n_merged: rows.length - used.length, dates_only: datesOnly, n_date_only: nDate,
    below_min_rows: rows.length < MIN_ROWS, habits, testable };
}

// trades: ParseResult.trades. Applies the same span and 20,000-row cap as the report, then counts.
export function countTrades(trades) {
  const r = toRows(trades, (n) => Array.from({ length: n }, (_, i) => i));
  return { ...countRows(r.rows), limited: r.limited, span_left_out: r.span_left_out };
}
