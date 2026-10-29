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

export function clean(s) {
  // Collapse inner whitespace runs to one space and trim the ends. Linear: after the collapse an
  // edge is at most one space (a WS+$ regex is quadratic on a long run of spaces, Tester F8).
  let t = String(s).replace(WS_RUN, ' ');
  if (t.charCodeAt(0) === 32) t = t.slice(1);
  if (t.length && t.charCodeAt(t.length - 1) === 32) t = t.slice(0, -1);
  return t;
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
    if (isXlsx(bytes)) fail('E_ENCODING', 'It is an Excel (.xlsx) file. Save it as CSV (File → Save as → CSV), then drop it here.');
    fail('E_ENCODING', 'It is a zip file. Open it and drop the CSV inside.');
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

// A zip and an .xlsx both start with PK\x03\x04. An .xlsx holds entries under xl/: one of the first
// local headers names one, or the central directory at the end lists xl/workbook.xml.
function u16(b, i) { return b[i] | (b[i + 1] << 8); }
function u32(b, i) { return (b[i] | (b[i + 1] << 8) | (b[i + 2] << 16)) + b[i + 3] * 16777216; }
const XL_WORKBOOK = [...'xl/workbook.xml'].map((c) => c.charCodeAt(0));

export function isXlsx(bytes) {
  let off = 0;
  for (let k = 0; k < 20 && off + 30 <= bytes.length; k++) {
    if (!(bytes[off] === 0x50 && bytes[off + 1] === 0x4b && bytes[off + 2] === 0x03 && bytes[off + 3] === 0x04)) break;
    const flags = u16(bytes, off + 6);
    const comp = u32(bytes, off + 18);
    const nameLen = u16(bytes, off + 26);
    const extraLen = u16(bytes, off + 28);
    const at = off + 30;
    if (nameLen >= 3 && at + 3 <= bytes.length && bytes[at] === 0x78 && bytes[at + 1] === 0x6c && bytes[at + 2] === 0x2f) return true;
    if ((flags & 8) && comp === 0) break; // sizes come after the data: the walk cannot go on
    off = at + nameLen + extraLen + comp;
  }
  const w = XL_WORKBOOK;
  for (let i = Math.max(0, bytes.length - 65557); i + w.length <= bytes.length; i++) {
    let j = 0;
    while (j < w.length && bytes[i + j] === w[j]) j++;
    if (j === w.length) return true;
  }
  return false;
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

// ---------------------------------------------------------------- dates in a format the user chose
// The universal importer (mapped.js) never guesses a date order: the mapping names one, and every
// cell must fit it. Forms: ymd = 2026-10-02, 2026/10/02, 2026.10.02, 20261002; mdy = 10/2/2026,
// 10-2-26, 10.2.2026; dmy = 2/10/2026 (and the same separators); excel = Excel date numbers (a
// fraction is the time); epoch_s / epoch_ms = seconds / milliseconds since 1970.
// Times: H:MM[:SS][.fff] with an optional AM/PM. Seconds fractions are dropped, as RE_ISO does.
// A trailing time zone label (EST, UTC, Z, +02:00, GMT+2) is ignored: times are read as written,
// like every other format; `seen.zone` records it for the time zone label.

export const DATE_FORMATS = Object.freeze(['ymd', 'mdy', 'dmy', 'excel', 'epoch_s', 'epoch_ms']);
const DATE_FORMAT_LABELS = {
  ymd: 'year-month-day', mdy: 'month/day/year', dmy: 'day/month/year', excel: 'Excel date numbers',
  epoch_s: 'seconds since 1970', epoch_ms: 'milliseconds since 1970',
};
const RE_DF = /^([0-9./-]+)(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?(?: ?([AaPp][Mm]))?)?$/;
const RE_ZONE_WORD = /^(.*[0-9AaPpMm]) ([A-Za-z]{2,5})$/;
const RE_ZONE_OFFSET = /^(.*\d:\d{2}.*?) ?(?:(?:UTC|GMT) ?)?[+-]\d{1,2}(?::?\d{2})?$/;
const RE_ZONE_Z = /^(.*\d)Z$/;
const RE_YMD = /^(\d{4})([-/.])(\d{1,2})\2(\d{1,2})$/;
const RE_YMD8 = /^(\d{4})(\d{2})(\d{2})$/;
const RE_DMY = /^(\d{1,2})([-/.])(\d{1,2})\2(\d{4}|\d{2})$/;
const RE_SERIAL = /^\d+(\.\d+)?$/;
const MAX_TS = Date.UTC(2101, 0, 1); // utcMs accepts years 1970-2100

// → [text without a trailing zone label, whether one was removed]
export function stripZone(s) {
  let zone = false;
  let m = RE_ZONE_WORD.exec(s);
  if (m && !/^[AaPp][Mm]$/.test(m[2]) && /\d/.test(m[1])) { s = m[1]; zone = true; }
  m = RE_ZONE_OFFSET.exec(s);
  if (m && /[0-9AaPpMm]$/.test(m[1])) { s = m[1]; zone = true; }
  m = RE_ZONE_Z.exec(s);
  if (m) { s = m[1]; zone = true; }
  return [s, zone];
}

function badOrder(fmt, row, column) {
  fail('E_BAD_DATE', `it does not fit the date form you chose (${DATE_FORMAT_LABELS[fmt]})`, row, column);
}

function inRange(ms, row, column) {
  if (!(ms >= 0 && ms < MAX_TS)) fail('E_BAD_DATE', 'the date or time is out of range', row, column);
  return ms;
}

export function parseDateFmt(raw, fmt, row, column, seen) {
  const [s, zone] = stripZone(clean(raw));
  if (s === '') fail('E_BAD_DATE', 'the date is empty', row, column);
  const m = RE_DF.exec(s);
  if (!m) badOrder(fmt, row, column);
  if (zone && seen) seen.zone = true;
  const d = m[1];
  const timed = m[2] !== undefined;
  let h = timed ? Number(m[2]) : 0;
  const mi = timed ? Number(m[3]) : 0;
  const sec = m[4] === undefined ? 0 : Number(m[4]);
  if (m[5] !== undefined) {
    if (h < 1 || h > 12) fail('E_BAD_DATE', 'the date or time is out of range', row, column);
    h = (h % 12) + (m[5].toUpperCase() === 'PM' ? 12 : 0);
  }
  if (fmt === 'epoch_s' || fmt === 'epoch_ms') {
    if (timed || !RE_SERIAL.test(d)) badOrder(fmt, row, column);
    const v = Number(d);
    return inRange(fmt === 'epoch_s' ? Math.floor(v) * 1000 : Math.floor(v / 1000) * 1000, row, column);
  }
  if (fmt === 'excel') {
    if (!RE_SERIAL.test(d)) badOrder(fmt, row, column);
    const v = Number(d);
    // Serial 60 is Excel's 29 Feb 1900, a day that never was; everything before 61 is before 1970 anyway.
    if (v < 61) fail('E_BAD_DATE', 'the date or time is out of range', row, column);
    if (timed) {
      if (d.indexOf('.') !== -1) badOrder(fmt, row, column);
      if (mi > 59 || sec > 59 || h > 23) fail('E_BAD_DATE', 'the date or time is out of range', row, column);
      return inRange((v - 25569) * 86400000 + ((h * 60 + mi) * 60 + sec) * 1000, row, column);
    }
    return inRange((Math.floor(v * 86400 + 0.5) - 25569 * 86400) * 1000, row, column);
  }
  let y, mo, dd, x;
  if (fmt === 'ymd') {
    if ((x = RE_YMD.exec(d))) { y = Number(x[1]); mo = Number(x[3]); dd = Number(x[4]); }
    else if ((x = RE_YMD8.exec(d))) { y = Number(x[1]); mo = Number(x[2]); dd = Number(x[3]); }
    else badOrder(fmt, row, column);
  } else if (fmt === 'mdy' || fmt === 'dmy') {
    x = RE_DMY.exec(d);
    if (!x) badOrder(fmt, row, column);
    const a = Number(x[1]), b = Number(x[3]);
    y = Number(x[4]) + (x[4].length === 2 ? 2000 : 0);
    if (fmt === 'mdy') { mo = a; dd = b; } else { dd = a; mo = b; }
    if (mo > 12) badOrder(fmt, row, column);
  } else {
    fail('E_BAD_DATE', 'no date form was chosen', row, column);
  }
  return utcMs(y, mo, dd, h, mi, sec, row, column);
}

// The form of one date cell, for detectDateFormat: 'ymd' | 'dm' (day and month in some order)
// | 'excel' | 'epoch_s' | 'epoch_ms' | 'other'.
export function dateShape(raw) {
  const m = RE_DF.exec(stripZone(clean(raw))[0]);
  if (!m) return { kind: 'other', a: 0, b: 0 };
  const d = m[1];
  const timed = m[2] !== undefined;
  if (RE_YMD.test(d) || /^(19|20)\d{6}$/.test(d)) return { kind: 'ymd', a: 0, b: 0 };
  const x = RE_DMY.exec(d);
  if (x) return { kind: 'dm', a: Number(x[1]), b: Number(x[3]) };
  if (!timed && /^\d{12,13}$/.test(d)) return { kind: 'epoch_ms', a: 0, b: 0 };
  if (!timed && /^\d{9,10}(\.\d+)?$/.test(d)) return { kind: 'epoch_s', a: 0, b: 0 };
  if (/^\d{5}(\.\d+)?$/.test(d) && Number(d) >= 20000 && Number(d) <= 80000) return { kind: 'excel', a: 0, b: 0 };
  return { kind: 'other', a: 0, b: 0 };
}

// The date form of a column, from its cells, or a reason it cannot be told:
// {format, reason, at, at2}: reason null (one form), 'seen' (a day part over 12 showed the order;
// at = that cell's index), 'ask' (every day and month part is 12 or less), 'mixed' (more than one
// form, or a cell that is no date), 'mixed_order' (day-first at `at` and month-first at `at2`),
// 'empty'. Nothing is ever guessed: 'ask' means the user chooses.
export function detectDateFormat(values) {
  const kinds = [];
  let dmyAt = -1;
  let mdyAt = -1;
  for (let i = 0; i < values.length; i++) {
    if (clean(values[i]) === '') continue;
    const sh = dateShape(values[i]);
    if (!kinds.includes(sh.kind)) kinds.push(sh.kind);
    if (sh.kind === 'dm') {
      if (sh.a > 12 && dmyAt < 0) dmyAt = i;
      if (sh.b > 12 && mdyAt < 0) mdyAt = i;
    }
  }
  if (kinds.length === 0) return { format: null, reason: 'empty', at: -1, at2: -1 };
  if (kinds.length > 1 || kinds[0] === 'other') return { format: null, reason: 'mixed', at: -1, at2: -1 };
  if (kinds[0] !== 'dm') return { format: kinds[0], reason: null, at: -1, at2: -1 };
  if (dmyAt >= 0 && mdyAt >= 0) return { format: null, reason: 'mixed_order', at: dmyAt, at2: mdyAt };
  if (dmyAt >= 0) return { format: 'dmy', reason: 'seen', at: dmyAt, at2: -1 };
  if (mdyAt >= 0) return { format: 'mdy', reason: 'seen', at: mdyAt, at2: -1 };
  return { format: null, reason: 'ask', at: -1, at2: -1 };
}

// ---------------------------------------------------------------- a pasted table
// Copying an HTML table or a web grid gives tab-separated text in Chrome, Firefox and Safari. A
// paste with a tab anywhere is split on tabs (a blank cell stays a cell). Otherwise the paste is a
// fixed-width grid: words are cut at runs of two or more spaces (never one: "2026-10-02 09:31:05"
// holds one), and each word of a row is placed under the heading it lines up with, by character
// position, so a blank cell never shifts the cells after it (Tester F1). The heading row is the
// first line with the most words; lines above it are left as they are (menus, balances). A row
// whose words do not line up under exactly one heading each is E_PASTE_ALIGN, naming its line,
// unless it holds at most half as many words as the headings (a footer: read as it is, and
// skipped as no_data later). Rows are like parseCsv's: {row: the 1-based line, cells}.
// Nothing here is kept: the pasted text lives only in the caller's memory.
const PASTE_SPACE = ' \u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000';

// Words of one line cut at runs of 2+ spaces: [{start, end, text}], positions in code points.
export function spaceWords(line) {
  const cps = Array.from(line);
  const n = cps.length;
  const sp = (c) => PASTE_SPACE.indexOf(c) !== -1;
  const out = [];
  let i = 0;
  while (i < n) {
    while (i < n && sp(cps[i])) i++;
    if (i >= n) break;
    const start = i;
    let end = i;
    while (i < n) {
      if (sp(cps[i])) {
        let j = i;
        while (j < n && sp(cps[j])) j++;
        if (j - i >= 2 || j >= n) break;
        i = j;
        continue;
      }
      i++;
      end = i;
    }
    out.push({ start, end, text: clean(cps.slice(start, end).join('')) });
  }
  return out;
}

// The cells of one row under the headings `ref`, or null when it cannot be told: a word under the
// text of two headings, or two words under one. A word under one heading's text goes there (a
// right-aligned number wider than its heading too); a word under none goes to the last heading
// that starts at or before it (a left-aligned value in the gap after a short heading).
export function alignWords(words, ref) {
  const cells = ref.map(() => '');
  for (const w of words) {
    let hit = -1;
    let hits = 0;
    for (let k = 0; k < ref.length; k++) {
      if (Math.min(w.end, ref[k].end) - Math.max(w.start, ref[k].start) > 0) { hits++; hit = k; }
    }
    if (hits > 1) return null;
    if (hits === 0) {
      hit = 0;
      for (let k = 0; k < ref.length; k++) if (ref[k].start <= w.start) hit = k;
    }
    if (cells[hit] !== '') return null;
    cells[hit] = w.text;
  }
  return cells;
}

export function fromPaste(text) {
  text = String(text);
  if (text.length > LIMITS.MAX_PASTE_CHARS) fail('E_PASTE_TOO_LARGE');
  if (clean(text) === '') fail('E_EMPTY');
  const lines = text.split(/\r\n|\n|\r/);
  const tabs = lines.some((l) => l.indexOf('\t') !== -1);
  const out = [];
  const push = (k, cells) => {
    out.push({ row: k + 1, cells, swallow: 0, ml: [], broken: false });
    if (out.length > LIMITS.MAX_ROWS + 1) fail('E_TOO_LARGE');
  };
  if (tabs) {
    let wide = 0;
    for (let k = 0; k < lines.length; k++) {
      if (clean(lines[k]) === '') continue;
      const cells = lines[k].split('\t').map(clean);
      if (cells.filter((c) => c !== '').length >= 2) wide++;
      push(k, cells);
    }
    if (wide === 0) fail('E_PASTE_FORMAT');
    return out;
  }
  const words = lines.map((l) => (clean(l) === '' ? null : spaceWords(l)));
  let refAt = -1;
  for (let k = 0; k < lines.length; k++) {
    if (words[k] && words[k].length >= 2 && (refAt < 0 || words[k].length > words[refAt].length)) refAt = k;
  }
  if (refAt < 0) fail('E_PASTE_FORMAT');
  const ref = words[refAt];
  for (let k = 0; k < lines.length; k++) {
    const w = words[k];
    if (!w) continue;
    if (k <= refAt) { push(k, w.map((x) => x.text)); continue; }
    const cells = alignWords(w, ref);
    if (cells) push(k, cells);
    else if (w.length * 2 <= ref.length) push(k, w.map((x) => x.text));
    else fail('E_PASTE_ALIGN', '', k + 1);
  }
  return out;
}
