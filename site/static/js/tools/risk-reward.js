// risk-reward.js — /tools/risk-reward-calculator/: arithmetic on the visitor's own inputs.
//
// Manual inputs only (V2 free-tools list #5). Three numbers that belong together:
//   R multiple          = reward ÷ risk  (reward = |target − entry|, risk = |entry − stop|)
//   break-even win rate = 1 ÷ (1 + R), before costs
//   expectancy in R     = p × R − (1 − p) × 1, at a win rate p the visitor types
// NON-ADVISER: no input has a default, no ratio or win rate is proposed, rated or compared;
// the output is labelled as arithmetic, with the formula filled in. Strict number input
// (num.js): anything that reads two ways is refused, never guessed.

import { parsePositive, parseNonNegative, InputError } from './num.js';
import { el, plain, pct, MINUS } from './format.js';
import { clearFieldErrors, fieldError, showProblems } from './tool-state.js';

const $ = (id) => document.getElementById(id);
const LABELS = {
  'rr-entry': 'the entry price', 'rr-stop': 'the stop price', 'rr-target': 'the target price',
  'rr-ratio': 'the reward-to-risk ratio', 'rr-winrate': 'the win rate',
};

export class RiskRewardError extends Error {
  constructor(id, message) { super(message); this.name = 'RiskRewardError'; this.id = id; }
}

// Pure calculation, exported for the tests. Inputs are already-validated numbers; winRate is a
// fraction (0–1) or null. Throws RiskRewardError when the prices cannot describe a trade.
export function riskReward({ mode, entry, stop, target, ratio, winRate = null }) {
  let side = null, risk = null, reward = null, r;
  if (mode === 'prices') {
    if (stop === entry) throw new RiskRewardError('rr-stop', 'The stop is at the entry price, so there is no risk to divide by. Enter a stop away from the entry.');
    if (target === entry) throw new RiskRewardError('rr-target', 'The target is at the entry price, so there is no reward. Enter a target away from the entry.');
    if ((stop < entry) === (target < entry)) {
      throw new RiskRewardError('rr-target', 'The stop and the target are on the same side of the entry. For a long trade the stop is below the entry and the target above it; for a short trade, the other way round.');
    }
    side = stop < entry ? 'long' : 'short';
    risk = Math.abs(entry - stop);
    reward = Math.abs(target - entry);
    r = reward / risk;
  } else {
    r = ratio;
  }
  const breakEven = 1 / (1 + r);
  const expectancy = winRate === null ? null : winRate * r - (1 - winRate);
  return { side, risk, reward, r, breakEven, winRate, expectancy };
}

function mode() { return document.querySelector('input[name="rr-mode"]:checked').value; }

function syncMode() {
  const prices = mode() === 'prices';
  $('rr-prices').hidden = !prices;
  $('rr-ratio-box').hidden = prices;
}

const decimalsOf = (x) => { const s = String(x); return s.includes('.') ? s.split('.')[1].length : 0; };
const signed = (x, dp) => (x > 0 ? '+' : x < 0 ? MINUS : '') + plain(Math.abs(x), dp);
const rText = (x) => `${plain(x, 2)}R`;

function calculate(ev) {
  ev.preventDefault();
  const problems = [];
  clearFieldErrors(Object.keys(LABELS), $('rr-errors'));
  const get = (id, parse = parsePositive, optional = false) => {
    if (optional && !$(id).value.trim()) return null;
    try { return parse($(id).value, LABELS[id]); } catch (e) {
      if (!(e instanceof InputError)) throw e;
      fieldError(id, e.message);
      problems.push({ id, message: e.message });
      return null;
    }
  };
  const m = mode();
  const v = { mode: m };
  if (m === 'prices') {
    v.entry = get('rr-entry'); v.stop = get('rr-stop'); v.target = get('rr-target');
    // decimals as typed ("1.08500" keeps five), so the formula reads like the inputs
    v.dp = Math.max(2, ...['rr-entry', 'rr-stop', 'rr-target'].map((id) => decimalsOf($(id).value.trim())));
  } else {
    v.ratio = get('rr-ratio');
  }
  const wr = get('rr-winrate', parseNonNegative, true);
  if (wr !== null && wr > 100) {
    const msg = 'The win rate cannot be more than 100.';
    fieldError('rr-winrate', msg);
    problems.push({ id: 'rr-winrate', message: msg });
  }
  v.winRate = wr === null || wr > 100 ? null : wr / 100;
  let out = null;
  if (!problems.length) {
    try { out = riskReward(v); } catch (e) {
      if (!(e instanceof RiskRewardError)) throw e;
      fieldError(e.id, e.message);
      problems.push({ id: e.id, message: e.message });
    }
  }
  if (problems.length) { $('rr-out').hidden = true; showProblems($('rr-errors'), problems); return; }
  render(v, out);
}

