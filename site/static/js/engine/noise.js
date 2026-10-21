// noise.js — "real or noise" permutation checks, shared by the free dashboard
// (in a Web Worker) and the paid analysis (server side, Node). No DOM, no I/O.
//
// Fixed by the plan so the p-values equal the Python reference EXACTLY:
//   N = 10,000 permutations (or resamples); PRNG = mulberry32 seeded 20261022 + check index;
//   shuffle = Fisher–Yates from the end; two-sided p = (1 + #{|perm| >= |obs|}) / (N + 1);
//   sums run in input order. A group under 30 trades → "not enough trades to tell".
// Check 1 (expectancy) is a bootstrap-t, not the plan's sign-flip (Tester D3): a sign
// flip assumes P&L is symmetric around zero, and on skewed zero-edge P&L ("many small
// wins, rare big loss") it said "distinguishable" up to 19% of the time instead of 5%.
// It carries a pre-registered skew guard (ARCHITECT-STATS-AMENDMENT-2026-10-21 §4): on
// strongly skewed P&L a claim pointing away from the long tail is withheld.
// Mirrors tests/reference/engine_ref.py (mulberry32 … noise_checks).

export const N_PERM = 10000;
export const SEED_BASE = 20261022;
export const MIN_GROUP = 30;
export const NOISE_LIMIT = 20000;

export const LABELS = Object.freeze({
  real: 'distinguishable from noise',
  noise: 'may be noise',
  tooFew: 'not enough trades to tell',
});

export function mulberry32(seed) {
  let a = seed | 0;
  return function rand() {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffle(arr, rand) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
  }
}

export function pValue(count) {
  return (1 + count) / (N_PERM + 1);
}

export function labelFor(p, tooFew) {
  if (tooFew) return LABELS.tooFew;
  return p < 0.05 ? LABELS.real : LABELS.noise;
}

// k-th smallest (0-based) by quickselect; reorders `a` (a scratch copy).
function select(a, k) {
  let l = 0;
  let r = a.length - 1;
  while (r > l) {
    const pivot = a[(l + r) >> 1];
    let i = l;
    let j = r;
    while (i <= j) {
      while (a[i] < pivot) i++;
      while (a[j] > pivot) j--;
      if (i <= j) { const t = a[i]; a[i] = a[j]; a[j] = t; i++; j--; }
    }
    if (k <= j) r = j;
    else if (k >= i) l = i;
    else break;
  }
  return a[k];
}

// Median without changing the input. O(n), so 10,000 permutations of 20,000
// trades stay fast; the value is the same as the reference's sort-based median.
export function median(xs, scratch) {
  const n = xs.length;
  if (n === 0) return null;
  const a = scratch && scratch.length >= n ? scratch.subarray(0, n) : new Float64Array(n);
  for (let i = 0; i < n; i++) a[i] = xs[i];
  const k = n >> 1;
  const hi = select(a, k);
  if (n % 2) return hi;
  let lo = a[0];
  for (let i = 1; i < k; i++) if (a[i] > lo) lo = a[i];
  return (lo + hi) / 2;
}

export function meanOf(xs) {
  let s = 0;
  for (const v of xs) s += v;
  return s / xs.length;
}

// Two-group label permutation: shuffle the pooled values (cumulatively), the first
// nA are group A. stat(a, b) gets plain subarrays. Returns the p-value.
export function labelPermutation(pool, nA, obs, stat, seed) {
  const work = Float64Array.from(pool);
  const rand = mulberry32(seed);
  let count = 0;
  for (let k = 0; k < N_PERM; k++) {
    shuffle(work, rand);
    const v = stat(work.subarray(0, nA), work.subarray(nA));
    if (Math.abs(v) >= Math.abs(obs)) count++;
  }
  return pValue(count);
}

function longestLossRun(xs) {
  let best = 0;
  let cur = 0;
  for (const v of xs) {
    if (v < 0) { cur++; if (cur > best) best = cur; } else cur = 0;
  }
  return best;
}

export const EXPECTANCY_METHOD = 'bootstrap-t';

// Skew guard (ARCHITECT-STATS-AMENDMENT-2026-10-21 §4, D-8). Pre-registered: a claim whose
// sign points AWAY from the long tail of the file's P&L becomes "not enough trades to tell"
// when the file is too short for its skew (n < SKEW_C·g1², |g1| ≥ SKEW_MIN), or when the
// claim does not survive one more trade the size of the file's largest opposite-side trade.
export const SKEW_MIN = 1;
export const SKEW_C = 10;

