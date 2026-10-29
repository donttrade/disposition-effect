// challenge-presets.js — a firm-rules library entry (site/config/challenge_rules.json) → the
// engine's rules and day boundary. Pure; mirrored by readiness_ref.preset_rules.
//
// A 'percent' preset states its amounts for its own account_size and scales to another size (the
// firm's rules are shares of the account); a 'fixed' preset (futures) keeps its amounts. The
// fields stay editable on the page: a trader's own account type may differ.

export const SCALED = Object.freeze(['target', 'daily_loss', 'max_loss', 'trail_stop_at', 'profitable_day_min']);

export function presetRules(preset, accountSize) {
  if (!preset || preset.status === 'not_quotable' || !preset.rules) throw new Error('preset: no rules to use');
  const k = preset.scale === 'percent' && accountSize ? accountSize / preset.account_size : 1;
  const r = { ...preset.rules };
  for (const f of SCALED) if (r[f] !== null && r[f] !== undefined) r[f] = r[f] * k;
  const dayStart = r.day_start;
  delete r.day_start;
  return { rules: r, dayStart, accountSize: k === 1 ? preset.account_size : accountSize, unconfirmed: preset.unconfirmed.slice() };
}
