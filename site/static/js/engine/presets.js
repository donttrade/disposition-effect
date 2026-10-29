// presets.js — saved mappings that ship with the site (plan §3). A preset fires only when ALL of its
// `match` headings (normalised) are in one row, so a wrong spelling means it never fires and the
// user lands in the mapper with the headings pre-filled: a preset never reads a file wrongly
// because of a heading. It runs with no clicks, unless the data leaves a question open (the date
// order, or a number style): then it returns the question instead of guessing.
//
// Every preset is beta (W_UNVERIFIED_FORMAT) until a real export is seen. `source` says where its
// columns come from: OFFICIAL = the platform's own documentation, 3RD = another importer's help.
// tests/test_engine_mapped.py checks this table equals PRESETS in tests/reference/engine_ref.py.

import { normHeader, detectDateFormat } from './csv.js';
import { MAP_FIELDS, dataRowsAfter, numberQuestion, isBlocked, isNoData, isRagged } from './mapped.js';
import { readRows, runFiles } from './index.js';

export const PRESET_SEARCH_ROWS = 50; // the heading row must be within the first 50 non-empty rows

const BUY_SELL_PREFIX = [['prefix', 'buy', 'buy'], ['prefix', 'sell', 'sell']];
const B_S_PREFIX = [['prefix', 'b', 'buy'], ['prefix', 's', 'sell']];

