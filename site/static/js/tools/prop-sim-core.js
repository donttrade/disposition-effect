// prop-sim-core.js — the prop-firm challenge simulation (the Challenge Readiness Check engine).
// Pure: no DOM, no I/O, so the Web Worker runs it and tests can check it against a hand calculation
// and the Python mirror (tests/reference/readiness_ref.py; the legacy mirror is simulate_py in
// tests/test_tool_prop_sim.py).
//
// One run = one simulated challenge, starting at equity 0 (all amounts relative to the starting
// balance, in the file's money unit):
//   for each trading day, up to time_limit days (null: no limit, stopped at NO_LIMIT_CAP days):
//     file mode     → draw one whole past trading day at random (with replacement) and replay its
//                     trades in their original order. Keeping days whole keeps the within-day
//                     bunching of losses that daily loss limits react to.
//     sequence mode → the file's real days once, in their real order, no random draw (one run).
//     manual mode   → trades_per_day trades, each a win (+avg_win) with probability win_rate,
//                     else a loss (−avg_loss).
//     after EVERY trade: bust if the day's loss reaches daily_loss (equity <= day start −
//                     daily_loss), or if equity reaches the max-loss floor (equity <= floor);
//                     daily is checked first. drawdown 'trailing_trade' then raises the floor to
//                     (highest closed-trade equity − max_loss).
//     at the END of the day: drawdown 'trailing_eod' raises the floor to (highest end-of-day
//                     equity − max_loss); trail_stop_at caps the floor (Topstep: 0 = it locks at
//                     the starting balance). Then pass if equity >= target, the run has enough
//                     days (min_days_kind 'trading': days traded; 'profitable': days whose P&L is
//                     above zero and at least profitable_day_min), and, with a consistency share c,
//                     the best single day's P&L is at most c × equity. Reaching the target while a
//                     day count or the consistency share is short is not a bust: the run goes on
//                     (counted once per run in held_min_days / held_consistency).
//     target_check 'intraday': the same pass test also runs after every trade, so a run passes the
//                     moment its closed-trade balance reaches the target (the rest of that day is not
//                     replayed); 'eod' (the default, as before) tests at the end of the day only.
//     count_day_if 'nonzero': a day counts toward min_days only with a trade whose result is not
//                     zero; 'any' (the default) counts every traded day.
//   no pass and no bust → time-out (sequence mode: 'end' when the file's days run out first).
// Every input is checked (normRules, checkInput): NaN, a missing required value, a negative amount
// or an out-of-range count throws an error with the rule it breaks.
// "Reaching" a limit counts as a breach (<=), so a loss exactly equal to the limit busts.
// Closed-trade granularity: what happens inside a trade (open P&L) is not in the file.
//
// The "Try a rule" what-if (rules.personal / p.personal, reset every day, applied to trades as
// replayed; a left-out trade changes nothing):
//   stop_after_losses k   after the k-th losing trade of the day, the rest of the day is left out
//   stop_at_day_loss s    after a trade takes the day to −s × daily_loss or below, the rest of the
//                         day is left out (the crossing trade stays); stop_at_day_loss_amount: the
//                         same with an amount, for rules with no daily limit
//   max_trades n          only the first n trades of the day count
//   cooldown_s m          a trade that opened within m seconds after the close of a taken losing
//                         trade (0 <= open − close <= m) is left out; needs p.open_s / p.close_s
//   after_loss_factor f   the taken trade right after a taken losing trade counts at f × its P&L
// At most two at once.
//
// PRNG: mulberry32. stream 'legacy' (the default, as before 29 Oct): one generator seeded with the
// seed, one draw per day (file) or per trade (manual), so old seeds give the same result. stream
// 'paired': run k has its own generator mulberry32(mix32(seed, k)), so a run draws the same days
// with and without a what-if rule even when a rule changes its length.

import { mulberry32 } from '../engine/noise.js';

export const RUNS = 10000;
export const DEFAULT_SEED = 20261022;
export const STREAK_MIN = 2; // a bust "after 2 or more losses in a row"
export const NO_LIMIT_CAP = 250;
export const METHOD_VERSION = Object.freeze({ legacy: '2026-10-22.prop-sim', paired: '2026-10-29.r1' });
export const DRAWDOWNS = Object.freeze(['static', 'trailing_eod', 'trailing_trade']);
export const PERSONAL_KEYS = Object.freeze(['stop_after_losses', 'stop_at_day_loss', 'stop_at_day_loss_amount',
  'max_trades', 'cooldown_s', 'after_loss_factor']);
