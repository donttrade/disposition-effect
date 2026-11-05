// generic.js — donttrade's template (one row per execution) and the
// TradeZella-style round-trip layout. Mirrors parse_generic() and
// parse_generic_roundtrip() in tests/reference/engine_ref.py.

import { parseDate, fallBackClose } from './csv.js';
import { fail } from './errors.js';
import { cell, reqNumber, optNumber, skip, isEmptyRow } from './mt.js';

export function sideLetter(v) {
  // Like Tradervue: anything starting with B is a buy, with S a sell ("Short" too).
  // "Long" and "Cover" are buys as well (Tester D8: they were skipped, which left the
  // position open and lost every later trade on the symbol).
  v = v.trim().toUpperCase();
  if (v.startsWith('B') || v === 'LONG' || v === 'COVER') return 'buy';
  if (v.startsWith('S')) return 'sell';
  return null;
}

// ---- slash dates. Never guessed: a file's slash dates are read when the file itself shows the order.
// 2026/11/05 (four-digit year first) is year-month-day. With the year last, one date whose first part is over 12
// (13/11/2026) shows day-first, one whose second part is over 12 (11/13/2026) shows month-first. A file where
// every day and month is 12 or less shows nothing, and stays refused. Two orders in one column are refused too.
// Mirrors slash_order() and slash_to_iso() in tests/reference/engine_ref.py.
const RE_SLASH_Y = /^(\d{4})\/(\d{1,2})\/(\d{1,2})(?=$|[ T])/;
const RE_SLASH_L = /^(\d{1,2})\/(\d{1,2})\/(\d{4})(?=$|[ T])/;

function slashVote(s) {
  s = s.trim();
  if (RE_SLASH_Y.test(s)) return 'ymd';
  const x = RE_SLASH_L.exec(s);
  if (!x) return null;
  const a = Number(x[1]), b = Number(x[2]);
  if (a > 12 && b <= 12) return 'dmy';
  if (b > 12 && a <= 12) return 'mdy';
  return null;   // both 12 or less (no order shown), or both over 12 (not a date)
}

// The order the file's slash dates show: the first one found ('ymd' | 'dmy' | 'mdy'), or null.
function slashOrder(cells) {
  for (const c of cells) {
    if (c.indexOf('/') === -1) continue;
    const v = slashVote(c);
    if (v) return v;
  }
  return null;
}

// A cell with a slash date → the same cell with yyyy-mm-dd; any other cell unchanged.
function slashToIso(raw, order, row, column) {
  if (raw.indexOf('/') === -1) return raw;
  const s = raw.trim();
  const yFirst = RE_SLASH_Y.exec(s);
  const x = yFirst || RE_SLASH_L.exec(s);
  if (!x) return raw;   // another shape: parseDate refuses it
  const vote = slashVote(s);
  if (order === null && !vote) {
    fail('E_AMBIGUOUS_DATE', 'In this file every date with slashes has a day and a month of 12 or less, so no row shows which comes first.', row, column);
  }
  if ((vote && vote !== order) || (order === 'ymd') !== !!yFirst) fail('E_BAD_DATE', 'the dates mix day-first and month-first (or year-first) forms', row, column);
  let y, mo, d;
  if (order === 'ymd') { y = x[1]; mo = x[2]; d = x[3]; }
  else if (order === 'dmy') { y = x[3]; mo = x[2]; d = x[1]; }
  else { y = x[3]; mo = x[1]; d = x[2]; }
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}${s.slice(x[0].length)}`;
}

export function parseGeneric(rows, hi, m) {
  const execs = [];
  const skipped = {};
  const feesKnown = 'fees' in m;
  const body = rows.slice(hi + 1);
  const dateCol = 'datetime' in m ? 'datetime' : 'date';
  const order = slashOrder(body.filter((r) => !isEmptyRow(r.cells)).map((r) => cell(r, m, dateCol)));
  let negQty = 0;
  for (const r of body) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    let ts;
    if ('datetime' in m) {
      ts = parseDate(slashToIso(cell(r, m, 'datetime'), order, row, 'datetime'), 'generic', row, 'datetime');
    } else {
      const d = cell(r, m, 'date');
      const t = cell(r, m, 'time');
      if (d === '') fail('E_BAD_DATE', 'the date is empty', row, 'date');
      const iso = slashToIso(d, order, row, 'date');
      ts = parseDate(t !== '' ? iso + ' ' + t : iso, 'generic', row, 'date');
    }
    const symbol = cell(r, m, 'symbol');
    const side = sideLetter(cell(r, m, 'side'));
    if (side === null) { skip(skipped, 'bad_side'); continue; }
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    const rawQty = reqNumber(cell(r, m, 'qty'), row, 'qty');
    const qty = Math.abs(rawQty);
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    if (rawQty < 0) negQty++;   // the Side column decides buy or sell; the minus sign is ignored, and said so
    const price = reqNumber(cell(r, m, 'price'), row, 'price');
    const fee = feesKnown ? Math.abs(optNumber(cell(r, m, 'fees'), row, 'fees')) : 0;
    const cur = cell(r, m, 'currency').toUpperCase() || null;
    execs.push({ row, ts, symbol, side, qty, price, fee, currency: cur, oc: null, pos_id: null,
      pnl_reported: null, multiplier: 1, _unit: cur ? cur : 'points', _fx: null });
  }
  return { executions: execs, roundtrips: [], skipped, extra: negQty ? { negative_qty: negQty } : {} };
}

export function parseGenericRoundtrip(rows, hi, m) {
  const rts = [];
  const skipped = {};
  for (const r of rows.slice(hi + 1)) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    const d = cell(r, m, 'direction').trim().toLowerCase();
    let dir;
    if (d.startsWith('l') || d.startsWith('b')) dir = 'long';
    else if (d.startsWith('s')) dir = 'short';
    else { skip(skipped, 'bad_side'); continue; }
    const symbol = cell(r, m, 'symbol');
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    const ot = parseDate(cell(r, m, 'open_time'), 'generic', row, 'open_time');
    let ct = parseDate(cell(r, m, 'close_time'), 'generic', row, 'close_time');
    const reordered = ct < ot; // read as the repeated hour of a fall-back night, and flagged (F-N3)
    if (reordered) {
      ct = fallBackClose(ot, ct);
      if (ct === null) fail('E_BAD_DATE', 'the close time is before the open time', row, 'close_time');
    }
    const qty = Math.abs(reqNumber(cell(r, m, 'qty'), row, 'qty'));
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    const op = reqNumber(cell(r, m, 'open_price'), row, 'open_price');
    const cp = reqNumber(cell(r, m, 'close_price'), row, 'close_price');
    const fee = Math.abs(optNumber(cell(r, m, 'fees'), row, 'fees'));
    const cur = cell(r, m, 'currency').toUpperCase() || null;
    rts.push({ row, symbol, dir, open_ts: ot, close_ts: ct, qty, entry: op, exit: cp, fees: fee,
      pnl_gross: null, reported: false, currency: cur, unit: cur ? cur : 'points', pos_id: null, reordered });
  }
  return { executions: [], roundtrips: rts, skipped, extra: {} };
}
