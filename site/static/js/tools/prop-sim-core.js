// prop-sim-core.js — the prop-firm challenge simulation. Pure: no DOM, no I/O, so the
// Web Worker runs it and tests can check it against a hand calculation and a Python
// mirror (tests/test_tool_prop_sim.py).
//
// One run = one simulated challenge, starting at equity 0 (all amounts relative to the
// starting balance, in the file's money unit):
//   for each trading day, up to time_limit days:
//     file mode   → draw one whole past trading day at random (with replacement) and
//                   replay its trades in their original order. Keeping days whole keeps
//                   the within-day bunching of losses that daily loss limits react to.
//     manual mode → trades_per_day trades, each a win (+avg_win) with probability
//                   win_rate, else a loss (−avg_loss).
//     after EVERY trade: bust if the day's loss reaches daily_loss (equity <= day start −
//                   daily_loss), or if equity reaches the max-loss floor (equity <= floor).
//     at the END of the day: trailing mode raises the floor to (highest end-of-day
//                   equity − max_loss); then pass if equity >= target and the run has
//                   traded at least min_days days.
//   no pass and no bust after time_limit days → time-out.
// "Reaching" a limit counts as a breach (<=), so a loss exactly equal to the limit busts.
// Closed-trade granularity: what happens inside a trade (open P&L) is not in the file.
//
// PRNG: mulberry32(seed), the same generator as the noise checks. Draw order per run is
// fixed (file mode: one draw per day; manual mode: one draw per trade), so a seed gives
// the same result in every browser.

import { mulberry32 } from '../engine/noise.js';

export const RUNS = 10000;
export const DEFAULT_SEED = 20261022;
export const STREAK_MIN = 2; // a bust "after 2 or more losses in a row"

export function simulate(p) {
  const runs = p.runs || RUNS;
  const rand = mulberry32(p.seed === undefined ? DEFAULT_SEED : p.seed);
  const r = p.rules;
  const out = { runs, pass: 0, bust: 0, timeout: 0, bust_daily: 0, bust_max: 0, bust_after_streak: 0,
    pass_days: [], mode: p.mode };
  for (let k = 0; k < runs; k++) {
    let eq = 0, peakEod = 0, floor = -r.max_loss, lossRun = 0, outcome = 'timeout', days = 0;
    run: for (let d = 1; d <= r.time_limit; d++) {
      const dayStart = eq;
      if (p.mode === 'file') {
        const day = p.days[Math.floor(rand() * p.days.length)];
        for (let i = 0; i < day.length; i++) {
          const before = lossRun;
          eq += day[i];
          lossRun = day[i] < 0 ? lossRun + 1 : 0;
          const why = breach(eq, dayStart, floor, r);
          if (why) { outcome = 'bust'; record(out, why, before); break run; }
        }
      } else {
        for (let i = 0; i < p.trades_per_day; i++) {
          const before = lossRun;
          const pnl = rand() < p.win_rate ? p.avg_win : -p.avg_loss;
          eq += pnl;
          lossRun = pnl < 0 ? lossRun + 1 : 0;
          const why = breach(eq, dayStart, floor, r);
          if (why) { outcome = 'bust'; record(out, why, before); break run; }
        }
      }
      days = d;
      if (r.trailing) {
        if (eq > peakEod) peakEod = eq;
        floor = peakEod - r.max_loss;
      }
      if (eq >= r.target && days >= r.min_days) { outcome = 'pass'; out.pass_days.push(days); break; }
    }
    out[outcome]++;
  }
  out.pass_days.sort((a, b) => a - b);
  const n = out.pass_days.length;
  out.median_pass_days = n ? (n % 2 ? out.pass_days[(n - 1) / 2] : (out.pass_days[n / 2 - 1] + out.pass_days[n / 2]) / 2) : null;
  delete out.pass_days;
  return out;
}

function breach(eq, dayStart, floor, r) {
  if (r.daily_loss !== null && eq <= dayStart - r.daily_loss) return 'daily';
  if (eq <= floor) return 'max';
  return null;
}

function record(out, why, lossesBefore) {
  if (why === 'daily') out.bust_daily++; else out.bust_max++;
  if (lossesBefore >= STREAK_MIN) out.bust_after_streak++;
}

// Trades → trading days: realised results grouped by the calendar day each trade closed
// (file time, naive UTC), in closing order. Only the numbers leave this function.
export function tradingDays(trades) {
  const days = [];
  let key = null;
  for (const t of trades) {
    const k = Math.floor(t.close_ts / 86400000);
    if (k !== key) { days.push([]); key = k; }
    days[days.length - 1].push(t.pnl);
  }
  return days;
}
