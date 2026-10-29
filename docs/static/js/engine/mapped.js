// mapped.js — the universal importer: a file read through a column mapping the user chose (or a
// preset that ships with the site), several files read together, and pasted tables.
//
// The mapping (plan §2.3) names, for each field, the index of the column that holds it, and the
// heading the user saw at that index. The engine checks the file against it and refuses with
// E_BAD_MAPPING (naming the field, never a cell) when anything does not fit: a stale saved mapping,
// a heading that moved, or a column on the block list (account, name, email, notes...), so a
// tampered saved mapping can never read one.
//
// Mapped rows go through the same finish() as every format, in the shapes parseGeneric and
// parseGenericRoundtrip push, so skip reasons, warnings and trades mean what they mean elsewhere.
// Mirrors parse_mapped(), parse_files() and the helpers around them in tests/reference/engine_ref.py.

import { clean, normHeader, parseNumber, resolveNumberStyle, checkQuoting, parseDateFmt, fallBackClose,
  numberShape, DATE_FORMATS } from './csv.js?v=e5cb6d8a';
import { ISO_CURRENCIES, checkCurrencyColumn } from './detect.js?v=617d097a';
import { fail, LIMITS } from './errors.js?v=eef16098';
import { reqNumber, optNumber, skip, isEmptyRow } from './mt.js?v=d38d008e';
import { sideLetter } from './generic.js?v=05fc4a4b';
import { CME_MULTIPLIERS } from './tradovate.js?v=312cc737';

// ---------------------------------------------------------------- the block list
// Never offered in a dropdown, never read: a heading that is one of `exact`, or holds one of
// `contains` (normalised: lowercase, letters and digits only). "Account Display Name", "Trade
// Account", "acct_no", "Wallet address", "E-mail" are all caught. An on-chain transaction hash is
// blocked too: it can be looked up to find the wallet.
export const BLOCKED = Object.freeze({
  contains: ['account', 'acct', 'wallet', 'email', 'phone'],
  exact: ['name', 'fullname', 'firstname', 'lastname', 'owner', 'user', 'uid', 'userid', 'username', 'address',
    'clientid', 'traderid', 'comment', 'comments', 'note', 'notes', 'remark', 'remarks', 'hash', 'txhash',
    'transactionhash'],
});

export function isBlocked(norm) {
  return BLOCKED.exact.includes(norm) || BLOCKED.contains.some((w) => norm.indexOf(w) !== -1);
}

// ---------------------------------------------------------------- money cells (mapped mode only)
// "$1,234.50" → "1,234.50"; "(12.30)" and "12.30-" → "-12.30"; "-$12.30", "$-12.30", "12.30 USD",
// "€ 12,30" too. Anything else is returned as it was, for parseNumber to refuse. Existing formats
// never go through this, so their results do not change.
const MONEY_SYMBOLS = '$€£¥₹';
const MONEY_SIGNS = '+-−';
const ISO = new Set(ISO_CURRENCIES);

export function moneyClean(raw) {
  const orig = clean(raw);
  let s = orig;
  if (s === '') return s;
  let neg = false;
  if (s.length > 2 && s[0] === '(' && s[s.length - 1] === ')') { neg = true; s = clean(s.slice(1, -1)); }
  else if (s.length > 1 && (s[s.length - 1] === '-' || s[s.length - 1] === '−')) { neg = true; s = clean(s.slice(0, -1)); }
  let sign = '';
  if (s !== '' && MONEY_SIGNS.includes(s[0])) { sign = s[0]; s = clean(s.slice(1)); }
  if (s !== '' && MONEY_SYMBOLS.includes(s[0])) s = clean(s.slice(1));
  else if (s.length > 3 && /^[A-Za-z]{3} ?[0-9.,]/.test(s) && ISO.has(s.slice(0, 3).toUpperCase())) s = clean(s.slice(3));
  if (s !== '' && MONEY_SYMBOLS.includes(s[s.length - 1])) s = clean(s.slice(0, -1));
  else if (s.length > 3 && /[0-9.,] ?[A-Za-z]{3}$/.test(s) && ISO.has(s.slice(-3).toUpperCase())) s = clean(s.slice(0, -3));
  if (sign === '' && s !== '' && MONEY_SIGNS.includes(s[0])) { sign = s[0]; s = clean(s.slice(1)); }
  if (s === '' || (neg && sign !== '')) return orig;
  return (neg || sign === '-' || sign === '−' ? '-' : '') + s;
}

