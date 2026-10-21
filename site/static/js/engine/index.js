// index.js — the engine's one entry point: bytes in, ParseResult out (or an EngineError).
//
// Runs entirely in the browser. Nothing here touches the network, the console,
// cookies or storage, and raw rows are never kept: only whitelisted fields
// survive into executions and trades.

import { decodeBytes, isHtml, parseCsv, sniffDelimiter } from './csv.js';
import { detectCsv, detectHtml, SIGNATURES } from './detect.js';
import { fail, LIMITS } from './errors.js';
import { htmlRows, parseMt, isEmptyRow } from './mt.js';
import { parseGeneric, parseGenericRoundtrip } from './generic.js';
import { parseIbkr } from './ibkr.js';
import { parseTradovate } from './tradovate.js';
import { finish } from './trades.js';

export { EngineError } from './errors.js';

export const TZ_LABELS = Object.freeze({
  mt5: 'broker server time', mt4: 'broker server time', ibkr_flex: 'as exported',
  tradovate_orders: 'local time, as exported', generic: 'as in the file', generic_roundtrip: 'as in the file',
});

export function parseFile(bytes) {
  const text = decodeBytes(bytes);
  if (isHtml(text)) {
    const det = detectHtml(htmlRows(text));
    return finish(det.format, false, parseMt(det.tables), 'gross', TZ_LABELS[det.format]);
  }
  const rows = parseCsv(text, sniffDelimiter(text));
  if (!rows.length) fail('E_EMPTY');
  const det = detectCsv(rows);
  const { format: name, headerIndex: hi, map: m } = det;
  let dataRows = 0;
  for (let i = hi + 1; i < rows.length; i++) if (!isEmptyRow(rows[i].cells)) dataRows++;
  if (dataRows === 0) fail('E_HEADER_ONLY');
  if (dataRows > LIMITS.MAX_ROWS) fail('E_TOO_LARGE');
  const verified = SIGNATURES[name].verified;
  if (name === 'mt5_deals') {
    const table = { kind: 'mt5_deals', section: 'deals', map: m,
      rows: rows.slice(hi + 1).map((r) => ({ row: r.row, cells: r.cells, section: 'deals' })) };
    return finish('mt5', verified, parseMt([table]), 'gross', TZ_LABELS.mt5);
  }
  if (name === 'ibkr_flex') return finish(name, verified, parseIbkr(rows, hi, m), 'net', TZ_LABELS[name]);
  if (name === 'tradovate_orders') return finish(name, verified, parseTradovate(rows, hi, m), null, TZ_LABELS[name]);
  if (name === 'generic_roundtrip') return finish(name, verified, parseGenericRoundtrip(rows, hi, m), null, TZ_LABELS[name]);
  return finish('generic', verified, parseGeneric(rows, hi, m), null, TZ_LABELS.generic);
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
