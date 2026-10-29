// mapping.js — the column guess for the universal importer (plan §2.2, §2.7, §3). JS only.
//
// It decides nothing on its own: everything it returns is shown on the mapper screen and confirmed
// by the user (or is a preset, which only fires on an exact set of headings). So it is tested
// against expected-guess files (tests/test_mapping_guess.py), not mirrored in Python.
//
// inspect(item) → {peek, guess, preset}: what the page needs to open the mapper.
//   peek: the heading row and up to 60 rows for the preview, with every blocked column's cells
//         replaced by null (never shown, never offered in a dropdown);
//   guess: the layout, the column for each field with a badge (matched / check / choose), the
//          buy/sell and status value lists, the date and number questions, and a mapping built
//          from all of it (date_format and number_style stay null while a question is open);
//   preset: a shipped preset whose headings are all in the file, or null.
// Every string from the file goes to the page as data: the page writes it with textContent.

import { clean, normHeader, numberShape, dateShape, detectDateFormat, wideRows } from './csv.js';
import { ISO_CURRENCIES } from './detect.js';
import { isBlocked, moneyClean, normValue, numberQuestion, futuresRoot, STATUS_KEEP, MAP_FIELDS, isNoData,
  isRagged, dataRowsAfter, readRows } from './mapped.js';
import { CME_MULTIPLIERS } from './tradovate.js';
import { matchPreset, presetById } from './presets.js';

export const HEADER_SEARCH_ROWS = 50;
export const PEEK_ROWS = 60;
export const CONTENT_ROWS = 200;   // content tests look at the first 200 data rows
export const MAX_VALUES = 30;      // a value list longer than this is kept for the session only
export const MAX_VALUE_LEN = 40;

// Normalised headings per field, best first (research §5.3, plus the engine's aliases).
// English first, then Spanish and German (headings are compared with accents folded: "Símbolo" →
// "simbolo", "Stück" → "stuck"; foldHeader).
export const SYNONYMS = Object.freeze({
  datetime: ['datetime', 'dateandtime', 'timestamp', 'exectime', 'executiontime', 'filltime', 'filledtime', 'filledat',
    'updatetime', 'closingtime', 'transactiontime', 'tradetime', 'time', 'date', 'tradedate', 'activitydate', 'rundate',
    'transactiondate', 'orderdate', 'when',
    'fechahora', 'fechayhora', 'fecha', 'fechadeoperacion', 'zeitpunkt', 'datumuhrzeit', 'datumundzeit', 'datum',
    'handelsdatum', 'ausfuhrungszeit'],
  date: ['date', 'tradedate', 'activitydate', 'rundate', 'transactiondate', 'orderdate',
    'fecha', 'fechadeoperacion', 'datum', 'handelsdatum'],
  time: ['time', 'tradetime', 'exectime', 'executiontime', 'filltime', 'hora', 'uhrzeit', 'zeit'],
  symbol: ['symbol', 'ticker', 'instrument', 'contract', 'contractname', 'coin', 'pair', 'market', 'product', 'asset',
    'security', 'simbolo', 'instrumento', 'activo', 'valor', 'wertpapier', 'basiswert'],
  side: ['side', 'buysell', 'bs', 'action', 'transcode', 'direction', 'dir', 'type', 'transactiontype', 'code',
    'operacion', 'tipo', 'lado', 'compraventa', 'sentido', 'typ', 'art', 'richtung', 'kaufverkauf', 'seite', 'transaktion'],
  qty: ['quantity', 'qty', 'filledqty', 'qtyfilled', 'filledquantity', 'filledvolume', 'filled', 'size', 'volume', 'vol',
    'units', 'sz', 'noofshares', 'shares', 'lots', 'contracts', 'closingquantity', 'closingvolume', 'amount',
    'cantidad', 'volumen', 'titulos', 'acciones', 'contratos', 'lotes', 'menge', 'anzahl', 'stuck', 'stueck', 'kontrakte'],
  price: ['price', 'fillprice', 'avgfillprice', 'avgprice', 'averageprice', 'executionprice', 'tradeprice', 'px',
    'pricepershare', 'priceshare', 'precio', 'preciomedio', 'preciodeejecucion', 'cotizacion', 'kurs', 'preis',
    'ausfuhrungskurs', 'durchschnittspreis', 'ausfuhrungspreis'],
  fees: ['commission', 'commissions', 'fee', 'fees', 'feeamount', 'feescomm', 'commissionfees', 'charges',
    'comision', 'comisiones', 'gastos', 'gebuhr', 'gebuhren', 'provision', 'kommission', 'spesen'],
  currency: ['currency', 'ccy', 'currencypriceshare', 'divisa', 'moneda', 'wahrung'],
  status: ['status', 'orderstatus', 'state', 'estado', 'zustand'],
  open_time: ['opentime', 'openingtime', 'entrytime', 'opened', 'opendate', 'timeopened', 'entrydate', 'open',
    'fechaapertura', 'fechadeapertura', 'horaapertura', 'apertura', 'eroffnungszeit', 'eroffnung', 'einstiegszeit'],
  close_time: ['closetime', 'closingtime', 'exittime', 'closed', 'closedate', 'timeclosed', 'exitdate', 'close',
    'fechacierre', 'fechadecierre', 'horacierre', 'cierre', 'schliesszeit', 'schlusszeit', 'schliessung', 'ausstiegszeit'],
  direction: ['direction', 'openingdirection', 'longshort', 'side', 'type', 'tradetype', 'position', 'direccion',
    'tipo', 'sentido', 'richtung', 'typ'],
  open_price: ['openprice', 'entryprice', 'avgentryprice', 'averageentryprice', 'priceopen', 'precioapertura',
    'preciodeapertura', 'preciodeentrada', 'eroffnungskurs', 'einstiegskurs', 'einstiegspreis'],
  close_price: ['closeprice', 'closingprice', 'exitprice', 'avgexitprice', 'priceclose', 'preciocierre',
    'preciodecierre', 'preciodesalida', 'schlusskurs', 'ausstiegskurs', 'ausstiegspreis'],
  pnl: ['pnl', 'pl', 'profit', 'profitloss', 'realizedpnl', 'netpnl', 'gross', 'net', 'closedpnl', 'result',
    'beneficio', 'ganancia', 'resultado', 'gewinn', 'gewinnverlust', 'ergebnis'],
});