// |mean - mu| / sd of xs[0..n) (sd with n - 1). Zero spread: 0 if mean = mu, else Infinity.
function studentGap(xs, n, mu) {
  let s = 0;
  for (let i = 0; i < n; i++) s += xs[i];
  const m = s / n;
  let q = 0;
  for (let i = 0; i < n; i++) { const d = xs[i] - m; q += d * d; }
  const sd = Math.sqrt(q / (n - 1));
  if (sd === 0) return m === mu ? 0 : Infinity;
  return Math.abs(m - mu) / sd;
}

// The shipped bootstrap-t: resample with replacement nBoot times; count the resamples whose
// t around the file's own mean is at least the file's t around zero. stopAt (optional) ends
// the loop once the count reaches it; only a decision "count >= stopAt" may use that count.
function bootstrapCount(x, seed, nBoot, stopAt) {
  const n = x.length;
  let s = 0;
  for (const v of x) s += v;
  const obs = s / n;
  const tObs = studentGap(x, n, 0);
  const rand = mulberry32(seed);
  const draw = new Float64Array(n);
  let count = 0;
  for (let k = 0; k < nBoot; k++) {
    for (let i = 0; i < n; i++) draw[i] = x[Math.floor(rand() * n)];
    if (studentGap(draw, n, obs) >= tObs) {
      count++;
      if (count >= stopAt) break;
    }
  }
  return count;
}

// Sample skewness g1 (population-moment form), sums in input order. m is the file's mean.
export function skewness(pnls, m) {
  const n = pnls.length;
  let m2 = 0;
  let m3 = 0;
  for (const x of pnls) { const d = x - m; m2 += d * d; m3 += d * d * d; }
  m2 = m2 / n;
  m3 = m3 / n;
  return m2 > 0 ? m3 / (m2 * Math.sqrt(m2)) : 0;
}

// Expectancy ≠ 0 by a studentized (bootstrap-t) test, then the skew guard. (The √n of a t
// statistic is the same on both sides, so it is left out.) Calibration on zero-edge P&L:
// CODER-FIX-REPORT-v2-2026-10-21 D3 (bootstrap-t) and CODER-STATS-REPORT-2026-10-21 (guard).
// nBoot is N_PERM in the product; the calibration scripts alone pass a smaller one.
export function checkExpectancy(pnls, seed, nBoot = N_PERM) {
  const n = pnls.length;
  const out = { stat: 'expectancy', method: EXPECTANCY_METHOD, n_a: n, n_b: null, value: null, p: null, label: null,
    skew: null, guard: null, n_needed: null, extreme: null, p_unguarded: null };
  if (n < MIN_GROUP) { out.label = labelFor(null, true); return out; }
  let s = 0;
  for (const v of pnls) s += v;
  const m = s / n;
  const p = (1 + bootstrapCount(pnls, seed, nBoot, Infinity)) / (nBoot + 1);
  const g1 = skewness(pnls, m);
  out.value = m;
  out.skew = g1;
  // the average points away from the long tail
  const against = (m > 0 && g1 <= -SKEW_MIN) || (m < 0 && g1 >= SKEW_MIN);
  if (against && n < SKEW_C * g1 * g1) {
    return Object.assign(out, { label: labelFor(null, true), guard: 'skew_small_n',
      n_needed: Math.floor(SKEW_C * g1 * g1) + 1, p_unguarded: p });
  }
  if (against && p < 0.05) {
    // first trade in input order with the largest value (average below zero) or the smallest
    let ext = pnls[0];
    for (let i = 1; i < n; i++) if (m < 0 ? pnls[i] > ext : pnls[i] < ext) ext = pnls[i];
    const stop = Math.ceil(0.05 * (nBoot + 1)) - 1;
    if (!((1 + stop) / (nBoot + 1) >= 0.05 && stop / (nBoot + 1) < 0.05)) {
      throw new Error(`skew guard: stop ${stop} does not mark p >= 0.05 for N = ${nBoot}`);
    }
    if (bootstrapCount(pnls.concat([ext]), seed, nBoot, stop) >= stop) {
      return Object.assign(out, { label: labelFor(null, true), guard: 'skew_one_more', extreme: ext, p_unguarded: p });
    }
  }
  return Object.assign(out, { p, label: labelFor(p, false) });
}