// ---------------------------------------------------------------- the mapping object

export const LAYOUTS = Object.freeze(['fills', 'orders', 'roundtrips']);
export const MAP_FIELDS = Object.freeze(['date', 'time', 'symbol', 'side', 'qty', 'price', 'fees', 'currency', 'status',
  'open_time', 'close_time', 'direction', 'open_price', 'close_price', 'pnl']);
const LAYOUT_FIELDS = {
  fills: { required: ['date', 'symbol', 'side', 'qty', 'price'], optional: ['time', 'fees', 'currency', 'status'] },
  roundtrips: { required: ['open_time', 'close_time', 'symbol', 'direction', 'qty', 'open_price', 'close_price'],
    optional: ['fees', 'currency', 'pnl'] },
};
LAYOUT_FIELDS.orders = LAYOUT_FIELDS.fills;
const NUMERIC = { fills: ['qty', 'price'], orders: ['qty', 'price'], roundtrips: ['qty', 'open_price', 'close_price', 'pnl'] };
const RULE_KINDS = ['eq', 'prefix', 'contains'];
// Kept when a Status column is mapped with no value list (the guess pre-ticks the same values).
export const STATUS_KEEP = Object.freeze(['filled', 'fully filled', 'executed', 'complete', 'completed', 'partially filled',
  'partial fill', 'partially executed']);
export const MAX_FEE_COLUMNS = 3;

function bad(field) {
  fail('E_BAD_MAPPING', `the choice for "${field}" does not fit`, null, field);
}

const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const isObj = (o) => o !== null && typeof o === 'object' && !Array.isArray(o);
const isIdx = (v) => Number.isInteger(v) && v >= 0;

// Value-map keys, and the cells they are looked up with: lowercase, inner whitespace collapsed.
export function normValue(v) {
  return clean(v).toLowerCase();
}

function checkValues(o, allowed, field) {
  if (o === null || o === undefined) return;
  if (!isObj(o)) bad(field);
  for (const [k, v] of Object.entries(o)) if (k.length > 40 || !allowed.includes(v)) bad(field);
}

function checkRules(list, allowed, field) {
  if (list === null || list === undefined) return;
  if (!Array.isArray(list) || list.length > 40) bad(field);
  for (const r of list) {
    if (!Array.isArray(r) || r.length !== 3 || !RULE_KINDS.includes(r[0]) || typeof r[1] !== 'string' ||
        r[1].length > 40 || !allowed.includes(r[2])) bad(field);
  }
}