// Headings compared with accents folded, for the synonyms only (the engine's own checks use normHeader).
export function foldHeader(h) {
  return normHeader(String(h).normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ß/g, 'ss'));
}

// The 23 researched platforms, for the "Send us your headings" dropdown (no free text).
export const PLATFORMS = Object.freeze(['Robinhood', 'thinkorswim / Schwab', 'Webull', 'Match-Trader', 'cTrader',
  'Binance', 'TopstepX / ProjectX', 'NinjaTrader', 'Coinbase', 'Bybit', 'DXtrade', 'Fidelity', 'E*TRADE',
  'TradeLocker', 'Trading 212', 'eToro', 'Rithmic R|Trader Pro', 'Kraken', 'Questrade', 'Wealthsimple', 'OKX',
  'Sierra Chart', 'Hyperliquid', 'Other']);

const ISO = new Set(ISO_CURRENCIES);
const RE_TIME_ONLY = /^\d{1,2}:\d{2}(:\d{2})?([.,]\d+)?( ?[AaPp][Mm])?$/;
const synonymHits = (h) => Object.values(SYNONYMS).some((list) => list.includes(foldHeader(h)));

// ---------------------------------------------------------------- the heading row

// The first of the first 50 non-empty rows with 3 or more cells that are known headings (not
// blocked). → {index (into rows), hits}; with no such row, the first row with the most cells.
export function findHeaderRow(rows) {
  let seen = 0;
  let widest = -1;
  for (let i = 0; i < rows.length && seen < HEADER_SEARCH_ROWS; i++) {
    const cells = rows[i].cells;
    if (cells.every((c) => c === '')) continue;
    seen++;
    const hits = cells.filter((c) => { const n = normHeader(c); return n !== '' && !isBlocked(n) && synonymHits(c); }).length;
    if (hits >= 3) return { index: i, hits };
    if (widest < 0 || cells.length > rows[widest].cells.length) widest = i;
  }
  return { index: widest, hits: 0 };
}

// "Time", "Time" → "Time (1)", "Time (2)"; an empty heading → "Column 3".
export function headingLabels(cells) {
  const counts = {};
  for (const c of cells) counts[clean(c)] = (counts[clean(c)] || 0) + 1;
  const seen = {};
  return cells.map((c, i) => {
    const h = clean(c);
    if (h === '') return `Column ${i + 1}`;
    if (counts[h] === 1) return h;
    seen[h] = (seen[h] || 0) + 1;
    return `${h} (${seen[h]})`;
  });
}

function short(v) {
  const s = clean(v);
  return s.length > MAX_VALUE_LEN ? s.slice(0, MAX_VALUE_LEN - 1) + '…' : s;
}

// ---------------------------------------------------------------- peek

// The rows of the table a mapping would read: one HTML table (the one with the most rows unless
// `table` is given), or the whole CSV or paste.
function tableRows(src, table) {
  if (src.kind !== 'html') return { rows: src.rows, tables: null, table: null };
  const counts = new Map();
  for (const r of src.rows) if (r.table >= 0) counts.set(r.table, (counts.get(r.table) || 0) + 1);
  const tables = [...counts.entries()].map(([t, n]) => ({ table: t, rows: n }));
  let pick = table;
  if (pick === null || pick === undefined || !counts.has(pick)) {
    pick = tables.length ? tables.slice().sort((a, b) => (b.rows - a.rows) || (a.table - b.table))[0].table : -1;
  }
  return { rows: src.rows.filter((r) => r.table === pick), tables, table: pick };
}

