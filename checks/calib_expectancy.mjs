// calib_expectancy.mjs — how often the free expectancy check says "distinguishable from
// noise" on P&L with NO edge (true mean 0). It should be about 5%. Shapes from the Tester's
// harness (TESTER-REPORT-v2 D3), including the skewed ones a sign flip got wrong.
//   node checks/calib_expectancy.mjs [files per cell] [n list] [shape list] [seed] [--mirror]
// --mirror also runs every file negated and counts files whose label, guard or n_needed differ
// (amendment F-5: they must be 0). The full F-1…F-5 grid is checks/calib_free.mjs.
// Data come from a seeded mulberry32, so a run is repeatable (the Tester's harness used
// Math.random; checks/README-style use: a larger files count gives a tighter estimate).
import { checkExpectancy, mulberry32, SEED_BASE } from '../site/static/js/engine/noise.js';

const FILES = Number(process.argv[2] || 600);
const NS = (process.argv[3] || '30,60,200').split(',').map(Number);
const seedArg = process.argv[5] && !process.argv[5].startsWith('--') ? process.argv[5] : 7;
const rnd = mulberry32(Number(seedArg));
const normal = () => { let u = 0; while (u === 0) u = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd()); };
const SHAPES = {
  normal: () => normal(),
  skew_75_25: () => (rnd() < 0.75 ? 1 : -3),         // 75% +1 / 25% -3
  skew_90_10: () => (rnd() < 0.9 ? 1 : -9),          // 90% +1 / 10% -9
  lognorm_tail: () => (rnd() < 0.6 ? 1 + 0.3 * normal() : -(0.6 / 0.4) * Math.exp(normal() - 0.5)), // 60% win, heavy loss tail
  // Tester F-D1 trend follower: 30% lognormal wins (mean 7/3, log-sd 1.2), 70% losses of -1; mean 0.
  trend_right_skew: () => (rnd() < 0.3 ? Math.exp(Math.log(7 / 3) - 0.72 + 1.2 * normal()) : -1),
};
const only = process.argv[4] && !process.argv[4].startsWith('--') ? process.argv[4].split(',') : Object.keys(SHAPES);
const mirror = process.argv.includes('--mirror');
const out = {};
let mirrorDiffs = 0;
for (const name of only) {
  for (const n of NS) {
    let hits = 0;
    for (let f = 0; f < FILES; f++) {
      const pnls = Array.from({ length: n }, SHAPES[name]);
      const r = checkExpectancy(pnls, SEED_BASE);
      if (r.p !== null && r.p < 0.05) hits++;   // "distinguishable from noise" (the guard sets p = null)
      if (mirror) {
        const m = checkExpectancy(pnls.map((v) => -v), SEED_BASE);
        if (m.label !== r.label || m.guard !== r.guard || m.n_needed !== r.n_needed || m.skew !== -r.skew) mirrorDiffs++;
      }
    }
    out[`${name}/n=${n}`] = hits / FILES;
  }
}
if (mirror) out.mirror_diffs = mirrorDiffs;
process.stdout.write(JSON.stringify(out) + '\n');