// The mapping's own shape, before any file is looked at.
export function checkMapping(mp) {
  if (!isObj(mp) || mp.v !== 1) bad('v');
  if (!LAYOUTS.includes(mp.layout)) bad('layout');
  if (!isIdx(mp.header_row)) bad('header_row');
  if (mp.delimiter !== undefined && mp.delimiter !== null && ![',', ';', '\t'].includes(mp.delimiter)) bad('delimiter');
  if (!isObj(mp.cols)) bad('cols');
  if (!isObj(mp.headers)) bad('headers');
  const lf = LAYOUT_FIELDS[mp.layout];
  for (const k of Object.keys(mp.cols)) if (!MAP_FIELDS.includes(k)) bad(k);
  for (const f of MAP_FIELDS) {
    const v = has(mp.cols, f) ? mp.cols[f] : null;
    if (v === null || (f === 'fees' && Array.isArray(v) && v.length === 0)) continue;
    if (!lf.required.includes(f) && !lf.optional.includes(f)) bad(f);
    if (f === 'fees') {
      if (!Array.isArray(v) || v.length > MAX_FEE_COLUMNS || !v.every(isIdx)) bad(f);
    } else if (!isIdx(v)) bad(f);
  }
  const sideFrom = mp.side_from === undefined || mp.side_from === null ? 'column' : mp.side_from;
  if (!['column', 'sign'].includes(sideFrom)) bad('side_from');
  if (sideFrom === 'sign' && mp.layout === 'roundtrips') bad('side_from');
  for (const f of lf.required) {
    if (f === 'side' && sideFrom === 'sign') continue;
    if (!has(mp.cols, f) || mp.cols[f] === null) bad(f);
  }
  checkValues(mp.side_values, ['buy', 'sell', 'skip'], 'side_values');
  checkRules(mp.side_rules, ['buy', 'sell', 'skip'], 'side_rules');
  if (mp.side_default !== undefined && mp.side_default !== null && mp.side_default !== 'skip') bad('side_default');
  checkValues(mp.status_values, ['keep', 'skip'], 'status_values');
  checkRules(mp.status_rules, ['keep', 'skip'], 'status_rules');
  if (!DATE_FORMATS.includes(mp.date_format)) bad('date_format');
  if (mp.number_style !== undefined && mp.number_style !== null && !['dot', 'comma'].includes(mp.number_style)) bad('number_style');
  if (mp.currency !== undefined && mp.currency !== null && !ISO.has(mp.currency)) bad('currency');
  if (mp.tz !== undefined && mp.tz !== null && mp.tz !== 'utc') bad('tz');
  if (mp.preset !== undefined && mp.preset !== null && !(typeof mp.preset === 'string' && /^[a-z0-9_]{1,40}$/.test(mp.preset))) bad('preset');
  for (const f of ['futures_sizes', 'section', 'trim_ragged', 'keep_partial']) {
    if (mp[f] !== undefined && mp[f] !== null && typeof mp[f] !== 'boolean') bad(f);
  }
  if (mp.futures_sizes && mp.layout === 'roundtrips') bad('futures_sizes');
  if (mp.source !== undefined && mp.source !== null) {
    if (!isObj(mp.source) || mp.source.kind !== 'html' || !isIdx(mp.source.table)) bad('source');
  }
  return sideFrom;
}

// The mapping against one file's heading row → the column map the parsers read through:
// {field: index}, with fees as fee0..fee2.
export function bindMapping(mp, header) {
  const m = {};
  const use = (key, field, i) => {
    if (i >= header.length) bad(field);
    const h = normHeader(header[i]);
    if (!has(mp.headers, String(i)) || mp.headers[String(i)] !== h) bad(field);
    if (isBlocked(h)) bad(field);
    m[key] = i;
  };
  for (const f of MAP_FIELDS) {
    const v = has(mp.cols, f) ? mp.cols[f] : null;
    if (v === null) continue;
    if (f === 'fees') v.forEach((i, k) => use('fee' + k, 'fees', i));
    else use(f, f, v);
  }
  return m;
}

// ---------------------------------------------------------------- rows
// The data rows under the header: all of them, or (section: true, the thinkorswim statement) only
// the block that ends at the first gap in line numbers (a blank line) or the first title row.
export function dataRowsAfter(rows, hdrAt, section) {
  const out = [];
  let prev = rows[hdrAt].row;
  for (let k = hdrAt + 1; k < rows.length; k++) {
    const r = rows[k];
    if (section && (r.row !== prev + 1 || r.cells.filter((c) => c !== '').length === 1)) break;
    out.push(r);
    prev = r.row;
  }
  return out;
}

// A title, footer or disclaimer line under a heading of 3 or more columns: one filled cell.
export function isNoData(cells, width) {
  return width >= 3 && cells.filter((c) => c !== '').length === 1;
}