// opts: {header_row (0-based physical line), table (HTML)}.
export function peekRows(src, opts = {}) {
  const t = tableRows(src, opts.table);
  const rows = t.rows;
  let at = -1;
  let hits = 0;
  if (opts.header_row !== undefined && opts.header_row !== null) {
    at = rows.findIndex((r) => r.row === opts.header_row + 1);
  }
  if (at < 0) ({ index: at, hits } = findHeaderRow(rows));
  else hits = rows[at].cells.filter((c) => { const n = normHeader(c); return !isBlocked(n) && synonymHits(c); }).length;
  if (at < 0) return { kind: src.kind, delimiter: src.delimiter, header_row: null, header_hits: 0, headers: [], labels: [],
    blocked: [], options: [], rows: [], n_rows: 0, tables: t.tables, table: t.table };
  const header = rows[at].cells;
  const norm = header.map(normHeader);
  const blocked = norm.map(isBlocked);
  const data = rows.slice(at + 1).filter((r) => !r.cells.every((c) => c === ''));
  const labels = headingLabels(header);
  const options = [];
  header.forEach((h, i) => {
    if (blocked[i]) return;
    const ex = data.map((r) => (i < r.cells.length ? r.cells[i] : '')).find((c) => c !== '');
    options.push({ index: i, label: labels[i], example: ex === undefined ? '' : short(ex) });
  });
  return {
    kind: src.kind, delimiter: src.delimiter, header_row: rows[at].row - 1, header_hits: hits, headers: header.slice(),
    labels, blocked, options,
    rows: data.slice(0, PEEK_ROWS).map((r) => ({ row: r.row, cells: header.map((_, i) => (blocked[i] ? null : (i < r.cells.length ? r.cells[i] : ''))) })),
    n_rows: data.length, tables: t.tables, table: t.table,
  };
}

// ---------------------------------------------------------------- value guesses

const SKIP_WORDS = ['dividend', 'deposit', 'withdrawal', 'interest', 'fee', 'tax', 'transfer', 'journal', 'ach', 'cdiv',
  'oexp', 'oasgn', 'split', 'funding', 'balance', 'credit', 'reinvestment', 'conversion'];

// → {value: 'buy' | 'sell' | 'skip', check: null | 'unknown' | 'options' | 'ask_side'}
export function guessSide(raw, all = []) {
  const k = normValue(raw).normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const words = k.split(/[^a-z]+/).filter(Boolean);
  if (['bto', 'btc'].includes(k)) return { value: 'buy', check: 'options' };
  if (['sto', 'stc'].includes(k)) return { value: 'sell', check: 'options' };
  if (k === 'a' && all.map(normValue).includes('b')) return { value: 'sell', check: 'ask_side' };
  if (k.indexOf('open long') !== -1 || k.indexOf('close short') !== -1) return { value: 'buy', check: null };
  if (k.indexOf('open short') !== -1 || k.indexOf('close long') !== -1) return { value: 'sell', check: null };
  if (SKIP_WORDS.some((w) => words.includes(w) || k === w)) return { value: 'skip', check: null };
  // Spanish and German: venta / Verkauf before compra / Kauf ("verkauf" holds "kauf").
  if (/venta|verkauf|vendido/.test(k)) return { value: 'sell', check: null };
  if (/compra|kauf|comprado/.test(k)) return { value: 'buy', check: null };
  if (/buy|bought|cover/.test(k) || words.includes('long') || k === 'b') return { value: 'buy', check: null };
  if (/sell|sold/.test(k) || words.includes('short') || k === 's') return { value: 'sell', check: null };
  if (k.startsWith('b')) return { value: 'buy', check: 'unknown' };
  if (k.startsWith('s')) return { value: 'sell', check: 'unknown' };
  return { value: 'skip', check: 'unknown' };
}

const STATUS_SKIP = ['cancelled', 'canceled', 'rejected', 'expired', 'working', 'pending', 'new', 'open', 'replaced',
  'suspended', 'pending cancel'];

export function guessStatus(raw) {
  const k = normValue(raw);
  if (STATUS_KEEP.includes(k) || k === 'fill' || k === 'fills') return { value: 'keep', check: null };
  if (STATUS_SKIP.includes(k)) return { value: 'skip', check: null };
  return { value: 'skip', check: 'unknown' };
}

// Distinct values of one column (normalised), with counts, in first-seen order.
function valueCounts(rows, i) {
  const counts = new Map();
  for (const r of rows) {
    const v = i < r.cells.length ? normValue(r.cells[i]) : '';
    if (v === '') continue;
    counts.set(v, (counts.get(v) || 0) + 1);
  }
  return counts;
}

// ---------------------------------------------------------------- content tests

