// heatmap-core.js — the counting behind /tools/trading-heatmap/. Pure functions, no DOM, so the
// tests import this module directly.
//
//  * Each closed trade goes in the cell of the weekday and hour it OPENED. The open time is
//    close_ts − hold_s × 1000 (the worker sends close time and hold time; hold_s is whole seconds,
//    so the open time is exact for files with whole-second times, which every supported format has).
//  * Engine timestamps are naive UTC: the wall-clock time written in the file. shiftHours moves
//    every time by a whole number of hours (an MT5 report is in the broker's server time), and the
//    page shows the first and last open times after the shift so the visitor can check them.
//  * block = 1, 2, 3 or 4 hours per column (2 puts more trades in each cell).
//  * Per cell: trades, total result, average result, win rate (break-even trades left out, as on
//    /tools/trade-stats/). Descriptive only: no cell is tested, ranked or called a pattern.

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
export const MIN_CELL = 30; // the teaser names a cell only when it holds at least this many trades

const HOUR_MS = 3600000;

function blank() { return { n: 0, total: 0, wins: 0, losses: 0 }; }
function add(c, p) { c.n++; c.total += p; if (p > 0) c.wins++; else if (p < 0) c.losses++; }
function done(c) {
  return { ...c, avg: c.n ? c.total / c.n : null, win_rate: c.wins + c.losses ? c.wins / (c.wins + c.losses) : null };
}

const pad = (h) => String(h).padStart(2, '0');
export function blockLabel(b, block) {
  return `${pad(b * block)}:00–${pad((b + 1) * block === 24 ? 24 : (b + 1) * block)}:00`;
}

export function heatmap(trades, { shiftHours = 0, block = 1 } = {}) {
  if (![1, 2, 3, 4].includes(block)) throw new Error('block must be 1, 2, 3 or 4 hours');
  const nb = 24 / block;
  const grid = Array.from({ length: 7 }, () => Array.from({ length: nb }, blank));
  const byDay = Array.from({ length: 7 }, blank);
  const byBlock = Array.from({ length: nb }, blank);
  let first = null, last = null;
  for (const t of trades) {
    const open = t.close_ts - t.hold_s * 1000 + shiftHours * HOUR_MS;
    const d = new Date(open);
    const wd = (d.getUTCDay() + 6) % 7;          // Monday = 0 … Sunday = 6
    const b = Math.floor(d.getUTCHours() / block);
    add(grid[wd][b], t.pnl);
    add(byDay[wd], t.pnl);
    add(byBlock[b], t.pnl);
    if (first === null || open < first) first = open;
    if (last === null || open > last) last = open;
  }
  const cells = [];
  for (let wd = 0; wd < 7; wd++) for (let b = 0; b < nb; b++) {
    if (grid[wd][b].n) cells.push({ wd, b, label: `${WEEKDAYS[wd]} ${blockLabel(b, block)}`, ...done(grid[wd][b]) });
  }
  // Lowest total among the cells with at least MIN_CELL trades (first in weekday, then hour order).
  let lowest = null;
  for (const c of cells) if (c.n >= MIN_CELL && (lowest === null || c.total < lowest.total)) lowest = c;
  const maxAbs = cells.reduce((m, c) => Math.max(m, Math.abs(c.total)), 0);
  return {
    n: trades.length, block, nb, shiftHours,
    grid: grid.map((row) => row.map(done)),
    byDay: byDay.map(done), byBlock: byBlock.map(done),
    cells, maxAbs, lowest,
    weekend: byDay[5].n + byDay[6].n > 0,
    n_small: cells.filter((c) => c.n < MIN_CELL).length,
    first_open: first, last_open: last,
  };
}

// Shading level of a cell total: 0 (zero), ±1…±4 by its size against the largest cell total.
export function level(total, maxAbs) {
  if (!total || !maxAbs) return 0;
  const k = Math.max(1, Math.ceil((4 * Math.abs(total)) / maxAbs));
  return total > 0 ? Math.min(k, 4) : -Math.min(k, 4);
}