export const FACTORS = Object.freeze([0.25, 0.5, 0.75]);
export const MAX_PERSONAL = 2;

// Ranked "Biggest changes on your past days" (§2.7.3): built, switched off until a lawyer has read
// the strings. site.toml [flags] whatif_ranked sets this line in the build (build.py set_ranked_flag);
// the worker passes it to rankRules, and nothing else turns ranking on.
export const WHATIF_RANKED = false;
export const SCREEN_RUNS = 2000;
export const RANK_TOP = 3;
export const RANK_MIN_POINTS = 3;   // the pass share has to rise by 3 points or more
export const RANK_GRID = Object.freeze([
  { stop_after_losses: 1 }, { stop_after_losses: 2 }, { stop_after_losses: 3 },
  { stop_at_day_loss: 0.25 }, { stop_at_day_loss: 0.5 }, { stop_at_day_loss: 0.75 },
  { max_trades: 1 }, { max_trades: 2 }, { max_trades: 3 }, { max_trades: 5 },
  { cooldown_s: 300 }, { cooldown_s: 900 }, { cooldown_s: 1800 },
  { after_loss_factor: 0.5 }, { after_loss_factor: 0.25 },
].map(Object.freeze));
const NEVER_RANKED = 'after_loss_factor'; // a size rule: tried and shown in the grid, never ranked (§2.7.5)

// User-visible strings of the engine (scanned by the wording tests).
export const WHATIF_TEXT = Object.freeze({
  unavailable_dates_only: 'Not available for files with dates but no times.',
  unavailable_no_times: 'Not available without trade times.',
  unavailable_no_daily: 'Not available: these rules have no daily loss limit. Use an amount instead.',
  caveat: "This leaves out or shrinks trades from your past days. It can't know what you would have done instead. Past days, not future ones. Not investment advice.",
  factor_caveat: "This assumes the result scales with size; fees, fills and minimum sizes don't scale exactly.",
  selection_bias: 'These are the best of the rules tried on the same past days, so they look better here than they would on new days.',
});

// Mixes the seed and the run index into one 32-bit seed (murmur3's finaliser).
export function mix32(a, b) {
  let h = (a ^ Math.imul((b + 1) | 0, 0x9e3779b9)) | 0;
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return (h ^ (h >>> 16)) >>> 0;
}

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isWhole = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const fail = (msg) => { throw new Error(msg); };
const opt = (r, k, dflt) => (r[k] === undefined ? dflt : r[k]);

// Checks and fills in the rules. Every value is checked here, not only on the page: NaN, a missing
// required value, a negative amount or an out-of-range count is an error, never a silent result.
export function normRules(r) {
  if (!r || typeof r !== 'object') fail('rules: missing');
  if (!isNum(r.target) || r.target <= 0) fail('rules: target is an amount above zero');
  if (!isNum(r.max_loss) || r.max_loss <= 0) fail('rules: max_loss is an amount above zero');
  if (r.daily_loss === undefined || (r.daily_loss !== null && (!isNum(r.daily_loss) || r.daily_loss <= 0))) {
    fail('rules: daily_loss is an amount above zero, or null for none');
  }
  if (r.time_limit === undefined || (r.time_limit !== null && !isWhole(r.time_limit, 1, 365))) {
    fail('rules: time_limit is a whole number of days from 1 to 365, or null for none');
  }
  if (r.trailing !== undefined && typeof r.trailing !== 'boolean') fail('rules: trailing is true or false');
  const drawdown = r.drawdown === undefined || r.drawdown === null ? (r.trailing ? 'trailing_eod' : 'static') : r.drawdown;
  if (!DRAWDOWNS.includes(drawdown)) fail('rules: drawdown is static, trailing_eod or trailing_trade');
  const stop = opt(r, 'trail_stop_at', null);
  if (stop !== null && (!isNum(stop) || stop < 0)) fail('rules: trail_stop_at is an amount of zero or more, or null');
  const c = opt(r, 'consistency', null);
  if (c !== null && (!isNum(c) || !(c > 0 && c <= 1))) fail('rules: consistency is a share above 0 and at most 1, or null');
  const minDays = opt(r, 'min_days', 0);
  if (!isWhole(minDays, 0, 365)) fail('rules: min_days is a whole number from 0 to 365');
  const kind = opt(r, 'min_days_kind', 'trading');
  if (kind !== 'trading' && kind !== 'profitable') fail('rules: min_days_kind is trading or profitable');
  const profMin = opt(r, 'profitable_day_min', 0);
  if (!isNum(profMin) || profMin < 0) fail('rules: profitable_day_min is an amount of zero or more');
  const countIf = opt(r, 'count_day_if', 'any');
  if (countIf !== 'any' && countIf !== 'nonzero') fail('rules: count_day_if is any or nonzero');
  const targetCheck = opt(r, 'target_check', 'eod');
  if (targetCheck !== 'eod' && targetCheck !== 'intraday') fail('rules: target_check is eod or intraday');
  const noLimit = r.time_limit === null;
  return {
    target: r.target, daily_loss: r.daily_loss, max_loss: r.max_loss, drawdown, trail_stop_at: stop, consistency: c,
    min_days: minDays, min_days_kind: kind, profitable_day_min: profMin, count_day_if: countIf, target_check: targetCheck,
    limit: noLimit ? NO_LIMIT_CAP : r.time_limit, no_limit: noLimit,
  };
}