function cellAt(r, i) {
  return i === undefined || i >= r.cells.length ? '' : r.cells[i];
}

function lookup(raw, values, rules) {
  const k = normValue(raw);
  if (values && has(values, k)) return values[k];
  if (rules) {
    for (const [kind, text, res] of rules) {
      if ((kind === 'eq' && k === text) || (kind === 'prefix' && k.startsWith(text)) ||
          (kind === 'contains' && k.indexOf(text) !== -1)) return res;
    }
  }
  return undefined;
}

// 'buy' | 'sell' | 'skip' | null (no rule for this value: bad_side)
function sideOf(raw, mp) {
  const listed = (mp.side_values !== undefined && mp.side_values !== null) || (mp.side_rules !== undefined && mp.side_rules !== null);
  const v = lookup(raw, mp.side_values, mp.side_rules);
  if (v !== undefined) return v;
  if (listed) return mp.side_default === 'skip' ? 'skip' : null;
  if (mp.layout === 'roundtrips') {
    const d = clean(raw).toLowerCase();
    if (d.startsWith('l') || d.startsWith('b')) return 'buy';
    if (d.startsWith('s')) return 'sell';
    return null;
  }
  return sideLetter(raw);
}

function statusKept(raw, mp) {
  const listed = (mp.status_values !== undefined && mp.status_values !== null) || (mp.status_rules !== undefined && mp.status_rules !== null);
  const v = lookup(raw, mp.status_values, mp.status_rules);
  if (v !== undefined) return v === 'keep';
  if (listed) return false;
  return STATUS_KEEP.includes(normValue(raw));
}

function statusReason(raw) {
  const v = normValue(raw);
  if (v.indexOf('reject') !== -1) return 'rejected';
  if (v.indexOf('cancel') !== -1) return 'cancelled';
  return 'not_filled';
}

// "ESZ6", "MNQ", "ES 12-26" → the CME root the contract-size table uses.
const RE_CONTRACT = /^([A-Z0-9]+?)[FGHJKMNQUVXZ][0-9]{1,2}$/;
export function futuresRoot(symbol) {
  const c = clean(symbol).toUpperCase().split(' ')[0];
  const mm = RE_CONTRACT.exec(c);
  return mm ? mm[1] : c;
}

// A number question the data leaves open (the guess asks it, a preset opens Part 3 for it):
// 'number_style' when a cell like 1,234 (always) or 1.500 (outside comma-separated files) has no
// other cell in the file to settle it. → 'number_style' | null.
export function numberQuestion(rows, idxs, delimiter) {
  let dot = false, comma = false, dot3 = false, lone = false;
  for (const r of rows) {
    for (const i of idxs) {
      if (i >= r.cells.length) continue;
      const c = moneyClean(r.cells[i]);
      const sh = numberShape(c);
      if (sh === 'dot') dot = true;
      else if (sh === 'comma') comma = true;
      else if (sh === 'dot3') dot3 = true;
      else if (sh === 'neutral' && /^[+-]?\d+,\d{3}$/.test(c.replace(/−/g, '-'))) lone = true;
    }
  }
  if (dot || comma) return lone ? 'number_style' : null;
  if (lone || (dot3 && delimiter !== ',')) return 'number_style';
  return null;
}