function sample(rows, i) {
  const out = [];
  for (const r of rows) {
    if (out.length >= CONTENT_ROWS) break;
    const v = i < r.cells.length ? r.cells[i] : '';
    if (v !== '') out.push(v);
  }
  return out;
}

const isNumberCell = (v) => { const s = numberShape(moneyClean(v)); return s !== 'other'; };

// A time-only column that is plainly a duration (a hold time), from its values alone: an hour part
// over 23, a minutes part of 3 or more digits, or an m:ss.f form (Tester F6, N3). Never joined.
// Units ("1m 30s") and day parts never match RE_TIME_ONLY, so they are never read as a time at all.
function plainlyDuration(vs) {
  return vs.some((v) => {
    const c = clean(v);
    const parts = c.replace(/ ?[AaPp][Mm]$/, '').split(':');
    return Number(parts[0]) > 23 || parts[0].length > 2 || (parts.length === 2 && /[.,]\d/.test(parts[1]));
  });
}

const secondsOf = (v) => {
  const p = clean(v).replace(/ ?[AaPp][Mm]$/, '').split(':').map((x) => parseFloat(x.replace(',', '.')));
  return (p[0] || 0) * 3600 + (p[1] || 0) * 60 + (p[2] || 0);
};

// A time column next to its date, as a clock or a duration: 'clock' | 'duration' | 'unsure'.
// Unsure when the times run both up and down within one date (a clock moves one way through a day,
// a hold time does not), or when every hour is 00 and the column is not next to the date (a hold of
// minutes reads just like trades in the first hour after midnight; next to the date it is a clock,
// Tester N3). The guess asks then (time_or_duration) and leaves the time out until the user says.
export function timeKind(rows, ti, di) {
  const vs = rows.map((r) => (ti < r.cells.length ? clean(r.cells[ti]) : '')).filter((v) => v !== '');
  if (plainlyDuration(vs)) return 'duration';
  let up = 0;
  let down = 0;
  let prevDate = null;
  let prev = null;
  for (const r of rows) {
    const d = di < r.cells.length ? clean(r.cells[di]) : '';
    const t = ti < r.cells.length ? clean(r.cells[ti]) : '';
    if (t === '') continue;
    const sec = secondsOf(t);
    if (d === prevDate && prev !== null) { if (sec > prev) up++; else if (sec < prev) down++; }
    prevDate = d;
    prev = sec;
  }
  if (up > 0 && down > 0) return 'unsure';
  const allZeroHour = vs.length > 0 && vs.every((v) => secondsOf(v) < 3600) && !vs.every((v) => secondsOf(v) === 0);
  if (allZeroHour && Math.abs(ti - di) !== 1) return 'unsure';
  return 'clock';
}

// What kind of value a cell holds, for telling a summary row from a data row.
function cellKind(v) {
  const c = clean(v);
  if (c === '') return '';
  if (RE_TIME_ONLY.test(c)) return 'time';
  if (numberShape(moneyClean(c)) !== 'other') return 'num';
  if (dateShape(c).kind !== 'other') return 'date';
  return 'text';
}

// Totals, report lines and footers, by what they hold rather than how many cells (Tester N2): a
// cell that starts with a summary word, or more than half of the usually-filled columns blank or
// holding another kind of value than the column does in the rows around it.
const RE_SUMMARY = /^((sub|grand) ?)?totals?\b|^summary\b|^report\b|^page \d|^showing\b|^generated\b|^printed\b|^period\b|^from$|^to$|^note\b|^notes\b|^disclaimer\b|^balance\b|^count\b|^average\b|^sum\b/i;

export function summaryRows(rows, width) {
  const fill = new Array(width).fill(0);
  const kinds = Array.from({ length: width }, () => ({}));
  for (const r of rows) {
    for (let i = 0; i < width; i++) {
      const k = cellKind(i < r.cells.length ? r.cells[i] : '');
      if (k === '') continue;
      fill[i]++;
      kinds[i][k] = (kinds[i][k] || 0) + 1;
    }
  }
  const usual = [];
  const dominant = [];
  for (let i = 0; i < width; i++) {
    if (rows.length && fill[i] >= 0.8 * rows.length) {
      usual.push(i);
      dominant[i] = Object.entries(kinds[i]).sort((a, b) => (b[1] - a[1]) || (a[0] < b[0] ? -1 : 1))[0][0];
    }
  }
  const out = new Set();
  for (const r of rows) {
    if (r.cells.some((c) => RE_SUMMARY.test(clean(c)))) { out.add(r); continue; }
    let bad = 0;
    for (const i of usual) if (cellKind(i < r.cells.length ? r.cells[i] : '') !== dominant[i]) bad++;
    if (usual.length && bad * 2 > usual.length) out.add(r);
  }
  return out;
}

