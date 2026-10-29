// index.js — the engine's one entry point: bytes in, ParseResult out (or an EngineError).
//
// Runs entirely in the browser. Nothing here touches the network, the console,
// cookies or storage, and raw rows are never kept: only whitelisted fields
// survive into executions and trades.

import { resolveNumberStyle, checkQuoting, normHeader, wideRows, splitCell, parseDate } from './csv.js?v=7dca0e6f';
import { detectCsv, detectHtml, SIGNATURES, NUMERIC_FIELDS, checkCurrencyColumn, ISO_CURRENCIES } from './detect.js?v=3d28a2dd';
import { fail, inFile, LIMITS } from './errors.js?v=8ee10796';
import { checkMapping, parseMapped, mappedTzLabel, mergeParsed, firstTs, idColumns, idLookup, readRows,
  isPaste } from './mapped.js?v=6107c001';
import { matchPreset, presetById, PRESET_AFTER } from './presets.js?v=25a2db8c';
import { parseMt, isEmptyRow } from './mt.js?v=3f5ee677';
import { parseGeneric, parseGenericRoundtrip } from './generic.js?v=b28059a4';
import { parseIbkr } from './ibkr.js?v=ec12f5c3';
import { parseTradovate } from './tradovate.js?v=038beb75';
import { parseTradingView, stripCurrencyCells } from './tradingview.js?v=b3b7e1f2';
import { finish } from './trades.js?v=f9a6a4a2';

export { EngineError } from './errors.js?v=8ee10796';

export const TZ_LABELS = Object.freeze({
  mt5: 'broker server time', mt4: 'broker server time', ibkr_flex: 'as exported',
  tradovate_orders: 'local time, as exported', tradingview: 'as exported, with no time zone stated',
  generic: 'as in the file', generic_roundtrip: 'as in the file', mapped: 'as in the file',
});

// Rows whose whitelisted cells all equal an earlier row's (e.g. two overlapping exports
// pasted together). They are kept, since two identical fills can be real, and counted
// for W_DUPLICATE_ROWS (Tester D6). Columns outside the whitelist are not looked at, except the
// ID and account columns (mapped.js idColumns): rows with different IDs are not copies (Tester F3).
function countDuplicateRows(rows, map, ids = []) {
  const idx = Object.values(map).concat(ids);
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
// An item is the bytes of a file (Uint8Array) or a pasted table ({paste: text}); mapped.js readRows.
export { readRows, isPaste };

function sizeOf(item) {
  return isPaste(item) ? item.paste.length : item.length;
}

// The read columns of a signature map by kind, for wideRows: numbers, dates and times, currency.
const ISO_SET = new Set(ISO_CURRENCIES);
function readKinds(m, numeric) {
  const kinds = {};
  for (const [f, i] of Object.entries(m)) {
    kinds[i] = numeric.includes(f) ? 'num' : f === 'currency' ? 'ccy' : /time|date/.test(f) ? 'date' : 'text';
  }
  return kinds;
}

// A fill refused as a split number (wideRows) has a side and a size the file does not show, so the
// count of its symbol is unknown from then on (Tester N1: a refused buy left its sell as a phantom
// short). → [{symbol, ts}] for trades.js, which leaves that symbol's dependent fills out; ts is
// null when the row's time cannot be read (then every fill of the symbol is left out).
// A round-trip row is whole on its own, so nothing depends on it.
const TIME_OF = {
  generic: (c, m) => ('datetime' in m ? parseDate(c('datetime'), 'generic') : parseDate(c('time') ? c('date') + ' ' + c('time') : c('date'), 'generic')),
  tradingview: (c) => parseDate(c('time'), 'generic'),
  tradovate_orders: (c) => parseDate(c('time'), 'tradovate'),
  ibkr_flex: (c, m) => parseDate('datetime' in m ? c('datetime') : c('tradetime') ? c('tradedate') + ';' + c('tradetime') : c('tradedate'), 'ibkr'),
  mt5_deals: (c) => parseDate(c('time'), 'mt'),
};

function refusedFills(name, m, rows, split) {
  if (!split.length || !TIME_OF[name]) return [];
  const byRow = new Map(rows.map((r) => [r.row, r]));
  return split.map((sp) => {
    const cells = byRow.get(sp.row).cells;
    const c = (f) => (f in m ? splitCell(cells, m[f], sp) : '');
    let ts = null;
    try { ts = TIME_OF[name](c, m); } catch (e) { if (!e || e.name !== 'EngineError') throw e; }
    return { symbol: c(name === 'tradovate_orders' ? 'contract' : 'symbol'), ts };
  });
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
    const tableOf = new Map();
    for (const t of det.tables) { const idx = idColumns(t.header.cells); for (const r of t.rows) tableOf.set(r.row, idx); }
    return { fmt: det.format, verified: false, res: withDuplicates(parseMt(det.tables), dup), mode: 'gross',
      tz: TZ_LABELS[det.format], nData, shape: det.format,
      idOf: idLookup(det.tables.flatMap((t) => t.rows), (r) => tableOf.get(r.row)) };
  }
  const { delimiter: delim } = src;
  let rows = src.rows;
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
  // Rows an unquoted comma made wider than the heading (csv.js wideRows): a split number is refused.
  const wr = wideRows(rows.slice(hi + 1), rows[hi].cells.length, readKinds(m, NUMERIC_FIELDS[name]), ISO_SET);
  const refused = refusedFills(name, m, rows, wr.split);
  if (wr.split.length) {
    const gone = new Set(wr.split.map((x) => x.row));
    rows = rows.slice(0, hi + 1).concat(rows.slice(hi + 1).filter((r) => !gone.has(r.row)));
  }
  if (name === 'tradingview') stripCurrencyCells(rows.slice(hi + 1), m);
  resolveNumberStyle([{ rows: rows.slice(hi + 1), map: m, fields: NUMERIC_FIELDS[name] }], delim === ',' ? 'dot' : null);
  const verified = SIGNATURES[name].verified;
  const dup = countDuplicateRows(rows.slice(hi + 1), m, idColumns(rows[hi].cells));
  const out = (fmt, res, mode) => {
    withDuplicates(res, dup, curIgnored);
    if (wr.split.length) res.skipped.split_number = (res.skipped.split_number || 0) + wr.split.length;
    res.extra.wide_rows = wr.wide;
    res.extra.refused = refused;
    const idx = idColumns(rows[hi].cells);
    return { fmt, verified, res, mode, tz: TZ_LABELS[fmt], nData: dataRows, shape: fmt,
      idOf: idLookup(rows.slice(hi + 1), () => idx) };
  };
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
  const h = rows.findIndex((r) => r.row === mp.header_row + 1);
  const idx = idColumns(rows[h].cells);
  return { fmt: 'mapped', verified: false, res, mode: null, tz: mappedTzLabel(res.extra), nData, shape,
    idOf: idLookup(rows.slice(h + 1), () => idx) };
}

