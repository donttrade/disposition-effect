// tradingview.js — TradingView "Order History" export (Trading Panel → History → ⋯ → Export
// data), from paper trading or a connected broker. One row per order, not per fill.
//
// Only Filled orders are used. Each is one execution: the Closing time (when it filled),
// Side, Quantity, Fill price, and Commission as its fee (empty = 0). A negative Commission is a
// rebate: like a MetaTrader net credit (mt.js mtCosts) it is not a negative fee; fee stays 0 and
// the rebate is a credit added to the trade's gross result (trades.js). Rejected, cancelled
// and other orders are skipped and counted by status. Symbols are kept whole, exchange
// prefix included ("NASDAQ:AAPL"), as every parser keeps the file's symbol text.
// The export has no currency column, so P&L is in price points × quantity ('points'),
// as for the generic template without a Currency column. Times carry no time zone and are
// read as naive wall-clock time, like every other format.
//
// Order ID, Level ID, Type, Limit/Stop price, Placing time, Leverage and Margin are not
// in the whitelist and are never read.
// verified_format is false (beta): only a paper-account export has been seen.
// Mirrors parse_tradingview() in tests/reference/engine_ref.py.

import { clean, parseDate } from './csv.js?v=e5cb6d8a';
import { ISO_CURRENCIES } from './detect.js?v=617d097a';
import { cell, reqNumber, optNumber, skip, isEmptyRow } from './mt.js?v=d38d008e';
import { sideLetter } from './generic.js?v=05fc4a4b';

// Money cells may carry a currency, as the Margin column does ("360.00 USD"): a 3-letter ISO
// code before or after the number ("0.50 USD", "USD 0.50") or a symbol ("$0.50", "0,50 €",
// "-$0.50"). It is removed before the number is read; anything else is left for parseNumber
// to refuse. Only the Fill price and Commission cells are cleaned this way.
const ISO = new Set(ISO_CURRENCIES);
const SYMBOLS = '$€£¥';
const SIGNS = '+-−';
export const MONEY_FIELDS = ['price', 'commission'];

export function stripCurrency(raw) {
  let s = clean(raw);
  let sign = '';
  let cut = false;
  if (s.length > 1 && SIGNS.includes(s[0]) && !/[0-9.,]/.test(s[1] === ' ' ? s[2] || '' : s[1])) {
    sign = s[0];
    s = s.slice(1).replace(/^ /, '');
  }
  if (s !== '' && SYMBOLS.includes(s[0])) { s = s.slice(1).replace(/^ /, ''); cut = true; }
  else if (/^[A-Za-z]{3}( |(?=[0-9+\-−.,]))/.test(s) && ISO.has(s.slice(0, 3).toUpperCase())) {
    s = s.slice(3).replace(/^ /, ''); cut = true;
  }
  if (s !== '' && SYMBOLS.includes(s[s.length - 1])) { s = s.slice(0, -1).replace(/ $/, ''); cut = true; }
  else if (/(^|[0-9.,] ?)[A-Za-z]{3}$/.test(s) && s.length > 3 && ISO.has(s.slice(-3).toUpperCase())) {
    s = s.slice(0, -3).replace(/ $/, ''); cut = true;
  }
  return cut ? sign + s : clean(raw);
}

// Before the file's decimal separator is decided (csv.js resolveNumberStyle), so "1.500 USD"
// counts as evidence like "1.500" does. Rewrites the cells in place.
export function stripCurrencyCells(rows, m) {
  for (const r of rows) {
    for (const f of MONEY_FIELDS) {
      const i = m[f];
      if (i !== undefined && i < r.cells.length) r.cells[i] = stripCurrency(r.cells[i]);
    }
  }
}

function skipReason(status) {
  if (status === 'rejected') return 'rejected';
  if (status === 'cancelled' || status === 'canceled') return 'cancelled';
  return 'not_filled';
}

export function parseTradingView(rows, hi, m) {
  const execs = [];
  const skipped = {};
  for (const r of rows.slice(hi + 1)) {
    if (isEmptyRow(r.cells)) continue;
    const row = r.row;
    const status = cell(r, m, 'status').trim().toLowerCase();
    if (status !== 'filled') { skip(skipped, skipReason(status)); continue; }
    const side = sideLetter(cell(r, m, 'side'));
    if (side === null) { skip(skipped, 'bad_side'); continue; }
    const symbol = cell(r, m, 'symbol');
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    const qty = Math.abs(reqNumber(cell(r, m, 'qty'), row, 'qty'));
    if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
    const price = reqNumber(cell(r, m, 'price'), row, 'price');
    const c = optNumber(cell(r, m, 'commission'), row, 'commission');
    const fee = c > 0 ? c : 0;
    const credit = c < 0 ? -c : 0;
    const ts = parseDate(cell(r, m, 'time'), 'generic', row, 'time');
    execs.push({ row, ts, symbol, side, qty, price, fee, currency: null, oc: null, pos_id: null,
      pnl_reported: null, multiplier: 1, _unit: 'points', _fx: null, _credit: credit });
  }
  return { executions: execs, roundtrips: [], skipped, extra: {} };
}