// One file's rows through a checked mapping. kind: 'csv' | 'html' | 'paste'; delimiter: the CSV's.
// → {res, nData}
export function parseMapped(rows, mp, sideFrom, kind, delimiter) {
  const hdrAt = rows.findIndex((r) => r.row === mp.header_row + 1);
  if (hdrAt < 0) bad('header_row');
  const header = rows[hdrAt].cells;
  const m = bindMapping(mp, header);
  const layout = mp.layout;
  const data = dataRowsAfter(rows, hdrAt, mp.section === true);
  const skipped = {};
  // Rows that hold no trade data: a pasted footer (trim_ragged), a legal footer or disclaimer line
  // (one filled cell, or every mapped required cell empty). Counted as no_data, never an error.
  const reqKeys = LAYOUT_FIELDS[layout].required.filter((f) => !(f === 'side' && sideFrom === 'sign'));
  const kept = [];
  let nData = 0;
  for (const r of data) {
    if (isEmptyRow(r.cells)) continue;
    nData++;
    if (mp.trim_ragged && r.cells.length * 2 < header.length) { skip(skipped, 'no_data'); continue; }
    if (isNoData(r.cells, header.length) || reqKeys.every((f) => cellAt(r, m[f]) === '')) { skip(skipped, 'no_data'); continue; }
    kept.push(r);
  }
  if (nData === 0) fail('E_HEADER_ONLY');
  if (nData > LIMITS.MAX_ROWS) fail('E_TOO_LARGE');
  if (kind === 'csv') checkQuoting([rows[hdrAt], ...data], 0, m);
  // A Currency column whose cells are not all ISO codes is not read at all (F-D3), as elsewhere.
  const cc = checkCurrencyColumn(kept, m);
  const cm = cc.map;
  // Numbers: money cleaning, then the file's decimal separator, from the mapped number cells only.
  const numMap = {};
  for (const f of NUMERIC[layout]) if (has(cm, f)) numMap[f] = cm[f];
  for (const k of ['fee0', 'fee1', 'fee2']) if (has(cm, k)) numMap[k] = cm[k];
  const numIdx = Object.values(numMap);
  for (const r of kept) for (const i of numIdx) if (i < r.cells.length) r.cells[i] = moneyClean(r.cells[i]);
  const chosen = mp.number_style === undefined ? null : mp.number_style;
  const fallback = chosen !== null ? chosen : (kind === 'csv' && delimiter === ',') || kind === 'html' ? 'dot' : null;
  const style = resolveNumberStyle([{ rows: kept, map: numMap, fields: Object.keys(numMap) }], fallback);
  if (chosen !== null && style !== chosen) fail('E_BAD_NUMBER', 'the numbers in this file do not fit the number style you chose');
  if (chosen !== null) {
    // The user said what 1,234 means in this file.
    for (const r of kept) {
      for (const i of numIdx) {
        if (i >= r.cells.length) continue;
        const bare = r.cells[i].replace(/−/g, '-');
        if (chosen === 'dot' && /^[+-]?\d{1,3},\d{3}$/.test(bare)) r.cells[i] = bare.replace(',', '');
        else if (chosen === 'comma' && /^[+-]?\d+,\d{3}$/.test(bare)) r.cells[i] = bare.replace(',', '.');
      }
    }
  }
  let dup = 0;
  {
    const idx = Object.values(cm);
    const seen = new Set();
    for (const r of kept) {
      const key = idx.map((i) => cellAt(r, i)).join('\u0001');
      if (seen.has(key)) dup++; else seen.add(key);
    }
  }
  const seen = { zone: false };
  const fmt = mp.date_format;
  const execs = [];
  const rts = [];
  let pnlSign = 0;
  const feeOf = (r, row) => {
    let fee = 0;
    for (const k of ['fee0', 'fee1', 'fee2']) if (has(cm, k)) fee += Math.abs(optNumber(cellAt(r, cm[k]), row, 'fees'));
    return fee;
  };
  for (const r of kept) {
    const row = r.row;
    if (layout === 'roundtrips') {
      const d = sideOf(cellAt(r, cm.direction), mp);
      if (d === 'skip') { skip(skipped, 'not_a_trade'); continue; }
      if (d === null) { skip(skipped, 'bad_side'); continue; }
      const dir = d === 'buy' ? 'long' : 'short';
      const symbol = cellAt(r, cm.symbol);
      if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
      const ot = parseDateFmt(cellAt(r, cm.open_time), fmt, row, 'open_time', seen);
      let ct = parseDateFmt(cellAt(r, cm.close_time), fmt, row, 'close_time', seen);
      const reordered = ct < ot; // the repeated hour of a fall-back night, flagged (F-N3), as generic does
      if (reordered) {
        ct = fallBackClose(ot, ct);
        if (ct === null) fail('E_BAD_DATE', 'the close time is before the open time', row, 'close_time');
      }
      const qty = Math.abs(reqNumber(cellAt(r, cm.qty), row, 'qty'));
      if (qty === 0) { skip(skipped, 'zero_qty'); continue; }
      const op = reqNumber(cellAt(r, cm.open_price), row, 'open_price');
      const cp = reqNumber(cellAt(r, cm.close_price), row, 'close_price');
      const fee = feeOf(r, row);
      if (has(cm, 'pnl')) {
        const p = optNumber(cellAt(r, cm.pnl), row, 'pnl');
        const g = (cp - op) * (dir === 'long' ? 1 : -1);
        if (p !== 0 && g !== 0 && (p > 0) !== (g > 0)) pnlSign++;
      }
      const cur = cellAt(r, cm.currency).toUpperCase() || (mp.currency || null);
      rts.push({ row, symbol, dir, open_ts: ot, close_ts: ct, qty, entry: op, exit: cp, fees: fee, pnl_gross: null,
        reported: false, currency: cur, unit: cur ? cur : 'points', pos_id: null, reordered });
      continue;
    }
    let side = null;
    if (sideFrom === 'column') {
      side = sideOf(cellAt(r, cm.side), mp);
      if (side === 'skip') { skip(skipped, 'not_a_trade'); continue; }
    }
    if (has(cm, 'status')) {
      const st = cellAt(r, cm.status);
      if (!statusKept(st, mp)) {
        // An order cancelled or expired after a part filled is still a fill of that part, when the
        // quantity column holds the filled quantity (Tradovate's rule, Tester D8).
        const v = normValue(st);
        const partial = mp.keep_partial === true && (v.indexOf('cancel') !== -1 || v.indexOf('expire') !== -1) &&
          (parseNumber(cellAt(r, cm.qty), row, 'qty') || 0) !== 0;
        if (!partial) { skip(skipped, statusReason(st)); continue; }
      }
    }
    if (sideFrom === 'column' && side === null) { skip(skipped, 'bad_side'); continue; }
    const symbol = cellAt(r, cm.symbol);
    if (symbol === '') { skip(skipped, 'no_symbol'); continue; }
    const d = cellAt(r, cm.date);
    const t = cellAt(r, cm.time);
    const ts = parseDateFmt(t !== '' && d !== '' ? d + ' ' + t : d, fmt, row, 'date', seen);
    let q = reqNumber(cellAt(r, cm.qty), row, 'qty');
    if (sideFrom === 'sign' && q !== 0) side = q < 0 ? 'sell' : 'buy';
    q = Math.abs(q);
    if (q === 0) { skip(skipped, 'zero_qty'); continue; }
    const price = reqNumber(cellAt(r, cm.price), row, 'price');
    const fee = feeOf(r, row);
    let cur = cellAt(r, cm.currency).toUpperCase() || (mp.currency || null);
    let mult = 1;
    let unit = cur ? cur : 'points';
    if (mp.futures_sizes) {
      const root = futuresRoot(symbol);
      if (has(CME_MULTIPLIERS, root)) { mult = CME_MULTIPLIERS[root]; cur = cur || 'USD'; unit = cur; }
      else { cur = null; unit = 'points'; }
    }
    execs.push({ row, ts, symbol, side, qty: q, price, fee, currency: cur, oc: null, pos_id: null,
      pnl_reported: null, multiplier: mult, _unit: unit, _fx: null });
  }
  const extra = { duplicate_rows: dup, currency_ignored: cc.ignored, mapped: !mp.preset, preset: mp.preset || null,
    orders_averaged: layout === 'orders', futures_sizes: mp.futures_sizes === true, pnl_sign: pnlSign,
    zone_ignored: seen.zone, tz: mp.tz || null };
  return { res: { executions: execs, roundtrips: rts, skipped, extra }, nData };
}

