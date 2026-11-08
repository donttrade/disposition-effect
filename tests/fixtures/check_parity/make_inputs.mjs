// make_inputs.mjs: the trade lists behind tests/fixtures/check_parity/*.json (the free check's parity fixtures).
//
// TEST FIXTURES ONLY. Never shown to a visitor, never shipped in docs/. Every list is either
//   * built here from a seeded generator (clearly synthetic: symbols "T1"..., prices and sizes made up), or
//   * the real public-data file checks/real_data/real-trades.coded.csv (Mendeley Stock Transactions Dataset,
//     CC BY 4.0, tickers replaced by codes), read with the browser engine's own parser.
// The private repo's tools/export_check_fixtures.mjs imports buildFixtures() from here, runs the server's analyse()
// on the rows these trades give (via paid/strip.js toRows) and writes ONLY the group counts next to this file.
// A Trade is the engine's shape: {id, symbol, dir, open_ts (ms), close_ts (ms), hold_s, qty, pnl, pnl_unit}.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFile } from '../../../site/static/js/engine/index.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MIN = 60000;
const DAY = 86400000;
export const MONDAY = Date.UTC(2026, 0, 5); // 2026-01-05 00:00 UTC, a Monday

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const cents = (x) => Math.round(x * 100) / 100;

function mk(id, symbol, dir, openTs, holdS, qty, pnl) {
  return { id: 't' + id, symbol, dir, open_ts: openTs, close_ts: openTs + holdS * 1000, hold_s: holdS, qty, pnl: cents(pnl),
    pnl_unit: 'USD' };
}

const byClose = (ts) => ts.slice().sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts))
  .map((t, i) => ({ ...t, id: 't' + (i + 1) }));

const SYMS = [{ s: 'T1', q: 100 }, { s: 'T2', q: 10 }, { s: 'T3', q: 1 }];

// One person's weekdays: trades run one after another inside a day (a gap of at least a minute after each close, so no two
// trades share an open minute). After a loss the next trade tends to come sooner and a little bigger (so every habit is hit).
function sequential({ seed, n, perDay = [2, 8], syms = SYMS, start = MONDAY, lossRate = 0.5, holdMin = [1, 90], bigLoss = 0.1 }) {
  const rnd = mulberry32(seed);
  const out = [];
  let day = 0;
  let count = 0;
  while (count < n) {
    const dow = new Date(start + day * DAY).getUTCDay();
    if (dow !== 0 && dow !== 6) {
      const k = Math.min(n - count, perDay[0] + Math.floor(rnd() * (perDay[1] - perDay[0] + 1)));
      let t = start + day * DAY + (9 * 60 + 30) * MIN;
      let lastLoss = false;
      for (let j = 0; j < k; j++) {
        const sym = syms[Math.floor(rnd() * syms.length)];
        const loss = rnd() < lossRate;
        const gapM = lastLoss ? 1 + Math.floor(rnd() * 12) : 2 + Math.floor(rnd() * 40);
        t += gapM * MIN;
        const holdS = (holdMin[0] + Math.floor(rnd() * (holdMin[1] - holdMin[0] + 1))) * 60 + Math.floor(rnd() * 60);
        const mag = 5 + rnd() * 45;
        const pnl = loss ? -(rnd() < bigLoss ? mag * 5 : mag) : mag;
        const qty = Math.round(sym.q * (lastLoss && rnd() < 0.5 ? 1.5 + rnd() : 1) * 1000) / 1000;
        out.push(mk(0, sym.s, rnd() < 0.8 ? 'long' : 'short', t, holdS, qty, pnl));
        t += holdS * 1000;
        lastLoss = loss;
        count++;
      }
    }
    day++;
  }
  return byClose(out);
}