// The rest of the input: mode, counts, seed and every replayed number.
export function checkInput(p) {
  if (!p || typeof p !== 'object') fail('simulate: missing input');
  if (p.mode !== 'file' && p.mode !== 'sequence' && p.mode !== 'manual') fail('simulate: mode is file, sequence or manual');
  if (p.runs !== undefined && !isWhole(p.runs, 1, 1000000)) fail('simulate: runs is a whole number from 1 to 1,000,000');
  if (p.seed !== undefined && !isWhole(p.seed, 0, 4294967295)) fail('simulate: seed is a whole number from 0 to 4294967295');
  if (p.stream !== undefined && p.stream !== 'legacy' && p.stream !== 'paired') fail('simulate: stream is legacy or paired');
  if (p.mode === 'manual') {
    if (!isNum(p.win_rate) || p.win_rate < 0 || p.win_rate > 1) fail('simulate: win_rate is a share from 0 to 1');
    if (!isNum(p.avg_win) || p.avg_win <= 0) fail('simulate: avg_win is an amount above zero');
    if (!isNum(p.avg_loss) || p.avg_loss <= 0) fail('simulate: avg_loss is an amount above zero');
    if (!isWhole(p.trades_per_day, 1, 50)) fail('simulate: trades_per_day is a whole number from 1 to 50');
    return;
  }
  if (!Array.isArray(p.days) || !p.days.length) fail('simulate: no trading days');
  for (const d of p.days) {
    if (!Array.isArray(d)) fail('simulate: each day is a list of trade results');
    for (const x of d) if (!isNum(x)) fail('simulate: every trade result is a finite number');
  }
}

// Why a what-if rule cannot run on this input (a code), or null. Never runs silently (case W7).
export function personalUnavailable(p, x, rules) {
  if (!x) return null;
  const r = rules || normRules(p.rules);
  if (x.cooldown_s !== undefined && x.cooldown_s !== null) {
    if (p.dates_only) return 'dates_only';
    if (p.mode === 'manual' || !p.open_s || !p.close_s) return 'no_times';
  }
  if (x.stop_at_day_loss !== undefined && x.stop_at_day_loss !== null && r.daily_loss === null) return 'no_daily';
  return null;
}

export function normPersonal(x, r) {
  if (!x) return null;
  const keys = Object.keys(x).filter((k) => x[k] !== undefined && x[k] !== null);
  for (const k of keys) if (!PERSONAL_KEYS.includes(k)) throw new Error(`personal: unknown rule ${k}`);
  if (!keys.length) return null;
  if (keys.length > MAX_PERSONAL) throw new Error(`personal: at most ${MAX_PERSONAL} rules at once`);
  const whole = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  const q = { stopLosses: 0, stopAt: null, maxTrades: 0, cooldown: -1, factor: 1 };
  if (x.stop_after_losses != null) {
    if (!whole(x.stop_after_losses, 1, 10)) throw new Error('personal: stop_after_losses is a whole number from 1 to 10');
    q.stopLosses = x.stop_after_losses;
  }
  if (x.stop_at_day_loss != null) {
    if (!isNum(x.stop_at_day_loss) || !(x.stop_at_day_loss >= 0.1 && x.stop_at_day_loss <= 0.95)) throw new Error('personal: stop_at_day_loss is a share from 0.1 to 0.95');
    if (r.daily_loss === null) throw new Error('personal: stop_at_day_loss needs a daily loss limit');
    q.stopAt = x.stop_at_day_loss * r.daily_loss;
  }
  if (x.stop_at_day_loss_amount != null) {
    if (x.stop_at_day_loss != null) throw new Error('personal: a share or an amount, not both');
    if (!isNum(x.stop_at_day_loss_amount) || x.stop_at_day_loss_amount <= 0) throw new Error('personal: stop_at_day_loss_amount is an amount above zero');
    q.stopAt = x.stop_at_day_loss_amount;
  }
  if (x.max_trades != null) {
    if (!whole(x.max_trades, 1, 50)) throw new Error('personal: max_trades is a whole number from 1 to 50');
    q.maxTrades = x.max_trades;
  }
  if (x.cooldown_s != null) {
    if (!whole(x.cooldown_s, 60, 14400) || x.cooldown_s % 60) throw new Error('personal: cooldown_s is whole minutes from 1 to 240');
    q.cooldown = x.cooldown_s;
  }
  if (x.after_loss_factor != null) {
    if (!FACTORS.includes(x.after_loss_factor)) throw new Error('personal: after_loss_factor is 0.25, 0.5 or 0.75');
    q.factor = x.after_loss_factor;
  }
  return q;
}

