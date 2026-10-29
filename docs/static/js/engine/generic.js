// generic.js — donttrade's template (one row per execution) and the
// TradeZella-style round-trip layout. Mirrors parse_generic() and
// parse_generic_roundtrip() in tests/reference/engine_ref.py.

import { parseDate, fallBackClose } from './csv.js?v=7dca0e6f';
import { fail } from './errors.js?v=8ee10796';
import { cell, reqNumber, optNumber, skip, isEmptyRow } from './mt.js?v=3f5ee677';

export function sideLetter(v) {
  // Like Tradervue: anything starting with B is a buy, with S a sell ("Short" too).
  // "Long" and "Cover" are buys as well (Tester D8: they were skipped, which left the
  // position open and lost every later trade on the symbol).
  v = v.trim().toUpperCase();
  if (v.startsWith('B') || v === 'LONG' || v === 'COVER') return 'buy';
  if (v.startsWith('S')) return 'sell';
  return null;
}

export function parseGeneric(rows, hi, m) {
  const execs = [];
  const skipped = {};
  const feesKnown = 'fees' in m;
  for (const r of rows.slice(hi + 1)) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    let ts;
    if ('datetime' in m) {
      ts = parseDate(cell(r, m, 'datetime'), 'generic', row, 'datetime');
    } else {
      const d = cell(r, m, 'date');
      const t = cell(r, m, 'time');
      if (d === '') fail('E_BAD_DATE', 'the date is empty', row, 'date');
      if (d.indexOf('/') !== -1) fail('E_AMBIGUOUS_DATE', '', row, 'date');
      ts = parseDate(t !== '' ? d + ' ' + t : d, 'generic', row, 'date');
    }
    const symbol = cell(r, m, 'symbol');
    const side = sideLetter(cell(r, m, 'side'));
    if (side === null) { skip(skipped, 'bad_side'); continue; }
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    const qty = Math.abs(reqNumber(cell(r, m, 'qty'), row, 'qty'));
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    const price = reqNumber(cell(r, m, 'price'), row, 'price');
    const fee = feesKnown ? Math.abs(optNumber(cell(r, m, 'fees'), row, 'fees')) : 0;
    const cur = cell(r, m, 'currency').toUpperCase() || null;
    execs.push({ row, ts, symbol, side, qty, price, fee, currency: cur, oc: null, pos_id: null,
      pnl_reported: null, multiplier: 1, _unit: cur ? cur : 'points', _fx: null });
  }
  return { executions: execs, roundtrips: [], skipped, extra: {} };
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
