// merge.js — several trade files of one platform, read as one history for the paid report (ARCHITECT-EVIDENCE-
// SCALE-AND-POWER §7 S3; Tester S3 report B2–B4, M1, M3). No DOM, no network: report.js calls readFiles, then
// strip.js strips the result.
//
// 1. Files are first put into accounts (Tester S3 re-test 2): the same account value (Account, ClientAccountID, an
//    MT5 report's "Account:" line) → one account; different values → separate accounts, whatever else they share (group
//    trading); else a shared fill, order, deal or trade ID → one account; else the buyer ALWAYS answers one question
//    before Run ("Are these files from one account or separate accounts?"), preset "One account" when the overlapping
//    rows match, "Separate accounts" when they differ or the dates do not overlap (Tester re-test 3).
//    Copy accounts are then decided per pair of accounts (COPY_NEVER, COPY_SURE below), with a second question in
//    between ("Do these accounts copy each other's trades?").
// 2. Each account's files are read together by the engine (runFiles: dropOverlap counts a row in two of its files once),
//    so each account is ONE position book; no fill is ever pooled across accounts (Tester B2, R2). An MT5 positions
//    report and an MT5 deals report are never mixed (B3). All files must be of one platform (E_MIXED_FILES).
// 3. All files must report in one currency or unit, or they are refused (Tester M1).
// 4. Copy collapse, after the books and before stripping, for the habit checks only (the dollar facts keep every
//    account's real trades). A trade copied to a second account shows up in each account's file. Trades
//    from DIFFERENT accounts with the same symbol and direction, opened within 15 minutes of each other and closed
//    within 15 minutes of each other, become one trade (P&L, gross, fees, fills and quantity summed; ARCHITECT-DT2-
//    CALIBRATION-FIXES item 6: slow copiers, 6-8 minutes, pushed Clear to 6.0 in 100 at 5 minutes). Unmerged copies
//    doubled revenge's false-alarm rate (copy.mjs: 8.0 in 100 at a 2.5 level; 1.8–3.0 after the collapse). Trades of
//    one account never collapse, however close; date-only trades (no time of day) never collapse (Tester M3).

import { runFile, runFiles, readRows } from '../engine/index.js?v=8410d06a';
import { idColumns } from '../engine/mapped.js?v=e8a99f4b';
import { normHeader } from '../engine/csv.js?v=7dca0e6f';
import { detectHtml } from '../engine/detect.js?v=fa17739c';
import { MESSAGES, LIMITS } from '../engine/errors.js?v=8ee10796';

export const COPY_WINDOW_MS = 15 * 60000;  // "within 15 minutes": a lag of exactly 15:00 collapses, 15:01 does not
export const NEAR_WINDOW_MS = 60 * 60000;  // near-copies: 15 to 60 minutes apart, counted and left separate
// Copy accounts are decided per PAIR of accounts, never per trade (Tester S3 re-test 3): the share of the two accounts'
// trades, on the symbols both trade, that pair one to one within the 15-minute window. The Tester's simulation of two
// INDEPENDENT accounts on one contract (60 days, lognormal holds, open-heavy days) pairs 0.6-38% of trades at 15
// minutes for 2-10 trades a day, and 53-61% only for 20-30 two-to-three-minute scalps a day; a copier pairs about all
// of its trades (100%, less skipped or split copies). So: under 50% the pair is never collapsed; 80% or more is a copy
// pair (collapsed at up to 15 minutes, which keeps the slow-copier fix); in between the buyer is asked, preset "yes"
// from 65%.
export const COPY_NEVER = 0.5;
export const COPY_SURE = 0.8;
export const COPY_PRESET = 0.65;
export const COPY_QUESTION = 'Do these accounts copy each other’s trades?';
export const copyPairLine = (a, b, k) => `Accounts ${a} and ${b} copy each other: ${grouped(k)} ${k === 1 ? 'trade' : 'trades'} counted once.`;
// stats3a (dt-private 6b8b82c): with more than one account, every row carries its account index a (strip.js), and the
// server combines rows with the same symbol, direction and open minute only within one account (key s:d:o:a), so two
// accounts that trade on their own are never combined.
export const ownPairLine = (a, b) => `Accounts ${a} and ${b} trade on their own: no trade is counted once as a copy, and their trades stay separate for the habit checks.`;
// The server takes an account index a of 0..99 (dt-private MAX_ACCOUNTS): more accounts than that are refused here.
export const MAX_ACCOUNTS = 100;
export const TOO_MANY_ACCOUNTS = `These files are from more than ${MAX_ACCOUNTS} accounts. One test reads at most ${MAX_ACCOUNTS} accounts at a time.`;
// The account index of a trade for the server (its group, in the order the files were met), or null for one account.
export const accountOf = (groups) => (groups > 1 ? (t) => t._g : null);
export const SMALL_FILE = 100;              // owner Q3: fewer trades than this → the small-file notice
const DAY_MS = 86400000;