export function simulate(p) {
  const seqMode = p.mode === 'sequence';
  const fileMode = p.mode === 'file';
  const manual = p.mode === 'manual';
  checkInput(p);
  const runs = seqMode ? 1 : (p.runs || RUNS);
  const seed = p.seed === undefined ? DEFAULT_SEED : p.seed;
  const stream = seqMode ? 'none' : (p.stream || 'legacy');
  const shared = stream === 'legacy' ? mulberry32(seed) : null;
  const r = normRules(p.rules);
  const why0 = personalUnavailable(p, p.personal, r);
  if (why0) throw new Error(`personal: not available (${why0})`);
  const pers = normPersonal(p.personal, r);
  const days = manual ? null : p.days;
  const nDays = days ? days.length : 0;
  const openS = pers && pers.cooldown >= 0 ? p.open_s : null;
  const closeS = pers && pers.cooldown >= 0 ? p.close_s : null;
  if (openS) {
    const same = (x) => Array.isArray(x) && x.length === nDays && x.every((t, i) => Array.isArray(t) && t.length === days[i].length && t.every(isNum));
    if (!same(openS) || !same(closeS)) fail('simulate: open_s and close_s hold one finite time per trade, day by day');
  }
  const daily = r.daily_loss;
  const maxLoss = r.max_loss;
  const stopAt = r.trail_stop_at;
  const eodTrail = r.drawdown === 'trailing_eod';
  const tradeTrail = r.drawdown === 'trailing_trade';
  const floorOf = (peak) => (stopAt === null || peak - maxLoss < stopAt ? peak - maxLoss : stopAt);
  const profitable = r.min_days_kind === 'profitable';
  const out = { runs, pass: 0, bust: 0, timeout: 0, bust_daily: 0, bust_max: 0, bust_after_streak: 0,
    held_consistency: 0, held_min_days: 0, capped: false, trades_seen: 0, trades_left_out: 0, mode: p.mode,
    stream, method: stream === 'paired' ? METHOD_VERSION.paired : METHOD_VERSION.legacy };
  if (seqMode) out.end = 0;
  // bust positions (source day, trade) and drawn losing days, for "Habits on breach days" (§2.3)
  let offset = null, bustFlat = null, drawnLosing = null;
  if (!manual) {
    offset = new Int32Array(nDays + 1);
    for (let i = 0; i < nDays; i++) offset[i + 1] = offset[i] + days[i].length;
    bustFlat = new Int32Array(offset[nDays]);
    drawnLosing = new Int32Array(nDays);
  }
  const passDays = [];
  const bustDays = [];
  let seen = 0, left = 0;
  let seqTarget = null;
  const seqDayPnl = seqMode ? [] : null;
  const lossCloses = [];
  const target = r.target, minDays = r.min_days, cons = r.consistency, profMin = r.profitable_day_min, limit = r.limit;
  const floor0 = floorOf(0);
  const intraday = r.target_check === 'intraday';
  const countAny = r.count_day_if === 'any';
  const plain = !pers && !intraday && countAny;   // the hot path below applies
  for (let k = 0; k < runs; k++) {
    const rand = stream === 'paired' ? mulberry32(mix32(seed, k)) : shared;
    let eq = 0, peak = 0, floor = floor0, lossRun = 0, outcome = 'timeout', best = -Infinity, prof = 0, tdays = 0;
    let heldC = false, heldM = false, d = 0, bustDay = 0, why = null, bi = -1, bdi = -1, bpnl = 0;
    run: for (d = 1; d <= limit; d++) {
      let di = -1, n, day = null;
      if (fileMode) { di = Math.floor(rand() * nDays); day = days[di]; n = day.length; }
      else if (seqMode) { if (d > nDays) { outcome = 'end'; break; } di = d - 1; day = days[di]; n = day.length; }
      else n = p.trades_per_day;
      const dayStart = eq;
      const dl = daily === null ? -Infinity : dayStart - daily;   // bust when equity <= dl
      let nz = false;   // a taken trade with a non-zero result today (count_day_if 'nonzero')
      if (day && plain) {
        // the plain replay (no what-if rule): the hot path
        for (let i = 0; i < n; i++) {
          const pnl = day[i];
          const before = lossRun;
          eq += pnl;
          lossRun = pnl < 0 ? lossRun + 1 : 0;
          if (eq <= dl || eq <= floor) {
            why = eq <= dl ? 'daily' : 'max';
            if (before >= STREAK_MIN) out.bust_after_streak++;
            seen += i + 1; bi = i; bdi = di; bpnl = eq - dayStart;
            break run;
          }
          if (tradeTrail && eq > peak) { peak = eq; floor = floorOf(peak); }
        }
        seen += n;
      } else {
        let taken = 0, losses = 0, stopped = false, prevLoss = false;
        if (pers) lossCloses.length = 0;
        for (let i = 0; i < n; i++) {
          let pnl = day ? day[i] : (rand() < p.win_rate ? p.avg_win : -p.avg_loss);
          seen++;
          if (pers) {
            if (stopped || (pers.maxTrades && taken >= pers.maxTrades)) { left++; continue; }
            if (openS) {
              // left out when any taken losing trade of the day closed in [open − cooldown, open]
              const o = openS[di][i];
              let skip = false;
              for (let j = 0; j < lossCloses.length && !skip; j++) {
                const c = lossCloses[j];
                if (c <= o && o - c <= pers.cooldown) skip = true;
              }
              if (skip) { left++; continue; }
            }
            if (prevLoss && pers.factor !== 1) pnl *= pers.factor;
          }
          const before = lossRun;
          eq += pnl;
          lossRun = pnl < 0 ? lossRun + 1 : 0;
          if (pnl !== 0) nz = true;
          if (eq <= dl || eq <= floor) {
            why = eq <= dl ? 'daily' : 'max';
            if (before >= STREAK_MIN) out.bust_after_streak++;
            bi = i; bdi = di; bpnl = eq - dayStart;
            break run;
          }
          if (tradeTrail && eq > peak) { peak = eq; floor = floorOf(peak); }
          if (pers) {
            taken++;
            prevLoss = pnl < 0;
            if (prevLoss) { losses++; if (openS) lossCloses.push(closeS[di][i]); }
            if (pers.stopLosses && losses >= pers.stopLosses) stopped = true;
            if (pers.stopAt !== null && eq - dayStart <= -pers.stopAt) stopped = true;
          }
          if (intraday && eq >= target) {
            // target_check 'intraday': the target counts the moment the closed-trade balance reaches it,
            // with today counted as a day so far (the end-of-day check below then passes the run)
            if (seqMode && seqTarget === null) seqTarget = d;
            const cur = eq - dayStart;
            const okM = (profitable ? prof + (cur > 0 && cur >= profMin ? 1 : 0) : tdays + (countAny || nz ? 1 : 0)) >= minDays;
            const okC = cons === null || (cur > best ? cur : best) <= cons * eq;
            if (okM && okC) break;   // passed: the rest of the day is not replayed
            if (!okM) heldM = true;
            if (!okC) heldC = true;
          }
        }
      }
      const dayPnl = eq - dayStart;
      if (drawnLosing && dayPnl < 0) drawnLosing[di]++;
      if (seqMode) seqDayPnl.push(dayPnl);
      if (eodTrail && eq > peak) { peak = eq; floor = floorOf(peak); }
      if (dayPnl > best) best = dayPnl;
      if (dayPnl > 0 && dayPnl >= profMin) prof++;
      if (countAny || nz) tdays++;
      if (eq >= target) {
        if (seqMode && seqTarget === null) seqTarget = d;
        const okM = (profitable ? prof : tdays) >= minDays;
        const okC = cons === null || best <= cons * eq;
        if (okM && okC) { outcome = 'pass'; passDays.push(d); break; }
        if (!okM) heldM = true;
        if (!okC) heldC = true;
      }
    }
    if (why) {
      outcome = 'bust';
      bustDay = d;
      if (why === 'daily') out.bust_daily++; else out.bust_max++;
      if (bustFlat) { bustFlat[offset[bdi] + bi]++; if (bpnl < 0) drawnLosing[bdi]++; }
      if (seqMode) { out.why = why; seqDayPnl.push(bpnl); }
    }
    if (outcome === 'bust') bustDays.push(bustDay);
    if (outcome === 'timeout' && r.no_limit) out.capped = true;
    if (heldC) out.held_consistency++;
    if (heldM) out.held_min_days++;
    out[outcome]++;
    if (seqMode) {
      out.outcome = outcome;
      out.day = outcome === 'pass' ? passDays[0] : outcome === 'bust' ? bustDay : Math.min(d, r.limit, nDays);
      out.target_day = seqTarget;
      out.day_pnl = seqDayPnl;
      if (outcome !== 'bust') out.why = null;
    }
  }
  out.trades_seen = seen;
  out.trades_left_out = left;
  out.median_pass_days = medianSorted(passDays.sort((a, b) => a - b));
  out.median_bust_days = medianSorted(bustDays.sort((a, b) => a - b));
  if (!manual) {
    const bustAt = [];
    for (let di = 0; di < nDays; di++) {
      for (let i = offset[di]; i < offset[di + 1]; i++) if (bustFlat[i]) bustAt.push([di, i - offset[di], bustFlat[i]]);
    }
    out.bust_at = bustAt;
    out.drawn_losing = Array.from(drawnLosing);
  }
  return out;
}

