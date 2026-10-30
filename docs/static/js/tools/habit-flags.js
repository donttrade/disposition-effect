// habit-flags.js — "Habits on breach days" for the Challenge Readiness Check (§2.3). Pure: no DOM,
// no I/O. Mirrored by tests/reference/readiness_ref.py.
//
// Four habits, with the paid report's definitions and labels (dt-private src/core/habits.mjs), on
// that engine's clock: a trade opens at its open time to the minute and closes at open + hold.
// P&L is taken to the cent and size as a multiple of the symbol's median size (3 dp), as in
// paid/strip.js, so a file gives the same counts here as in the report.
//   reentry          opened within 900 s after the close of a losing trade (not itself):
//                    0 <= open − loss close <= 900 (the paid report's revenge group)
//   streak           the last trade closed at or before its open ended a run of 2 or more
//                    losses (the paid report's tilt group)
//   size_after_loss  the last trade closed at or before its open was a loss, and its size is 1.5
//                    times the symbol's median size or more
//   large_loss       a loss larger than 2 × the file's median loss
// Difference from the report, kept on purpose: the report first merges rows that share symbol,
// direction and open minute; here every trade keeps its own flags, so they line up with the P&L the
// simulation replays. Files without such rows give identical counts (tests/test_readiness_engine.py).
// Dates-only files (5% or more of the trades open at 00:00 and are held whole days): reentry and
// size_after_loss are not described.
//
// Presence is counted, not cause: breach days have more losses, so habits tied to losses appear
// there more often by design. The baseline is the trader's other losing days.

import { median } from '../engine/noise.js?v=d0f6a787';

export const HABITS = Object.freeze(['reentry', 'streak', 'size_after_loss', 'large_loss']);
export const BIT = Object.freeze({ reentry: 1, streak: 2, size_after_loss: 4, large_loss: 8 });
export const NEEDS_TIMES = Object.freeze(['reentry', 'size_after_loss']);
export const REENTRY_S = 900;
export const STREAK_N = 2;
export const SIZE_X = 1.5;
export const LARGE_X = 2;
export const DATES_ONLY_SHARE = 0.05;
export const MIN_BREACH_DAYS = 5;
export const MIN_BUSTS = 30;
export const HIT_POINTS = 10;   // pill-hit: the breach-day share is 10 points or more above the baseline

export const HABIT_TEXT = Object.freeze({
  heading: 'Habits on breach days',
  reentry: 'Re-entering soon after a loss',
  streak: 'Trading after a losing streak',
  size_after_loss: 'Size after a loss',
  large_loss: 'Losses much larger than your usual loss',
  not_described: 'Not described for files with dates but no times',
  few: 'Too few breach days to describe',
  by_design: 'Breach days have more losses, so habits tied to losses appear there more often by design.',
});

const roundHalfAway = (x) => Math.floor(Math.abs(x) + 0.5) * (x >= 0 ? 1 : -1);
const round2 = (x) => roundHalfAway(x * 100) / 100;
const round3 = (x) => roundHalfAway(x * 1000) / 1000;
const holdOf = (t) => (t.hold_s === undefined ? Math.floor((t.close_ts - t.open_ts) / 1000) : t.hold_s);

// Engine trades → the report's items {open, close, p, q} (seconds; P&L to the cent; relative size).
export function itemsFromTrades(trades) {
  const bySym = new Map();
  for (const t of trades) {
    if (!bySym.has(t.symbol)) bySym.set(t.symbol, []);
    bySym.get(t.symbol).push(t.qty);
  }
  const med = new Map([...bySym].map(([s, qs]) => [s, median(qs)]));
  return trades.map((t) => {
    const open = 60 * Math.floor(t.open_ts / 60000);
    const m = med.get(t.symbol);
    return { open, close: open + holdOf(t), p: round2(t.pnl), q: m > 0 ? round3(t.qty / m) : 0 };
  });
}

export function isDatesOnly(trades) {
  let k = 0;
  for (const t of trades) if (t.open_ts % 86400000 === 0 && holdOf(t) % 86400 === 0) k++;
  return trades.length > 0 && 20 * k >= trades.length;
}

function bisectRight(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (x < a[m]) hi = m; else lo = m + 1; } return lo; }
function bisectLeft(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; }

