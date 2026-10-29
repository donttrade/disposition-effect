// challenge-presets.js — a firm-rules library entry (site/config/challenge_rules.json) → the
// engine's rules and day boundary. Pure; mirrored by readiness_ref.preset_rules.
//
// A 'percent' preset states its amounts for its own account_size and scales to another size (the
// firm's rules are shares of the account); a 'fixed' preset (futures) keeps its amounts. A value the
// firm's page does not state is "not stated" in the library: it runs with the engine's default
// (DEFAULTS) and is listed in notStated, so the page can say so next to the field. The fields stay
// editable on the page: a trader's own account type may differ.

export const NOT_STATED = 'not stated';
export const SCALED = Object.freeze(['target', 'daily_loss', 'max_loss', 'trail_stop_at', 'profitable_day_min']);
export const DEFAULTS = Object.freeze({ target_check: 'eod', drawdown: 'static', trail_stop_at: null, consistency: null,
  min_days: 0, count_day_if: 'any', time_limit: null, day_start: null, daily_loss: null });
const TARGET_CHECK = { intraday: 'intraday', 'end of day': 'eod' };
const COUNT_DAY_IF = { 'any trade': 'any', 'non-zero P&L': 'nonzero' };
const QUOTED = ['target', 'target_check', 'daily_loss', 'max_loss', 'drawdown', 'trail_stop_at', 'consistency',
  'min_days', 'count_day_if', 'time_limit', 'day_start'];

// Whether a field changes the result (as checks/check_rules.py relevant()).
function relevant(f, r) {
  if (f === 'trail_stop_at' && r.drawdown === 'static') return false;
  if (f === 'count_day_if' && (r.min_days === 0 || r.min_days === NOT_STATED || r.min_days_kind === 'profitable')) return false;
  return true;
}

export function presetRules(preset, accountSize) {
  if (!preset || preset.status === 'not_quotable' || !preset.rules) throw new Error('preset: no rules to use');
  const src = preset.rules;
  const notStated = QUOTED.filter((f) => src[f] === NOT_STATED && relevant(f, src));
  const k = preset.scale === 'percent' && accountSize ? accountSize / preset.account_size : 1;
  const r = {};
  for (const [f, v] of Object.entries(src)) r[f] = v === NOT_STATED ? DEFAULTS[f] : v;
  for (const f of SCALED) if (r[f] !== null && r[f] !== undefined) r[f] = r[f] * k;
  r.target_check = TARGET_CHECK[r.target_check] || r.target_check;
  r.count_day_if = COUNT_DAY_IF[r.count_day_if] || r.count_day_if;
  const dayStart = r.day_start;
  delete r.day_start;
  return { rules: r, dayStart, accountSize: k === 1 ? preset.account_size : accountSize, notStated,
    notModelled: preset.not_modelled.slice() };
}