const CONTENT = {
  datetime: (vs) => vs.length > 0 && vs.every((v) => dateShape(v).kind !== 'other'),
  date: (vs) => vs.length > 0 && vs.every((v) => dateShape(v).kind !== 'other'),
  time: (vs) => vs.length > 0 && vs.every((v) => RE_TIME_ONLY.test(clean(v))) && !plainlyDuration(vs),
  symbol: (vs) => vs.length > 0 && vs.every((v) => v.length <= 40 && !/^[+-]?[\d.,]+$/.test(v)),
  side: (vs) => {
    const all = [...new Set(vs.map(normValue))];
    const g = all.map((v) => guessSide(v, all).value);
    return all.length > 0 && all.length <= MAX_VALUES && g.includes('buy') && g.includes('sell');
  },
  qty: (vs) => vs.length > 0 && vs.every(isNumberCell),
  price: (vs) => vs.length > 0 && vs.every(isNumberCell),
  fees: (vs) => vs.every(isNumberCell),
  currency: (vs) => vs.length > 0 && vs.every((v) => ISO.has(clean(v).toUpperCase())),
  status: (vs) => vs.length > 0 && vs.some((v) => guessStatus(v).check === null),
  pnl: (vs) => vs.every(isNumberCell),
};
CONTENT.open_time = CONTENT.datetime;
CONTENT.close_time = CONTENT.datetime;
CONTENT.direction = (vs) => {
  const all = [...new Set(vs.map(normValue))];
  return all.length > 0 && all.length <= MAX_VALUES && all.every((v) => /^(l|b|s)/.test(v) || guessSide(v, all).value !== 'skip');
};
CONTENT.open_price = CONTENT.price;
CONTENT.close_price = CONTENT.price;

// ---------------------------------------------------------------- the guess

function pick(norm, blocked, used, synonyms, test) {
  // The first synonym (best first) whose column passes the content test; else the first by name.
  let byName = -1;
  for (const s of synonyms) {
    for (let i = 0; i < norm.length; i++) {
      if (norm[i] !== s || blocked[i] || used.has(i)) continue;
      if (test(i)) return { index: i, badge: 'matched' };
      if (byName < 0) byName = i;
    }
  }
  return byName >= 0 ? { index: byName, badge: 'check' } : null;
}

export function guessLayout(norm) {
  const has = (field) => norm.some((n) => SYNONYMS[field].includes(n));
  if ((has('open_time') && has('close_time')) || (has('open_price') && has('close_price'))) return 'roundtrips';
  if (has('status') && norm.some((n) => ['avgfillprice', 'avgprice', 'averageprice', 'filledqty', 'qtyfilled',
    'filledquantity', 'filledvolume', 'filled'].includes(n))) return 'orders';
  return 'fills';
}

const REQUIRED = {
  fills: ['date', 'symbol', 'side', 'qty', 'price'],
  orders: ['date', 'symbol', 'side', 'qty', 'price'],
  roundtrips: ['open_time', 'close_time', 'symbol', 'direction', 'qty', 'open_price', 'close_price'],
};

// "03/04/2026" → both readings as yyyy-mm-dd, for "Which date is it?" (the page words them).
function readings(v) {
  const m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})/.exec(clean(v));
  if (!m) return null;
  const y = m[3].length === 2 ? 2000 + Number(m[3]) : Number(m[3]);
  const p = (n) => String(n).padStart(2, '0');
  return { dmy: `${y}-${p(m[2])}-${p(m[1])}`, mdy: `${y}-${p(m[1])}-${p(m[2])}` };
}