const grouped = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
export const copyLine = (k) => (k === 1
  ? '1 trade in one file matched a trade in another file within 15 minutes and was counted once.'
  : `${grouped(k)} trades in one file matched a trade in another file within 15 minutes and were counted once.`);
// Calibration fixes item 6: the near-misses, stated definitely, when there are any.
export const nearLine = (j) => (j === 1
  ? '1 more trade matches a trade in another file 15 to 60 minutes apart; it is counted as a separate trade.'
  : `${grouped(j)} more trades match a trade in another file 15 to 60 minutes apart; they are counted as separate trades.`);

// The small-file notice (owner Q3, Architect addendum wording). Definite: no may, might, maybe, unclear, could be or
// possibly.
export const SMALL_NOTICE = 'Files this size mostly show No sign for habits. You still get every dollar total and your rule check.';
export const WAIT_LINE = 'Nothing is sent until you press Run. Adding files does not use a run.';
export const UPLOAD_HINT = 'Add all your accounts and months: more trades, clearer answers.';
export const MIXED_UNITS = 'These files report results in different currencies or units, so they cannot be added up. Add the files of one currency at a time.';
export const overlapLine = (n) => `${grouped(n)} ${n === 1 ? 'row was' : 'rows were'} in more than one file of one account and ${n === 1 ? 'was' : 'were'} counted once.`;
// Accounts and files, as page 1 and the panel name them (Tester re-test 2 R6: by detected accounts, never by file count).
export const filesLabel = (accts, files) => `${grouped(accts)} ${accts === 1 ? 'account' : 'accounts'}, ${grouped(files)} ${files === 1 ? 'file' : 'files'}`;
export const accountsLine = (accts, files) => (accts === 1
  ? `These results read ${grouped(files)} files as 1 account.`
  : `These results combine ${grouped(accts)} accounts from ${grouped(files)} files. Dollar totals add every account’s trades; for accounts that copy each other, the habit checks count each copied trade once. The rule check covers one account at a time.`);
export const edgeLine = (n) => `${grouped(n)} ${n === 1 ? 'position was' : 'positions were'} open at the start or end of an account’s files and ${n === 1 ? 'was' : 'were'} left out.`;
export const ACCOUNT_QUESTION = 'Are these files from one account or separate accounts?';
export const ACCOUNT_ONE = 'One account';
export const ACCOUNT_SEPARATE = 'Separate accounts';

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
    const k = r.s + ':' + r.d + ':' + r.o + (r.a === undefined ? '' : ':' + r.a);   // the server's key (s:d:o:a with accounts)
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
export function collapseCopies(trades, originOf, windowMs = COPY_WINDOW_MS, pairOk = null) {
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
      if (!of.size || !disjoint(of, files) || (pairOk && !pairOk(files, of))) continue;
      cands.push({ b, d: Math.abs(T.open_ts - L.open_ts) + Math.abs(T.close_ts - L.close_ts) });
    }
    if (!cands.length) continue;
    cands.sort((x, y) => (x.d - y.d) || (x.b - y.b));
    const group = [a];
    for (const c of cands) {
      const of = originOf(trades[c.b]);
      if (!disjoint(of, files) || (pairOk && !pairOk(files, of))) continue;
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
    t._in = new Set();
    for (const j of g) for (const k of originOf(trades[j])) t._in.add(k);
    out.push(t);
  }
  return { trades: out, collapsed };
}

// The copies among the trades a report keeps (strip.js / small-facts.js reportTrades: the span and the 20,000 cap).
export const copiesIn = (trades) => trades.reduce((k, t) => k + (t._copies || 0), 0);

