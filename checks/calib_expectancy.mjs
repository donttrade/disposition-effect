// calib_expectancy.mjs — how often the free expectancy check says "distinguishable from
// noise" on P&L with NO edge (true mean 0). It should be about 5%. Shapes from the Tester's
// harness (TESTER-REPORT-v2 D3), including the skewed ones a sign flip got wrong.
//   node checks/calib_expectancy.mjs [files per cell] [n list] [shape list] [seed]
// Data come from a seeded mulberry32, so a run is repeatable (the Tester's harness used
// Math.random; checks/README-style use: a larger files count gives a tighter estimate).
import { checkExpectancy, mulberry32, SEED_BASE } from '../site/static/js/engine/noise.js';

const FILES = Number(process.argv[2] || 600);
const NS = (process.argv[3] || '30,60,200').split(',').map(Number);
const rnd = mulberry32(Number(process.argv[5] || 7));
const normal = () => { let u = 0; while (u === 0) u = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd()); };
const SHAPES = {
  normal: () => normal(),
  skew_75_25: () => (rnd() < 0.75 ? 1 : -3),         // 75% +1 / 25% -3
  skew_90_10: () => (rnd() < 0.9 ? 1 : -9),          // 90% +1 / 10% -9
  lognorm_tail: () => (rnd() < 0.6 ? 1 + 0.3 * normal() : -(0.6 / 0.4) * Math.exp(normal() - 0.5)), // 60% win, heavy loss tail
};
const only = process.argv[4] ? process.argv[4].split(',') : Object.keys(SHAPES);
const out = {};
for (const name of only) {
  for (const n of NS) {
    let hits = 0;
    for (let f = 0; f < FILES; f++) {
      const pnls = Array.from({ length: n }, SHAPES[name]);
      if (checkExpectancy(pnls, SEED_BASE).p < 0.05) hits++;
    }
    out[`${name}/n=${n}`] = hits / FILES;
  }
}
process.stdout.write(JSON.stringify(out) + '\n');