export const PRESETS = Object.freeze([
  {
    id: 'ninjatrader_exec',
    name: 'NinjaTrader 8 executions',
    source: 'OFFICIAL NinjaTrader 8 help, Executions tab column list; 3RD TradeZella NinjaTrader header',
    match: ['instrument', 'action', 'quantity', 'price', 'time', 'ex'],
    layout: 'fills',
    cols: { date: 'time', symbol: 'instrument', side: 'action', qty: 'quantity', price: 'price', fees: ['commission'] },
    side_rules: BUY_SELL_PREFIX, // Buy, BuyToCover → buy; Sell, SellShort → sell
    side_default: null,
    status_rules: null,
    futures_sizes: true,
    tz: null,
    keep_partial: false,
    section: false,
    before_known: false,
  },
  {
    id: 'trading212_history',
    name: 'Trading 212 history',
    source: '3RD Export-To-Ghostfolio trading212Record field list (heading spelling inferred)',
    match: ['action', 'time', 'ticker', 'noofshares', 'priceshare'],
    layout: 'fills',
    cols: { date: 'time', symbol: 'ticker', side: 'action', qty: 'noofshares', price: 'priceshare', currency: 'currencypriceshare' },
    side_rules: [['contains', 'buy', 'buy'], ['contains', 'sell', 'sell']], // "Market buy", "Limit sell"
    side_default: 'skip', // Deposit, Dividend (Ordinary), Interest on cash...
    status_rules: null,
    futures_sizes: false,
    tz: null,
    keep_partial: false,
    section: false,
    before_known: false,
  },
  {
    id: 'kraken_trades',
    name: 'Kraken trades',
    source: 'OFFICIAL Kraken support, Trades export fields',
    match: ['txid', 'ordertxid', 'pair', 'time', 'type', 'price', 'vol'],
    layout: 'fills',
    cols: { date: 'time', symbol: 'pair', side: 'type', qty: 'vol', price: 'price', fees: ['fee'] },
    side_rules: [['eq', 'buy', 'buy'], ['eq', 'sell', 'sell']],
    side_default: null,
    status_rules: null,
    futures_sizes: false,
    tz: 'utc', // Kraken: "time is in UTC"
    keep_partial: false,
    section: false,
    before_known: false,
  },
  {
    id: 'sierra_fills',
    name: 'Sierra Chart trade activity (fills)',
    source: 'OFFICIAL Sierra Chart Trade Activity Log documentation (spaced or run-together headings: UNVERIFIED)',
    match: ['activitytype', 'datetime', 'symbol', 'buysell', 'fillprice', 'filledquantity'],
    layout: 'fills',
    cols: { date: 'datetime', symbol: 'symbol', side: 'buysell', qty: 'filledquantity', price: 'fillprice', status: 'activitytype' },
    side_rules: B_S_PREFIX,
    side_default: null,
    status_rules: [['prefix', 'fill', 'keep']], // ActivityType: Fills kept, everything else skipped
    futures_sizes: false,
    tz: null,
    keep_partial: false,
    section: false,
    // The log's DateTime, Symbol, Buy Sell, Quantity and Price headings also fit the IBKR Flex and
    // generic signatures, which would read the order quantity and price of every activity row:
    // this preset is tried before the known formats.
    before_known: true,
  },
  {
    id: 'rithmic_orders',
    name: 'Rithmic R|Trader Pro completed orders',
    source: '3RD TradeZella R|Trader column list; 3RD Tradervue (Qty Filled)',
    match: ['buysell', 'symbol', 'qtyfilled', 'avgfillprice', 'status', 'updatetime'],
    layout: 'orders',
    cols: { date: 'updatetime', symbol: 'symbol', side: 'buysell', qty: 'qtyfilled', price: 'avgfillprice', status: 'status',
      fees: ['commission'] },
    side_rules: B_S_PREFIX,
    side_default: null,
    status_rules: [['eq', 'filled', 'keep'], ['eq', 'complete', 'keep'], ['eq', 'completed', 'keep'],
      ['eq', 'partially filled', 'keep']],
    futures_sizes: true,
    tz: null,
    keep_partial: true,
    section: false,
    before_known: false,
  },
  {
    id: 'ctrader_history',
    name: 'cTrader history',
    source: 'OFFICIAL cTrader Web History column list (on screen, not a file heading)',
    match: ['symbol', 'openingdirection', 'openingtime', 'closingtime', 'entryprice', 'closingprice', 'closingquantity'],
    layout: 'roundtrips',
    cols: { open_time: 'openingtime', close_time: 'closingtime', symbol: 'symbol', direction: 'openingdirection',
      qty: 'closingquantity', open_price: 'entryprice', close_price: 'closingprice', fees: ['commissions', 'swap'], pnl: 'gross' },
    side_rules: B_S_PREFIX,
    side_default: null,
    status_rules: null,
    futures_sizes: false,
    tz: null,
    keep_partial: false,
    section: false,
    before_known: false,
  },
  {
    id: 'dxtrade_orders',
    name: 'DXtrade order history (pasted)',
    source: '3RD TradesViz DXtrade columns to show',
    match: ['dateandtime', 'symbol', 'status', 'side', 'filledvolume', 'fillprice'],
    layout: 'orders',
    cols: { date: 'dateandtime', symbol: 'symbol', side: 'side', qty: 'filledvolume', price: 'fillprice', status: 'status',
      fees: ['commission'] },
    side_rules: BUY_SELL_PREFIX,
    side_default: null,
    status_rules: [['eq', 'filled', 'keep'], ['eq', 'partially filled', 'keep']],
    futures_sizes: false,
    tz: null,
    keep_partial: true,
    section: false,
    before_known: false,
  },
  {
    id: 'hyperliquid_fills',
    name: 'Hyperliquid fills',
    source: 'OFFICIAL Hyperliquid API userFills fields (the web CSV heading was not found)',
    match: ['coin', 'side', 'px', 'sz', 'time'],
    layout: 'fills',
    cols: { date: 'time', symbol: 'coin', side: 'side', qty: 'sz', price: 'px', fees: ['fee'] },
    side_rules: [['eq', 'b', 'buy'], ['eq', 'a', 'sell'], ['eq', 'buy', 'buy'], ['eq', 'sell', 'sell']],
    side_default: null,
    status_rules: null,
    futures_sizes: false,
    tz: null,
    keep_partial: false,
    section: false,
    before_known: false,
  },
]);

export function presetById(id) {
  return PRESETS.find((p) => p.id === id) || null;
}

// The index in rows of the preset's heading row, or -1.
export function findPresetHeader(rows, preset, kind) {
  const all = preset.section || kind === 'html';
  let seen = 0;
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].cells.every((c) => c === '')) continue;
    if (!all && ++seen > PRESET_SEARCH_ROWS) break;
    const norm = rows[i].cells.map(normHeader);
    if (preset.match.every((h) => norm.includes(h))) return i;
  }
  return -1;
}