export const MAPPED_TZ = Object.freeze({ plain: 'as in the file', zone: 'as in the file; time zone labels ignored',
  utc: 'UTC, as exported' });

export function mappedTzLabel(extra) {
  if (extra.tz === 'utc') return MAPPED_TZ.utc;
  return extra.zone_ignored ? MAPPED_TZ.zone : MAPPED_TZ.plain;
}

// ---------------------------------------------------------------- several files
// Two overlapping exports (IBKR's 365-day cap, yearly Trading 212 or Binance files, a paste of
// page 1 and then pages 1-2) count each fill once: a key is kept as many times as it occurs in
// any ONE file, so two identical fills inside one file both survive, as they always have.
export function execKey(e) {
  return [e.ts, e.symbol, e.side, e.qty, e.price, e.fee].join('\u0001');
}

export function rtKey(r) {
  return [r.symbol, r.dir, r.open_ts, r.close_ts, r.qty, r.entry, r.exit].join('\u0001');
}

// lists: one array per file, in reading order → {out, dropped}
export function dropOverlap(lists, keyOf) {
  const keep = new Map();
  for (const list of lists) {
    const c = new Map();
    for (const x of list) { const k = keyOf(x); c.set(k, (c.get(k) || 0) + 1); }
    for (const [k, n] of c) if (n > (keep.get(k) || 0)) keep.set(k, n);
  }
  const used = new Map();
  const out = [];
  let dropped = 0;
  for (const list of lists) {
    for (const x of list) {
      const k = keyOf(x);
      const u = (used.get(k) || 0) + 1;
      used.set(k, u);
      if (u <= keep.get(k)) out.push(x); else dropped++;
    }
  }
  return { out, dropped };
}

