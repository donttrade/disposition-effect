// calib_gen.mjs — data generators for the calibration checks (no-edge P&L shapes).
// COPIED from the Architect's throwaway harness (/home/claude/architect-stats/lib/tester-gen.mjs
// and run-free.mjs, ARCHITECT-STATS-AMENDMENT-2026-10-21 §5.1, §5.7), not imported from it.
// The data PRNG is the Tester's xoshiro128** (seeded by splitmix32), deliberately NOT the
// engine's mulberry32, so the data and the bootstrap draws are independent streams.
// Every shape has population mean exactly 0.

export function rng(seed) {
  let z = seed >>> 0;
  const sm = () => { z = (z + 0x9e3779b9) >>> 0; let t = z; t = Math.imul(t ^ (t >>> 16), 0x85ebca6b) >>> 0; t = Math.imul(t ^ (t >>> 13), 0xc2b2ae35) >>> 0; return (t ^ (t >>> 16)) >>> 0; };
  let a = sm(), b = sm(), c = sm(), d = sm();
  const next = () => {
    const r = Math.imul(((Math.imul(b, 5) << 7) | (Math.imul(b, 5) >>> 25)), 9) >>> 0;
    const t = (b << 9) >>> 0;
    c ^= a; d ^= b; b ^= c; a ^= d; c ^= t; d = ((d << 11) | (d >>> 21)) >>> 0;
    return r / 4294967296;
  };
  const u = () => { let x; do x = next(); while (x === 0); return x; };
  const norm = () => Math.sqrt(-2 * Math.log(u())) * Math.cos(2 * Math.PI * next());
  return { u, norm, next };
}

const lognMean = (R, mean, s) => Math.exp(Math.log(mean) - s * s / 2 + s * R.norm());

// The 12 zero-edge shapes of amendment §5.7.
export const SHAPES = {
  normal: (R) => R.norm(),
  skew_75_25: (R) => (R.u() < 0.75 ? 1 : -3),
  skew_90_10: (R) => (R.u() < 0.9 ? 1 : -9),
  heavy_loss_tail: (R) => (R.u() < 0.6 ? -Math.log(R.u()) : -lognMean(R, 1.5, 1.0)),
  student_t3: (R) => { const z = R.norm(); let c = 0; for (let k = 0; k < 3; k++) { const y = R.norm(); c += y * y; } return z / Math.sqrt(c / 3); },
  trend_right_skew: (R) => (R.u() < 0.3 ? lognMean(R, 7 / 3, 1.2) : -1),
  pareto_loss: (R) => (R.u() < 0.7 ? 2 * R.u() : -1.4 / Math.pow(R.u(), 1 / 2.5)),
  lottery: (R) => (R.u() < 0.1 ? lognMean(R, 9, 1.0) : -1),
  trend_heavier: (R) => (R.u() < 0.2 ? lognMean(R, 4, 1.5) : -1),
  mild_right: (R) => (R.u() < 0.4 ? lognMean(R, 1.5, 0.6) : -1),
  left_lottery: (R) => (R.u() < 0.1 ? -lognMean(R, 9, 1.0) : 1),
  trend_left: (R) => -(R.u() < 0.3 ? lognMean(R, 7 / 3, 1.2) : -1),
};

// One file of zero-edge P&L in cents-rounded dollars (scale 25), as in the Architect's runs.
export function freeFile(shape, n, fileIndex, seedSet = 0) {
  const f = SHAPES[shape];
  if (!f) throw new Error(`unknown shape ${shape}`);
  const R = rng(0x5eed0000 + seedSet * 99991 * 7 + fileIndex * 7919 + n * 31 + shape.length * 3);
  return Array.from({ length: n }, () => Math.round(f(R) * 2500) / 100);
}

// Wilson 95% interval, as fractions.
export function wilson(k, n) {
  if (!n) return [null, null];
  const z = 1.96, ph = k / n, d = 1 + z * z / n;
  const c = (ph + z * z / (2 * n)) / d, h = (z * Math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n))) / d;
  return [c - h, c + h];
}

// Plain one-sample t-test two-sided p (evaluation only: it says which cells are sampling noise).
function lgamma(z) { const g = 7, c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059, 12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]; if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lgamma(1 - z); z -= 1; let x = c[0]; for (let i = 1; i < g + 2; i++) x += c[i] / (z + i); const t = z + g + 0.5; return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x); }
function betacf(a, b, x) { let qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap; if (Math.abs(d) < 1e-30) d = 1e-30; d = 1 / d; let h = d; for (let m = 1; m <= 300; m++) { const m2 = 2 * m; let aa = m * (b - m) * x / ((qam + m2) * (a + m2)); d = 1 + aa * d; if (Math.abs(d) < 1e-30) d = 1e-30; c = 1 + aa / c; if (Math.abs(c) < 1e-30) c = 1e-30; d = 1 / d; h *= d * c; aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2)); d = 1 + aa * d; if (Math.abs(d) < 1e-30) d = 1e-30; c = 1 + aa / c; if (Math.abs(c) < 1e-30) c = 1e-30; d = 1 / d; const del = d * c; h *= del; if (Math.abs(del - 1) < 3e-14) break; } return h; }
function ibeta(a, b, x) { if (x <= 0) return 0; if (x >= 1) return 1; const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x)); return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b; }
export function tTestP(x) {
  const n = x.length; let s = 0; for (const v of x) s += v; const m = s / n;
  let q = 0; for (const v of x) q += (v - m) * (v - m);
  const sd = Math.sqrt(q / (n - 1));
  if (sd === 0) return m === 0 ? 1 : 0;
  const t = m / (sd / Math.sqrt(n));
  return ibeta((n - 1) / 2, 0.5, (n - 1) / ((n - 1) + t * t));
}
