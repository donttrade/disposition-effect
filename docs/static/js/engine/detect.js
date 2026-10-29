// detect.js — the column whitelist and format detection.
//
// Parsers read columns ONLY through these alias tables. A header that is not
// listed here (account numbers, account alias, model, trader id, owner name,
// comments) is never mapped, so its values are never read, shown or stored.
//
// Header text is normalised (lowercase, spaces and punctuation stripped) before
// matching, so "Buy/Sell", "buy / sell" and "BuySell" are the same column.
// An alias written "time#2" means "the second column whose header is Time"
// (MetaTrader reports repeat Time and Price for the open and the close).
//
// Column names marked UNVERIFIED come from vendor help pages and open-source
// importers, not from a real export; see tests/fixtures/PROVENANCE.txt.
// tests/test_alias_parity.py checks this table equals the Python reference's.

import { clean, normHeader } from './csv.js?v=09ecf6e4';
import { fail } from './errors.js?v=31d80675';

// verified: false = column names not yet confirmed against a real export.
export const SIGNATURES = {
  // MetaTrader 5 report, Deals table (also accepted as CSV with the same headers).
  mt5_deals: {
    verified: false,
    fields: {
      time: ['time'], deal: ['deal'], symbol: ['symbol'], type: ['type'], direction: ['direction'],
      volume: ['volume'], price: ['price'], commission: ['commission'], fee: ['fee'], swap: ['swap'],
      profit: ['profit'], position: ['position', 'positionid'],
    },
    required: [['time'], ['deal'], ['symbol'], ['type'], ['direction'], ['volume'], ['price'], ['profit']],
  },
  // MetaTrader 5 report, Positions table. With two Time columns it lists closed
  // positions (open + close); with one it lists positions still open.
  mt5_positions: {
    verified: false,
    fields: {
      open_time: ['time#1'], close_time: ['time#2'], position: ['position'], symbol: ['symbol'], type: ['type'],
      volume: ['volume'], open_price: ['price#1'], close_price: ['price#2'], commission: ['commission'],
      fee: ['fee'], swap: ['swap'], profit: ['profit'],
    },
    required: [['open_time'], ['position'], ['symbol'], ['type'], ['volume'], ['open_price']],
  },
  // MetaTrader 4 statement: one row per round trip.
  mt4: {
    verified: false,
    fields: {
      open_time: ['opentime', 'time#1'], close_time: ['closetime', 'time#2'], type: ['type'],
      size: ['size', 'lots'], symbol: ['item', 'symbol'], open_price: ['price#1'], close_price: ['price#2'],
      commission: ['commission'], taxes: ['taxes'], swap: ['swap'], profit: ['profit'],
    },
    required: [['open_time'], ['close_time'], ['type'], ['size'], ['symbol'], ['open_price'], ['close_price'], ['profit']],
  },
  // Interactive Brokers Flex Query, Trades section, executions. UNVERIFIED spellings.
  ibkr_flex: {
    verified: false,
    fields: {
      symbol: ['symbol'], datetime: ['datetime'], tradedate: ['tradedate'], tradetime: ['tradetime'],
      quantity: ['quantity'], price: ['tradeprice', 'price'], side: ['buysell'],
      oc: ['opencloseindicator', 'openclose'], code: ['notescodes', 'code'],
      commission: ['ibcommission', 'commission'], currency: ['currencyprimary', 'currency'],
      fx: ['fxratetobase'], multiplier: ['multiplier'],
      realized: ['fifopnlrealized', 'realizedpnl', 'realizedpl'], level: ['levelofdetail'],
    },
    required: [['symbol'], ['datetime', 'tradedate'], ['quantity'], ['price'], ['side']],
  },
  // Tradovate Orders report. UNVERIFIED column names (third-party importers only).
  tradovate_orders: {
    verified: false,
    fields: {
      side: ['bs'], contract: ['contract'], product: ['product'], status: ['status'],
      qty: ['filledqty'], price: ['avgfillprice', 'avgprice'], time: ['filltime'],
    },
    required: [['side'], ['contract'], ['status'], ['qty'], ['price'], ['time']],
  },
  // TradingView Order History export (Trading Panel → History → Export data). Column names
  // confirmed against one real paper-trading export (29 Oct 2026); see PROVENANCE.txt.
  tradingview: {
    verified: true,
    fields: {
      symbol: ['symbol'], side: ['side'], qty: ['quantity', 'qty'], price: ['fillprice'], status: ['status'],
      commission: ['commission'], time: ['closingtime'],
    },
    required: [['symbol'], ['side'], ['qty'], ['price'], ['status'], ['time']],
  },
  // The TradeZella-style round-trip layout we also accept.
  generic_roundtrip: {
    verified: false,
    fields: {
      open_time: ['opentime'], close_time: ['closetime'], symbol: ['symbol', 'ticker', 'instrument'],
      direction: ['direction', 'side'], qty: ['volume', 'quantity', 'qty'],
      open_price: ['openprice', 'entryprice'], close_price: ['closeprice', 'exitprice'],
      fees: ['fees', 'fee', 'commission', 'commissions'], currency: ['currency'],
    },
    required: [['open_time'], ['close_time'], ['symbol'], ['direction'], ['qty'], ['open_price'], ['close_price']],
  },
  // donttrade's own template: Date, Time, Symbol, Side, Quantity, Price (+ Currency, Fees).
  generic: {
    verified: true,
    fields: {
      date: ['date', 'tradedate'], time: ['time', 'tradetime'], datetime: ['datetime', 'timestamp'],
      symbol: ['symbol', 'ticker', 'instrument'], side: ['side', 'action', 'buysell'],
      qty: ['quantity', 'qty', 'shares'], price: ['price', 'fillprice', 'executionprice'],
      currency: ['currency'], fees: ['fees', 'fee', 'commission', 'commissions'],
    },
    required: [['date', 'datetime'], ['time', 'datetime'], ['symbol'], ['side'], ['qty'], ['price']],
  },
};

