// merge.js — several trade files of one platform, read as one history for the paid report (ARCHITECT-EVIDENCE-
// SCALE-AND-POWER §7 S3; Tester S3 report B2–B4, M1, M3). No DOM, no network: report.js calls readFiles, then
// strip.js strips the result.
//
// 1. Every file is read ON ITS OWN, as its own account: its own fills make its own positions and trades. No fill is
//    ever deduped, matched or pooled across files (Tester S3 B2 and re-test R2: a shared position book, even one joined
//    by one identical fill, makes up trades). A position open across the edge of a file is left out, and said so.
//    All files must be of one platform and report type (E_MIXED_FILES).
// 2. Closed trades that are identical in two files (an overlapping export of one account: same symbol, direction,
//    open, close, size, prices, fees and P&L) are counted once, and the page says how many before the run.
// 3. All files must report in one currency or unit, or they are refused (Tester M1).
// 4. Copy collapse, after positions and before stripping: a trade copied to a second account shows up in each account's file. Trades
//    from DIFFERENT accounts with the same symbol and direction, opened within 5 minutes of each other and closed
//    within 5 minutes of each other, become one trade (P&L, gross, fees, fills and quantity summed). Unmerged copies
//    doubled revenge's false-alarm rate (copy.mjs: 8.0 in 100 at a 2.5 level; 1.8–3.0 after the collapse). Trades of
//    one account never collapse, however close; date-only trades (no time of day) never collapse (Tester M3).

import { runFile, readRows } from '../engine/index.js';
import { detectHtml } from '../engine/detect.js';
import { MESSAGES, LIMITS } from '../engine/errors.js';

export const COPY_WINDOW_MS = 5 * 60000;   // "within 5 minutes": a lag of exactly 5 minutes collapses, 5:01 does not
export const SMALL_FILE = 100;              // owner Q3: fewer trades than this → the small-file notice
const DAY_MS = 86400000;

const grouped = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
export const copyLine = (k) => (k === 1
  ? '1 trade in one file matched a trade in another file within 5 minutes and was counted once.'
  : `${grouped(k)} trades in one file matched a trade in another file within 5 minutes and were counted once.`);

// The small-file notice (owner Q3, Architect addendum wording). Definite: no may, might, maybe, unclear, could be or
// possibly.
export const SMALL_NOTICE = 'Files this size mostly show No sign for habits. You still get every dollar total and your rule check.';
export const WAIT_LINE = 'Nothing is sent until you press Run. Adding files does not use a run.';
export const UPLOAD_HINT = 'Add all your accounts and months: more trades, clearer answers.';
export const MIXED_UNITS = 'These files report results in different currencies or units, so they cannot be added up. Add the files of one currency at a time.';
export const overlapLine = (n) => `${grouped(n)} ${n === 1 ? 'trade was' : 'trades were'} the same in more than one file and ${n === 1 ? 'was' : 'were'} counted once.`;
export const accountsLine = (k) => `These results combine ${grouped(k)} accounts, one per file. The rule check covers one account at a time.`;
export const edgeLine = (n) => `${grouped(n)} ${n === 1 ? 'position was' : 'positions were'} open at the start or end of a file and ${n === 1 ? 'was' : 'were'} left out: each file is read as one account.`;

// A trade with dates but no times: opened at 00:00 and held whole days (habits.mjs isDateOnlyRow, on trades).
export const isDateOnlyTrade = (t) => t.open_ts % DAY_MS === 0 && t.hold_s % 86400 === 0;

// The number of trades the server will analyse for these stripped rows: dt-private habits.mjs (delivery-39) merges
// rows with the same symbol index, direction and open minute into one trade (mergeRows), keeps date-only rows
// one by one, and does not merge at all in a dates-only file (date-only rows 5% or more of the rows). Tester B4.
const isDateOnlyRow = (r) => r.o % 1440 === 0 && r.h % 86400 === 0;
export function serverTradeCount(rows) {
  let dateOnly = 0;
  for (const r of rows) if (isDateOnlyRow(r)) dateOnly++;
  if (rows.length > 0 && 20 * dateOnly >= rows.length) return rows.length;
  const keys = new Set();
  let n = 0;
  for (const r of rows) {
    if (isDateOnlyRow(r)) { n++; continue; }
    const k = r.s + ':' + r.d + ':' + r.o;
    if (!keys.has(k)) { keys.add(k); n++; }
  }
  return n;
}

