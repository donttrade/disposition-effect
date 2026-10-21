// drawdown-core.js — the arithmetic behind /tools/drawdown-calculator/. Pure functions, no DOM,
// so the tests import this module directly.
//
// Definitions (the page's "How it is counted" section says the same in words):
//  * Equity is the running sum of closed-trade results, starting at 0 before the first trade.
//  * A drawdown starts when equity falls below its running high (the high can be the start, 0)
//    and ends on the first trade that brings equity back to that high or above ("recovered").
//    Its depth is the largest fall from that high before it ended. A drawdown still open at the
//    end of the file is the current drawdown.
//  * "Trades in the drawdown" counts the trades after the high, up to and including the trade
//    that recovered it (or the last trade in the file, if it has not recovered).
//  * Calendar days run from the close of the trade that set the high (the first trade's open,
//    when the high is the start) to the close of the recovering trade (or the last trade).
//  * With a starting balance B, a drawdown from high H (equity) of depth D is D ÷ (B + H) as a
//    percentage, the same definition as the trade-stats page (engine/stats.js), and the gain
//    that recovers it is D ÷ (B + H − D).
// Trades: [{pnl, close_ts, hold_s}] in close-time order (the engine's order). Timestamps are the
// engine's naive-UTC milliseconds; open time = close_ts − hold_s × 1000.

export const DAY_MS = 86400000;
export const LOSS_WINDOW_S = 15 * 60;  // "opened within 15 minutes of a loss" (the habit report's re-entry window)

// Gain that takes an account back to its high after a fall of d (a fraction, 0 ≤ d < 1).
export function recoveryGain(d) {
  if (!(d >= 0) || d >= 1) return null;
  return d / (1 - d);
}

const openTs = (t) => t.close_ts - t.hold_s * 1000;
const dayIndex = (ts) => Math.floor(ts / DAY_MS);

export function drawdowns(trades, startingBalance = null) {
  const n = trades.length;
  const bal = startingBalance !== null && startingBalance > 0 ? startingBalance : null;
  const episodes = [];
  let eq = 0, peak = 0, peakI = -1, cur = null;
  const startTs = (i) => (i < 0 ? openTs(trades[0]) : trades[i].close_ts);
  const close = (ep, endI, recovered) => {
    ep.end_i = endI;
    ep.recovered = recovered;
    ep.trades = endI - ep.peak_i;
    ep.start_ts = startTs(ep.peak_i);
    ep.end_ts = trades[endI].close_ts;
    ep.days = dayIndex(ep.end_ts) - dayIndex(ep.start_ts);
    ep.trades_to_trough = ep.trough_i - ep.peak_i;
    if (bal !== null) {
      const top = bal + ep.peak;
      ep.depth_pct = top > 0 ? ep.depth / top : null;
      ep.recovery_gain = top - ep.depth > 0 ? ep.depth / (top - ep.depth) : null;
    } else {
      ep.depth_pct = null;
      ep.recovery_gain = null;
    }
    episodes.push(ep);
  };
  const curve = new Array(n);
  for (let i = 0; i < n; i++) {
    eq += trades[i].pnl;
    if (eq >= peak) {
      if (cur) { close(cur, i, true); cur = null; }
      peak = eq;
      peakI = i;
    } else if (!cur) {
      cur = { peak_i: peakI, peak, trough_i: i, depth: peak - eq };
    } else if (peak - eq > cur.depth) {
      cur.trough_i = i;
      cur.depth = peak - eq;
    }
    curve[i] = { equity: eq, drawdown: eq - peak, ts: trades[i].close_ts };
  }
  if (cur) close(cur, n - 1, false);

  const pick = (key) => episodes.reduce((best, e) => (best === null || e[key] > best[key] ? e : best), null);
  const deepest = pick('depth');
  const current = episodes.length && !episodes[episodes.length - 1].recovered ? episodes[episodes.length - 1] : null;
  const recovered = episodes.filter((e) => e.recovered);
  return {
    n,
    episodes,
    curve,
    deepest,                                     // the first deepest, by money
    max_abs: deepest ? deepest.depth : 0,
    max_pct: bal === null ? null : episodes.reduce((m, e) => Math.max(m, e.depth_pct ?? 0), 0),
    longest_trades: pick('trades'),              // the first longest, in trades
    longest_days: pick('days'),
    current,
    n_recovered: recovered.length,
    median_recovery_trades: median(recovered.map((e) => e.trades)),
    final_equity: eq,
    high: peak,
  };
}

function median(xs) {
  if (!xs.length) return null;
  const s = xs.slice().sort((a, b) => a - b);
  const k = s.length >> 1;
  return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2;
}

// How many of the trades in episode `ep` were opened within LOSS_WINDOW_S after an earlier losing
// trade closed (the latest loss that closed at or before the open). Returns {n, hits}.
export function openedAfterLoss(trades, ep) {
  const lossClose = [], lossIdx = [];
  trades.forEach((t, i) => { if (t.pnl < 0) { lossClose.push(t.close_ts); lossIdx.push(i); } });  // ascending
  let hits = 0, count = 0;
  for (let i = ep.peak_i + 1; i <= ep.end_i; i++) {
    count++;
    const o = openTs(trades[i]);
    let lo = 0, hi = lossClose.length - 1, j = -1;          // the last loss close <= o
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (lossClose[mid] <= o) { j = mid; lo = mid + 1; } else hi = mid - 1;
    }
    while (j >= 0 && lossIdx[j] === i) j--;                  // a zero-length loss is not its own "earlier loss"
    if (j >= 0 && o - lossClose[j] <= LOSS_WINDOW_S * 1000) hits++;
  }
  return { n: count, hits };
}