const kindOf = (r) => r.format + (r.preset ? ':' + r.preset : '');
const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
const mixed = () => ({ code: 'E_MIXED_FILES', message: MESSAGES.E_MIXED_FILES });
const warned = (r, code) => { const w = r.warnings.find((x) => x.code === code); return w && w.n ? w.n : 0; };
const execKey = (e) => [e.ts, e.symbol, e.side, e.qty, e.price, e.fee].join('\u0001');
const meets = (a, b) => { for (const x of a) if (b.has(x)) return true; return false; };

// An MT5 file is a positions report (its closed positions are its trades) or a deals report (trades are built from
// its deals). One account's two reports read the same position differently, so the two kinds are never mixed
// (Tester S3 B3): the files are refused by name.
function mt5Kind(bytes) {
  try {
    const src = readRows(bytes);
    if (src.kind !== 'html') return 'deals';
    return detectHtml(src.rows).tables.some((t) => t.kind === 'mt5_positions_closed') ? 'positions' : 'deals';
  } catch (e) {
    return null;
  }
}
// The same trade (symbol, direction, open, close, size) in two files of one account with a different P&L or fee.
// → null | {k, why: 'fees_a' | 'fees_b' | 'fees' | 'pnl'}  (fees_a: only the first file has fees on them)
const cents = (x) => Math.round(x * 100);
function amountsDiffer(A, B) {
  const at = new Map();
  for (const t of A) {
    const k = [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty].join('\u0001');
    if (!at.has(k)) at.set(k, []);
    at.get(k).push(t);
  }
  let k = 0, feesA = 0, feesB = 0, feeGap = false;
  for (const t of B) {
    const list = at.get([t.symbol, t.dir, t.open_ts, t.close_ts, t.qty].join('\u0001'));
    if (!list || !list.length) continue;
    const i = list.findIndex((u) => cents(u.pnl) === cents(t.pnl) && cents(u.fees) === cents(t.fees));
    if (i >= 0) { list.splice(i, 1); continue; }
    const u = list.shift();
    k++;
    feesA += cents(u.fees); feesB += cents(t.fees);
    if (cents(u.fees) !== cents(t.fees)) feeGap = true;
  }
  if (!k) return null;
  return { k, why: !feeGap ? 'pnl' : feesB === 0 ? 'fees_a' : feesA === 0 ? 'fees_b' : 'fees' };
}
export const differLine = (a, b, d) => `${a} and ${b} show different amounts for the same ${grouped(d.k)} ${d.k === 1 ? 'trade' : 'trades'} (`
  + (d.why === 'fees_a' ? `${a} includes commissions` : d.why === 'fees_b' ? `${b} includes commissions`
    : d.why === 'fees' ? 'their commissions differ' : 'their results differ') + '). Upload one of them.';

export const mt5MixLine = (pos, deals) => `${pos} is an MT5 positions report and ${deals} is an MT5 deals report. Add reports of one kind: all positions reports, or all deals reports.`;

// Which account a file is from, as far as the file says (Tester re-test 2 R4–R6). accounts: the values of its account
// columns (Account, ClientAccountID, …; an MT5 report's "Account:" line); ids: its fill, order, deal or trade IDs. The
// values are only compared here: they never reach a result, a message or the page (as mapped.js idColumns).
const NUMERIC = /^[-+$€£¥]?\s*[\d.,\s]+%?$/;
export function fileIdentity(bytes) {
  const accounts = new Set();
  const ids = new Set();
  let src;
  try { src = readRows(bytes); } catch (e) { return { accounts, ids }; }
  const rows = src.rows;
  for (const r of rows.slice(0, 60)) {   // a report's header block: "Account:" and its value, alone on a row
    const full = r.cells.map((c) => c.trim()).filter((c) => c !== '');
    if (full.length === 2 && normHeader(full[0]) === 'account') accounts.add(full[1]);
  }
  let h = -1;
  for (let i = 0; i < Math.min(rows.length, 200); i++) {
    const full = rows[i].cells.map((c) => c.trim()).filter((c) => c !== '');
    if (full.length < 3 || !idColumns(rows[i].cells).length) continue;
    if (2 * full.filter((c) => NUMERIC.test(c)).length > full.length) continue;
    h = i;
    break;
  }
  if (h >= 0) {
    const head = rows[h].cells;
    const idx = idColumns(head);
    for (const r of rows.slice(h + 1)) {
      if (src.kind === 'html' && r.table !== rows[h].table) continue;
      for (const i of idx) {
        const v = (r.cells[i] || '').trim();
        if (!v) continue;
        const n = normHeader(head[i]);
        if (n.indexOf('account') !== -1 || n.indexOf('acct') !== -1) accounts.add(v); else ids.add(n + ':' + v);
      }
    }
  }
  return { accounts, ids };
}

