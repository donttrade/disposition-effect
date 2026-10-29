// mt.js — MetaTrader 5 / 4 HTML reports.
//
// The report is parsed with DOMParser into plain rows of cell text; detect.js
// then finds the section titles and table headers. The header block (broker,
// account number, owner name) sits before the first section title and is never
// mapped, so its text never reaches a result. Balance, credit and cancelled rows
// are skipped and counted. Mirrors parse_mt() in tests/reference/engine_ref.py.

import { clean, parseNumber, parseDate, fallBackClose } from './csv.js?v=e5cb6d8a';
import { fail, LIMITS } from './errors.js?v=eef16098';

// Rows of an HTML document, like the reference's _Rows parser:
// every <tr> in document order, each cell's textContent with whitespace
// collapsed, and colspan expanded into empty cells so columns stay aligned.
// table: the index (in document order) of the innermost <table> holding the row, or -1; the
// universal importer offers one table of a statement that is not MetaTrader (cTrader, Match-Trader).
export function htmlRows(text) {
  const doc = new DOMParser().parseFromString(text, 'text/html');
  const trs = doc.querySelectorAll('tr');
  if (trs.length > LIMITS.MAX_ROWS) fail('E_TOO_LARGE');
  const tableIndex = new Map();
  doc.querySelectorAll('table').forEach((t, i) => tableIndex.set(t, i));
  const rows = [];
  let n = 0;
  for (const tr of trs) {
    n++;
    const cells = [];
    for (const c of tr.cells) {
      cells.push(clean(c.textContent));
      for (let k = 1; k < c.colSpan; k++) cells.push('');
    }
    const t = tr.closest('table');
    rows.push({ row: n, cells, table: t && tableIndex.has(t) ? tableIndex.get(t) : -1 });
  }
  return rows;
}

export function cell(r, m, field) {
  const i = m[field];
  if (i === undefined || i >= r.cells.length) return '';
  return r.cells[i];
}

export function reqNumber(raw, row, column) {
  const v = parseNumber(raw, row, column);
  if (v === null) fail('E_BAD_NUMBER', 'the cell is empty', row, column);
  return v;
}

export function optNumber(raw, row, column, dflt = 0) {
  const v = parseNumber(raw, row, column);
  return v === null ? dflt : v;
}

export function skip(skipped, reason) {
  skipped[reason] = (skipped[reason] || 0) + 1;
}

export function isEmptyRow(cells) {
  return cells.every((c) => c === '');
}

// MetaTrader costs are signed (negative = cost). fee is the net cost as a
// positive number; a net credit (a positive swap bigger than the commission) is
// returned separately and added to the reported profit, so
// pnl = profit + commission + fee + swap exactly while fee stays >= 0.
function mtCosts(commission, fee, swap) {
  const c = commission + fee + swap;
  if (c < 0) return [-c, 0];
  return [0, c];
}

const PENDING = ['buy limit', 'sell limit', 'buy stop', 'sell stop', 'buy stop limit', 'sell stop limit'];

function mtType(t) {
  t = t.toLowerCase();
  if (t === 'buy' || t === 'sell') return [t, null];
  if (t.indexOf('cancel') !== -1) return [null, 'cancelled'];
  if (t === 'balance' || t === 'credit') return [null, t];
  if (PENDING.includes(t)) return [null, 'cancelled']; // a pending order that never filled
  return [null, 'other_type'];
}

export function parseMt(tables) {
  const execs = [];
  const rts = [];
  const skipped = {};
  const extra = { open_positions: 0, has_closed_positions: false, has_deals: false };
  for (const t of tables) {
    const m = t.map;
    const kind = t.kind;
    if (kind === 'mt5_positions_closed') extra.has_closed_positions = true;
    if (kind === 'mt5_deals') extra.has_deals = true;
    for (const r of t.rows) {
      if (isEmptyRow(r.cells)) continue;
      if (kind === 'mt4') {
        if (!['closed transactions', 'closed trades', 'open trades'].includes(r.section)) continue;
      } else if (r.section !== t.section) continue;
      const firstTime = cell(r, m, kind === 'mt5_deals' ? 'time' : 'open_time');
      if (firstTime === '') continue; // totals or spacer row under the table
      const [side, why] = mtType(cell(r, m, 'type'));
      if (side === null) { skip(skipped, why); continue; }
      if (kind === 'mt5_positions_open' ||
          (kind === 'mt4' && (r.section === 'open trades' || cell(r, m, 'close_time') === ''))) {
        extra.open_positions++;
        continue;
      }
      const row = r.row;
      const symbol = cell(r, m, 'symbol');
      if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
      if (kind === 'mt5_deals') {
        const ts = parseDate(cell(r, m, 'time'), 'mt', row, 'time');
        const qty = Math.abs(reqNumber(cell(r, m, 'volume'), row, 'volume'));
        if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
        const price = reqNumber(cell(r, m, 'price'), row, 'price');
        const [fee, credit] = mtCosts(optNumber(cell(r, m, 'commission'), row, 'commission'),
          optNumber(cell(r, m, 'fee'), row, 'fee'), optNumber(cell(r, m, 'swap'), row, 'swap'));
        const profit = reqNumber(cell(r, m, 'profit'), row, 'profit');
        const d = cell(r, m, 'direction').toLowerCase();
        const oc = d === 'in' ? 'open' : (d === 'out' || d === 'out by') ? 'close' : null;
        const pos = cell(r, m, 'position');
        execs.push({ row, ts, symbol, side, qty, price, fee, currency: null, oc, pos_id: pos !== '' ? pos : null,
          pnl_reported: profit + credit, multiplier: 1, _unit: 'account', _fx: null, _rev: d === 'in/out' });
      } else {
        const sizeField = kind === 'mt5_positions_closed' ? 'volume' : 'size';
        const ot = parseDate(cell(r, m, 'open_time'), 'mt', row, 'open_time');
        let ct = parseDate(cell(r, m, 'close_time'), 'mt', row, 'close_time');
        const reordered = ct < ot; // read as the repeated hour of a fall-back night, and flagged (F-N3)
        if (reordered) {
          ct = fallBackClose(ot, ct);
          if (ct === null) fail('E_BAD_DATE', 'the close time is before the open time', row, 'close_time');
        }
        const qty = Math.abs(reqNumber(cell(r, m, sizeField), row, sizeField));
        if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
        const op = reqNumber(cell(r, m, 'open_price'), row, 'open_price');
        const cp = reqNumber(cell(r, m, 'close_price'), row, 'close_price');
        const feeField = kind !== 'mt4' ? 'fee' : 'taxes';
        const [fee, credit] = mtCosts(optNumber(cell(r, m, 'commission'), row, 'commission'),
          optNumber(cell(r, m, feeField), row, feeField), optNumber(cell(r, m, 'swap'), row, 'swap'));
        const profit = reqNumber(cell(r, m, 'profit'), row, 'profit');
        const pos = kind === 'mt5_positions_closed' ? cell(r, m, 'position') : '';
        rts.push({ row, symbol, dir: side === 'buy' ? 'long' : 'short', open_ts: ot, close_ts: ct, qty,
          entry: op, exit: cp, fees: fee, pnl_gross: profit + credit, reported: true, currency: null,
          unit: 'account', pos_id: pos !== '' ? pos : null, reordered });
      }
    }
  }
  return { executions: execs, roundtrips: rts, skipped, extra };
}
