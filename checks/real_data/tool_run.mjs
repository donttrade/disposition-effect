// tool_run.mjs: the free tools' own arithmetic, run in node on the real public-data trades (no browser, no DOM).
// make_tool_real.py pipes {trades, preset, account_size, odean} in (trades parsed by tests/reference/engine_ref.py,
// the browser engine's tested Python mirror) and reads back what each tool's core module computes:
//   drawdown-core.js drawdowns() · heatmap-core.js heatmap() and level() · challenge-presets.js presetRules() ·
//   prop-sim-core.js groupDays(), simulate() (10,000 paired replays, the page's default seed), the real-order sequence,
//   mcError() and dayResampleRange() (200 resamples x 1,000 replays) · legacy/disposition-calculator.js compute().
// The same modules the tool pages load, so no figure is re-implemented. Prints JSON; writes nothing.
import { createRequire } from 'node:module';
import { drawdowns } from '../../site/static/js/tools/drawdown-core.js';
import { heatmap, level } from '../../site/static/js/tools/heatmap-core.js';
import { presetRules } from '../../site/static/js/tools/challenge-presets.js';
import { groupDays, simulate, mcError, dayResampleRange, RUNS } from '../../site/static/js/tools/prop-sim-core.js';

const require = createRequire(import.meta.url);
globalThis.dtNumbers = require('../../site/static/js/legacy/numbers.js');
const disposition = require('../../site/static/js/legacy/disposition-calculator.js');

let s = '';
process.stdin.on('data', (d) => { s += d; });
process.stdin.on('end', () => {
  const inp = JSON.parse(s);
  const trades = inp.trades;
  const dd = drawdowns(trades);
  const hm = heatmap(trades, { shiftHours: 0, block: 1 });
  const hmLevels = hm.grid.map((row) => row.map((c) => (c.n ? level(c.total, hm.maxAbs) : null)));
  const pr = presetRules(inp.preset, inp.account_size);
  const g = groupDays(trades, { fileTz: 'UTC', dayStart: pr.dayStart });
  const p = { rules: pr.rules, runs: RUNS, stream: 'paired', mode: 'file', days: g.days, open_s: g.open_s, close_s: g.close_s };
  const sim = simulate(p);
  const seq = simulate({ mode: 'sequence', days: g.days, rules: pr.rules });
  const range = inp.range ? dayResampleRange(p) : null;
  const odean = disposition.compute(...inp.odean);
  process.stdout.write(JSON.stringify({
    dd: { max: dd.max || null, summary: Object.fromEntries(Object.entries(dd).filter(([k]) => k !== 'episodes' && k !== 'curve')),
      curve: dd.curve, episodes: dd.episodes },
    hm: { grid: hm.grid, maxAbs: hm.maxAbs, levels: hmLevels, cells: hm.cells.length, n_small: hm.n_small, n: hm.n },
    rules: pr.rules, dayStart: pr.dayStart,
    days: g.days, sim: { pass: sim.pass, bust: sim.bust, timeout: sim.timeout, bust_daily: sim.bust_daily,
      bust_max: sim.bust_max, median_bust_days: sim.median_bust_days, median_pass_days: sim.median_pass_days, runs: sim.runs },
    seq: { outcome: seq.outcome, day: seq.day, why: seq.why === undefined ? null : seq.why },
    mc: { pass: mcError(sim.pass / sim.runs, sim.runs) },
    range, odean,
  }));
});
