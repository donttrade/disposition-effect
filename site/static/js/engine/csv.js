// csv.js — bytes → text → rows, plus the number and date readers every parser shares.
//
// Everything here is mirrored line for line in tests/reference/engine_ref.py.
// Two rules keep the two implementations identical:
//   * one explicit whitespace class (never \s, whose meaning differs between JS and Python);
//   * dates are read as "naive UTC" with Date.UTC, never with the browser's time zone,
//     so a file gives the same numbers in Toronto, Kolkata or UTC.

import { fail, LIMITS } from './errors.js';

// Whitespace we strip or collapse: ASCII whitespace, NBSP, the en/em/thin spaces,
// narrow NBSP, medium mathematical space and the ideographic space.
export const WS_CLASS = '[\\t\\n\\v\\f\\r \\u00a0\\u2000-\\u200a\\u202f\\u205f\\u3000]';
const WS_RUN = new RegExp(WS_CLASS + '+', 'g');
const WS_EDGE = new RegExp('^' + WS_CLASS + '+|' + WS_CLASS + '+$', 'g');

export function clean(s) {
  // Collapse inner whitespace runs to one space and trim the ends.
  return String(s).replace(WS_RUN, ' ').replace(WS_EDGE, '');
}

export function normHeader(h) {
  // Header matching is case- and punctuation-blind: "Buy/Sell" → "buysell".
  return clean(h).toLowerCase().replace(/[^a-z0-9]/g, '');
}

// ---------------------------------------------------------------- decoding

export function decodeBytes(bytes) {
  const n = bytes.length;
  if (n === 0) fail('E_EMPTY');
  if (n > LIMITS.MAX_BYTES) fail('E_TOO_LARGE');
  if (n >= 4 && bytes[0] === 0x50 && bytes[1] === 0x4b && bytes[2] === 0x03 && bytes[3] === 0x04) {
    fail('E_ENCODING', 'It looks like an Excel (.xlsx) or zip file. Export the report as HTML or CSV instead.');
  }
  let enc = null;
  let start = 0;
  if (n >= 3 && bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) { enc = 'utf-8'; start = 3; }
  else if (n >= 2 && bytes[0] === 0xff && bytes[1] === 0xfe) { enc = 'utf-16le'; start = 2; }
  else if (n >= 2 && bytes[0] === 0xfe && bytes[1] === 0xff) { enc = 'utf-16be'; start = 2; }
  else enc = sniffUtf16(bytes);

  const body = bytes.subarray(start);
  let text;
  if (enc === 'utf-16le' || enc === 'utf-16be') {
    if (body.length % 2 !== 0) fail('E_ENCODING', 'The file looks like UTF-16 but has an odd number of bytes.');
    try { text = new TextDecoder(enc, { fatal: true }).decode(body); }
    catch (e) { fail('E_ENCODING', 'The UTF-16 text is damaged.'); }
  } else if (enc === 'utf-8') {
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(body); }
    catch (e) { fail('E_ENCODING', 'The UTF-8 text is damaged.'); }
  } else {
    // No BOM: try strict UTF-8, then fall back to Windows-1252 (old MetaTrader reports).
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(body); }
    catch (e) { text = new TextDecoder('windows-1252').decode(body); }
  }
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  if (text.indexOf('\u0000') !== -1) fail('E_ENCODING', 'The file contains binary data.');
  if (clean(text) === '') fail('E_EMPTY');
  return text;
}

function sniffUtf16(bytes) {
  // UTF-16 without a BOM: ASCII-heavy text has a zero in every other byte.
  const m = Math.min(bytes.length, 1000) & ~1;
  if (m < 4) return null;
  let zOdd = 0, zEven = 0;
  for (let i = 0; i < m; i++) {
    if (bytes[i] === 0) { if (i % 2) zOdd++; else zEven++; }
  }
  const half = m / 2;
  if (zOdd > 0.3 * half && zEven === 0) return 'utf-16le';
  if (zEven > 0.3 * half && zOdd === 0) return 'utf-16be';
  return null;
}

