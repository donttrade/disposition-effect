// tradovate.js — Tradovate Orders report (one row per order, partial fills
// averaged). Only Filled orders are used. The report has no commissions and no
// currency column, so P&L is gross and futures are taken as USD.
//
// verified_format stays false: the column names come from third-party importer
// documentation only (UNVERIFIED). The Account column is never read.
// Mirrors parse_tradovate() in tests/reference/engine_ref.py.

import { parseDate, parseNumber } from './csv.js?v=7dca0e6f';
import { cell, reqNumber, skip, isEmptyRow } from './mt.js?v=22f54b12';
import { sideLetter } from './generic.js?v=fdcacce4';

// UNVERIFIED: dollars per point per contract. Check each against CME contract specs.
export const CME_MULTIPLIERS = Object.freeze({
  ES: 50, MES: 5, NQ: 20, MNQ: 2, YM: 5, MYM: 0.5, RTY: 50, M2K: 5, CL: 1000, MCL: 100, GC: 100, MGC: 10,
});

const RE_CONTRACT = /^([A-Z0-9]+?)[FGHJKMNQUVXZ][0-9]{1,2}$/;
const PARTIAL_STATUSES = ['canceled', 'cancelled', 'expired'];

function filledSome(raw, row) {
  const v = parseNumber(raw, row, 'qty');
  return v !== null && v !== 0;
}

export function productRoot(contract, product) {
  const p = product.trim().toUpperCase();
  if (p !== '') return p;
  const c = contract.trim().toUpperCase();
  const mm = RE_CONTRACT.exec(c); // "MNQZ6" → "MNQ" (month code + year stripped)
  return mm ? mm[1] : c;
}

export function parseTradovate(rows, hi, m) {
  const execs = [];
  const skipped = {};
  for (const r of rows.slice(hi + 1)) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    // A Canceled or Expired order that filled part of its size is still a fill of that part
    // (Tester D8: dropping it left the position open). UNVERIFIED: avgPrice is the average of
    // the filled part, as for Filled orders.
    const status = cell(r, m, 'status').trim().toLowerCase();
    if (status !== 'filled' && !(PARTIAL_STATUSES.includes(status) && filledSome(cell(r, m, 'qty'), row))) {
      skip(skipped, 'not_filled');
      continue;
    }
    const side = sideLetter(cell(r, m, 'side'));
    if (side === null) { skip(skipped, 'bad_side'); continue; }
    const contract = cell(r, m, 'contract');
    if (contract === '') { skip(skipped, 'no_symbol'); continue; }
    const qty = Math.abs(reqNumber(cell(r, m, 'qty'), row, 'qty'));
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    const price = reqNumber(cell(r, m, 'price'), row, 'price');
    const ts = parseDate(cell(r, m, 'time'), 'tradovate', row, 'time');
    const root = productRoot(contract, cell(r, m, 'product'));
    const mult = Object.prototype.hasOwnProperty.call(CME_MULTIPLIERS, root) ? CME_MULTIPLIERS[root] : null;
    execs.push({ row, ts, symbol: contract, side, qty, price, fee: 0, currency: mult !== null ? 'USD' : null,
      oc: null, pos_id: null, pnl_reported: null, multiplier: mult !== null ? mult : 1,
      _unit: mult !== null ? 'USD' : 'points', _fx: null });
  }
  return { executions: execs, roundtrips: [], skipped, extra: {} };
}
