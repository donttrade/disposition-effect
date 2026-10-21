// calib_free.mjs — Tester invariants F-1…F-5 for the free expectancy check with its skew guard
// (ARCHITECT-STATS-AMENDMENT-2026-10-21 §4, §8). Runs the SHIPPED checkExpectancy on seeded
// zero-edge files (checks/calib_gen.mjs) and prints one JSON object; exit code 1 if an invariant fails.
//
//   node checks/calib_free.mjs            fast CI size (about 20 s): F-1 and F-2 on fewer files,
//                                         F-3/F-4/F-5 at the production N on 144 files
//   node checks/calib_free.mjs --slow     the amendment's sizes: 2,000 files per cell, n up to 1,000
//                                         (several minutes; record the numbers in the Coder report)
//   options: --files K  --boot B  --seedset S  --workers W
//
// Calibration uses B = 1,999 bootstrap resamples (the Architect's runs did the same). A Monte
// Carlo p-value is valid for any B, so this changes only the run time; F-3/F-4/F-5 use N = 10,000.
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { checkExpectancy, N_PERM, SEED_BASE, LABELS } from '../site/static/js/engine/noise.js';
import { SHAPES, freeFile, wilson, tTestP } from './calib_gen.mjs';

const ALL_SHAPES = Object.keys(SHAPES);

function arg(name, dflt) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : dflt;
}

// One cell: counts of the amended "distinguishable", today's (unguarded p < 0.05), withheld, t-test.
function runCell({ shape, n, from, to, boot, seedSet }) {
  const c = { files: 0, claims: 0, current: 0, withheld: 0, ttest: 0 };
  for (let s = from; s < to; s++) {
    const x = freeFile(shape, n, s, seedSet);
    const r = checkExpectancy(x, SEED_BASE, boot);
    const pToday = r.guard === null ? r.p : r.p_unguarded;
    c.files++;
    if (r.label === LABELS.real) c.claims++;
    if (pToday < 0.05) c.current++;
    if (r.guard !== null) c.withheld++;
    if (tTestP(x) < 0.05) c.ttest++;
  }
  return c;
}