// Order matters: the first signature that fully matches wins.
// The whitelisted columns that hold numbers, per signature. The file's decimal
// separator is decided from these cells only (csv.js resolveNumberStyle).
export const NUMERIC_FIELDS = {
  mt5_deals: ['volume', 'price', 'commission', 'fee', 'swap', 'profit'],
  mt5_positions: ['volume', 'open_price', 'close_price', 'commission', 'fee', 'swap', 'profit'],
  mt4: ['size', 'open_price', 'close_price', 'commission', 'taxes', 'swap', 'profit'],
  ibkr_flex: ['quantity', 'price', 'commission', 'realized', 'multiplier', 'fx'],
  tradovate_orders: ['qty', 'price'],
  tradingview: ['qty', 'price', 'commission'],
  generic_roundtrip: ['qty', 'open_price', 'close_price', 'fees'],
  generic: ['qty', 'price', 'fees'],
};

// ISO 4217 currency codes (the active list, plus the metal and fund codes; not XTS or XXX),
// plus CNH: offshore yuan, not an ISO code but what IBKR writes for CNH-settled trades.
// A Currency column is read only if every non-empty cell is one of these: anything else
// (a name shifted in by an unquoted comma, a note, a fragment like "ANN") means the column
// is not what its header says, so it is ignored as a whole, with a warning that never
// repeats the cell (Tester F-D3). The page shows and the paid request sends only these.
export const ISO_CURRENCIES = Object.freeze([
  'AED', 'AFN', 'ALL', 'AMD', 'ANG', 'AOA', 'ARS', 'AUD', 'AWG', 'AZN', 'BAM', 'BBD', 'BDT', 'BGN', 'BHD',
  'BIF', 'BMD', 'BND', 'BOB', 'BOV', 'BRL', 'BSD', 'BTN', 'BWP', 'BYN', 'BZD', 'CAD', 'CDF', 'CHE', 'CHF',
  'CHW', 'CLF', 'CLP', 'CNH', 'CNY', 'COP', 'COU', 'CRC', 'CUC', 'CUP', 'CVE', 'CZK', 'DJF', 'DKK', 'DOP', 'DZD',
  'EGP', 'ERN', 'ETB', 'EUR', 'FJD', 'FKP', 'GBP', 'GEL', 'GHS', 'GIP', 'GMD', 'GNF', 'GTQ', 'GYD', 'HKD',
  'HNL', 'HTG', 'HUF', 'IDR', 'ILS', 'INR', 'IQD', 'IRR', 'ISK', 'JMD', 'JOD', 'JPY', 'KES', 'KGS', 'KHR',
  'KMF', 'KPW', 'KRW', 'KWD', 'KYD', 'KZT', 'LAK', 'LBP', 'LKR', 'LRD', 'LSL', 'LYD', 'MAD', 'MDL', 'MGA',
  'MKD', 'MMK', 'MNT', 'MOP', 'MRU', 'MUR', 'MVR', 'MWK', 'MXN', 'MXV', 'MYR', 'MZN', 'NAD', 'NGN', 'NIO',
  'NOK', 'NPR', 'NZD', 'OMR', 'PAB', 'PEN', 'PGK', 'PHP', 'PKR', 'PLN', 'PYG', 'QAR', 'RON', 'RSD', 'RUB',
  'RWF', 'SAR', 'SBD', 'SCR', 'SDG', 'SEK', 'SGD', 'SHP', 'SLE', 'SLL', 'SOS', 'SRD', 'SSP', 'STN', 'SVC',
  'SYP', 'SZL', 'THB', 'TJS', 'TMT', 'TND', 'TOP', 'TRY', 'TTD', 'TWD', 'TZS', 'UAH', 'UGX', 'USD', 'USN',
  'UYI', 'UYU', 'UYW', 'UZS', 'VED', 'VES', 'VND', 'VUV', 'WST', 'XAF', 'XAG', 'XAU', 'XBA', 'XBB', 'XBC',
  'XBD', 'XCD', 'XCG', 'XDR', 'XOF', 'XPD', 'XPF', 'XPT', 'XSU', 'XUA', 'YER', 'ZAR', 'ZMW', 'ZWG', 'ZWL',
]);
const ISO_SET = new Set(ISO_CURRENCIES);

