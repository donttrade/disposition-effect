// prop-sim-rank.js — the ranked "Biggest changes on your past days" rules (ARCHITECT-CHALLENGE-READINESS §2.7.3).
// Built, and switched off until a Canadian securities lawyer has read the strings: the build copies this file
// only with site.toml [flags] whatif_ranked = true (build.py), and the worker imports it only then.
// Mirrored by readiness_ref.rank_rules.

import { simulate, normRules, personalUnavailable, ruleLabel, RUNS } from './prop-sim-core.js';

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

export const RANK_TEXT = Object.freeze({
  heading: 'Biggest changes on your past days',
  lead: 'Rules that changed the result most on your own past days.',
  selection_bias: 'These are the best of the rules tried on the same past days, so they look better here than they would on new days.',
});

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