function medianSorted(a) {
  const n = a.length;
  return n ? (n % 2 ? a[(n - 1) / 2] : (a[n / 2 - 1] + a[n / 2]) / 2) : null;
}

// ------------------------------------------------------------------ "Try a rule" (§2.7)
// Before and after on paired streams: the same draws, only the rule differs.
export function whatIf(p, personal) {
  const r = normRules(p.rules);
  const why = personalUnavailable(p, personal, r);
  if (why) return { unavailable: why, message: unavailableText(why) };
  const base = { ...p, stream: 'paired', personal: null };
  const before = simulate(base);
  const after = simulate({ ...base, personal });
  return { before, after, rule: personal, label: ruleLabel(personal) };
}

export function unavailableText(why) {
  return why === 'dates_only' ? WHATIF_TEXT.unavailable_dates_only
    : why === 'no_daily' ? WHATIF_TEXT.unavailable_no_daily : WHATIF_TEXT.unavailable_no_times;
}

const FACTOR_WORDS = { 0.25: 'a quarter of', 0.5: 'half', 0.75: 'three quarters of' };
const count = (n, one, many) => `${n} ${n === 1 ? one : many}`;
// The menu's rule names (§2.7.2), in its fixed order; fmt formats an amount (the page passes money()).
export function ruleLabel(x, fmt = String) {
  if (!x) return '';
  const parts = [];
  if (x.stop_after_losses != null) parts.push(`Stop for the day after ${count(x.stop_after_losses, 'losing trade', 'losing trades')}`);
  if (x.stop_at_day_loss != null) parts.push(`Stop for the day at ${Math.round(x.stop_at_day_loss * 100)}% of the daily loss limit`);
  if (x.stop_at_day_loss_amount != null) parts.push(`Stop for the day at a day loss of ${fmt(x.stop_at_day_loss_amount)}`);
  if (x.max_trades != null) parts.push(`At most ${count(x.max_trades, 'trade', 'trades')} a day`);
  if (x.cooldown_s != null) parts.push(`No new trade for ${count(x.cooldown_s / 60, 'minute', 'minutes')} after a loss`);
  if (x.after_loss_factor != null) parts.push(`Count each trade after a loss at ${FACTOR_WORDS[x.after_loss_factor]} its result`);
  return parts.join(' + ');
}

