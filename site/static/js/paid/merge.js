// merge.js — several trade files of one platform, read as one history for the paid report (ARCHITECT-EVIDENCE-
// SCALE-AND-POWER §7 S3; Tester S3 report B2–B4, M1, M3). No DOM, no network: report.js calls readFiles, then
// strip.js strips the result.
//
// 1. Every file is read ON ITS OWN first (index.js runFile), so fills from different accounts never share one
//    position book (Tester B2: pooled books made up trades). All files must be of one platform and report type
//    (E_MIXED_FILES): an MT5 positions report and an MT5 deals report are two report types.
// 2. Files that share rows (an overlapping monthly export, or two months of one account) are one account: they are
//    read together by the engine (runFiles → dropOverlap counts each shared row once). A group read that gives fewer
//    trades than one of its files alone is refused, naming the files (Tester B3: a file is never dropped silently).
// 3. All accounts must report in one currency or unit, or the files are refused (Tester M1).
// 4. Copy collapse, before stripping: a trade copied to a second account shows up in each account's file. Trades
//    from DIFFERENT accounts with the same symbol and direction, opened within 5 minutes of each other and closed
//    within 5 minutes of each other, become one trade (P&L, gross, fees, fills and quantity summed). Unmerged copies
//    doubled revenge's false-alarm rate (copy.mjs: 8.0 in 100 at a 2.5 level; 1.8–3.0 after the collapse). Trades of
//    one account never collapse, however close; date-only trades (no time of day) never collapse (Tester M3).

import { runFiles, runFile } from '../engine/index.js';
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
export const disagreeLine = (names) => `${names.join(' and ')} share rows, but read together they give fewer trades than one of them alone. Export them as the same kind of report and add them again.`;
export const overlapLine = (n) => `${grouped(n)} ${n === 1 ? 'row was' : 'rows were'} in more than one file and ${n === 1 ? 'was' : 'were'} counted once.`;

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

const execKey = (e) => [e.ts, e.symbol, e.side, e.qty, e.price, e.fee].join('\u0001');
const kindOf = (r) => r.format + (r.preset ? ':' + r.preset : '');
const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const mixed = () => ({ code: 'E_MIXED_FILES', message: MESSAGES.E_MIXED_FILES });

// byteArrays: one Uint8Array per file; names: their names, for the messages.
// → {error, file?} | {trades, executions, copies, overlap, groups, notes}
//   trades: every account's trades after the copy collapse, in close-time order (strip.js keeps the latest 20,000:
//   the cap applies after the merge); executions: every account's fills, symbols kept apart per account, for pgr.js;
//   copies: trades counted once as copies; overlap: rows in more than one file of one account; groups: accounts;
//   notes: the engine's left-out lines a buyer sees before the run (currencies left out inside one file).
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
  let total = 0;
  for (const r of own) total += r.trades.length;
  if (total > LIMITS.MAX_ROWS) return { error: { code: 'E_TOO_LARGE', message: MESSAGES.E_TOO_LARGE } };
  // accounts: files that share a fill are one account (union-find on the fills' keys)
  const parent = own.map((_, k) => k);
  const root = (k) => (parent[k] === k ? k : (parent[k] = root(parent[k])));
  const seen = new Map();
  own.forEach((r, k) => {
    for (const e of r.executions) {
      const key = execKey(e);
      if (!seen.has(key)) seen.set(key, k);
      else { const a = root(seen.get(key)), b = root(k); if (a !== b) parent[Math.max(a, b)] = Math.min(a, b); }
    }
  });
  const members = new Map();
  own.forEach((_, k) => { const g = root(k); if (!members.has(g)) members.set(g, []); members.get(g).push(k); });
  const groups = [...members.values()];
  const trades = [];
  const executions = [];
  const notes = [];
  let overlap = 0;
  groups.forEach((ks, g) => {
    let res = own[ks[0]];
    if (ks.length > 1) {
      const r = runFiles(ks.map((k) => byteArrays[k]));
      if (r.error) throw Object.assign(new Error('group'), { engine: { ...r.error, message: `${r.error.message} (${ks.map(name).join(', ')})` }, file: ks[0] });
      res = r.result;
      const most = Math.max(...ks.map((k) => own[k].trades.length));
      if (res.trades.length < most) throw Object.assign(new Error('group'), { engine: { code: 'E_FILES_DISAGREE', message: disagreeLine(ks.map(name)) }, file: ks[0] });
      const w = res.warnings.find((x) => x.code === 'W_OVERLAP_ROWS');
      if (w) overlap += w.n;
    }
    const cur = res.warnings.find((x) => x.code === 'W_MIXED_CURRENCY' && x.n > 0);
    if (cur) notes.push(cur.message);
    for (const t of res.trades) trades.push(Object.assign({}, t, { _g: g }));
    for (const e of res.executions) executions.push(Object.assign({}, e, { symbol: g + '\u0001' + e.symbol }));
  });
  const units = [...new Set(trades.map((t) => t.pnl_unit))];
  if (units.length > 1) return { error: { code: 'E_MIXED_UNITS', message: MIXED_UNITS } };
  trades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || cmpStr(a.symbol, b.symbol) || (a._g - b._g));
  let out = trades;
  let copies = 0;
  if (groups.length > 1) {
    const sets = new Map();
    const c = collapseCopies(trades, (t) => { if (!sets.has(t._g)) sets.set(t._g, new Set([t._g])); return sets.get(t._g); });
    out = c.trades;
    copies = c.collapsed;
  }
  out = out.map((t, i) => Object.assign(t, { id: 't' + (i + 1) }));
  return { trades: out, executions, copies, overlap, groups: groups.length, notes, format: own[0].format };
}

// readFiles, with a group refusal returned rather than thrown.
export function readAll(byteArrays, names = []) {
  try {
    return readFiles(byteArrays, names);
  } catch (e) {
    if (e && e.engine) return { error: e.engine, file: e.file };
    throw e;
  }
}