// Several files (or pastes) of one platform, read as one history. Every file is read the same way:
// all recognised as one format, or all through the same mapping. Files are taken in the order of
// their first time; rows that are in more than one file are counted once (mapped.js dropOverlap).
// An error in one of several files names it by its place: "file 2 of 3, row 14".
//
// With no mapping, the presets that ship with the site take part (presets.js), on every page that
// reads a file, so every page gives one read (Tester F4): a preset marked before_known first (a
// Sierra Chart log, whose headings also fit the IBKR Flex signature), then the known formats as
// they always were, then the other presets for a file those cannot read. A preset with an open
// question (the date order, a number style) cannot be answered here: it ends in the error the
// pages already show for it. readWithPresets returns the question instead, for the mapper.
export function parseFiles(items, opts = {}) {
  if (opts && opts.mapping) return parseWith(items, opts.mapping);
  const r = readWithPresetsRaw(items);
  if (r.error) throw r.error;
  if (r.question) {
    const q = r.question.questions[0];
    const name = presetById(r.question.preset).name;
    let e;
    try {
      if (q.q === 'number_style') fail('E_BAD_NUMBER', `read as ${name}: a number like 1,234 or 1.500 could be read two ways, and no other number in the file shows which.`);
      if (q.reason === 'ask') fail('E_AMBIGUOUS_DATE', `Read as ${name}, every day and month in the file is 12 or less.`);
      fail('E_BAD_DATE', `read as ${name}: the date column mixes date forms`);
    } catch (x) { e = x; }
    throw items.length > 1 ? inFile(e, 0, items.length) : e;
  }
  return r.result;
}

function tryParse(items, mapping) {
  try {
    return { result: parseWith(items, mapping) };
  } catch (e) {
    if (e && e.name === 'EngineError') return { error: e };
    throw e;
  }
}

// → {result} | {error: EngineError} | {question}
function readWithPresetsRaw(items) {
  if (!Array.isArray(items) || items.length === 0) fail('E_EMPTY');
  let src = null;
  try { src = readRows(items[0]); } catch (e) { if (!e || e.name !== 'EngineError') throw e; }
  const use = (p) => (p.questions.length ? { question: { preset: p.preset, questions: p.questions } }
    : tryParse(items, p.mapping));
  if (src) {
    const p = matchPreset(src, (x) => x.before_known);
    if (p) return use(p);
  }
  const auto = tryParse(items, null);
  const e = auto.error;
  if (!e || !PRESET_AFTER.includes(e.code) || !src || (e.file !== undefined && e.file !== null && e.file !== 1)) return auto;
  const p = matchPreset(src);
  return p ? use(p) : auto;
}

// The flow parseFiles uses, for the mapper: → {result} | {error} | {question: {preset, questions}}.
// The page puts a mapping saved in this browser before it (plan §2.1).
export function readWithPresets(items) {
  const r = readWithPresetsRaw(items);
  return r.error ? { error: r.error.toJSON() } : r;
}

// Known formats (mapping null) or one mapping, for every file.
function parseWith(items, mapping) {
  if (!Array.isArray(items) || items.length === 0) fail('E_EMPTY');
  const mp = mapping || null;
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
  for (const p of parts) {
    for (const x of p.res.executions) x._id = p.idOf(x.row);
    for (const x of p.res.roundtrips) x._id = p.idOf(x.row);
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