// ------------------------------------------------------------------ ranked rules (§2.7.3, off)
// Screens every RANK_GRID rule at SCREEN_RUNS paired runs, re-runs the top RANK_TOP (never the size
// rule) at the full count, and keeps those whose pass share rose by RANK_MIN_POINTS or more while the
// bust share did not rise. Returns {enabled: false} unless the caller passes enabled: true.
export function rankRules(p, opts = {}) {
  if (opts.enabled !== true) return { enabled: false };
  const r = normRules(p.rules);
  const runs = p.runs || RUNS;
  const screenRuns = Math.min(SCREEN_RUNS, runs);
  const base = { ...p, stream: 'paired', personal: null };
  const before = simulate(base);
  const beforeS = screenRuns === runs ? before : simulate({ ...base, runs: screenRuns });
  const grid = RANK_GRID.map((rule, idx) => {
    const why = personalUnavailable(p, rule, r);
    if (why) return { idx, rule, unavailable: why };
    const s = simulate({ ...base, personal: rule, runs: screenRuns });
    return { idx, rule, label: ruleLabel(rule), runs: screenRuns, pass: s.pass, bust: s.bust, timeout: s.timeout,
      rise: s.pass - beforeS.pass };
  });
  const tried = grid.filter((g) => !g.unavailable).length;
  const top = grid.filter((g) => !g.unavailable && !(NEVER_RANKED in g.rule))
    .sort((a, b) => (b.rise - a.rise) || (a.idx - b.idx)).slice(0, RANK_TOP);
  const ranked = [];
  for (const g of top) {
    const a = simulate({ ...base, personal: g.rule });
    if (100 * (a.pass - before.pass) >= RANK_MIN_POINTS * runs && a.bust <= before.bust) {
      ranked.push({ idx: g.idx, rule: g.rule, label: g.label, before: { pass: before.pass, bust: before.bust, timeout: before.timeout },
        after: { pass: a.pass, bust: a.bust, timeout: a.timeout }, runs });
    }
  }
  ranked.sort((x, y) => ((y.after.pass - y.before.pass) - (x.after.pass - x.before.pass)) || (x.idx - y.idx));
  return { enabled: true, tried, grid, ranked, before };
}

