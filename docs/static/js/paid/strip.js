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

import { median } from '../engine/noise.js?v=d0f6a787';

export const MAX_ROWS = 20000;
const DAY = 86400000;
// The server takes at most 10 years: o <= 520 weeks of minutes from the first trade's week, h <= 3,650
// days (dt-private validate.mjs MAX_O, MAX_H). Delivery plan C-10: keep the trades opened in the last
// 519 weeks before the latest open (the week anchor can sit up to 7 days before the first kept open)
// and held at most 3,650 days, as the 20,000-row cap keeps the latest trades.
export const SPAN_WEEKS = 520;
export const MAX_HOLD_S = 86400 * 3650;
const SPAN_KEEP_MS = (SPAN_WEEKS - 1) * 7 * DAY;
// R-D1 D-4: what was left out, exactly (519 weeks is about 9.95 years, so never "the last 10 years").
export const spanLine = (n) => `Left out: ${n} trade${n === 1 ? '' : 's'} opened more than 519 weeks (about 10 years) before this file's latest trade, or held longer than 3,650 days.`;
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
// accountOf (merge.js accountOf): with more than one account, each row carries a, its account's index 0..99 (the
// order the files were met in, never a name or number), on every row; with one account, no row has it (stats3a).
export async function stripRows(trades, salt, perm = randomPerm, accountOf = null) {
  let maxOpen = -Infinity;
  for (const t of trades) if (t.open_ts > maxOpen) maxOpen = t.open_ts;
  const inSpan = trades.filter((t) => t.open_ts >= maxOpen - SPAN_KEEP_MS && t.hold_s <= MAX_HOLD_S);
  const used = inSpan.length > MAX_ROWS ? inSpan.slice(inSpan.length - MAX_ROWS) : inSpan;
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
    const row = { o: Math.floor((t.open_ts - anchor) / 60000), h: t.hold_s, d: t.dir === 'long' ? 1 : -1,
      q: round3(t.qty / med.get(t.symbol)), p: round2(t.pnl), s: index.get(t.symbol), f: await fingerprint(salt, t) };
    if (accountOf) {
      const a = accountOf(t);
      if (!Number.isInteger(a) || a < 0 || a > 99) throw new Error(`strip: account index ${a}`);
      row.a = a;
    }
    rows.push(row);
  }
  return { rows, limited: inSpan.length > MAX_ROWS, anchor, span_left_out: trades.length - inSpan.length };
}
