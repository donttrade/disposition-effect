// tools/days.js: a trade file's results by calendar day, for every page that shows days (the journal's
// P&L calendar, the shareable card). One function, so a day total is the same number everywhere
// (ARCHITECT-BRAND §4.8; journal/model.js re-exports it).
//
// Engine timestamps are naive UTC (the file's wall clock read as UTC), so the UTC getters give back the
// time written in the file in every browser time zone. A trade belongs to the day it CLOSED (V3 D10, J14).
// Open positions never get here: the engine keeps closed trades only. Pure: no DOM, no storage.

export const dayKey = (ts) => new Date(ts).toISOString().slice(0, 10);

// trades (already filtered) → Map date → {date, net, n, wins, losses, trades[]}, in the order first seen.
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