// ------------------------------------------------------------------ trades → trading days
// Day grouping (§2.2): a file's naive times are read in the file's time zone (fileTz), and a day
// runs from dayStart.hour in dayStart.tz (DST-aware, through Intl). Consecutive trades (close-time
// order) with the same day key form one day. With neither option, the key is the UTC calendar day
// of the naive file time, as before.
//   fileTz:   'UTC' (or null) | an IANA name | {offset_min} | 'broker' (New York time + 7 hours:
//             GMT+2, and GMT+3 while New York is on summer time)
//   dayStart: null | {tz: 'file' (the file's own clock) | 'broker' (as fileTz) | 'UTC' | IANA name, hour: 0-23}
const DAY = 86400000;
const HOUR = 3600000;
const BUCKET = 900000; // offsets are read at the start of each 15-minute UTC bucket
const fmtCache = new Map();
const offCache = new Map();

function formatter(tz) {
  let f = fmtCache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric',
      day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric', era: 'short' });
    fmtCache.set(tz, f);
  }
  return f;
}

// The zone's offset from UTC (ms) at a UTC instant, read at the start of its 15-minute bucket.
export function tzOffset(tz, utcMs) {
  if (tz === 'UTC') return 0;
  const b = Math.floor(utcMs / BUCKET);
  let m = offCache.get(tz);
  if (!m) { m = new Map(); offCache.set(tz, m); }
  let o = m.get(b);
  if (o === undefined) {
    const at = b * BUCKET;
    const v = {};
    for (const part of formatter(tz).formatToParts(new Date(at))) v[part.type] = part.value;
    let y = Number(v.year);
    if (v.era === 'BC' || v.era === 'B') y = 1 - y;
    const local = Date.UTC(y, Number(v.month) - 1, Number(v.day), Number(v.hour), Number(v.minute), Number(v.second));
    o = local - at;
    m.set(b, o);
  }
  return o;
}

// A naive wall-clock time in zone tz → UTC ms (two-step; deterministic in DST gaps and overlaps).
export function zonedToUtc(naiveMs, tz) {
  const o1 = tzOffset(tz, naiveMs);
  const g = naiveMs - o1;
  const o2 = tzOffset(tz, g);
  return o2 === o1 ? g : naiveMs - o2;
}

export function fileToUtc(naiveMs, fileTz) {
  if (fileTz === undefined || fileTz === null || fileTz === 'UTC') return naiveMs;
  if (typeof fileTz === 'object') return naiveMs - fileTz.offset_min * 60000;
  if (fileTz === 'broker') return zonedToUtc(naiveMs - 7 * HOUR, 'America/New_York');
  return zonedToUtc(naiveMs, fileTz);
}

