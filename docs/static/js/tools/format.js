// format.js — display helpers shared by the free tools. Pure functions, no DOM state.
//
// Every formatter returns "—" for a missing value, so a page can never print NaN,
// Infinity or undefined (the plan's DOM scan checks this).

export const MINUS = '−'; // U+2212, so negative numbers read as minus signs, not hyphens
export const DASH = '—';

const finite = (x) => typeof x === 'number' && Number.isFinite(x);

function grouped(n, dp) {
  const [i, d] = Math.abs(n).toFixed(dp).split('.');
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (d ? '.' + d : '');
}

// The unit comes from the engine's pnl_unit: an ISO code, "points", "account" (MetaTrader
// deposit currency, which lives in the header block we never read) or "base" (IBKR FX).
export function money(n, unit, { sign = true } = {}) {
  if (!finite(n)) return DASH;
  const s = n < 0 ? MINUS : (n > 0 && sign ? '+' : '');
  if (unit === 'USD') return `${s}$${grouped(n, 2)}`;
  if (unit === 'points') return `${s}${grouped(n, 2)} pts`;
  if (unit === 'account') return `${s}${grouped(n, 2)}`;
  if (unit === 'base') return `${s}${grouped(n, 2)}`;
  return `${s}${grouped(n, 2)} ${unit || ''}`.trim();
}

// What the money unit means, said once per page instead of on every number.
export function unitNote(unit) {
  if (unit === 'USD') return 'Amounts are in US dollars.';
  if (unit === 'points') return 'Amounts are in price points (the file has no currency or contract size).';
  if (unit === 'account') return 'Amounts are in your account currency, as in your MetaTrader report.';
  if (unit === 'base') return 'Amounts are in your base currency, converted with the FX rate on each row.';
  return unit ? `Amounts are in ${unit}.` : '';
}

export function plain(n, dp = 2) {
  return finite(n) ? (n < 0 ? MINUS : '') + grouped(n, dp) : DASH;
}

export function pct(x, dp = 1) {
  return finite(x) ? (x < 0 ? MINUS : '') + (100 * Math.abs(x)).toFixed(dp) + '%' : DASH;
}

export function ratio(x, dp = 2) {
  return finite(x) ? x.toFixed(dp) + '×' : DASH;
}

export function duration(s) {
  if (!finite(s)) return DASH;
  s = Math.round(s);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

// Engine timestamps are naive UTC (wall-clock time read as UTC), so UTC getters give
// back exactly the time written in the file, in every browser time zone.
export function day(ts) {
  return finite(ts) ? new Date(ts).toISOString().slice(0, 10) : DASH;
}

export function intText(n) {
  return finite(n) ? grouped(n, 0) : DASH;
}

// Small DOM helper: el('td', {class: 'num', text: '1.0'}, child, ...)
export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}

export function signClass(n) {
  return finite(n) ? (n > 0 ? 'gain' : n < 0 ? 'loss' : null) : null;
}