// items: [{open, close, p, q}] → Uint8Array of BIT flags, one per item (in the items' order).
export function habitFlags(items, opts = {}) {
  const datesOnly = !!opts.datesOnly;
  const n = items.length;
  const flags = new Uint8Array(n);
  const it = items.map((t, i) => ({ ...t, i }));
  const byClose = it.slice().sort((a, b) => (a.close - b.close) || (a.open - b.open) || (a.i - b.i));
  const byOpen = it.slice().sort((a, b) => (a.open - b.open) || (a.close - b.close) || (a.i - b.i));
  const closes = byClose.map((t) => t.close);
  const streak = [];
  let run = 0;
  for (const t of byClose) { run = t.p < 0 ? run + 1 : 0; streak.push(run); }
  const lossItems = byClose.filter((t) => t.p < 0);
  const lc = lossItems.map((t) => t.close);
  const prior = (t) => {
    let k = bisectRight(closes, t.open) - 1;
    while (k >= 0 && byClose[k].i === t.i) k--;
    return k;
  };
  byOpen.forEach((t, pos) => {
    const k = prior(t);
    if (k >= 0 && streak[k] >= STREAK_N) flags[t.i] |= BIT.streak;
    if (datesOnly) return;
    if (pos > 0) {   // as the report: the first trade by open has nothing before it
      for (let m = bisectLeft(lc, t.open - REENTRY_S); m < lc.length && lc[m] <= t.open; m++) {
        if (lossItems[m].i !== t.i) { flags[t.i] |= BIT.reentry; break; }
      }
    }
    if (k >= 0 && byClose[k].p < 0 && t.q >= SIZE_X) flags[t.i] |= BIT.size_after_loss;
  });
  const med = median(lossItems.map((t) => -t.p));
  if (med !== null) for (const t of lossItems) if (-t.p > LARGE_X * med) flags[t.i] |= BIT.large_loss;
  return flags;
}

export function countFlags(flags) {
  const c = { reentry: 0, streak: 0, size_after_loss: 0, large_loss: 0 };
  for (const f of flags) for (const h of HABITS) if (f & BIT[h]) c[h]++;
  return c;
}

// Per-trade flags → per day, aligned with groupDays(trades).days (index: groupDays().index).
export function dayFlags(flags, index) {
  return index.map((ix) => Uint8Array.from(ix, (i) => flags[i]));
}

const orUpTo = (f, last) => { let m = 0; for (let i = 0; i <= last; i++) m |= f[i]; return m; };

function status(share, base, n, min, datesOnly, h) {
  if (datesOnly && NEEDS_TIMES.includes(h)) return 'not_described';
  if (n < min || share === null || base === null) return 'few';
  return 100 * (share - base) >= HIT_POINTS - 1e-9 ? 'hit' : 'muted';
}

// View 2, real days: a daily-limit breach day is a file day whose running closed-trade P&L reaches
// −daily_loss. Per habit: breach days with it on a trade up to and including the breaching trade,
// against the other losing days with it on any trade.
export function realBreachDays(days, flagsByDay, dailyLoss, opts = {}) {
  const breach = [], other = [];
  if (dailyLoss !== null && dailyLoss !== undefined) {
    days.forEach((d, j) => {
      let run = 0, at = -1;
      for (let i = 0; i < d.length; i++) { run += d[i]; if (run <= -dailyLoss) { at = i; break; } }
      if (at >= 0) breach.push([j, at]);
    });
  }
  const isBreach = new Set(breach.map(([j]) => j));
  days.forEach((d, j) => {
    if (isBreach.has(j)) return;
    let s = 0;
    for (const x of d) s += x;
    if (s < 0) other.push(j);
  });
  const out = { n_breach: breach.length, n_other_losing: other.length, breach_days: breach.map(([j]) => j), habits: {} };
  for (const h of HABITS) {
    const b = BIT[h];
    const nb = breach.filter(([j, at]) => orUpTo(flagsByDay[j], at) & b).length;
    const no = other.filter((j) => orUpTo(flagsByDay[j], flagsByDay[j].length - 1) & b).length;
    const share = breach.length ? nb / breach.length : null;
    const base = other.length ? no / other.length : null;
    out.habits[h] = { on_breach: nb, on_other_losing: no, share, base,
      status: status(share, base, breach.length, MIN_BREACH_DAYS, opts.datesOnly, h) };
  }
  return out;
}

// View 1, simulated paths: per habit, the share of busts whose source day had it on a trade up to
// and including the breaching trade, against the share of all drawn losing days that had it.
export function simulatedHabits(res, flagsByDay, opts = {}) {
  const out = { busts: res.bust, drawn_losing: 0, habits: {} };
  let drawn = 0;
  for (const c of res.drawn_losing) drawn += c;
  out.drawn_losing = drawn;
  for (const h of HABITS) {
    const b = BIT[h];
    let nb = 0, nl = 0;
    for (const [j, at, c] of res.bust_at) if (orUpTo(flagsByDay[j], at) & b) nb += c;
    res.drawn_losing.forEach((c, j) => { if (c && (orUpTo(flagsByDay[j], flagsByDay[j].length - 1) & b)) nl += c; });
    const share = res.bust ? nb / res.bust : null;
    const base = drawn ? nl / drawn : null;
    out.habits[h] = { on_busts: nb, on_drawn_losing: nl, share, base,
      status: status(share, base, res.bust, MIN_BUSTS, opts.datesOnly, h) };
  }
  return out;
}
