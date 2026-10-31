// merge.js — several trade files of one platform, read as one history for the paid report (ARCHITECT-EVIDENCE-
// SCALE-AND-POWER §7 S3). No DOM, no network: report.js calls readFiles, then strip.js strips the result.
//
// 1. The engine reads every file together (index.js runFiles → parseFiles): one platform only (E_MIXED_FILES),
//    and rows that are in more than one file are counted once (mapped.js dropOverlap).
// 2. Copy collapse, before stripping: a trade copied to a second account shows up in each account's file. Rows
//    from DIFFERENT files with the same symbol and direction, opened within 5 minutes of each other and closed
//    within 5 minutes of each other, become one trade (P&L, gross, fees, fills and quantity summed). Unmerged
//    copies doubled revenge's false-alarm rate (copy.mjs: 8.0 in 100 at a 2.5 level; 1.8–3.0 after the collapse).
//    Two trades from the same file never collapse, however close they are.
//
// Which file a merged trade came from: each file is also read on its own, and a merged trade belongs to every file
// whose own reading has a trade with the same symbol, direction, open, close, quantity and P&L. A trade the files
// share (an overlapping monthly export) belongs to both, so it never collapses with a trade from either. A trade
// no single file shows on its own (a position opened in one file and closed in the next) has no file and never
// collapses: the rule only ever counts once what it can place in two different files.

import { runFiles, runFile } from '../engine/index.js?v=8410d06a';

export const COPY_WINDOW_MS = 5 * 60000;   // "within 5 minutes": a lag of exactly 5 minutes collapses, 6 does not
export const SMALL_FILE = 100;              // owner Q3: fewer trades than this → the pre-run notice

export const copyLine = (k) => (k === 1
  ? '1 trade in one file matched a trade in another file within 5 minutes and was counted once.'
  : `${k} trades in one file matched a trade in another file within 5 minutes and were counted once.`);

// The pre-run notice (owner Q3). Definite wording: no may, might, maybe, unclear, could be or possibly.
export const SMALL_NOTICE = 'Files this size mostly show No sign for habits. You still get every dollar total and your rule check.';
export const SMALL_WAIT = 'Adding files does not use your run.';
export const UPLOAD_HINT = 'Add all your accounts and months: more trades, clearer answers.';

const tradeKey = (t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, t.pnl].join('\u0001');

// perFile: one trades array per file (in the order the files were given) → (trade) => Set of file indexes.
export function originsOf(perFile) {
  const at = new Map();
  perFile.forEach((trades, k) => {
    for (const t of trades || []) {
      const key = tradeKey(t);
      if (!at.has(key)) at.set(key, new Set());
      at.get(key).add(k);
    }
  });
  const none = new Set();
  return (t) => at.get(tradeKey(t)) || none;
}

const disjoint = (a, b) => { for (const x of a) if (b.has(x)) return false; return true; };

// trades: ParseResult.trades (close-time order); originOf: originsOf(...). → {trades, collapsed}
// collapsed is the number of trades counted into another one (a trade copied to 2 other accounts counts 2).
// Deterministic: leaders are taken in open-time order; each takes, nearest first, at most one trade from each
// file it does not share, all within the window of the leader. The collapsed trade keeps the leader's times
// (and so its place in close-time order), id and symbol.
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
    if (!files.size) continue;
    const cands = [];
    for (let q = p + 1; q < n && trades[order[q]].open_ts - L.open_ts <= windowMs; q++) {
      const b = order[q];
      if (used[b]) continue;
      const T = trades[b];
      if (T.symbol !== L.symbol || T.dir !== L.dir || Math.abs(T.close_ts - L.close_ts) > windowMs) continue;
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
    out.push(t);
  }
  return { trades: out, collapsed };
}

// byteArrays: one Uint8Array per file → {error} | {result, trades, copies}
// result is the engine's merged ParseResult (its executions feed pgr.js); trades are result.trades after the copy
// collapse, in close-time order, ready for strip.js (which keeps the latest 20,000: the cap applies after the merge).
export function readFiles(byteArrays) {
  const parsed = runFiles(byteArrays);
  if (parsed.error) return { error: parsed.error };
  let trades = parsed.result.trades;
  let copies = 0;
  if (byteArrays.length > 1) {
    const perFile = byteArrays.map((b) => { const r = runFile(b); return r.result ? r.result.trades : []; });
    const c = collapseCopies(trades, originsOf(perFile));
    trades = c.trades;
    copies = c.collapsed;
  }
  return { result: parsed.result, trades, copies };
}
