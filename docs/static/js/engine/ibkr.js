// ibkr.js — Interactive Brokers Flex Query, Trades section at execution level.
//
// verified_format stays false until a real export is seen: the CSV header
// spellings are UNVERIFIED (see PROVENANCE.txt). Side comes from Buy/Sell,
// never from the quantity's sign. Open/close comes from the Open/Close
// indicator or the O / C codes. Realized P&L, when present, is taken as
// reported and net of commission (UNVERIFIED). Account ID, alias, model and
// trader id are not in the whitelist and are never read.
// Mirrors parse_ibkr() in tests/reference/engine_ref.py.

import { parseDate } from './csv.js?v=c0193c2a';
import { cell, reqNumber, optNumber, skip, isEmptyRow } from './mt.js?v=ec30543d';
import { sideLetter } from './generic.js?v=128dbf64';

// A cancellation row ("BUY (Ca.)" / "SELL (Ca.)", or the code Ca; UNVERIFIED spellings
// from the Flex docs) takes back an earlier execution. It is not a fill: the execution it
// cancels (same symbol, side, quantity and price, the latest one at or before its time)
// is removed, and both rows count as skipped "cancelled" (Tester D8). A cancellation with
// no such execution in the file counts as "cancel_unmatched".
const RE_CANCEL_SIDE = /\(CA\.?\)/;

function applyCancels(execs, cancels, skipped) {
  for (const c of cancels) {
    let best = -1;
    for (let k = 0; k < execs.length; k++) {
      const e = execs[k];
      if (e === null || e.symbol !== c.symbol || e.side !== c.side || e.qty !== c.qty || e.price !== c.price || e.ts > c.ts) continue;
      if (best === -1 || e.ts >= execs[best].ts) best = k;
    }
    if (best === -1) { skip(skipped, 'cancel_unmatched'); continue; }
    execs[best] = null;
    skip(skipped, 'cancelled');
    skip(skipped, 'cancelled');
  }
  return execs.filter((e) => e !== null);
}

export function parseIbkr(rows, hi, m) {
  const execs = [];
  const cancels = [];
  const skipped = {};
  for (const r of rows.slice(hi + 1)) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    const level = cell(r, m, 'level').toUpperCase();
    // ORDER / CLOSED_LOT / summary rows would double-count the executions.
    if (level !== '' && level !== 'EXECUTION') { skip(skipped, 'not_execution'); continue; }
    const sideText = cell(r, m, 'side').toUpperCase();
    const codeToks = cell(r, m, 'code').toUpperCase().split(';').map((x) => x.trim());
    const isCancel = RE_CANCEL_SIDE.test(sideText) || codeToks.includes('CA');
    const side = sideLetter(cell(r, m, 'side'));
    if (side === null) { skip(skipped, 'bad_side'); continue; }
    const symbol = cell(r, m, 'symbol');
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    let ts;
    if ('datetime' in m) ts = parseDate(cell(r, m, 'datetime'), 'ibkr', row, 'datetime');
    else {
      const d = cell(r, m, 'tradedate');
      const t = cell(r, m, 'tradetime');
      ts = parseDate(t !== '' ? d + ';' + t : d, 'ibkr', row, 'tradedate');
    }
    const qty = Math.abs(reqNumber(cell(r, m, 'quantity'), row, 'quantity'));
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    const price = reqNumber(cell(r, m, 'price'), row, 'price');
    const c = optNumber(cell(r, m, 'commission'), row, 'commission');
    const fee = c < 0 ? -c : 0;
    let ocv = cell(r, m, 'oc').toUpperCase();
    if (ocv === '') ocv = cell(r, m, 'code').toUpperCase();
    const toks = ocv.split(';').map((x) => x.trim());
    const hasO = toks.includes('O');
    const hasC = toks.includes('C');
    const oc = hasO && !hasC ? 'open' : hasC && !hasO ? 'close' : null;
    let realized = null;
    if ('realized' in m && cell(r, m, 'realized') !== '') realized = reqNumber(cell(r, m, 'realized'), row, 'realized');
    let mult = 1;
    if ('multiplier' in m && cell(r, m, 'multiplier') !== '') {
      mult = reqNumber(cell(r, m, 'multiplier'), row, 'multiplier');
      if (mult <= 0) mult = 1;
    }
    const cur = cell(r, m, 'currency').toUpperCase() || null;
    let fx = null;
    if ('fx' in m && cell(r, m, 'fx') !== '') fx = reqNumber(cell(r, m, 'fx'), row, 'fx');
    const e = { row, ts, symbol, side, qty, price, fee, currency: cur, oc, pos_id: null,
      pnl_reported: realized, multiplier: mult, _unit: cur ? cur : 'points', _fx: fx, _rev: hasO && hasC };
    if (isCancel) cancels.push(e); else execs.push(e);
  }
  return { executions: applyCancels(execs, cancels, skipped), roundtrips: [], skipped, extra: {} };
}