// Trades opened at random times of day, held up to hours: many open while another is still open.
function overlapping({ seed, n }) {
  const rnd = mulberry32(seed);
  const out = [];
  let day = 0;
  while (out.length < n) {
    const dow = new Date(MONDAY + day * DAY).getUTCDay();
    if (dow !== 0 && dow !== 6) {
      const k = 4 + Math.floor(rnd() * 5);
      for (let j = 0; j < k && out.length < n; j++) {
        const sym = SYMS[Math.floor(rnd() * SYMS.length)];
        const open = MONDAY + day * DAY + (9 * 60 + Math.floor(rnd() * 360)) * MIN + Math.floor(rnd() * 60) * 1000;
        const holdS = (5 + Math.floor(rnd() * 235)) * 60 + Math.floor(rnd() * 60);
        const loss = rnd() < 0.5;
        out.push(mk(0, sym.s, rnd() < 0.75 ? 'long' : 'short', open, holdS, sym.q, loss ? -(5 + rnd() * 60) : 5 + rnd() * 40));
      }
    }
    day++;
  }
  return byClose(out);
}

function partialFills() {
  const base = sequential({ seed: 202, n: 320 });
  const rnd = mulberry32(7);
  const extra = [];
  // 60 trades get a second or third fill that opens in the same minute with the same symbol and direction.
  for (let i = 5; i < base.length && extra.length < 70; i += 5) {
    const t = base[i];
    const minuteStart = Math.floor(t.open_ts / MIN) * MIN;
    const sib = (secOff, holdS, pnl, q) => mk(0, t.symbol, t.dir, minuteStart + secOff * 1000, holdS, q, pnl);
    extra.push(sib(Math.min(59, (t.open_ts - minuteStart) / 1000 + 7) % 60, t.hold_s + 30 * (1 + Math.floor(rnd() * 5)), rnd() < 0.5 ? -3 - rnd() * 10 : 2 + rnd() * 9, t.qty));
    if (i % 15 === 0) extra.push(sib(1, t.hold_s - 20 > 0 ? t.hold_s - 20 : 5, 4 + rnd() * 6, t.qty)); // a three-fill group
  }
  // Designed groups: win + loss that cancel to exactly 0.00, one that flips to a small loss, one to a small win.
  const d = base[base.length - 1];
  const at = d.close_ts + 3 * 3600000;
  const open = (k) => Math.floor((at + k * 30 * MIN) / MIN) * MIN;
  const designed = [
    mk(0, 'T2', 'long', open(0), 600, 10, 10), mk(0, 'T2', 'long', open(0) + 5000, 700, 10, -10), // cancels to 0.00 (neither win nor loss)
    mk(0, 'T2', 'long', open(1), 600, 10, 5), mk(0, 'T2', 'long', open(1) + 9000, 640, 10, -8), // net loss -3.00
    mk(0, 'T2', 'long', open(2), 600, 10, -2), mk(0, 'T2', 'long', open(2) + 2000, 640, 10, 6.5), // net win +4.50
    // not merged: same minute but another direction, and the same minute but another symbol
    mk(0, 'T1', 'long', open(3), 600, 100, -9), mk(0, 'T1', 'short', open(3) + 3000, 600, 100, -9), mk(0, 'T3', 'long', open(3) + 4000, 600, 1, -9),
  ];
  return byClose([...base, ...extra, ...designed]);
}

// A date-only row: opened at 00:00 UTC, held a whole number of days.
function dateOnlyRows({ seed, n, startIndex = 0, dupEvery = 0 }) {
  const rnd = mulberry32(seed);
  const out = [];
  let day = 0;
  while (out.length < n) {
    const dow = new Date(MONDAY + day * DAY).getUTCDay();
    if (dow !== 0 && dow !== 6) {
      const k = 1 + Math.floor(rnd() * 3);
      for (let j = 0; j < k && out.length < n; j++) {
        const sym = SYMS[Math.floor(rnd() * SYMS.length)];
        const holdDays = 1 + Math.floor(rnd() * 6);
        out.push(mk(0, sym.s, 'long', MONDAY + (startIndex + day) * DAY, holdDays * 86400, sym.q, rnd() < 0.5 ? -(5 + rnd() * 40) : 5 + rnd() * 30));
        if (dupEvery && out.length % dupEvery === 0 && out.length < n) {
          const l = out[out.length - 1];
          out.push(mk(0, l.symbol, l.dir, l.open_ts, l.hold_s, l.qty, -2.5)); // same symbol, direction and open day
        }
      }
    }
    day++;
  }
  return byClose(out);
}