// ---------------------------------------------------------------- CSV

const WS_LEAD = new RegExp('^' + WS_CLASS + '+');

export function isHtml(text) {
  const head = text.replace(WS_LEAD, '').slice(0, 4096).toLowerCase();
  return head.startsWith('<') || head.indexOf('<table') !== -1;
}

export function sniffDelimiter(text) {
  // Count candidates outside quotes on the first non-empty line. Ties go to the
  // earlier candidate, so ',' wins over ';' and ';' over tab.
  const lines = text.split(/\r\n|\n|\r/);
  let line = '';
  for (const l of lines) { if (clean(l) !== '') { line = l; break; } }
  const cands = [',', ';', '\t'];
  const counts = [0, 0, 0];
  let inQ = false;
  for (const ch of line) {
    if (ch === '"') inQ = !inQ;
    else if (!inQ) { const k = cands.indexOf(ch); if (k !== -1) counts[k]++; }
  }
  let best = 0;
  for (let k = 1; k < 3; k++) if (counts[k] > counts[best]) best = k;
  return counts[best] === 0 ? ',' : cands[best];
}

// RFC 4180 with the usual leniencies. Returns [{row, cells}] where row is the
// 1-based physical line the record starts on. Blank lines are dropped.
export function parseCsv(text, delim) {
  const out = [];
  let cells = [];
  let field = '';
  let inQ = false;
  let atStart = true; // at the start of a field (a quote here opens a quoted field)
  let line = 1;
  let recLine = 1;
  const n = text.length;
  const endField = () => { cells.push(field); field = ''; atStart = true; };
  const endRecord = () => {
    endField();
    if (!(cells.length === 1 && clean(cells[0]) === '')) {
      out.push({ row: recLine, cells: cells.map(clean) });
      if (out.length > LIMITS.MAX_ROWS + 1) fail('E_TOO_LARGE');
    }
    cells = [];
  };
  let i = 0;
  while (i < n) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"') {
        if (i + 1 < n && text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQ = false; i++; continue;
      }
      if (ch === '\r' || ch === '\n') {
        if (ch === '\r' && i + 1 < n && text[i + 1] === '\n') { field += '\r\n'; i += 2; }
        else { field += ch; i++; }
        line++;
        continue;
      }
      field += ch; i++; continue;
    }
    if (ch === '"' && atStart) { inQ = true; atStart = false; i++; continue; }
    if (ch === delim) { endField(); i++; continue; }
    if (ch === '\r' || ch === '\n') {
      if (ch === '\r' && i + 1 < n && text[i + 1] === '\n') i += 2; else i++;
      endRecord();
      line++;
      recLine = line;
      continue;
    }
    field += ch; atStart = false; i++;
  }
  if (field !== '' || cells.length > 0) endRecord();
  return out;
}

// ---------------------------------------------------------------- numbers

const RE_PLAIN = /^[+-]?(\d+\.?\d*|\.\d+)$/;
const RE_THOUSANDS_COMMA = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
const RE_EURO = /^[+-]?\d{1,3}(\.\d{3})+,\d+$/;
const RE_SINGLE_COMMA = /^[+-]?\d+,\d+$/;
const RE_STRIP = new RegExp(WS_CLASS, 'g');