export function dayKey(naiveMs, fileTz, dayStart) {
  if (!dayStart) return Math.floor(fileToUtc(naiveMs, fileTz) / DAY);
  const h = dayStart.hour * HOUR;
  if (dayStart.tz === 'file') return Math.floor((naiveMs - h) / DAY);
  const utc = fileToUtc(naiveMs, fileTz);
  const off = dayStart.tz === 'broker' ? tzOffset('America/New_York', utc) + 7 * HOUR : tzOffset(dayStart.tz, utc);
  return Math.floor((utc + off - h) / DAY);
}

// {days: P&L per day, open_s / close_s: seconds from the day's first close (habits.mjs's clock:
// open to the minute, close = open + hold), index: each trade's place in `trades`, keys}.
export function groupDays(trades, opts = {}) {
  const fileTz = opts.fileTz === undefined ? null : opts.fileTz;
  const dayStart = opts.dayStart || null;
  const days = [], openS = [], closeS = [], index = [], keys = [];
  let key = null, base = 0;
  // close-time order (the parser's order already; a stable sort keeps it and repairs any other)
  const order = trades.map((t, i) => i).sort((a, b) => (trades[a].close_ts - trades[b].close_ts) || (a - b));
  order.forEach((i) => {
    const t = trades[i];
    const k = dayKey(t.close_ts, fileTz, dayStart);
    const o = 60 * Math.floor(t.open_ts / 60000);
    const c = o + (t.hold_s === undefined ? Math.floor((t.close_ts - t.open_ts) / 1000) : t.hold_s);
    if (k !== key) { days.push([]); openS.push([]); closeS.push([]); index.push([]); keys.push(k); key = k; base = c; }
    const j = days.length - 1;
    days[j].push(t.pnl); openS[j].push(o - base); closeS[j].push(c - base); index[j].push(i);
  });
  return { days, open_s: openS, close_s: closeS, index, keys };
}

// Trades → trading days: realised results grouped by trading day, in closing order. Only the
// numbers leave this function. With no options: the UTC calendar day of the naive file time.
export function tradingDays(trades, opts) {
  return groupDays(trades, opts).days;
}

// ------------------------------------------------------------------ Expert details: uncertainty (§2.8)
// Monte Carlo error of a share from n runs: the 95% half-width 1.96·√(p(1−p)/n).
export function mcError(share, n) {
  return 1.96 * Math.sqrt(share * (1 - share) / n);
}

// File uncertainty: B outer resamples of the file's days (with replacement, each the file's length),
// `inner` paired runs each; 90% percentile intervals of the pass / bust / time-out shares and, with a
// what-if rule, of its change in each. Deterministic: resample b draws from mulberry32(mix32(seed ^
// RANGE_SALT, b)). Percentile q of B sorted values: the value at index round(q·(B − 1)).
export const RANGE_SALT = 0x5bd1e995;
export const RANGE_B = 200;
export const RANGE_INNER = 1000;
export function dayResampleRange(p, opts = {}) {
  const B = opts.B || RANGE_B, inner = opts.inner || RANGE_INNER;
  const seed = p.seed === undefined ? DEFAULT_SEED : p.seed;
  const personal = opts.personal || null;
  checkInput(p);
  if (p.mode === 'manual') throw new Error('range: needs a file');
  const n = p.days.length;
  const keys = ['pass', 'bust', 'timeout'];
  const vals = { pass: [], bust: [], timeout: [] }, diffs = { pass: [], bust: [], timeout: [] };
  for (let b = 0; b < B; b++) {
    const rand = mulberry32(mix32((seed ^ RANGE_SALT) >>> 0, b));
    const pick = [];
    for (let i = 0; i < n; i++) pick.push(Math.floor(rand() * n));
    const q = { ...p, mode: 'file', runs: inner, stream: 'paired', personal: null, days: pick.map((i) => p.days[i]) };
    if (p.open_s) { q.open_s = pick.map((i) => p.open_s[i]); q.close_s = pick.map((i) => p.close_s[i]); }
    const a = simulate(q);
    const w = personal ? simulate({ ...q, personal }) : null;
    for (const k of keys) {
      vals[k].push(a[k] / inner);
      if (w) diffs[k].push((w[k] - a[k]) / inner);
    }
  }
  const at = (arr, qq) => { const s = arr.slice().sort((x, y) => x - y); return s[Math.round(qq * (s.length - 1))]; };
  const out = { B, inner, level: 0.9, shares: {}, change: personal ? {} : null };
  for (const k of keys) {
    out.shares[k] = [at(vals[k], 0.05), at(vals[k], 0.95)];
    if (personal) out.change[k] = [at(diffs[k], 0.05), at(diffs[k], 0.95)];
  }
  return out;
}
