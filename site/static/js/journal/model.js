// journal/model.js: the journal's pure functions (ARCHITECT-V3 §d.5): days, the month grid, filters, group
// tables, the CSV export. No DOM and no storage, so the harness and the tests call them directly.
//
// Engine timestamps are naive UTC (the file's wall clock read as UTC), so the UTC getters give back the
// time written in the file in every browser time zone; a day is the CLOSE date (D10, J14). Open
// positions never reach the journal (the engine keeps closed trades only).

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const WD_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];

const pad = (n) => String(n).padStart(2, '0');
export const dayKey = (ts) => new Date(ts).toISOString().slice(0, 10);
export const monthKey = (ts) => new Date(ts).toISOString().slice(0, 7);
export function fmtTs(ts) {
  if (typeof ts !== 'number' || !Number.isFinite(ts)) return '—';
  const s = new Date(ts).toISOString();
  return s.slice(0, 10) + ' ' + s.slice(11, 16);
}
// "2026-08-14" → Date.UTC of that day; weekday 0 = Monday.
export const dayTs = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
export const weekday = (d) => (new Date(dayTs(d)).getUTCDay() + 6) % 7;
export function addDays(d, n) { return dayKey(dayTs(d) + n * 86400000); }
export function addMonths(m, n) {
  const y = +m.slice(0, 4), mo = +m.slice(5, 7) - 1 + n;
  const yy = y + Math.floor(mo / 12), mm = ((mo % 12) + 12) % 12;
  return `${yy}-${pad(mm + 1)}`;
}
export const monthName = (m) => `${MONTHS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;
export function longDay(d) {
  return `${WEEKDAYS[weekday(d)]} ${+d.slice(8, 10)} ${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
}
export function weekStart(d) { return addDays(d, -weekday(d)); }

// date → {date, net, n, wins, losses, trades[]} for the trades given (already filtered), by close date.
export function dayTotals(trades) {
  const m = new Map();
  for (const t of trades) {
    const d = dayKey(t.close_ts);
    let x = m.get(d);
    if (!x) { x = { date: d, net: 0, n: 0, wins: 0, losses: 0, trades: [] }; m.set(d, x); }
    x.net += t.pnl;
    x.n++;
    if (t.pnl > 0) x.wins++; else if (t.pnl < 0) x.losses++;
    x.trades.push(t);
  }
  return m;
}

// The colour step (1-3) of a day's |net| against the 90th percentile of |net| over all days given.
export function p90(days) {
  const v = [...days].map((x) => Math.abs(x.net)).filter((x) => x > 0).sort((a, b) => a - b);
  if (!v.length) return 0;
  return v[Math.min(v.length - 1, Math.floor(0.9 * (v.length - 1)))];
}
export function step(net, ref) {
  if (!net || !ref) return net ? 3 : 0;
  const r = Math.abs(net) / ref;
  return r >= 2 / 3 ? 3 : r >= 1 / 3 ? 2 : 1;
}

// The month grid: weeks (Monday first) of {date, inMonth}; 4 to 6 rows.
export function monthGrid(m) {
  const first = m + '-01';
  let d = weekStart(first);
  const weeks = [];
  do {
    const w = [];
    for (let i = 0; i < 7; i++) { w.push({ date: d, inMonth: d.slice(0, 7) === m }); d = addDays(d, 1); }
    weeks.push(w);
  } while (d.slice(0, 7) === m);
  return weeks;
}

// Month summary from dayTotals: net, trading days, green/red days, largest gain and loss days.
export function monthSummary(days, m) {
  const ds = [...days.values()].filter((x) => x.date.slice(0, 7) === m);
  let net = 0, n = 0, green = 0, red = 0, best = null, worst = null;
  for (const x of ds) {
    net += x.net; n += x.n;
    if (x.net > 0) { green++; if (!best || x.net > best.net) best = x; }
    if (x.net < 0) { red++; if (!worst || x.net < worst.net) worst = x; }
  }
  return { net, trades: n, days: ds.length, green, red, best, worst };
}

// ------------------------------------------------------------------ filters (§d.5, J23)
export const EMPTY_FILTER = Object.freeze({ from: null, to: null, symbol: '', side: '', setup: '', tag: '', mistake: '',
  result: '', note: '' });