// Returns a finite number, or null for an empty cell. Never guesses: a lone comma
// followed by exactly three digits ("1,234") could be 1.234 or 1234, so it is an error.
export function parseNumber(raw, row, column) {
  let s = String(raw).replace(RE_STRIP, '').replace(/−/g, '-');
  if (s === '') return null;
  const commas = (s.match(/,/g) || []).length;
  const dots = (s.match(/\./g) || []).length;
  if (commas > 0) {
    if (dots === 0 && commas === 1 && RE_SINGLE_COMMA.test(s)) {
      if (/,\d{3}$/.test(s)) fail('E_BAD_NUMBER', `"${s}" could mean a decimal comma or a thousands separator`, row, column);
      s = s.replace(',', '.');
    } else if (RE_THOUSANDS_COMMA.test(s)) {
      s = s.replace(/,/g, '');
    } else if (RE_EURO.test(s)) {
      s = s.replace(/\./g, '').replace(',', '.');
    } else {
      fail('E_BAD_NUMBER', `"${s}" is not a number`, row, column);
    }
  }
  if (!RE_PLAIN.test(s)) fail('E_BAD_NUMBER', `"${s}" is not a number`, row, column);
  const v = Number(s);
  if (!Number.isFinite(v)) fail('E_BAD_NUMBER', `"${s}" is not a number`, row, column);
  return v;
}

// ---------------------------------------------------------------- dates
// Every reader returns milliseconds since 1970 for the wall-clock time read as UTC,
// or null when the text does not match that reader's pattern at all.

function daysInMonth(y, m) {
  return [31, (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
}

export function utcMs(y, mo, d, h, mi, s, row, column) {
  if (!(y >= 1970 && y <= 2100 && mo >= 1 && mo <= 12 && d >= 1 && d <= daysInMonth(y, mo) &&
        h >= 0 && h <= 23 && mi >= 0 && mi <= 59 && s >= 0 && s <= 59)) {
    fail('E_BAD_DATE', 'the date or time is out of range', row, column);
  }
  return Date.UTC(y, mo - 1, d, h, mi, s);
}

const RE_MT = /^(\d{4})\.(\d{1,2})\.(\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
const RE_ISO = /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?Z?)?$/;
const RE_IBKR = /^(\d{4})(\d{2})(\d{2})(?:[;, ]+(\d{2}):?(\d{2}):?(\d{2}))?$/;
const RE_US = /^(\d{1,2})\/(\d{1,2})\/(\d{4}|\d{2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/;

function fromMatch(m, order, row, column) {
  // order: indexes of year, month, day in the match
  const y = Number(m[order[0]]), mo = Number(m[order[1]]), d = Number(m[order[2]]);
  const h = m[4] === undefined ? 0 : Number(m[4]);
  const mi = m[5] === undefined ? 0 : Number(m[5]);
  const s = m[6] === undefined ? 0 : Number(m[6]);
  return utcMs(y, mo, d, h, mi, s, row, column);
}

export function parseDate(raw, kind, row, column) {
  // kind: 'mt' | 'ibkr' | 'tradovate' | 'generic'
  const s = clean(raw);
  if (s === '') fail('E_BAD_DATE', 'the date is empty', row, column);
  let m;
  if (kind === 'mt' && (m = RE_MT.exec(s))) return fromMatch(m, [1, 2, 3], row, column);
  if ((m = RE_ISO.exec(s))) return fromMatch(m, [1, 2, 3], row, column);
  if (kind === 'generic' && (m = RE_MT.exec(s))) return fromMatch(m, [1, 2, 3], row, column);
  if (kind === 'ibkr' && (m = RE_IBKR.exec(s))) return fromMatch(m, [1, 2, 3], row, column);
  if (kind === 'tradovate' && (m = RE_US.exec(s))) {
    // UNVERIFIED: Tradovate's export is assumed to be month-first (US).
    let y = Number(m[3]);
    if (m[3].length === 2) y += 2000;
    return utcMs(y, Number(m[1]), Number(m[2]), m[4] === undefined ? 0 : Number(m[4]),
      m[5] === undefined ? 0 : Number(m[5]), m[6] === undefined ? 0 : Number(m[6]), row, column);
  }
  if (s.indexOf('/') !== -1) fail('E_AMBIGUOUS_DATE', '', row, column);
  fail('E_BAD_DATE', `"${s}" is not a date this format uses`, row, column);
}