const disjoint = (a, b) => { for (const x of a) if (b.has(x)) return false; return true; };

// trades: one list in close-time order; originOf(t) → Set of account (group) indexes. → {trades, collapsed}
// collapsed counts the trades counted into another one (a trade copied to 2 other accounts counts 2); each collapsed
// trade carries _copies, so a caller can count only the trades it keeps. Deterministic: leaders are taken in
// open-time order; each takes, nearest first, at most one trade from each account it does not share, all within the
// window of the leader. The collapsed trade keeps the leader's times (and so its place in close-time order) and id.
export function collapseCopies(trades, originOf, windowMs = COPY_WINDOW_MS) {
  const n = trades.length;
  const order = trades.map((_, i) => i).sort((a, b) => (trades[a].open_ts - trades[b].open_ts)
    || (trades[a].close_ts - trades[b].close_ts) || (a - b));
  const used = new Uint8Array(n);
  const into = new Map();   // leader index → its group (indexes)
  let collapsed = 0;
  for (let p = 0; p < n; p++) {
    const a = order[p];
    if (used[a]) continue;
    used[a] = 1;
    const L = trades[a];
    const files = new Set(originOf(L));
    if (!files.size || isDateOnlyTrade(L)) continue;
    const cands = [];
    for (let q = p + 1; q < n && trades[order[q]].open_ts - L.open_ts <= windowMs; q++) {
      const b = order[q];
      if (used[b]) continue;
      const T = trades[b];
      if (T.symbol !== L.symbol || T.dir !== L.dir || Math.abs(T.close_ts - L.close_ts) > windowMs || isDateOnlyTrade(T)) continue;
      const of = originOf(T);
      if (!of.size || !disjoint(of, files)) continue;
      cands.push({ b, d: Math.abs(T.open_ts - L.open_ts) + Math.abs(T.close_ts - L.close_ts) });
    }
    if (!cands.length) continue;
    cands.sort((x, y) => (x.d - y.d) || (x.b - y.b));
    const group = [a];
    for (const c of cands) {
      const of = originOf(trades[c.b]);
      if (!disjoint(of, files)) continue;
      group.push(c.b);
      used[c.b] = 1;
      for (const k of of) files.add(k);
    }
    if (group.length > 1) { into.set(a, group); collapsed += group.length - 1; }
  }
  if (!collapsed) return { trades, collapsed: 0 };
  const absorbed = new Set();
  for (const g of into.values()) for (const i of g.slice(1)) absorbed.add(i);
  const out = [];
  for (let i = 0; i < n; i++) {
    if (absorbed.has(i)) continue;
    const g = into.get(i);
    if (!g) { out.push(trades[i]); continue; }
    const t = Object.assign({}, trades[i]);
    for (const j of g.slice(1)) {
      const c = trades[j];
      t.qty += c.qty; t.pnl += c.pnl; t.pnl_gross += c.pnl_gross; t.fees += c.fees; t.fills_n += c.fills_n;
    }
    t._copies = g.length - 1;
    out.push(t);
  }
  return { trades: out, collapsed };
}

// The copies among the trades a report keeps (strip.js / small-facts.js reportTrades: the span and the 20,000 cap).
export const copiesIn = (trades) => trades.reduce((k, t) => k + (t._copies || 0), 0);

const kindOf = (r) => r.format + (r.preset ? ':' + r.preset : '');
// An MT5 file is a positions report (its closed positions are its trades) or a deals report (trades are built from
// its deals). One account's two reports read the same position differently, and nothing tells them apart from two
// copy accounts, so the two kinds are never mixed (Tester S3 B3): the files are refused by name.
function mt5Kind(bytes) {
  try {
    const src = readRows(bytes);
    if (src.kind !== 'html') return 'deals';
    return detectHtml(src.rows).tables.some((t) => t.kind === 'mt5_positions_closed') ? 'positions' : 'deals';
  } catch (e) {
    return null;
  }
}
export const mt5MixLine = (pos, deals) => `${pos} is an MT5 positions report and ${deals} is an MT5 deals report. Add reports of one kind: all positions reports, or all deals reports.`;
const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const mixed = () => ({ code: 'E_MIXED_FILES', message: MESSAGES.E_MIXED_FILES });
const tradeKey = (t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, t.entry_vwap, t.exit_vwap, t.fees, t.pnl].join('\u0001');
const warned = (r, code) => { const w = r.warnings.find((x) => x.code === code); return w && w.n ? w.n : 0; };