// A preset against one file's rows (index.js readRows) → {preset, mapping, questions} or null.
// questions: [{q: 'date_order' | 'number_style', reason}]; with one open, mapping.date_format (or
// number_style) is null and the engine refuses the mapping until the user answers.
export function presetMapping(preset, src) {
  let rows = src.rows;
  let at = findPresetHeader(rows, preset, src.kind);
  if (at < 0) return null;
  let source = null;
  if (src.kind === 'html') {
    const table = rows[at].table;
    const hdr = rows[at];
    rows = rows.filter((r) => r.table === table);
    at = rows.indexOf(hdr);
    source = { kind: 'html', table };
  }
  const norm = rows[at].cells.map(normHeader);
  const cols = {};
  for (const f of MAP_FIELDS) cols[f] = null;
  const headers = {};
  for (const [f, want] of Object.entries(preset.cols)) {
    if (f === 'fees') {
      const idx = [];
      for (const h of want) {
        const i = norm.indexOf(h);
        if (i >= 0 && !isBlocked(h)) { idx.push(i); headers[String(i)] = h; }
      }
      cols.fees = idx.length ? idx : null;
      continue;
    }
    const i = norm.indexOf(want);
    if (i < 0 || isBlocked(want)) continue;
    cols[f] = i;
    headers[String(i)] = want;
  }
  const trim = src.kind === 'paste';
  const width = rows[at].cells.length;
  const data = dataRowsAfter(rows, at, preset.section).filter((r) => !r.cells.every((c) => c === '') &&
    !(trim && isRagged(r.cells, width)) && !isNoData(r.cells, width));
  const dateCols = preset.layout === 'roundtrips' ? [cols.open_time, cols.close_time] : [cols.date];
  const values = [];
  for (const r of data) for (const i of dateCols) values.push(i < r.cells.length ? r.cells[i] : '');
  const det = detectDateFormat(values);
  const questions = [];
  if (det.format === null) questions.push({ q: 'date_order', reason: det.reason });
  const numIdx = [];
  const numFields = preset.layout === 'roundtrips' ? ['qty', 'open_price', 'close_price', 'pnl'] : ['qty', 'price'];
  for (const f of numFields) if (cols[f] !== null) numIdx.push(cols[f]);
  if (cols.fees) for (const i of cols.fees) numIdx.push(i);
  const nq = numberQuestion(data, numIdx, src.kind === 'csv' ? src.delimiter : src.kind === 'html' ? ',' : '\t');
  if (nq) questions.push({ q: nq, reason: 'ask' });
  const mapping = {
    v: 1, layout: preset.layout, header_row: rows[at].row - 1, delimiter: src.kind === 'csv' ? src.delimiter : null,
    cols, headers, side_from: 'column', side_values: null, side_rules: preset.side_rules, side_default: preset.side_default,
    status_values: null, status_rules: preset.status_rules, date_format: det.format, number_style: null,
    futures_sizes: preset.futures_sizes, currency: null, preset: preset.id, section: preset.section, trim_ragged: trim,
    source, tz: preset.tz, keep_partial: preset.keep_partial,
  };
  return { preset: preset.id, mapping, questions };
}

// The first preset whose headings are in the file. only: a filter on the presets tried.
export function matchPreset(src, only = null) {
  for (const p of PRESETS) {
    if (only && !only(p)) continue;
    const m = presetMapping(p, src);
    if (m) return m;
  }
  return null;
}

// The codes after which a file that the known formats cannot read is offered to the presets.
export const PRESET_AFTER = Object.freeze(['E_UNKNOWN_FORMAT', 'E_MISSING_COLUMN', 'E_AMBIGUOUS_DATE']);

// A preset marked before_known first, then the known formats, then the other presets.
// → {result} | {error} | {question: {preset, questions}}.
// The page puts a mapping saved in this browser before all of them (plan §2.1); this is the rest.
export function readWithPresets(items) {
  let src = null;
  try { src = readRows(items[0]); } catch (e) { if (!e || e.name !== 'EngineError') throw e; }
  const use = (p) => (p.questions.length ? { question: { preset: p.preset, questions: p.questions } }
    : runFiles(items, { mapping: p.mapping }));
  if (src) {
    const p = matchPreset(src, (x) => x.before_known);
    if (p) return use(p);
  }
  const auto = runFiles(items);
  if (!auto.error || !PRESET_AFTER.includes(auto.error.code) || !src) return auto;
  const p = matchPreset(src);
  return p ? use(p) : auto;
}