function stat(label, value, key) {
  return el('div', { class: 'stat' }, el('dt', { text: label }), el('dd', { 'data-k': key, text: value }));
}

function render(v, o) {
  const lines = [];
  if (v.mode === 'prices') {
    const dp = Math.min(10, v.dp);
    lines.push(`Risk   = |entry − stop|   = |${plain(v.entry, dp)} − ${plain(v.stop, dp)}| = ${plain(o.risk, dp)}`);
    lines.push(`Reward = |target − entry| = |${plain(v.target, dp)} − ${plain(v.entry, dp)}| = ${plain(o.reward, dp)}`);
    lines.push(`R multiple = reward ÷ risk = ${plain(o.reward, dp)} ÷ ${plain(o.risk, dp)} = ${plain(o.r, 2)}`);
  } else {
    lines.push(`R multiple = ${plain(o.r, 2)} (typed in)`);
  }
  lines.push(`Break-even win rate = 1 ÷ (1 + R) = 1 ÷ (1 + ${plain(o.r, 2)}) = ${pct(o.breakEven)}`);
  if (o.expectancy !== null) {
    lines.push(`Expectancy = win rate × R − loss rate × 1R = ${pct(o.winRate)} × ${rText(o.r)} − ${pct(1 - o.winRate)} × 1R = ${signed(o.expectancy, 2)}R`);
  }
  const kids = [
    el('h2', { id: 'rr-out-h', tabindex: '-1', text: 'Result' }),
    el('dl', { class: 'stats' },
      o.side ? stat('Direction', o.side === 'long' ? 'Long' : 'Short', 'side') : null,
      stat('R multiple (reward ÷ risk)', rText(o.r), 'r'),
      stat('Break-even win rate', pct(o.breakEven), 'break_even'),
      o.expectancy !== null ? stat(`Expectancy at a ${pct(o.winRate)} win rate`, `${signed(o.expectancy, 2)}R`, 'expectancy') : null),
  ];
  if (o.expectancy === null) {
    kids.push(el('p', { class: 'small muted', id: 'rr-no-winrate', text: 'Enter a win rate above to see the expectancy per trade in R at that win rate.' }));
  }
  kids.push(el('h3', { text: 'The arithmetic, with your numbers' }),
    el('pre', { class: 'formula', tabindex: '0', role: 'region', 'aria-label': 'The formula with your numbers', text: lines.join('\n') }),
    el('p', { class: 'small muted', text: 'Arithmetic on the numbers you entered. A loss is counted as exactly 1R and a win as exactly the R multiple; real exits, partial closes, slippage and fees move both. It is not a suggestion of what ratio, win rate or trade to use.' }));
  $('rr-out').replaceChildren(...kids.filter(Boolean));
  $('rr-out').hidden = false;
  $('rr-out-h').focus();
}

function init() {
  for (const r of document.querySelectorAll('input[name="rr-mode"]')) r.addEventListener('change', syncMode);
  $('rr-form').addEventListener('submit', calculate);
  $('rr-js-needed').hidden = true;
  $('rr-form').hidden = false;
  syncMode();
}

if (typeof document !== 'undefined' && document.getElementById('rr-form')) init();
