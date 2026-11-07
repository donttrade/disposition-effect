// bad-day-core.js — the counting behind /tools/bad-day-check/. Pure functions, no DOM, so the tests import this module directly
// and tests/reference/bad_day_ref.py checks it against an independent Python version.
//
// One or more days of the visitor's file, set beside the visitor's own typical day. Every number is a count or a sum taken from the
// file; nothing is scored, tested or judged. The four habit counts are the habit-flags.js definitions the Challenge Readiness Check
// uses (re-entry within 15 minutes of a loss, a trade after 2 or more losses, a bigger size after a loss, a loss over 2 times the
// median loss), computed on the whole file first so a day's first trades see the losses of the day before.
//
// A trade belongs to the day it CLOSED (as /tools/days.js and the journal). Engine times are naive wall-clock; shiftHours moves
// every time by whole hours before the day is cut (an MT5 report is in the broker's server time).
//   typical day  = for each measure, the median over the file's other days that have trades; shown only with at least
//                  MIN_OTHER_DAYS such days (below that a median says nothing).

import { itemsFromTrades, habitFlags, isDatesOnly, BIT } from './habit-flags.js';
import { median } from '../engine/noise.js';

export const MIN_OTHER_DAYS = 10;
export const MAX_DAYS = 5;
const HOUR_MS = 3600000;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

export const MEASURES = Object.freeze([
  { key: 'n', label: 'Trades', times: false },
  { key: 'net', label: 'Net result', times: false },
  { key: 'largest_loss', label: 'Largest loss', times: false },
  { key: 'reentry', label: 'Trades opened within 15 minutes of a loss', times: true },
  { key: 'streak', label: 'Trades opened after 2 or more losses in a row', times: false },
  { key: 'size_after_loss', label: 'Trades at 1.5 times usual size or more, right after a loss', times: true },
  { key: 'large_loss', label: 'Losses over 2 times your median loss', times: false },
]);

const dayOf = (ts, shiftHours) => new Date(ts + shiftHours * HOUR_MS).toISOString().slice(0, 10);
const valid = (s) => ISO_DAY.test(s) && !Number.isNaN(Date.parse(s + 'T00:00:00Z')) && new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) === s;

// "2026-11-05, 2026-11-06" → ['2026-11-05', '2026-11-06']. Dates only; anything else is dropped; at most MAX_DAYS; no repeats.
export function parseDays(text) {
  const out = [];
  for (const part of String(text || '').split(/[,\s;]+/)) {
    if (valid(part) && !out.includes(part)) out.push(part);
    if (out.length === MAX_DAYS) break;
  }
  return out;
}

const cents = (x) => Math.round(x * 100) / 100;

// trades: engine trades. Returns {days: Map date → row, order: [dates], datesOnly}.
export function perDay(trades, shiftHours = 0) {
  const items = itemsFromTrades(trades);
  const datesOnly = isDatesOnly(trades);
  const flags = habitFlags(items, { datesOnly });
  const days = new Map();
  trades.forEach((t, i) => {
    const d = dayOf(t.close_ts, shiftHours);
    let r = days.get(d);
    if (!r) { r = { date: d, n: 0, net: 0, largest_loss: 0, reentry: 0, streak: 0, size_after_loss: 0, large_loss: 0 }; days.set(d, r); }
    r.n++;
    r.net += t.pnl;
    if (t.pnl < 0 && -t.pnl > r.largest_loss) r.largest_loss = -t.pnl;
    const f = flags[i];
    if (f & BIT.reentry) r.reentry++;
    if (f & BIT.streak) r.streak++;
    if (f & BIT.size_after_loss) r.size_after_loss++;
    if (f & BIT.large_loss) r.large_loss++;
  });
  for (const r of days.values()) { r.net = cents(r.net); r.largest_loss = cents(r.largest_loss); }
  return { days, order: [...days.keys()].sort(), datesOnly };
}

// requested: ISO dates (may be empty). Empty or none-with-trades → the day with the lowest net result.
export function badDay(trades, { shiftHours = 0, requested = [] } = {}) {
  const { days, order, datesOnly } = perDay(trades, shiftHours);
  const missing = requested.filter((d) => !days.has(d));
  let chosen = requested.filter((d) => days.has(d));
  let fellBack = false;
  if (!chosen.length && order.length) {
    let worst = order[0];
    for (const d of order) if (days.get(d).net < days.get(worst).net) worst = d;
    chosen = [worst];
    fellBack = true;
  }
  const others = order.filter((d) => !chosen.includes(d));
  const typical = {};
  const enough = others.length >= MIN_OTHER_DAYS;
  if (enough) for (const m of MEASURES) typical[m.key] = median(others.map((d) => days.get(d)[m.key]));
  return {
    datesOnly, shiftHours, requested, missing, fellBack,
    chosen: chosen.map((d) => days.get(d)), n_days: order.length, n_other: others.length,
    typical: enough ? typical : null, first_day: order[0] || null, last_day: order[order.length - 1] || null,
  };
}
