// stats.js — FreeStats on closed trades (close-time order). Mirrors free_stats()
// in tests/reference/engine_ref.py operation for operation.
//
// Never produces NaN or Infinity: a ratio with nothing to divide by is null, and
// the profit factor with no losing trades is the words "no losing trades".

import { median } from './noise.js?v=d0f6a787';

export const NO_LOSSES = 'no losing trades';

function split(trades, dir) {
  let n = 0, w = 0, l = 0, pnl = 0;
  for (const t of trades) {
    if (t.dir !== dir) continue;
    n++;
    pnl += t.pnl;
    if (t.pnl > 0) w++; else if (t.pnl < 0) l++;
  }
  return { n, wins: w, losses: l, win_rate: (w + l) ? w / (w + l) : null, pnl };
}

export function freeStats(trades, startingBalance = null) {
  const n = trades.length;
  let wins = 0, losses = 0, scratch = 0, gp = 0, gl = 0, total = 0;
  let largestWin = null, largestLoss = null;
  for (const t of trades) {
    const p = t.pnl;
    total += p;
    if (p > 0) { wins++; gp += p; if (largestWin === null || p > largestWin) largestWin = p; }
    else if (p < 0) { losses++; gl += p; if (largestLoss === null || p < largestLoss) largestLoss = p; }
    else scratch++;
  }
  // Streaks: a scratch trade ends both kinds; the first longest run is kept.
  let bw = [0, 0], bl = [0, 0], cw = [0, 0], cl = [0, 0];
  for (const t of trades) {
    const p = t.pnl;
    if (p > 0) { cw = [cw[0] + 1, cw[1] + p]; cl = [0, 0]; if (cw[0] > bw[0]) bw = cw.slice(); }
    else if (p < 0) { cl = [cl[0] + 1, cl[1] + p]; cw = [0, 0]; if (cl[0] > bl[0]) bl = cl.slice(); }
    else { cw = [0, 0]; cl = [0, 0]; }
  }
  // Drawdown on the closed-trade equity curve; % only when a starting balance is given.
  let eq = 0, peak = 0, maxdd = 0;
  const usePct = startingBalance !== null && startingBalance > 0;
  let maxddPct = usePct ? 0 : null;
  for (const t of trades) {
    eq += t.pnl;
    if (eq > peak) peak = eq;
    const dd = peak - eq;
    if (dd > maxdd) maxdd = dd;
    if (usePct) {
      const top = startingBalance + peak;
      const pct = top > 0 ? (top - (startingBalance + eq)) / top : 0;
      if (pct > maxddPct) maxddPct = pct;
    }
  }
  const hw = median(trades.filter((t) => t.pnl > 0).map((t) => t.hold_s));
  const hl = median(trades.filter((t) => t.pnl < 0).map((t) => t.hold_s));
  return {
    n, wins, losses, scratch,
    win_rate: (wins + losses) ? wins / (wins + losses) : null,
    gross_profit: gp, gross_loss: gl,
    profit_factor: losses ? gp / -gl : NO_LOSSES,
    net_pnl: total,
    expectancy: n ? total / n : null,
    avg_win: wins ? gp / wins : null,
    avg_loss: losses ? gl / losses : null,
    largest_win: largestWin, largest_loss: largestLoss,
    max_consec_wins: { n: bw[0], pnl: bw[1] },
    max_consec_losses: { n: bl[0], pnl: bl[1] },
    max_drawdown_abs: maxdd,
    max_drawdown_pct: maxddPct,
    long: split(trades, 'long'), short: split(trades, 'short'),
    hold_median_win_s: hw, hold_median_loss_s: hl,
    hold_ratio: (hw !== null && hl !== null && hw > 0) ? hl / hw : null,
  };
}

// Equity and drawdown points for the chart: one point per closed trade.
export function equityCurve(trades) {
  let eq = 0, peak = 0;
  return trades.map((t) => {
    eq += t.pnl;
    if (eq > peak) peak = eq;
    return { ts: t.close_ts, equity: eq, drawdown: eq - peak };
  });
}