// Wording for a guarded expectancy badge (amendment §7.2), exactly as given. "below": the
// average is below zero (the long tail is the wins); "above": it is above zero (the losses).
export const EXPECTANCY_GUARD_TEXT = Object.freeze({
  skew_small_n: Object.freeze({
    below: "Not enough trades to tell. Most of this file's gains come from a few large wins, so one more large win can move the average a lot. For results shaped like these, this check waits for at least {n_needed} trades before saying whether the average is above or below zero.",
    above: "Not enough trades to tell. Most of this file's losses come from a few large losses, so one more large loss can move the average a lot. For results shaped like these, this check waits for at least {n_needed} trades before saying whether the average is above or below zero.",
  }),
  skew_one_more: Object.freeze({
    below: "Not enough trades to tell. With one more trade the size of this file's largest win ({extreme}), the average would be within what chance alone produces.",
    above: "Not enough trades to tell. With one more trade the size of this file's largest loss ({extreme}), the average would be within what chance alone produces.",
  }),
});

// The fixed footnote under the three free checks (amendment D-9, §7.2).
export const FREE_CHECKS_FOOTNOTE = "Each check is run on its own. In files with no real effect, each one shows 'distinguishable from noise' about 1 time in 20, so at least one of the three does so more often: up to about 1 file in 7 in our tests.";

// The badge sentence for a guarded check, or null when the guard did not act.
// money(x) formats the extreme trade the way the page formats money.
export function guardSentence(check, money = String) {
  if (!check || check.guard === null) return null;
  const t = EXPECTANCY_GUARD_TEXT[check.guard];
  if (!t || !(check.value < 0 || check.value > 0)) throw new Error(`guardSentence: bad check ${check.guard}`);
  const s = check.value < 0 ? t.below : t.above;
  return s.replace('{n_needed}', String(check.n_needed)).replace('{extreme}', check.guard === 'skew_one_more' ? money(check.extreme) : '');
}

export function checkHoldGap(trades, seed) {
  const a = [];
  const b = [];
  const pool = [];
  for (const t of trades) {
    if (t.pnl < 0) a.push(t.hold_s); else if (t.pnl > 0) b.push(t.hold_s);
    if (t.pnl !== 0) pool.push(t.hold_s);
  }
  const out = { stat: 'hold_gap_s', method: 'label permutation', n_a: a.length, n_b: b.length, value: null, p: null };
  if (a.length < MIN_GROUP || b.length < MIN_GROUP) { out.label = labelFor(null, true); return out; }
  const obs = median(a) - median(b);
  const scratch = new Float64Array(pool.length);
  const p = labelPermutation(pool, a.length, obs, (x, y) => median(x, scratch) - median(y, scratch), seed);
  return Object.assign(out, { value: obs, p, label: labelFor(p, false) });
}

export function checkStreak(pnls, seed) {
  const n = pnls.length;
  const out = { stat: 'longest_losing_streak', method: 'order shuffle', n_a: n, n_b: null, value: null, p: null };
  if (n < MIN_GROUP) { out.label = labelFor(null, true); return out; }
  const obs = longestLossRun(pnls);
  const work = Int8Array.from(pnls, (v) => (v < 0 ? -1 : v > 0 ? 1 : 0));
  const rand = mulberry32(seed);
  let count = 0;
  for (let k = 0; k < N_PERM; k++) {
    shuffle(work, rand);
    if (longestLossRun(work) >= obs) count++;
  }
  const p = pValue(count);
  return Object.assign(out, { value: obs, p, label: labelFor(p, false) });
}

// trades: [{pnl, hold_s}] in close-time order. Uses the most recent 20,000.
export function noiseChecks(trades) {
  const used = trades.length > NOISE_LIMIT ? trades.slice(trades.length - NOISE_LIMIT) : trades;
  const pnls = used.map((t) => t.pnl);
  return {
    n_used: used.length,
    limited: trades.length > NOISE_LIMIT,
    checks: [checkExpectancy(pnls, SEED_BASE + 0), checkHoldGap(used, SEED_BASE + 1), checkStreak(pnls, SEED_BASE + 2)],
  };
}