// Timed trades with `k` date-only rows mixed in (n rows in all): 4 of 100 is not dates-only, 5 of 100 is.
function mixedDates(k, seed) {
  const n = 100;
  const timed = sequential({ seed, n: n - k, perDay: [2, 5] });
  const last = timed[timed.length - 1].close_ts;
  const startIdx = Math.ceil((last - MONDAY) / DAY) + 2;
  const dated = dateOnlyRows({ seed: seed + 1, n: k, startIndex: startIdx, dupEvery: 2 });
  return byClose([...timed, ...dated.slice(0, k)]);
}

function fewGroups() {
  // 45 trades, one a day or less, so very few follow a loss within 15 minutes or a losing run.
  return sequential({ seed: 55, n: 45, perDay: [1, 2], holdMin: [10, 120] }).map((t, i) => ({ ...t, id: 't' + (i + 1) }));
}

function zeroLosses() {
  return sequential({ seed: 66, n: 80, lossRate: 0 });
}

function cap20000() {
  const trades = sequential({ seed: 99, n: 20500, perDay: [24, 24], holdMin: [1, 6] });
  return trades;
}

function multiSymbolSize() {
  const syms = [{ s: 'FX1', q: 0.01 }, { s: 'FX2', q: 0.1 }, { s: 'EQ1', q: 100 }, { s: 'EQ2', q: 5000 }, { s: 'FUT1', q: 2 }];
  const t = sequential({ seed: 303, n: 380, syms });
  // Exactly 1.5 x a symbol's usual size, right after a loss: the >= 1.5 edge. FUT1's median size is 2, so 3 is 1.5.
  const edge = [];
  const last = t[t.length - 1];
  let open = Math.floor((last.close_ts + 20 * MIN) / MIN) * MIN;
  const pnls = [-10, -10, 8, -6, 7];
  for (let i = 0; i < pnls.length; i++) {
    edge.push(mk(0, 'FUT1', 'long', open, 240, i % 2 ? 3 : 2, pnls[i]));
    open += 20 * MIN;
  }
  // A symbol with a single trade (its size ratio is 1).
  edge.push(mk(0, 'ONE1', 'long', open + 30 * MIN, 300, 7, -4));
  return byClose([...t, ...edge]);
}

// 11 years of trades (the browser keeps the last 519 weeks) plus one held longer than 3,650 days.
function spanTrim() {
  const rnd = mulberry32(404);
  const out = [];
  const total = 11 * 365;
  for (let d = 0; d < total; d += 4) {
    const sym = SYMS[Math.floor(rnd() * SYMS.length)];
    const open = MONDAY + (d + 0) * DAY + (10 * 60 + Math.floor(rnd() * 200)) * MIN;
    const holdS = (30 + Math.floor(rnd() * 600)) * 60;
    const loss = rnd() < 0.5;
    out.push(mk(0, sym.s, 'long', open, holdS, sym.q, loss ? -(5 + rnd() * 40) : 5 + rnd() * 30));
  }
  const first = out[0];
  out.push(mk(0, 'T1', 'long', first.open_ts + 8 * DAY, 3651 * 86400, 100, 12)); // 3,651 days: left out
  return byClose(out);
}

function realPublic() {
  const f = path.join(HERE, '..', '..', '..', 'checks', 'real_data', 'real-trades.coded.csv');
  return parseFile(new Uint8Array(fs.readFileSync(f))).trades;
}

export function buildFixtures() {
  return {
    plain: sequential({ seed: 101, n: 360 }),
    partial_fills_merge: partialFills(),
    overlapping_trades: overlapping({ seed: 303, n: 300 }),
    dates_only: dateOnlyRows({ seed: 505, n: 120, dupEvery: 7 }),
    dates_mixed_4_of_100: mixedDates(4, 606),
    dates_mixed_5_of_100: mixedDates(5, 607),
    fewer_than_30_groups: fewGroups(),
    zero_losses: zeroLosses(),
    cap_20000_rows: cap20000(),
    multi_symbol_size: multiSymbolSize(),
    span_trim_519_weeks: spanTrim(),
    real_public_data: realPublic(),
  };
}