// byteArrays: one Uint8Array per file; names: their names, for the messages.
// → {error, file?} | {trades, accounts, executions, copies, overlap, groups, notes, format}
//   trades: every file's trades, identical trades counted once, after the copy collapse, in close-time order (strip.js
//   keeps the latest 20,000: the cap applies after the merge); accounts: [{name, trades}], each file's own trades,
//   never added together (the rule check replays one account at a time: Tester re-test R1); executions: every file's
//   fills, symbols kept apart per file, for pgr.js; copies: trades counted once as copies; overlap: identical trades
//   counted once; groups: files (one account each); notes: lines a buyer sees before the run.
export function readFiles(byteArrays, names = []) {
  const n = byteArrays.length;
  const name = (k) => names[k] || `file ${k + 1} of ${n}`;
  let bytes = 0;
  for (const b of byteArrays) bytes += b.length;
  if (bytes > LIMITS.MAX_BYTES) return { error: { code: 'E_TOO_LARGE', message: MESSAGES.E_TOO_LARGE } };
  const own = [];
  for (let k = 0; k < n; k++) {
    const r = runFile(byteArrays[k]);
    if (r.error) return { error: n > 1 ? { ...r.error, message: `${r.error.message} (${name(k)})` } : r.error, file: k };
    if (k > 0 && kindOf(r.result) !== kindOf(own[0])) return { error: mixed(), file: k };
    own.push(r.result);
  }
  if (n > 1 && own[0].format === 'mt5') {
    const kinds = byteArrays.map(mt5Kind);
    const p = kinds.indexOf('positions'), d = kinds.indexOf('deals');
    if (p >= 0 && d >= 0) return { error: { code: 'E_MIXED_FILES', message: mt5MixLine(name(p), name(d)) }, file: Math.max(p, d) };
  }
  let total = 0;
  for (const r of own) total += r.trades.length;
  if (total > LIMITS.MAX_ROWS) return { error: { code: 'E_TOO_LARGE', message: MESSAGES.E_TOO_LARGE } };
  const units = [...new Set(own.flatMap((r) => r.trades.map((t) => t.pnl_unit)))];
  if (units.length > 1) return { error: { code: 'E_MIXED_UNITS', message: MIXED_UNITS } };
  // identical closed trades: kept as many times as the file that has the most of them (a multiset, as dropOverlap)
  const keep = new Map();
  const where = new Map();
  own.forEach((r, k) => {
    const c = new Map();
    for (const t of r.trades) { const key = tradeKey(t); c.set(key, (c.get(key) || 0) + 1); }
    for (const [key, m] of c) {
      if (m > (keep.get(key) || 0)) keep.set(key, m);
      if (!where.has(key)) where.set(key, new Set());
      where.get(key).add(k);
    }
  });
  const used = new Map();
  const trades = [];
  const executions = [];
  const notes = [];
  let overlap = 0;
  let edge = 0;
  own.forEach((r, k) => {
    for (const t of r.trades) {
      const key = tradeKey(t);
      const u = (used.get(key) || 0) + 1;
      used.set(key, u);
      if (u <= keep.get(key)) trades.push(Object.assign({}, t, { _g: k, _in: where.get(key) })); else overlap++;
    }
    for (const e of r.executions) executions.push(Object.assign({}, e, { symbol: k + '\u0001' + e.symbol }));
    const cur = r.warnings.find((x) => x.code === 'W_MIXED_CURRENCY' && x.n > 0);
    if (cur) notes.push(n > 1 ? `${cur.message} (${name(k)})` : cur.message);
    edge += warned(r, 'W_OPEN_POSITIONS') + warned(r, 'W_OPEN_AT_START');
  });
  if (n > 1 && edge) notes.push(edgeLine(edge));
  trades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || cmpStr(a.symbol, b.symbol) || (a._g - b._g));
  let out = trades;
  let copies = 0;
  if (n > 1) {
    const c = collapseCopies(trades, (t) => t._in);
    out = c.trades;
    copies = c.collapsed;
  }
  out = out.map((t, i) => Object.assign(t, { id: 't' + (i + 1) }));
  const accounts = own.map((r, k) => ({ name: name(k), trades: r.trades }));
  return { trades: out, accounts, executions, copies, overlap, groups: n, notes, format: own[0].format };
}

// readFiles, kept as the page's entry point (it returns refusals; it never throws for a bad file).
export const readAll = readFiles;