// Today's check (v2-rebuild 9318e19), copied verbatim in behaviour: the bootstrap-t p only.
function todayP(pnls, seed) {
  const n = pnls.length;
  const gap = (xs, mu) => { let s = 0; for (let i = 0; i < n; i++) s += xs[i]; const m = s / n; let q = 0; for (let i = 0; i < n; i++) { const d = xs[i] - m; q += d * d; } const sd = Math.sqrt(q / (n - 1)); if (sd === 0) return m === mu ? 0 : Infinity; return Math.abs(m - mu) / sd; };
  let s = 0; for (const v of pnls) s += v; const obs = s / n; const tObs = gap(pnls, 0);
  let a = seed | 0; const rand = () => { a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const draw = new Float64Array(n); let count = 0;
  for (let k = 0; k < N_PERM; k++) { for (let i = 0; i < n; i++) draw[i] = pnls[Math.floor(rand() * n)]; if (gap(draw, obs) >= tObs) count++; }
  return (1 + count) / (N_PERM + 1);
}

// F-3 (p unchanged), F-4 (only withholds), F-5 (mirror symmetry), at the production N.
function props() {
  const fails = [];
  const guards = { none: 0, skew_small_n: 0, skew_one_more: 0 };
  let k = 0;
  for (const shape of ['trend_right_skew', 'trend_left', 'lottery', 'skew_90_10', 'heavy_loss_tail', 'normal']) {
    for (const n of [30, 60, 120]) {
      for (const shift of [0, -0.3, 0.3, 0.6]) {
        for (let rep = 0; rep < 2; rep++) {
          k++;
          const x = freeFile(shape, n, 9000 + rep, 7).map((v) => Math.round((v + shift * 25) * 100) / 100);
          const r = checkExpectancy(x, SEED_BASE);
          guards[r.guard || 'none']++;
          const p0 = todayP(x, SEED_BASE);
          const label0 = p0 < 0.05 ? LABELS.real : LABELS.noise;
          const pNow = r.guard === null ? r.p : r.p_unguarded;
          if (pNow !== p0) fails.push(`F-3 ${shape} n=${n} shift=${shift}: p ${pNow} != today ${p0}`);
          if (r.guard === null && r.label !== label0) fails.push(`F-3 ${shape} n=${n}: label ${r.label} != today ${label0}`);
          if (r.label === LABELS.real && label0 !== LABELS.real) fails.push(`F-4 ${shape} n=${n}: guard made a claim`);
          if (r.guard !== null && r.p !== null) fails.push(`guard ${r.guard} with p ${r.p}`);
          const m = checkExpectancy(x.map((v) => -v), SEED_BASE);
          if (m.label !== r.label || m.guard !== r.guard || m.n_needed !== r.n_needed || m.skew !== -r.skew
            || m.p !== r.p || m.p_unguarded !== r.p_unguarded || (r.extreme !== null && m.extreme !== -r.extreme)) {
            fails.push(`F-5 ${shape} n=${n} shift=${shift}: mirror ${JSON.stringify([m.label, m.guard, m.skew])} vs ${JSON.stringify([r.label, r.guard, r.skew])}`);
          }
        }
      }
    }
  }
  return { files: k, guards, fails };
}

async function cell(shape, n, files, boot, seedSet, workers) {
  if (workers <= 1) return runCell({ shape, n, from: 0, to: files, boot, seedSet });
  const parts = await Promise.all(Array.from({ length: workers }, (_, w) => new Promise((res, rej) => {
    const wk = new Worker(new URL(import.meta.url), { workerData: { shape, n, from: Math.floor(files * w / workers), to: Math.floor(files * (w + 1) / workers), boot, seedSet } });
    wk.on('message', res); wk.on('error', rej);
  })));
  return parts.reduce((a, b) => { for (const k of Object.keys(a)) a[k] += b[k]; return a; });
}

const pct = (k, t) => +(100 * k / t).toFixed(2);
const ci = (k, t) => wilson(k, t).map((v) => +(100 * v).toFixed(2));

async function main() {
  const slow = process.argv.includes('--slow');
  const boot = Number(arg('--boot', 1999));
  const seedSet = Number(arg('--seedset', 0));
  const workers = Number(arg('--workers', slow ? 2 : 1));
  const f1Files = Number(arg('--files', slow ? 2000 : 400));
  const f2Files = Number(arg('--files', slow ? 2000 : 150));
  const f2Ns = slow ? [30, 60, 200, 1000] : [30, 60, 200];
  const t0 = Date.now();
  const out = { mode: slow ? 'slow' : 'fast', boot, seedSet, f1: {}, f2: { cells: {} }, fails: [] };

  // F-1: the F-D1 repro, trend follower at n = 30 / 60 / 200.
  const f1Limit = slow ? 5.5 : 6.5;
  for (const n of [30, 60, 200]) {
    const c = await cell('trend_right_skew', n, f1Files, boot, seedSet, workers);
    out.f1[`n=${n}`] = { files: c.files, distinguishable: pct(c.claims, c.files), ci: ci(c.claims, c.files), current: pct(c.current, c.files), withheld: pct(c.withheld, c.files) };
    if (pct(c.claims, c.files) > f1Limit) out.fails.push(`F-1 n=${n}: ${pct(c.claims, c.files)}% > ${f1Limit}%`);
  }

  // F-2: the 12-shape grid. Pooled <= 5.0%; every cell <= 6.5% (fast: <= 10%, a gross-failure net
  // at 150 files); a cell above 5.5% must also be above 5.5% under the plain t-test (sampling noise).
  const pool = { files: 0, claims: 0, current: 0 };
  let worst = { v: 0, cell: '' };
  for (const shape of ALL_SHAPES) {
    for (const n of f2Ns) {
      const c = await cell(shape, n, f2Files, boot, seedSet, workers);
      const v = pct(c.claims, c.files);
      out.f2.cells[`${shape}@${n}`] = { distinguishable: v, ci: ci(c.claims, c.files), current: pct(c.current, c.files), withheld: pct(c.withheld, c.files), ttest: pct(c.ttest, c.files) };
      pool.files += c.files; pool.claims += c.claims; pool.current += c.current;
      if (v > worst.v) worst = { v, cell: `${shape}@${n}` };
      const cellLimit = slow ? 6.5 : 10;
      if (v > cellLimit) out.fails.push(`F-2 ${shape}@${n}: ${v}% > ${cellLimit}%`);
      if (slow && v > 5.5 && !(pct(c.ttest, c.files) > 5.5)) out.fails.push(`F-2 ${shape}@${n}: ${v}% > 5.5% while the t-test reads ${pct(c.ttest, c.files)}%`);
    }
  }
  out.f2.pooled = { files: pool.files, distinguishable: pct(pool.claims, pool.files), ci: ci(pool.claims, pool.files), current: pct(pool.current, pool.files) };
  out.f2.worst = worst;
  if (pct(pool.claims, pool.files) > 5.0) out.fails.push(`F-2 pooled ${pct(pool.claims, pool.files)}% > 5.0%`);

  // F-3 / F-4 / F-5 at the production N.
  const pr = props();
  out.props = { files: pr.files, guards: pr.guards };
  out.fails.push(...pr.fails);
  if (pr.guards.skew_small_n === 0 || pr.guards.skew_one_more === 0) out.fails.push(`props: a guard branch was not exercised ${JSON.stringify(pr.guards)}`);

  out.seconds = Math.round((Date.now() - t0) / 1000);
  process.stdout.write(JSON.stringify(out) + '\n');
  process.exitCode = out.fails.length ? 1 : 0;
}

if (isMainThread) main();
else parentPort.postMessage(runCell(workerData));