// The first time in a file's parsed rows, for reading files in time order.
export function firstTs(res) {
  let t = Infinity;
  for (const e of res.executions) if (e.ts < t) t = e.ts;
  for (const r of res.roundtrips) if (r.open_ts < t) t = r.open_ts;
  return t;
}

const SUM_EXTRA = ['duplicate_rows', 'open_positions', 'pnl_sign'];
const OR_EXTRA = ['currency_ignored', 'has_closed_positions', 'has_deals', 'zone_ignored'];

// Parsed files (in time order) → one parser result for finish(). Row numbers are moved past the
// rows of the files before, so same-time fills keep file order and then row order (chronoOrder).
export function mergeParsed(parts) {
  const first = parts[0].res;
  const extra = Object.assign({}, first.extra);
  for (const k of SUM_EXTRA) if (has(extra, k)) extra[k] = 0;
  for (const k of OR_EXTRA) if (has(extra, k)) extra[k] = false;
  const skipped = {};
  let offset = 0;
  for (const p of parts) {
    for (const e of p.res.executions) e.row += offset;
    for (const r of p.res.roundtrips) r.row += offset;
    offset += p.lastRow;
    for (const [k, n] of Object.entries(p.res.skipped)) skipped[k] = (skipped[k] || 0) + n;
    for (const k of SUM_EXTRA) if (has(p.res.extra, k)) extra[k] = (extra[k] || 0) + p.res.extra[k];
    for (const k of OR_EXTRA) if (has(p.res.extra, k)) extra[k] = extra[k] || p.res.extra[k];
  }
  const ex = dropOverlap(parts.map((p) => p.res.executions), execKey);
  const rt = dropOverlap(parts.map((p) => p.res.roundtrips), rtKey);
  extra.overlap_rows = ex.dropped + rt.dropped;
  return { executions: ex.out, roundtrips: rt.out, skipped, extra };
}