// peek + all of the file's rows after the heading → the guess.
export function guessMapping(peek, dataRows, opts = {}) {
  const norm = peek.headers.map(normHeader);   // what the mapping records (the engine checks it)
  const syn = peek.headers.map(foldHeader);    // what the synonyms are matched with
  const blocked = peek.blocked;
  const layout = opts.layout || guessLayout(syn);
  const width = peek.headers.length;
  const valueRows = dataRows.filter((r) => !r.cells.every((c) => c === '') && !isNoData(r.cells, width) &&
    !(peek.kind === 'paste' && isRagged(r.cells, width)));
  // Footers, totals and page lines ("Total fills,20", "Page 1 of 3", "Report date,2026-10-29,
  // Total,20") are left out of every content test and question (Tester F5, N2): a row with at most
  // half the median number of filled cells, or a summary row by what it holds (summaryRows).
  const filled = (r) => r.cells.filter((c) => c !== '').length;
  const counts = valueRows.map(filled).sort((a, b) => a - b);
  const median = counts.length ? counts[Math.floor(counts.length / 2)] : 0;
  const summary = summaryRows(valueRows, width);
  const rows = valueRows.filter((r) => filled(r) * 2 > median && !summary.has(r));
  const shortRows = valueRows.filter((r) => filled(r) * 2 <= median || summary.has(r));
  const vals = (i) => sample(rows, i);
  const used = new Set();
  let timeQuestion = null;
  const cols = {};
  for (const f of MAP_FIELDS) cols[f] = null;
  const badges = {};
  const take = (field, synonyms, test) => {
    const p = pick(syn, blocked, used, synonyms, (i) => test(vals(i)));
    if (p) { cols[field] = p.index; badges[field] = p.badge; used.add(p.index); }
    return p;
  };
  if (layout === 'roundtrips') {
    take('open_time', SYNONYMS.open_time, CONTENT.open_time);
    take('close_time', SYNONYMS.close_time, CONTENT.close_time);
    take('symbol', SYNONYMS.symbol, CONTENT.symbol);
    take('direction', SYNONYMS.direction, CONTENT.direction);
    take('qty', SYNONYMS.qty, CONTENT.qty);
    take('open_price', SYNONYMS.open_price, CONTENT.open_price);
    take('close_price', SYNONYMS.close_price, CONTENT.close_price);
    take('pnl', SYNONYMS.pnl, CONTENT.pnl);
  } else {
    // A date column plus a time-only column, or one date-and-time column.
    const d = pick(syn, blocked, used, SYNONYMS.date, (i) => CONTENT.date(vals(i)));
    let dateDone = false;
    if (d && d.badge === 'matched' && vals(d.index).every((v) => dateShape(v).kind !== 'other' && !/\d:\d{2}/.test(v))) {
      used.add(d.index);
      const t = pick(syn, blocked, used, SYNONYMS.time, (i) => CONTENT.time(vals(i)));
      const tk = t && t.badge === 'matched' ? timeKind(rows, t.index, d.index) : null;
      if (tk === 'clock') {
        cols.date = d.index; badges.date = 'matched'; cols.time = t.index; badges.time = 'matched'; used.add(t.index);
        dateDone = true;
      } else if (tk === 'unsure') {
        // A clock or a hold time: the date alone until the user says (never a time dropped unasked).
        cols.date = d.index; badges.date = 'matched'; badges.time = 'check';
        const k = rows.findIndex((r) => t.index < r.cells.length && r.cells[t.index] !== '');
        timeQuestion = { q: 'time_or_duration', column: t.index, label: peek.labels[t.index],
          example: k >= 0 ? short(rows[k].cells[t.index]) : '', row: k >= 0 ? rows[k].row : null };
        dateDone = true;
      } else used.delete(d.index);
    }
    if (!dateDone) take('date', SYNONYMS.datetime, CONTENT.datetime);
    take('symbol', SYNONYMS.symbol, CONTENT.symbol);
    take('side', SYNONYMS.side, CONTENT.side);
    take('qty', SYNONYMS.qty, CONTENT.qty);
    take('price', SYNONYMS.price, CONTENT.price);
    take('status', SYNONYMS.status, CONTENT.status);
  }
  take('currency', SYNONYMS.currency, CONTENT.currency);
  // Fees: every fee-like column, up to three, summed.
  const fees = [];
  for (const s of SYNONYMS.fees) {
    for (let i = 0; i < norm.length && fees.length < 3; i++) {
      if (syn[i] === s && !blocked[i] && !used.has(i) && CONTENT.fees(vals(i))) { fees.push(i); used.add(i); }
    }
  }
  if (fees.length) { cols.fees = fees; badges.fees = 'matched'; }
  // Side: a column, or the sign of Quantity when there is no side column and quantities go negative.
  let sideFrom = 'column';
  if (layout !== 'roundtrips' && cols.side === null && cols.qty !== null &&
      vals(cols.qty).some((v) => moneyClean(v).startsWith('-'))) {
    sideFrom = 'sign';
    badges.side = 'check';
  }
  for (const f of REQUIRED[layout]) {
    if (f === 'side' && sideFrom === 'sign') continue;
    if (cols[f] === null) badges[f] = 'choose';
  }
  // Value lists.
  const sideCol = layout === 'roundtrips' ? cols.direction : cols.side;
  let sideValues = null;
  const sideChecks = {};
  let sideCounts = null;
  let sideSessionOnly = false;
  if (sideCol !== null && sideFrom === 'column') {
    // Short rows add a value only when it reads as a known word (a Dividend row, not "of 3").
    const counts = valueCounts(rows, sideCol);
    for (const [v, n] of valueCounts(shortRows, sideCol)) {
      if (counts.has(v)) counts.set(v, counts.get(v) + n); else if (guessSide(v).check === null) counts.set(v, n);
    }
    const all = [...counts.keys()];
    sideValues = {};
    sideCounts = {};
    for (const v of all) {
      const g = guessSide(v, all);
      sideValues[v] = g.value;
      sideCounts[v] = counts.get(v);
      if (g.check) sideChecks[v] = g.check;
    }
    sideSessionOnly = all.length > MAX_VALUES || all.some((v) => v.length > MAX_VALUE_LEN);
  }
  let statusValues = null;
  const statusChecks = {};
  let statusCounts = null;
  if (layout !== 'roundtrips' && cols.status !== null) {
    const counts = valueCounts(rows, cols.status);
    for (const [v, n] of valueCounts(shortRows, cols.status)) {
      if (counts.has(v)) counts.set(v, counts.get(v) + n); else if (guessStatus(v).check === null) counts.set(v, n);
    }
    statusValues = {};
    statusCounts = {};
    for (const [v, n] of counts) {
      const g = guessStatus(v);
      statusValues[v] = g.value;
      statusCounts[v] = n;
      if (g.check) statusChecks[v] = g.check;
    }
  }
  // Questions the data leaves open.
  const questions = [];
  if (timeQuestion) questions.push(timeQuestion);
  let dateInfo = null;
  const dateCols = layout === 'roundtrips' ? [cols.open_time, cols.close_time] : [cols.date];
  if (dateCols.every((i) => i !== null)) {
    const values = [];
    for (const r of rows) for (const i of dateCols) values.push(i < r.cells.length ? r.cells[i] : '');
    const det = detectDateFormat(values);
    // The file's own row numbers, never an index or a -1 (Tester F5).
    const rowOf = (k) => (k >= 0 ? rows[Math.floor(k / dateCols.length)].row : null);
    dateInfo = { format: det.format, reason: det.reason, seen: det.at >= 0 ? short(values[det.at]) : null,
      seen_row: rowOf(det.at), seen2: det.at2 >= 0 ? short(values[det.at2]) : null, seen2_row: rowOf(det.at2) };
    // Two-digit years 50-99: the engine reads them only with a century chosen (year_base).
    const yk = values.findIndex((v) => { const y = /^\d{1,2}[-/.]\d{1,2}[-/.](\d{2})(?!\d)/.exec(clean(v)); return y && Number(y[1]) >= 50; });
    if (yk >= 0) questions.push({ q: 'two_digit_year', example: short(values[yk]), row: rowOf(yk) });
    if (det.reason === 'ask') {
      const k = values.findIndex((v) => dateShape(v).kind === 'dm');
      questions.push({ q: 'date_order', example: short(values[k]), row: rowOf(k), readings: readings(values[k]) });
    } else if (det.format === null) {
      questions.push({ q: 'date_order', error: det.reason, rows: [rowOf(det.at), rowOf(det.at2)].filter((x) => x !== null) });
    }
  }
  const numIdx = [];
  for (const f of layout === 'roundtrips' ? ['qty', 'open_price', 'close_price', 'pnl'] : ['qty', 'price']) {
    if (cols[f] !== null) numIdx.push(cols[f]);
  }
  for (const i of fees) numIdx.push(i);
  const nq = numberQuestion(rows, numIdx, peek.kind === 'csv' ? peek.delimiter : peek.kind === 'html' ? ',' : '\t');
  if (nq) {
    let ex = '';
    for (const r of rows) {
      for (const i of numIdx) {
        const c = i < r.cells.length ? moneyClean(r.cells[i]) : '';
        if (/^[+-]?\d+,\d{3}$/.test(c) || numberShape(c) === 'dot3') { ex = c; break; }
      }
      if (ex) break;
    }
    questions.push({ q: 'number_style', example: short(ex) });
  }
  // Rows an unquoted comma made wider than the heading: a split number (1,000) in a read number
  // column is refused by the engine, so the page says which rows, before the run (Tester F2).
  {
    const kinds = {};
    for (const f of MAP_FIELDS) {
      const v = cols[f];
      if (v === null) continue;
      const kind = ['qty', 'price', 'open_price', 'close_price', 'pnl', 'fees'].includes(f) ? 'num'
        : f === 'currency' ? 'ccy' : ['date', 'time', 'open_time', 'close_time'].includes(f) ? 'date' : 'text';
      for (const i of Array.isArray(v) ? v : [v]) kinds[i] = kind;
    }
    const wr = wideRows(rows, width, kinds, ISO);
    if (wr.split.length) questions.push({ q: 'split_number', rows: wr.split.slice(0, 5).map((x) => x.row), n: wr.split.length });
  }
  // Futures sizes: offered when the symbols are CME contracts the size table knows.
  let futuresOffer = false;
  if (cols.symbol !== null && layout !== 'roundtrips') {
    const syms = [...new Set(vals(cols.symbol).map((s) => s.toUpperCase()))];
    futuresOffer = syms.length > 0 && syms.filter((s) => Object.prototype.hasOwnProperty.call(CME_MULTIPLIERS, futuresRoot(s))).length * 2 >= syms.length;
  }
  const headers = {};
  for (const f of MAP_FIELDS) {
    const v = cols[f];
    if (v === null) continue;
    for (const i of Array.isArray(v) ? v : [v]) headers[String(i)] = norm[i];
  }
  const mapping = {
    v: 1, layout, header_row: peek.header_row, delimiter: peek.kind === 'csv' ? peek.delimiter : null, cols, headers,
    side_from: sideFrom, side_values: sideValues, side_rules: null, side_default: null,
    status_values: statusValues, status_rules: null,
    date_format: dateInfo && dateInfo.format ? dateInfo.format : null, number_style: null, futures_sizes: false,
    currency: null, year_base: null, preset: null, section: false, trim_ragged: peek.kind === 'paste',
    source: peek.kind === 'html' ? { kind: 'html', table: peek.table } : null, tz: null, keep_partial: false,
  };
  return {
    layout, badges, side_checks: sideChecks, side_counts: sideCounts, side_session_only: sideSessionOnly,
    status_checks: statusChecks, status_counts: statusCounts, date: dateInfo, questions,
    futures_offer: futuresOffer, currency_offer: cols.currency === null, mapping,
  };
}