// The date part counts as one filter; each other field set counts one.
export function activeCount(f) {
  let n = (f.from || f.to) ? 1 : 0;
  for (const k of ['symbol', 'side', 'setup', 'tag', 'mistake', 'result', 'note']) if (f[k]) n++;
  return n;
}
// trades: with account_id; notes: Map k → note. from/to: 'YYYY-MM-DD' inclusive, on the close date.
// dates: false leaves the date range out (the calendar moves through months itself).
export function applyFilter(trades, f, notes, dates = true) {
  const sym = (f.symbol || '').trim().toUpperCase();
  return trades.filter((t) => {
    if (dates && (f.from || f.to)) {
      const d = dayKey(t.close_ts);
      if (f.from && d < f.from) return false;
      if (f.to && d > f.to) return false;
    }
    if (sym && String(t.symbol).toUpperCase() !== sym) return false;
    if (f.side && t.dir !== f.side) return false;
    if (f.result === 'win' && !(t.pnl > 0)) return false;
    if (f.result === 'loss' && !(t.pnl < 0)) return false;
    if (f.result === 'even' && t.pnl !== 0) return false;
    const n = notes.get(t.k);
    if (f.setup && (!n || n.setup !== f.setup)) return false;
    if (f.tag && (!n || !(n.tags || []).includes(f.tag))) return false;
    if (f.mistake && (!n || !(n.mistakes || []).includes(f.mistake))) return false;
    if (f.note === 'yes' && !(n && n.note)) return false;
    if (f.note === 'no' && n && n.note) return false;
    return true;
  });
}

// Date presets relative to `today` ('YYYY-MM-DD').
export function preset(name, today) {
  const m = today.slice(0, 7);
  if (name === 'this-month') return { from: m + '-01', to: addDays(addMonths(m, 1) + '-01', -1) };
  if (name === 'last-month') { const p = addMonths(m, -1); return { from: p + '-01', to: addDays(m + '-01', -1) }; }
  if (name === 'this-year') return { from: today.slice(0, 4) + '-01-01', to: today.slice(0, 4) + '-12-31' };
  return { from: null, to: null };
}

// ------------------------------------------------------------------ group tables (§d.5 Stats, d.7)
// kind: 'setup' | 'tag' | 'mistake' | 'symbol'. Rows A–Z by name (J25: never by profit by default).
export function groups(trades, notes, kind) {
  const m = new Map();
  const add = (name, t) => {
    let g = m.get(name);
    if (!g) { g = { name, n: 0, net: 0, wins: 0, losses: 0 }; m.set(name, g); }
    g.n++; g.net += t.pnl;
    if (t.pnl > 0) g.wins++; else if (t.pnl < 0) g.losses++;
  };
  for (const t of trades) {
    if (kind === 'symbol') { add(t.symbol, t); continue; }
    const n = notes.get(t.k);
    if (!n) continue;
    if (kind === 'setup') { if (n.setup) add(n.setup, t); continue; }
    for (const v of new Set((kind === 'tag' ? n.tags : n.mistakes) || [])) add(v, t);
  }
  return [...m.values()].map((g) => ({ ...g, win_rate: (g.wins + g.losses) ? g.wins / (g.wins + g.losses) : null,
    avg: g.n ? g.net / g.n : null })).sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' }) || (a.name < b.name ? -1 : 1));
}

// ------------------------------------------------------------------ CSV export (§d.6)
// One row per trade, UTF-8 with a BOM for Excel. The first columns are the round-trip layout the engine
// reads back (Open Time, Close Time, Symbol, Direction, Volume, Open Price, Close Price, Fees, Currency),
// so an export re-imports through the generic round-trip reader (J30); the rest are the journal's own.
const CSV_HEAD = ['Open Time', 'Close Time', 'Symbol', 'Direction', 'Volume', 'Open Price', 'Close Price', 'Fees',
  'Currency', 'Net P&L', 'Gross P&L', 'Result unit', 'Account', 'Setup', 'Tags', 'Mistakes', 'Note'];
const ISO3 = /^[A-Z]{3}$/;
// txt: a text column (symbol, account, setup, tags, mistakes, note), where a leading = + - @ gets a ' so a
// spreadsheet never runs the cell as a formula. Number columns are written as numbers.
function cell(v, txt = false) {
  let s = v === null || v === undefined ? '' : String(v);
  if (txt && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const csvTime = (ts) => new Date(ts).toISOString().slice(0, 19).replace('T', ' ');
const num = (x) => (typeof x === 'number' && Number.isFinite(x) ? String(x) : '');
export function toCsv(trades, notes, accounts) {
  const names = new Map(accounts.map((a) => [a.id, a.name]));
  const lines = [CSV_HEAD.map(cell).join(',')];
  for (const t of trades) {
    const n = notes.get(t.k) || {};
    const row = [csvTime(t.open_ts), csvTime(t.close_ts), t.symbol, t.dir === 'long' ? 'Long' : 'Short', num(t.qty),
      num(t.entry), num(t.exit), num(t.fees), ISO3.test(t.pnl_unit || '') ? t.pnl_unit : '', num(t.pnl), num(t.pnl_gross),
      t.pnl_unit || '', names.get(t.account_id) || '', n.setup || '', (n.tags || []).join(';'),
      (n.mistakes || []).join(';'), n.note || ''];
    lines.push(row.map((v, i) => cell(v, i === 2 || i >= 12)).join(','));
  }
  return '﻿' + lines.join('\r\n') + '\r\n';
}
export const csvName = (now = new Date()) => `donttrade-journal-trades-${now.toISOString().slice(0, 10)}.csv`;
