// index.js — the engine's one entry point: bytes in, ParseResult out (or an EngineError).
//
// Runs entirely in the browser. Nothing here touches the network, the console,
// cookies or storage, and raw rows are never kept: only whitelisted fields
// survive into executions and trades.

import { decodeBytes, isHtml, parseCsv, sniffDelimiter, resolveNumberStyle, checkQuoting } from './csv.js?v=09ecf6e4';
import { detectCsv, detectHtml, SIGNATURES, NUMERIC_FIELDS, checkCurrencyColumn } from './detect.js?v=82af9fc8';
import { fail, LIMITS } from './errors.js?v=31d80675';
import { htmlRows, parseMt, isEmptyRow } from './mt.js?v=39256871';
import { parseGeneric, parseGenericRoundtrip } from './generic.js?v=9c60e210';
import { parseIbkr } from './ibkr.js?v=f6948b1c';
import { parseTradovate } from './tradovate.js?v=1928f2b1';
import { parseTradingView, stripCurrencyCells } from './tradingview.js?v=7c5b71f3';
import { finish } from './trades.js?v=dc047e95';

export { EngineError } from './errors.js?v=31d80675';

export const TZ_LABELS = Object.freeze({
  mt5: 'broker server time', mt4: 'broker server time', ibkr_flex: 'as exported',
  tradovate_orders: 'local time, as exported', tradingview: 'as exported, with no time zone stated',
  generic: 'as in the file', generic_roundtrip: 'as in the file',
});

// Rows whose whitelisted cells all equal an earlier row's (e.g. two overlapping exports
// pasted together). They are kept, since two identical fills can be real, and counted
// for W_DUPLICATE_ROWS (Tester D6). Columns outside the whitelist are not looked at.
function countDuplicateRows(rows, map) {
  const idx = Object.values(map);
  const seen = new Set();
  let n = 0;
  for (const r of rows) {
    if (isEmptyRow(r.cells)) continue;
    const key = idx.map((i) => (i < r.cells.length ? r.cells[i] : '')).join('\u0001');
    if (seen.has(key)) n++; else seen.add(key);
  }
  return n;
}

function withDuplicates(res, n, currencyIgnored = false) {
  res.extra.duplicate_rows = n;
  res.extra.currency_ignored = currencyIgnored;
  return res;
}

// The number cells of one MetaTrader table: only rows of its own section(s), as parseMt reads them.
function htmlNumberGroup(t) {
  const kind = t.kind.startsWith('mt5_positions') ? 'mt5_positions' : t.kind;
  const own = kind === 'mt4' ? (r) => ['closed transactions', 'closed trades', 'open trades'].includes(r.section)
    : (r) => r.section === t.section;
  return { rows: t.rows.filter(own), map: t.map, fields: NUMERIC_FIELDS[kind] };
}

export function parseFile(bytes) {
  const text = decodeBytes(bytes);
  if (isHtml(text)) {
    const det = detectHtml(htmlRows(text));
    const groups = det.tables.map(htmlNumberGroup);
    resolveNumberStyle(groups, 'dot');
    let dup = 0;
    for (const g of groups) dup += countDuplicateRows(g.rows, g.map);
    return finish(det.format, false, withDuplicates(parseMt(det.tables), dup), 'gross', TZ_LABELS[det.format]);
  }
  const delim = sniffDelimiter(text);
  const rows = parseCsv(text, delim);
  if (!rows.length) fail('E_EMPTY');
  const det = detectCsv(rows);
  const { format: name, headerIndex: hi } = det;
  // A Currency column whose cells are not all ISO codes is not read at all (F-D3).
  const { map: m, ignored: curIgnored } = checkCurrencyColumn(rows.slice(hi + 1), det.map);
  let dataRows = 0;
  for (let i = hi + 1; i < rows.length; i++) if (!isEmptyRow(rows[i].cells)) dataRows++;
  if (dataRows === 0) fail('E_HEADER_ONLY');
  if (dataRows > LIMITS.MAX_ROWS) fail('E_TOO_LARGE');
  checkQuoting(rows, hi, det.map);
  if (name === 'tradingview') stripCurrencyCells(rows.slice(hi + 1), m);
  resolveNumberStyle([{ rows: rows.slice(hi + 1), map: m, fields: NUMERIC_FIELDS[name] }], delim === ',' ? 'dot' : null);
  const verified = SIGNATURES[name].verified;
  const dup = countDuplicateRows(rows.slice(hi + 1), m);
  if (name === 'mt5_deals') {
    const table = { kind: 'mt5_deals', section: 'deals', map: m,
      rows: rows.slice(hi + 1).map((r) => ({ row: r.row, cells: r.cells, section: 'deals' })) };
    return finish('mt5', verified, withDuplicates(parseMt([table]), dup, curIgnored), 'gross', TZ_LABELS.mt5);
  }
  if (name === 'ibkr_flex') return finish(name, verified, withDuplicates(parseIbkr(rows, hi, m), dup, curIgnored), 'net', TZ_LABELS[name]);
  if (name === 'tradovate_orders') return finish(name, verified, withDuplicates(parseTradovate(rows, hi, m), dup, curIgnored), null, TZ_LABELS[name]);
  if (name === 'tradingview') return finish(name, verified, withDuplicates(parseTradingView(rows, hi, m), dup, curIgnored), null, TZ_LABELS[name]);
  if (name === 'generic_roundtrip') return finish(name, verified, withDuplicates(parseGenericRoundtrip(rows, hi, m), dup, curIgnored), null, TZ_LABELS[name]);
  return finish('generic', verified, withDuplicates(parseGeneric(rows, hi, m), dup, curIgnored), null, TZ_LABELS.generic);
}

// The same, but never throws: {result} or {error}. Used by the pages and the golden test.
export function runFile(bytes) {
  try {
    return { result: parseFile(bytes) };
  } catch (e) {
    if (e && e.name === 'EngineError') return { error: e.toJSON() };
    throw e; // a bug, not a bad file: fail loudly
  }
}