// ---------------------------------------------------------------- one call for the page

// The delimiter of a CSV whose first line is a title (a Sierra log, a Fidelity history): the one
// that splits the most of the first 60 non-empty lines into 3 or more cells; a tie keeps `first`
// (sniffDelimiter's choice from the first line, which known formats are read with).
export function sniffDeep(text, first) {
  const lines = [];
  for (const l of text.split(/\r\n|\n|\r/)) {
    if (clean(l) !== '') lines.push(l);
    if (lines.length >= 60) break;
  }
  const score = (d) => lines.filter((l) => {
    let n = 1;
    let inQ = false;
    for (const ch of l) { if (ch === '"') inQ = !inQ; else if (!inQ && ch === d) n++; }
    return n >= 3;
  }).length;
  let best = first;
  let top = score(first);
  for (const d of [',', ';', '\t']) {
    const v = score(d);
    if (v > top) { best = d; top = v; }
  }
  return best;
}

// item: file bytes or {paste}. opts: {delimiter, header_row, table, layout}.
// Throws only what reading the file throws (E_EMPTY, E_ENCODING, E_BAD_QUOTE, E_PASTE_FORMAT...).
export function inspect(item, opts = {}) {
  let src = readRows(item, opts.delimiter || null);
  if (src.kind === 'csv' && !opts.delimiter) {
    const d = sniffDeep(src.text, src.delimiter);
    if (d !== src.delimiter) src = readRows(item, d);
  }
  const peek = peekRows(src, opts);
  const p = matchPreset(src);
  const preset = p ? { id: p.preset, name: presetById(p.preset).name, mapping: p.mapping, questions: p.questions } : null;
  if (peek.header_row === null) return { peek, guess: null, preset };
  const t = src.kind === 'html' ? src.rows.filter((r) => r.table === peek.table) : src.rows;
  const at = t.findIndex((r) => r.row === peek.header_row + 1);
  const guess = guessMapping(peek, dataRowsAfter(t, at, false), opts);
  return { peek, guess, preset };
}