// → {map, ignored}: the column map without 'currency' when its cells are not all ISO codes.
export function checkCurrencyColumn(rows, map) {
  if (!('currency' in map)) return { map, ignored: false };
  const i = map.currency;
  for (const r of rows) {
    const v = i < r.cells.length ? clean(r.cells[i]).toUpperCase() : '';
    if (v !== '' && !ISO_SET.has(v)) {
      const rest = Object.assign({}, map);
      delete rest.currency;
      return { map: rest, ignored: true };
    }
  }
  return { map, ignored: false };
}

export const CSV_ORDER = ['mt5_deals', 'ibkr_flex', 'tradovate_orders', 'tradingview', 'generic_roundtrip', 'generic'];
export const HTML_ORDER = ['mt5_deals', 'mt5_positions', 'mt4'];

// MetaTrader section titles. Rows under a HEADER title (account number, owner
// name, broker) are skipped without being looked at.
export const HEADER_TITLES = ['trade history report', 'statement', 'detailed statement', 'account statement'];
export const SECTION_TITLES = [
  'positions', 'open positions', 'orders', 'deals', 'working orders', 'summary', 'results', 'details',
  'closed transactions', 'open trades', 'closed trades',
];

export const SEARCH_ROWS = 10; // a CSV header must be within the first 10 non-empty rows

