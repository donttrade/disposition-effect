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

// RFC 4180 with the usual leniencies. Returns [{row, cells, swallow, ml, broken}] where row
// is the 1-based physical line the record starts on. Blank lines are dropped.
// A stray quote mark must never hide rows silently. parseCsv records what checkQuoting
// (below) needs, once the header is known:
//   * a quoted cell still open at the end of the file → E_BAD_QUOTE at the row it opened in;
//   * swallow = the most delimiters on one physical line *inside* a quoted cell after a
//     line break. A cell that swallowed whole rows has (columns − 1) of them;
//   * ml = the indexes of the cells that span a line break;
//   * broken = a cell that spans a line break was closed by a quote followed by more text.
//     That is the next row's opening quote closing a stray one (an all-quoted file:
//     `"moved stop to 5` + newline + `"2026-01-05","10:21:00",…`), never a real note.
export function parseCsv(text, delim) {
  const out = [];
  let cells = [];
  let field = '';
  let inQ = false;
  let atStart = true; // at the start of a field (a quote here opens a quoted field)
  let line = 1;
  let recLine = 1;
  let swallow = 0;
  let lineDelims = -1; // delimiters on the current inner line of a quoted cell; -1 = no line break yet
  let ml = [];
  let broken = false;
  let closedMl = false; // the quote of a multi-line cell has just closed
  const n = text.length;
  const endField = () => { cells.push(field); field = ''; atStart = true; };
  const endRecord = () => {
    endField();
    if (!(cells.length === 1 && clean(cells[0]) === '')) {
      out.push({ row: recLine, cells: cells.map(clean), swallow, ml, broken });
      if (out.length > LIMITS.MAX_ROWS + 1) fail('E_TOO_LARGE');
    }
    cells = [];
    swallow = 0;
    ml = [];
    broken = false;
  };
  let i = 0;
  while (i < n) {
    const ch = text[i];
    if (inQ) {
      if (ch === '"') {
        if (i + 1 < n && text[i + 1] === '"') { field += '"'; i += 2; continue; }
        if (lineDelims >= 0) { ml.push(cells.length); closedMl = true; }
        inQ = false; lineDelims = -1; i++; continue;
      }
      if (ch === '\r' || ch === '\n') {
        if (ch === '\r' && i + 1 < n && text[i + 1] === '\n') { field += '\r\n'; i += 2; }
        else { field += ch; i++; }
        line++;
        lineDelims = 0;
        continue;
      }
      if (ch === delim && lineDelims >= 0) { lineDelims++; if (lineDelims > swallow) swallow = lineDelims; }
      field += ch; i++; continue;
    }
    if (closedMl) {
      if (ch !== delim && ch !== '\r' && ch !== '\n') broken = true;
      closedMl = false;
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
  if (inQ) fail('E_BAD_QUOTE', '', recLine);
  if (field !== '' || cells.length > 0) endRecord();
  return out;
}

// After the header is known: refuse, naming the row, any data record whose quoting shows
// that rows were merged or cut (Tester B3, F-B2). A whitelisted cell never holds a quote
// mark or a line break (symbols, sides, dates and numbers have neither), so one that does
// came from a stray quote. Free-text columns we never read (notes) may hold both.
//   * broken (see parseCsv);
//   * a multi-line record with more cells than the header (the next row's cells were
//     appended to it);
//   * a quoted cell holding whole rows (columns − 1 delimiters on one inner line);
//   * a quote mark or a line break inside a whitelisted cell;
//   * a header cell that spans a line break (the first data row went into it).
export function checkQuoting(rows, hi, map) {
  const width = rows[hi].cells.length;
  const idx = Object.values(map);
  if (rows[hi].ml.length || rows[hi].broken) fail('E_BAD_QUOTE', '', rows[hi].row);
  for (let k = hi + 1; k < rows.length; k++) {
    const r = rows[k];
    if (r.broken || (r.ml.length && r.cells.length > width) || (width >= 3 && r.swallow >= width - 1)) {
      fail('E_BAD_QUOTE', '', r.row);
    }
    for (const i of idx) {
      if (r.ml.includes(i) || (i < r.cells.length && r.cells[i].indexOf('"') !== -1)) fail('E_BAD_QUOTE', '', r.row);
    }
  }
}

// ---------------------------------------------------------------- numbers

const RE_PLAIN = /^[+-]?(\d+\.?\d*|\.\d+)$/;
const RE_THOUSANDS_COMMA = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
const RE_EURO = /^[+-]?\d{1,3}(\.\d{3})+,\d+$/;
const RE_SINGLE_COMMA = /^[+-]?\d+,\d+$/;
const RE_STRIP = new RegExp(WS_CLASS, 'g');

// Returns a finite number, or null for an empty cell. Never guesses: a lone comma
// followed by exactly three digits ("1,234") could be 1.234 or 1234, so it is an error.
// Error messages name the row and column but never repeat the cell's text: a shifted
// row can put an account or name into a number or date column (Tester D5).
export function parseNumber(raw, row, column) {
  let s = String(raw).replace(RE_STRIP, '').replace(/−/g, '-');
  if (s === '') return null;
  const commas = (s.match(/,/g) || []).length;
  const dots = (s.match(/\./g) || []).length;
  if (commas > 0) {
    if (dots === 0 && commas === 1 && RE_SINGLE_COMMA.test(s)) {
      if (/,\d{3}$/.test(s)) fail('E_BAD_NUMBER', 'a number like 1,234 could mean a decimal comma or a thousands separator. Export it again without thousands separators.', row, column);
      s = s.replace(',', '.');
    } else if (RE_THOUSANDS_COMMA.test(s)) {
      s = s.replace(/,/g, '');
    } else if (RE_EURO.test(s)) {
      s = s.replace(/\./g, '').replace(',', '.');
    } else {
      fail('E_BAD_NUMBER', 'the cell is not a plain number', row, column);
    }
  }
  if (!RE_PLAIN.test(s)) fail('E_BAD_NUMBER', 'the cell is not a plain number', row, column);
  const v = Number(s);
  if (!Number.isFinite(v)) fail('E_BAD_NUMBER', 'the cell is not a plain number', row, column);
  return v;
}

// ---------------------------------------------------------------- the file's decimal separator
// parseNumber reads one cell at a time, so "1.500" alone could be 1.5 or 1,500.
// resolveNumberStyle decides once per file, from every number cell:
//   comma evidence: "12,50", "1.234,5", "1.234.567"   dot evidence: "12.5", "1,234.5", "1234.567"
//   "1.500" / "18.250" (one dot, then exactly 3 digits, 1-3 before it, not starting with 0) is
//   evidence of neither. "0.125" is dot evidence: no exporter writes 125 as 0.125.
// Both kinds in one file → E_BAD_NUMBER (never guess). Comma evidence → the dots in
// "1.500"-style cells are thousands separators, so they are removed here. Dot evidence
// → those cells are decimals. Neither → the fallback: 'dot' (comma-separated CSV and
// MetaTrader HTML), or null (';' or tab CSV, where "1.500" is a real ambiguity) →
// E_BAD_NUMBER. "1,234" is left to parseNumber, which always refuses it (plan rule).

const SH_INT = /^[+-]?\d+$/;
const SH_ONE_COMMA = /^[+-]?\d+,(\d+)$/;
const SH_EURO = /^[+-]?\d{1,3}(\.\d{3})+,\d+$/;
const SH_US = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
// Thousands groups never start with 0: "0.125" is a decimal (dot evidence), never 125 (Tester F-D7).
const SH_DOT3 = /^[+-]?[1-9]\d{0,2}\.\d{3}$/;
const SH_ONE_DOT = /^[+-]?(\d+\.?\d*|\.\d+)$/;
const SH_DOTS_THOUSANDS = /^[+-]?[1-9]\d{0,2}(\.\d{3}){2,}$/;

export function numberShape(raw) {
  const s = String(raw).replace(RE_STRIP, '').replace(/−/g, '-');
  if (s === '' || SH_INT.test(s)) return 'neutral';
  const c = SH_ONE_COMMA.exec(s);
  if (c) return c[1].length === 3 ? 'neutral' : 'comma';
  if (SH_EURO.test(s) || SH_DOTS_THOUSANDS.test(s)) return 'comma';
  if (SH_US.test(s)) return 'dot';
  if (SH_DOT3.test(s)) return 'dot3';
  if (SH_ONE_DOT.test(s)) return 'dot';
  return 'other'; // parseNumber reports it
}

// groups: [{rows: [{row, cells}], map, fields}] — every number cell of the file.
// Returns 'dot' | 'comma'; rewrites "1.500"-style cells in place when 'comma'.
export function resolveNumberStyle(groups, fallback) {
  let firstComma = null;
  let firstDot = null;
  let firstDot3 = null;
  for (const g of groups) {
    for (const r of g.rows) {
      for (const f of g.fields) {
        const i = g.map[f];
        if (i === undefined || i >= r.cells.length) continue;
        const shape = numberShape(r.cells[i]);
        const at = { row: r.row, column: f };
        if (shape === 'comma') {
          if (firstDot) fail('E_BAD_NUMBER', `This file mixes decimal commas and decimal points (a decimal point is in row ${firstDot.row}). Export it again with one number format.`, at.row, at.column);
          if (!firstComma) firstComma = at;
        } else if (shape === 'dot') {
          if (firstComma) fail('E_BAD_NUMBER', `This file mixes decimal commas and decimal points (a decimal comma is in row ${firstComma.row}). Export it again with one number format.`, at.row, at.column);
          if (!firstDot) firstDot = at;
        } else if (shape === 'dot3' && !firstDot3) firstDot3 = at;
      }
    }
  }
  const style = firstComma ? 'comma' : firstDot ? 'dot' : fallback;
  if (style === null) {
    if (firstDot3) fail('E_BAD_NUMBER', 'a number like 1.500 could mean 1.5 or 1,500, and no other number in the file shows which. Export it again without thousands separators.', firstDot3.row, firstDot3.column);
    return 'dot';
  }
  if (style === 'comma') {
    for (const g of groups) {
      for (const r of g.rows) {
        for (const f of g.fields) {
          const i = g.map[f];
          if (i === undefined || i >= r.cells.length) continue;
          const bare = r.cells[i].replace(RE_STRIP, '').replace(/−/g, '-');
          if (SH_DOT3.test(bare) || SH_DOTS_THOUSANDS.test(bare)) r.cells[i] = bare.replace(/\./g, '');
        }
      }
    }
  }
  return style;
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

// ---------------------------------------------------------------- daylight-saving changes
// Times are read as naive wall-clock time (plan rule), so a trade held across a
// daylight-saving change can be off by one hour, and in the repeated hour of a fall-back
// night a close can even read earlier than its open (Tester D4). The file has no time
// zone, so the engine cannot correct this; it flags it. A DST night is the early hours,
// 00:00–05:00, of a US change Sunday (2nd Sunday of March, 1st Sunday of November) or an
// EU one (last Sunday of March and of October); 05:00 covers the UK, central and eastern
// European change times.

const DAY = 86400000;
const DST_NIGHT_MS = 5 * 3600000;

function nthSunday(y, month, n) {
  // n = 1, 2, … from the start of the month; n = -1 is the last Sunday.
  if (n > 0) {
    const first = Date.UTC(y, month - 1, 1);
    const dow = (Math.floor(first / DAY) + 4) % 7; // 0 = Sunday (1970-01-01 was a Thursday)
    return first + (((7 - dow) % 7) + 7 * (n - 1)) * DAY;
  }
  const last = Date.UTC(y, month, 0); // day 0 of the next month = last day of this one
  const dow = (Math.floor(last / DAY) + 4) % 7;
  return last - dow * DAY;
}

// [start, end, fallBack] for the four DST nights of year y.
export function dstNights(y) {
  return [[nthSunday(y, 3, 2), false], [nthSunday(y, 11, 1), true], [nthSunday(y, 3, -1), false], [nthSunday(y, 10, -1), true]]
    .map(([d, fb]) => [d, d + DST_NIGHT_MS, fb]);
}

export function yearOf(ms) {
  return new Date(ms).getUTCFullYear();
}

// True if [openTs, closeTs] overlaps a DST night.
export function spansDstNight(openTs, closeTs) {
  for (let y = yearOf(openTs); y <= yearOf(closeTs); y++) {
    for (const [s, e] of dstNights(y)) if (openTs < e && closeTs >= s) return true;
  }
  return false;
}

// A round-trip row whose close reads up to 1 hour before its open, both on a fall-back
// night: the close is in the repeated hour, so it is read as the second pass (+1 hour)
// and the trade is flagged by W_DST. Anything else stays E_BAD_DATE.
export function fallBackClose(openTs, closeTs) {
  if (closeTs >= openTs || openTs - closeTs > 3600000) return null;
  for (const [s, e, fallBack] of dstNights(yearOf(openTs))) {
    if (fallBack && openTs >= s && openTs < e && closeTs >= s && closeTs < e) return closeTs + 3600000;
  }
  return null;
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
  fail('E_BAD_DATE', 'the cell is not a date and time in a form this format uses (for example 2026-09-01 09:30:00)', row, column);
}
