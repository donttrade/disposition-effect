// tradingview.js — TradingView "Order History" export (Trading Panel → History → ⋯ → Export
// data), from paper trading or a connected broker. One row per order, not per fill.
//
// Only Filled orders are used. Each is one execution: the Closing time (when it filled),
// Side, Quantity, Fill price, and Commission as its fee (empty = 0). Rejected, cancelled
// and other orders are skipped and counted by status. Symbols are kept whole, exchange
// prefix included ("NASDAQ:AAPL"), as every parser keeps the file's symbol text.
// The export has no currency column, so P&L is in price points × quantity ('points'),
// as for the generic template without a Currency column. Times carry no time zone and are
// read as naive wall-clock time, like every other format.
//
// Order ID, Level ID, Type, Limit/Stop price, Placing time, Leverage and Margin are not
// in the whitelist and are never read.
// Mirrors parse_tradingview() in tests/reference/engine_ref.py.

import { parseDate } from './csv.js';
import { cell, reqNumber, optNumber, skip, isEmptyRow } from './mt.js';
import { sideLetter } from './generic.js';

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
    const fee = Math.abs(optNumber(cell(r, m, 'commission'), row, 'commission'));
    const ts = parseDate(cell(r, m, 'time'), 'generic', row, 'time');
    execs.push({ row, ts, symbol, side, qty, price, fee, currency: null, oc: null, pos_id: null,
      pnl_reported: null, multiplier: 1, _unit: 'points', _fx: null });
  }
  return { executions: execs, roundtrips: [], skipped, extra: {} };
}