export function mapColumns(cells, fields) {
  const norm = cells.map(normHeader);
  const map = {};
  for (const [field, aliases] of Object.entries(fields)) {
    for (const alias of aliases) {
      const [name, nth] = alias.split('#');
      const want = nth === undefined ? 1 : Number(nth);
      let seen = 0;
      let at = -1;
      for (let i = 0; i < norm.length; i++) {
        if (norm[i] === name) { seen++; if (seen === want) { at = i; break; } }
      }
      if (at !== -1) { map[field] = at; break; }
    }
  }
  return map;
}

function score(map, required) {
  let ok = 0;
  const missing = [];
  for (const alts of required) {
    if (alts.some((f) => f in map)) ok++;
    else missing.push(alts[0]);
  }
  return { ok, total: required.length, missing };
}

export function matchSignature(cells, name) {
  const sig = SIGNATURES[name];
  const map = mapColumns(cells, sig.fields);
  const s = score(map, sig.required);
  return { name, map, ok: s.ok, total: s.total, missing: s.missing, full: s.missing.length === 0 };
}

function rowIsEmpty(cells) {
  return cells.every((c) => c === '');
}

// CSV: find the header row, return {format, headerIndex, map}.
export function detectCsv(rows) {
  let best = null;
  let seen = 0;
  for (let i = 0; i < rows.length && seen < SEARCH_ROWS; i++) {
    if (rowIsEmpty(rows[i].cells)) continue;
    seen++;
    for (const name of CSV_ORDER) {
      const m = matchSignature(rows[i].cells, name);
      if (m.full) return { format: name, headerIndex: i, map: m.map };
      if (!best || m.ok / m.total > best.m.ok / best.m.total) best = { m, i };
    }
  }
  if (best && best.m.ok >= 3 && best.m.ok / best.m.total >= 0.5) {
    fail('E_MISSING_COLUMN', `"${best.m.missing[0]}" was not found`, rows[best.i].row, best.m.missing[0]);
  }
  fail('E_UNKNOWN_FORMAT');
}

function titleOf(cells) {
  const filled = cells.filter((c) => c !== '');
  if (filled.length !== 1) return null;
  const t = clean(filled[0]).toLowerCase().replace(/:$/, '');
  if (HEADER_TITLES.includes(t)) return { kind: 'header', title: t };
  if (SECTION_TITLES.includes(t)) return { kind: 'section', title: t };
  return null;
}

// HTML (MetaTrader): walk the rows, track section titles, collect tables.
// Returns {format, tables: [{kind, section, header: rowObj, map, rows: [{row, cells, section}]}]}.
export function detectHtml(rows) {
  let section = null; // null = before any title → skipped, like the header block
  const tables = [];
  let cur = null;
  for (const r of rows) {
    const t = titleOf(r.cells);
    // A title changes the section but keeps the current table: MT4 lists its open
    // trades under "Open Trades:" without repeating the header row. Each data row
    // carries its section, and the parsers only use rows from the sections they own.
    if (t) { section = t.kind === 'header' ? null : t.title; continue; }
    if (section === null) continue; // header block: never read
    if (rowIsEmpty(r.cells)) continue;
    let matched = null;
    for (const name of HTML_ORDER) {
      const m = matchSignature(r.cells, name);
      if (m.full) { matched = m; break; }
    }
    if (matched) {
      let kind = matched.name;
      if (kind === 'mt5_positions') kind = 'close_time' in matched.map ? 'mt5_positions_closed' : 'mt5_positions_open';
      cur = { kind, section, header: r, map: matched.map, rows: [] };
      tables.push(cur);
      continue;
    }
    if (cur) cur.rows.push({ row: r.row, cells: r.cells, section });
  }
  if (tables.length === 0) fail('E_UNKNOWN_FORMAT');
  const format = tables.some((t) => t.kind.startsWith('mt5')) ? 'mt5' : 'mt4';
  if (tables.every((t) => t.rows.length === 0)) fail('E_HEADER_ONLY');
  return { format, tables };
}