// A file's rows as written, for comparing two files without account or ID columns (Tester re-test 3: the engine's
// KEPT fills leave out a fill that closes a position opened before the file, so an overlapping re-export of one
// account looked different). → {head: normalised headings, rows: cell arrays} (CSV only; HTML → empty).
function rawRows(bytes) {
  try {
    const src = readRows(bytes);
    if (src.kind === 'html') return { head: [], rows: [] };
    const rows = src.rows;
    let h = -1;
    for (let i = 0; i < Math.min(rows.length, 50); i++) {
      const full = rows[i].cells.map((c) => c.trim()).filter((c) => c !== '');
      if (full.length >= 2 && 2 * full.filter((c) => NUMERIC.test(c)).length < full.length) { h = i; break; }
    }
    if (h < 0) return { head: [], rows: [] };
    const data = rows.slice(h + 1).map((r) => r.cells).filter((c) => c.filter((x) => x.trim() !== '').length >= 2);
    return { head: rows[h].cells.map(normHeader), rows: data };
  } catch (e) {
    return { head: [], rows: [] };
  }
}

// Rows of two files that are the same in every column both files have (a multiset count), and the smaller row count.
function sharedRows(a, b) {
  const common = a.head.filter((x, i) => x && a.head.indexOf(x) === i && b.head.includes(x));
  if (!common.length) return { shared: 0, fewer: Math.min(a.rows.length, b.rows.length) };
  const key = (f, cells) => common.map((x) => (cells[f.head.indexOf(x)] || '').trim()).join('\u0001');
  const m = new Map();
  for (const c of a.rows) { const k = key(a, c); m.set(k, (m.get(k) || 0) + 1); }
  let shared = 0;
  for (const c of b.rows) { const k = key(b, c); const n = m.get(k) || 0; if (n) { shared++; m.set(k, n - 1); } }
  return { shared, fewer: Math.min(a.rows.length, b.rows.length) };
}

// Two files with no account column and no shared ID: the default answer to ACCOUNT_QUESTION is "one account" when their
// dates overlap and every fill of the earlier file inside the overlap is also in the later file (an overlapping
// re-export). → true (looks like one account), false (dates overlap, rows differ), null (no overlap: no evidence).
function looksLikeOneAccount(a, b) {
  const span = (r) => { let lo = Infinity, hi = -Infinity; for (const e of r.executions) { if (e.ts < lo) lo = e.ts; if (e.ts > hi) hi = e.ts; } return [lo, hi]; };
  let [x, y] = [a, b];
  if (span(y)[0] < span(x)[0]) [x, y] = [y, x];
  const from = span(y)[0], to = span(x)[1];
  if (!(from <= to)) return null;
  const later = new Map();
  for (const e of y.executions) { const k = execKey(e); later.set(k, (later.get(k) || 0) + 1); }
  let inside = 0;
  for (const e of x.executions) {
    if (e.ts < from || e.ts > to) continue;
    inside++;
    const k = execKey(e);
    const c = later.get(k) || 0;
    if (!c) return false;
    later.set(k, c - 1);
  }
  return inside > 0 ? true : null;
}

