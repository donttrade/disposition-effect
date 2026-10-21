// strip.js — turns parsed trades into StrippedRows, the ONLY trade data that ever
// leaves the browser (paid report only). Mirrors strip_rows() in engine_ref.py.
//
//   o  minutes from Monday 00:00 of the first trade's week (keeps weekday and hour, drops the date)
//   h  hold time, seconds
//   d  1 long / -1 short
//   q  size ÷ that symbol's median size in this file (3 dp): lots are never mixed across symbols
//   p  realised P&L (2 dp)
//   s  a per-request random index standing in for the symbol (the symbol text is never sent)
//   f  first 32 hex of SHA-256(salt|symbol|open_ts|close_ts|dir|qty_units|pnl_cents): stable for
//      this buyer across files, unlinkable by anyone without the salt (the server only HMACs it)
// Nothing else — no symbol, date, account, price or currency per row.

import { median } from '../engine/noise.js';

export const MAX_ROWS = 20000;
const DAY = 86400000;
const roundHalfAway = (x) => Math.floor(Math.abs(x) + 0.5) * (x >= 0 ? 1 : -1);
export const round3 = (x) => roundHalfAway(x * 1000) / 1000;
export const round2 = (x) => roundHalfAway(x * 100) / 100;

export function weekAnchor(minOpenTs) {
  const day = Math.floor(minOpenTs / DAY);
  const weekday = (((day + 3) % 7) + 7) % 7; // 1970-01-01 was a Thursday; Monday = 0
  return (day - weekday) * DAY;
}

function hex(buf) {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function fingerprint(salt, t) {
  const text = [salt, t.symbol, t.open_ts, t.close_ts, t.dir, roundHalfAway(t.qty * 1e8), roundHalfAway(t.pnl * 100)].join('|');
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return hex(digest).slice(0, 32);
}

// A random permutation of 0..n-1 (crypto random), so s carries no order of symbols.
export function randomPerm(n) {
  const a = Array.from({ length: n }, (_, i) => i);
  const r = new Uint32Array(Math.max(n, 1));
  crypto.getRandomValues(r);
  for (let i = n - 1; i > 0; i--) { const j = r[i] % (i + 1); const t = a[i]; a[i] = a[j]; a[j] = t; }
  return a;
}

// trades: ParseResult.trades (close-time order). perm(n) is injectable for tests.
export async function stripRows(trades, salt, perm = randomPerm) {
  const used = trades.length > MAX_ROWS ? trades.slice(trades.length - MAX_ROWS) : trades;
  let minOpen = Infinity;
  for (const t of used) if (t.open_ts < minOpen) minOpen = t.open_ts;
  const anchor = weekAnchor(minOpen);
  const symbols = [];
  const qtyBySym = new Map();
  for (const t of used) {
    if (!qtyBySym.has(t.symbol)) { qtyBySym.set(t.symbol, []); symbols.push(t.symbol); }
    qtyBySym.get(t.symbol).push(t.qty);
  }
  symbols.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const p = perm(symbols.length);
  const index = new Map(symbols.map((s, i) => [s, p[i]]));
  const med = new Map([...qtyBySym].map(([s, qs]) => [s, median(qs)]));
  const rows = [];
  for (const t of used) {
    rows.push({ o: Math.floor((t.open_ts - anchor) / 60000), h: t.hold_s, d: t.dir === 'long' ? 1 : -1,
      q: round3(t.qty / med.get(t.symbol)), p: round2(t.pnl), s: index.get(t.symbol), f: await fingerprint(salt, t) });
  }
  return { rows, limited: trades.length > MAX_ROWS, anchor };
}