// ---------------------------------------------------------------- the signature of a file's headings

// 32 hex characters of SHA-256 over the sorted normalised headings, the column count and the
// delimiter. No row data goes in. Keys the mappings saved in this browser.
export async function signature(headers, delimiter) {
  const norm = headers.map(normHeader).sort();
  const text = JSON.stringify([norm, headers.length, delimiter || '']);
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
}

// ---------------------------------------------------------------- "Send us your headings"

export const HEADINGS_MAX_CELL = 60;
export const HEADINGS_MAX_BODY = 1000;

// The heading row only, never a data row. → {ok, reason, subject, body}. reason (when not ok):
// 'platform' | 'long_cell' | 'data_cell' | 'digits' | 'not_found' | 'too_long'.
// confirmed: the user set "Headings are on row n" themselves.
export function headingsEmail(headers, platform, hits, confirmed = false) {
  const no = (reason) => ({ ok: false, reason, subject: null, body: null });
  if (!PLATFORMS.includes(platform)) return no('platform');
  const cells = headers.map(clean);
  for (let i = 0; i < cells.length; i++) {
    const c = cells[i];
    if (c.length > HEADINGS_MAX_CELL) return no('long_cell');
    // A tab inside a cell would break the tab-joined body; an @ is an e-mail address, never a heading.
    if (/[\t@]/.test(String(headers[i]))) return no('data_cell');
    if (/\d{4,}/.test(c)) return no('digits');
    if (c !== '' && (numberShape(moneyClean(c)) !== 'other' || dateShape(c).kind !== 'other')) return no('data_cell');
  }
  if (!(hits >= 3 || confirmed)) return no('not_found');
  const subject = `Header row: ${platform}`;
  const body = `Platform: ${platform}\n\n${cells.join('\t')}\n`;
  if (body.length > HEADINGS_MAX_BODY) return no('too_long');
  return { ok: true, reason: null, subject, body };
}

// The mailto: link; the address comes from the page's build-time <meta name="dt-contact">.
export function headingsMailto(address, mail) {
  return `mailto:${address}?subject=${encodeURIComponent(mail.subject)}&body=${encodeURIComponent(mail.body)}`;
}