// byteArrays: one Uint8Array per file; names: their names; opts.oneAccount: the buyer's answer to ACCOUNT_QUESTION
// (true, false, or null for the default).
// → {error, file?} | {trades, factsTrades, accounts, executions, copies, overlap, groups, files, question, notes, format}
//   Files are first put into accounts (Tester re-test 2): the same account value → one account; different account
//   values → separate accounts, whatever else they share (group trading); else a shared fill, order or deal ID → one
//   account; else the buyer's one answer (question: {default}), which never joins files whose account values differ.
//   Each account's files are read together by the engine (runFiles: dropOverlap counts a row in two of its files
//   once), so each account is one position book; no fill is pooled across accounts (Tester B2, R2).
//   trades: every account's trades after the copy collapse (one trade per copy), in close-time order, for the habit
//   checks (strip.js keeps the latest 20,000: the cap applies after the merge); factsTrades: every account's own trades,
//   copies kept (real money: the dollar facts); accounts: [{name, trades}] (the rule check, one at a time); executions:
//   fills, symbols kept apart per account, for pgr.js; copies; overlap: rows counted once inside an account; groups:
//   accounts; files; notes: lines a buyer sees before the run.
export function readFiles(byteArrays, names = [], opts = {}) {
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
  // ---- accounts
  const parent = own.map((_, k) => k);
  const root = (k) => (parent[k] === k ? k : (parent[k] = root(parent[k])));
  const ident = n > 1 ? byteArrays.map(fileIdentity) : [];
  // apart: different account values (never joined, whatever the buyer answers)
  const apart = (i, j) => ident[i].accounts.size > 0 && ident[j].accounts.size > 0 && !meets(ident[i].accounts, ident[j].accounts);
  const members = (r) => own.map((_, k) => k).filter((k) => root(k) === r);
  const canJoin = (i, j) => !members(root(i)).some((a) => members(root(j)).some((b) => apart(a, b)));
  const join = (i, j) => { const a = root(i), b = root(j); if (a !== b) parent[Math.max(a, b)] = Math.min(a, b); };
  const open = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const A = ident[i], B = ident[j];
      if (A.accounts.size && B.accounts.size) { if (meets(A.accounts, B.accounts)) join(i, j); continue; }
      if (A.ids.size && B.ids.size && meets(A.ids, B.ids)) { join(i, j); continue; }
      open.push([i, j]);
    }
  }
  // Nothing in the files settles these pairs, so the buyer is always asked (Tester re-test 3: never "separate"
  // silently). Each pair's evidence sets the preset: 'match' (the overlapping kept fills match, or at least 2 rows and a
  // quarter of the smaller file are the same in every shared column) → "One account"; 'differ' (dates overlap, rows
  // differ) → "Separate accounts"; 'none' (no overlap: consecutive months, or unrelated files).
  const raw = open.length ? byteArrays.map(rawRows) : [];
  const span = (r) => { let lo = Infinity, hi = -Infinity; for (const e of r.executions) { if (e.ts < lo) lo = e.ts; if (e.ts > hi) hi = e.ts; }
    for (const t of r.trades) { if (t.open_ts < lo) lo = t.open_ts; if (t.close_ts > hi) hi = t.close_ts; } return [lo, hi]; };
  const evidence = new Map();
  for (const [i, j] of open) {
    if (root(i) === root(j)) continue;
    const [a0, a1] = span(own[i]), [b0, b1] = span(own[j]);
    const overlap = a0 <= b1 && b0 <= a1;
    const { shared, fewer } = sharedRows(raw[i], raw[j]);
    const match = looksLikeOneAccount(own[i], own[j]) === true || (shared >= 2 && 4 * shared >= fewer);
    evidence.set(i + ':' + j, match ? 'match' : overlap ? 'differ' : 'none');
  }
  const undecided = open.filter(([i, j]) => evidence.has(i + ':' + j) && root(i) !== root(j) && canJoin(i, j));
  let question = null;
  if (undecided.length) {
    const anyMatch = undecided.some(([i, j]) => evidence.get(i + ':' + j) === 'match');
    const one = opts.oneAccount === true || opts.oneAccount === false ? opts.oneAccount : anyMatch;
    question = { default: anyMatch, answer: one };
    // "One account" joins the files that match or do not overlap; files whose dates overlap with rows that differ are
    // joined only when no pair matches (then the answer is about them)
    if (one) {
      for (const [i, j] of undecided) {
        const ev = evidence.get(i + ':' + j);
        if ((ev !== 'differ' || !anyMatch) && root(i) !== root(j) && canJoin(i, j)) join(i, j);
      }
    }
  }
  const groups = [];
  const at = new Map();
  own.forEach((_, k) => { const r = root(k); if (!at.has(r)) { at.set(r, groups.length); groups.push([]); } groups[at.get(r)].push(k); });
  // ---- one book per account
  if (groups.length > MAX_ACCOUNTS) return { error: { code: 'E_TOO_MANY_ACCOUNTS', message: TOO_MANY_ACCOUNTS } };
  const factsTrades = [];
  const executions = [];
  const accounts = [];
  const notes = [];
  let overlap = 0;
  let edge = 0;
  for (let g = 0; g < groups.length; g++) {
    const ks = groups[g];
    let res = own[ks[0]];
    if (ks.length > 1) {
      // Tester re-test 4 F1: files of one account that show different amounts for the same trades (one export with
      // commissions, one without) would double some fills in the joined book. Refused, by name, never one picked.
      for (let x = 0; x < ks.length; x++) {
        for (let y = x + 1; y < ks.length; y++) {
          const d = amountsDiffer(own[ks[x]].trades, own[ks[y]].trades);
          if (d) return { error: { code: 'E_FILES_DIFFER', message: differLine(name(ks[x]), name(ks[y]), d) }, file: ks[y] };
        }
      }
      const r = runFiles(ks.map((k) => byteArrays[k]));
      if (r.error) return { error: { ...r.error, message: `${r.error.message} (${ks.map(name).join(', ')})` }, file: ks[0] };
      res = r.result;
      overlap += warned(res, 'W_OVERLAP_ROWS');
    }
    const cur = res.warnings.find((x) => x.code === 'W_MIXED_CURRENCY' && x.n > 0);
    if (cur) notes.push(n > 1 ? `${cur.message} (${ks.map(name).join(', ')})` : cur.message);
    edge += warned(res, 'W_OPEN_POSITIONS') + warned(res, 'W_OPEN_AT_START');
    const mine = res.trades.map((t) => Object.assign({}, t, { _g: g }));
    accounts.push({ name: ks.map(name).join(' + '), files: ks.map(name), trades: mine });
    factsTrades.push(...mine);
    for (const e of res.executions) executions.push(Object.assign({}, e, { symbol: g + '\u0001' + e.symbol }));
  }
  const units = [...new Set(factsTrades.map((t) => t.pnl_unit))];
  if (units.length > 1) return { error: { code: 'E_MIXED_UNITS', message: MIXED_UNITS } };
  if (n > 1 && edge) notes.push(edgeLine(edge));
  factsTrades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || cmpStr(a.symbol, b.symbol) || (a._g - b._g));
  let out = factsTrades;
  let copies = 0;
  let near = 0;
  const pairs = [];
  if (groups.length > 1) {
    const sets = groups.map((_, g) => new Set([g]));
    const of = (t) => t._in || sets[t._g];
    // copy accounts, per pair (COPY_NEVER / COPY_SURE above)
    const yes = new Set();
    for (let g = 0; g < groups.length; g++) {
      for (let h = g + 1; h < groups.length; h++) {
        const A = accounts[g].trades, B = accounts[h].trades;
        const sa = new Set(A.map((t) => t.symbol)), sb = new Set(B.map((t) => t.symbol));
        const a2 = A.filter((t) => sb.has(t.symbol)), b2 = B.filter((t) => sa.has(t.symbol));
        const base = Math.min(a2.length, b2.length);
        const matched = base ? collapseCopies(a2.concat(b2), of).collapsed : 0;
        const share = base ? matched / base : 0;
        const status = share >= COPY_SURE ? 'copy' : share < COPY_NEVER ? 'own' : 'ask';
        const preset = status === 'copy' || (status === 'ask' && share >= COPY_PRESET);
        const key = accounts[g].name + '\u0001' + accounts[h].name;
        const given = opts.copies && typeof opts.copies[key] === 'boolean' ? opts.copies[key] : null;
        const copy = status === 'ask' && given !== null ? given : preset;
        pairs.push({ key, a: accounts[g].name, b: accounts[h].name, matched, share, status, preset, copy });
        if (copy) yes.add(g + ':' + h);
      }
    }
    const pairOk = (S, T) => { for (const x of S) for (const y of T) if (x !== y && !yes.has(Math.min(x, y) + ':' + Math.max(x, y))) return false; return true; };
    if (yes.size) {
      const c = collapseCopies(factsTrades, of, COPY_WINDOW_MS, pairOk);
      out = c.trades;
      copies = c.collapsed;
      // near-copies of copy accounts: the trades left that still pair, one to one and nearest first, with a trade of
      // the other account within 60 minutes on both ends (the same matching, a wider window; nothing is merged)
      near = collapseCopies(out, of, NEAR_WINDOW_MS, pairOk).collapsed;
    }
  }
  out = out.map((t, i) => Object.assign({}, t, { id: 't' + (i + 1) }));
  return { trades: out, factsTrades, accounts, executions, copies, near, pairs, overlap, groups: groups.length, files: n, question, notes,
    format: own[0].format };
}

// readFiles, kept as the page's entry point (it returns refusals; it never throws for a bad file).
export const readAll = readFiles;
