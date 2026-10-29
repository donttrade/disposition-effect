// pgr.js — PGR / PLR counts with partial coverage, computed in the browser for the
// paid report (only these four counts and a percentage are ever sent).
//
// Odean (1998) counts, on every day with a sale, each still-open position as a
// paper gain or a paper loss. That needs a price for every open position on every
// sell day, which trade files don't carry. So a position is marked only when its
// symbol traded that same day (the last execution price that day); unmarked
// position-days lower coverage_pct. Mirrors pgr_plr_counts() in engine_ref.py.

import { chronoOrder } from './trades.js?v=44126a74';

const UNIT = 1e8;
const DAY_MS = 86400000;
const roundHalfAway = (x) => Math.floor(Math.abs(x) + 0.5) * (x >= 0 ? 1 : -1);

export function pgrPlrCounts(executions) {
  const order = chronoOrder(executions);
  const pos = new Map(); // symbol -> [units, avg]
  let rg = 0, rl = 0, pg = 0, pl = 0, marked = 0, total = 0;
  let i = 0;
  while (i < order.length) {
    const day = Math.floor(executions[order[i]].ts / DAY_MS);
    let j = i;
    while (j < order.length && Math.floor(executions[order[j]].ts / DAY_MS) === day) j++;
    const todays = [];
    for (let k = i; k < j; k++) todays.push(executions[order[k]]);
    const mark = new Map();
    for (const e of todays) mark.set(e.symbol, e.price);
    const sold = new Set();
    for (const e of todays) {
      const sym = e.symbol;
      const s = e.side === 'buy' ? 1 : -1;
      const q = roundHalfAway(e.qty * UNIT);
      if (q === 0) continue;
      let [units, avg] = pos.has(sym) ? pos.get(sym) : [0, 0];
      if (units === 0 || (units > 0) === (s > 0)) {
        const nu = units + s * q;
        avg = (avg * Math.abs(units) + e.price * q) / Math.abs(nu);
        pos.set(sym, [nu, avg]);
        continue;
      }
      const diff = (e.price - avg) * (units > 0 ? 1 : -1);
      if (diff > 0) rg++; else if (diff < 0) rl++;
      sold.add(sym);
      const close = Math.min(q, Math.abs(units));
      const rem = q - close;
      units = units + s * close;
      if (units === 0 && rem) pos.set(sym, [s * rem, e.price]);
      else if (units === 0) pos.set(sym, [0, 0]);
      else pos.set(sym, [units, avg]);
    }
    if (sold.size) {
      const syms = [...pos.keys()].sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
      for (const sym of syms) {
        const [units, avg] = pos.get(sym);
        if (units === 0 || sold.has(sym)) continue;
        total++;
        if (mark.has(sym)) {
          marked++;
          const diff = (mark.get(sym) - avg) * (units > 0 ? 1 : -1);
          if (diff > 0) pg++; else if (diff < 0) pl++;
        }
      }
    }
    i = j;
  }
  return { rg, pg, rl, pl, coverage_pct: total ? (100 * marked) / total : null };
}
