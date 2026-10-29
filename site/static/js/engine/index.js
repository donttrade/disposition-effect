// index.js — the engine's one entry point: bytes in, ParseResult out (or an EngineError).
//
// Runs entirely in the browser. Nothing here touches the network, the console,
// cookies or storage, and raw rows are never kept: only whitelisted fields
// survive into executions and trades.

import { decodeBytes, isHtml, parseCsv, sniffDelimiter, resolveNumberStyle, checkQuoting, normHeader, fromPaste } from './csv.js';
import { detectCsv, detectHtml, SIGNATURES, NUMERIC_FIELDS, checkCurrencyColumn } from './detect.js';
import { fail, inFile, LIMITS } from './errors.js';
import { checkMapping, parseMapped, mappedTzLabel, mergeParsed, firstTs } from './mapped.js';
import { htmlRows, parseMt, isEmptyRow } from './mt.js';
import { parseGeneric, parseGenericRoundtrip } from './generic.js';
import { parseIbkr } from './ibkr.js';
import { parseTradovate } from './tradovate.js';
import { parseTradingView, stripCurrencyCells } from './tradingview.js';
import { finish } from './trades.js';

export { EngineError } from './errors.js';

export const TZ_LABELS = Object.freeze({
  mt5: 'broker server time', mt4: 'broker server time', ibkr_flex: 'as exported',
  tradovate_orders: 'local time, as exported', tradingview: 'as exported, with no time zone stated',
  generic: 'as in the file', generic_roundtrip: 'as in the file', mapped: 'as in the file',
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

// ---------------------------------------------------------------- reading one file or paste
// An item is the bytes of a file (Uint8Array) or a pasted table ({paste: text}).

export function isPaste(item) {
  return item !== null && typeof item === 'object' && !(item instanceof Uint8Array) && typeof item.paste === 'string';
}

function sizeOf(item) {
  return isPaste(item) ? item.paste.length : item.length;
}

// → {kind: 'csv' | 'html' | 'paste', delimiter, rows, text}
export function readRows(item, delimiter = null) {
  if (isPaste(item)) return { kind: 'paste', delimiter: '\t', rows: fromPaste(item.paste), text: null };
  const text = decodeBytes(item);
  if (isHtml(text)) return { kind: 'html', delimiter: null, rows: htmlRows(text), text };
  const delim = delimiter || sniffDelimiter(text);
  return { kind: 'csv', delimiter: delim, rows: parseCsv(text, delim), text };
}

// A recognised format (no mapping) → {fmt, verified, res, mode, tz, nData, shape}
function readAuto(src) {
  if (src.kind === 'html') {
    const det = detectHtml(src.rows);
    const groups = det.tables.map(htmlNumberGroup);
    resolveNumberStyle(groups, 'dot');
    let dup = 0;
    let nData = 0;
    for (const g of groups) { dup += countDuplicateRows(g.rows, g.map); nData += g.rows.length; }
    return { fmt: det.format, verified: false, res: withDuplicates(parseMt(det.tables), dup), mode: 'gross',
      tz: TZ_LABELS[det.format], nData, shape: det.format };
  }
  const { rows, delimiter: delim } = src;
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
  const out = (fmt, res, mode) => ({ fmt, verified, res: withDuplicates(res, dup, curIgnored), mode, tz: TZ_LABELS[fmt],
    nData: dataRows, shape: fmt });
  if (name === 'mt5_deals') {
    const table = { kind: 'mt5_deals', section: 'deals', map: m,
      rows: rows.slice(hi + 1).map((r) => ({ row: r.row, cells: r.cells, section: 'deals' })) };
    return out('mt5', parseMt([table]), 'gross');
  }
  if (name === 'ibkr_flex') return out(name, parseIbkr(rows, hi, m), 'net');
  if (name === 'tradovate_orders') return out(name, parseTradovate(rows, hi, m), null);
  if (name === 'tradingview') return out(name, parseTradingView(rows, hi, m), null);
  if (name === 'generic_roundtrip') return out(name, parseGenericRoundtrip(rows, hi, m), null);
  return out('generic', parseGeneric(rows, hi, m), null);
}

// The heading row a mapping points at, normalised: what "the same columns" means across files.
function headerShape(rows, mp) {
  const h = rows.find((r) => r.row === mp.header_row + 1);
  return h ? h.cells.map(normHeader).join('\u0001') : null;
}

// Through a mapping → the same as readAuto. expect: the first file's heading row (null for it).
function readMappedItem(src, mp, sideFrom, expect) {
  let rows = src.rows;
  if (src.kind === 'html') {
    if (!mp.source) fail('E_BAD_MAPPING', 'the choice for "source" does not fit', null, 'source');
    rows = rows.filter((r) => r.table === mp.source.table);
  } else if (mp.source) fail('E_BAD_MAPPING', 'the choice for "source" does not fit', null, 'source');
  if (!rows.length) fail('E_EMPTY');
  const shape = headerShape(rows, mp);
  if (expect !== null && shape !== expect) fail('E_MIXED_FILES');
  const { res, nData } = parseMapped(rows, mp, sideFrom, src.kind, src.delimiter);
  return { fmt: 'mapped', verified: false, res, mode: null, tz: mappedTzLabel(res.extra), nData, shape };
}

// Several files (or pastes) of one platform, read as one history. Every file is read the same way:
// all recognised as one format, or all through the same mapping. Files are taken in the order of
// their first time; rows that are in more than one file are counted once (mapped.js dropOverlap).
// An error in one of several files names it by its place: "file 2 of 3, row 14".
export function parseFiles(items, opts = {}) {
  if (!Array.isArray(items) || items.length === 0) fail('E_EMPTY');
  const mp = opts && opts.mapping ? opts.mapping : null;
  const sideFrom = mp ? checkMapping(mp) : null;
  const n = items.length;
  let total = 0;
  for (const it of items) total += sizeOf(it);
  if (total > LIMITS.MAX_BYTES) fail('E_TOO_LARGE');
  const parts = [];
  let nRows = 0;
  for (let k = 0; k < n; k++) {
    try {
      const src = readRows(items[k], mp ? mp.delimiter || null : null);
      const p = mp ? readMappedItem(src, mp, sideFrom, k === 0 ? null : parts[0].shape) : readAuto(src);
      if (k > 0 && p.shape !== parts[0].shape) fail('E_MIXED_FILES');
      p.lastRow = src.rows.length ? src.rows[src.rows.length - 1].row : 0;
      p.first = firstTs(p.res);
      nRows += p.nData;
      parts.push(p);
    } catch (e) {
      if (n > 1 && e && e.name === 'EngineError') throw inFile(e, k, n);
      throw e;
    }
  }
  if (nRows > LIMITS.MAX_ROWS) fail('E_TOO_LARGE');
  if (n === 1) {
    const p = parts[0];
    return finish(p.fmt, p.verified, p.res, p.mode, p.tz);
  }
  const order = parts.map((p, k) => k).sort((a, b) => (parts[a].first - parts[b].first) || (a - b));
  const sorted = order.map((k) => parts[k]);
  const res = mergeParsed(sorted);
  const p = parts[0];
  return finish(p.fmt, p.verified, res, p.mode, mp ? mappedTzLabel(res.extra) : p.tz);
}

export function parseFile(bytes, opts = {}) {
  return parseFiles([bytes], opts);
}

// The same, but never throws: {result} or {error}. Used by the pages and the golden test.
export function runFiles(items, opts = {}) {
  try {
    return { result: parseFiles(items, opts) };
  } catch (e) {
    if (e && e.name === 'EngineError') return { error: e.toJSON() };
    throw e; // a bug, not a bad file: fail loudly
  }
}

export function runFile(bytes, opts = {}) {
  return runFiles([bytes], opts);
}
