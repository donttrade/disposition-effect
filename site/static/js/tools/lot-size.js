// lot-size.js — /tools/lot-size-calculator/: arithmetic on the visitor's own inputs.
//
// NON-ADVISER CONCERN 4: this sits next to "position-size suggestions", so:
//  * no input has a default (the risk % in particular starts blank and stays the user's);
//  * the output is labelled as arithmetic, with the formula filled in;
//  * nothing on the page proposes, rates or compares a risk level.
// Strict number input (num.js): anything that reads two ways is refused, never guessed.

import { parsePositive, InputError } from './num.js';
import { el, plain } from './format.js';

const $ = (id) => document.getElementById(id);
const LABELS = {
  'ls-balance': 'the account balance', 'ls-risk': 'the risk amount', 'ls-stop': 'the stop distance',
  'ls-vpp': 'the value per point for one lot', 'ls-step': 'the lot step',
};

function riskMode() { return document.querySelector('input[name="ls-mode"]:checked').value; }

function syncMode() {
  const pctMode = riskMode() === 'pct';
  $('ls-risk-label').textContent = pctMode ? 'Risk, as a % of the balance' : 'Risk, as an amount';
  $('ls-risk-hint').textContent = pctMode
    ? 'The share of the balance you would lose if the stop is hit. There is no default: the number is yours.'
    : 'What you would lose if the stop is hit, in your account currency. There is no default: the number is yours.';
  $('ls-balance-opt').hidden = pctMode;
}

function decimalsOf(x) {
  const s = String(x);
  return s.includes('.') ? s.split('.')[1].length : 0;
}

// Pure calculation, exported for the tests. Inputs are already-validated numbers.
export function lotSize({ mode, balance, risk, stop, vpp, step }) {
  const riskAmount = mode === 'pct' ? (balance * risk) / 100 : risk;
  const perLot = stop * vpp;               // loss for one lot if the stop is hit
  const lots = riskAmount / perLot;
  const out = { riskAmount, perLot, lots, step: step ?? null, rounded: null, riskAtRounded: null, belowMin: false };
  if (step) {
    // Round DOWN to the broker's step, so the rounded size never risks more than entered.
    // The 1e-9 guards against 0.3/0.1 = 2.9999999999999996 style float noise.
    const k = Math.floor(lots / step + 1e-9);
    out.rounded = Number((k * step).toFixed(decimalsOf(step)));
    out.riskAtRounded = out.rounded * perLot;
    out.belowMin = k === 0;
  }
  return out;
}

function showErrors(problems) {
  const box = $('ls-errors');
  box.replaceChildren(el('strong', { text: problems.length === 1 ? 'One input needs a change' : `${problems.length} inputs need a change` }),
    el('ul', {}, ...problems.map((x) => el('li', {}, el('a', { href: '#' + x.id, text: x.message })))));
  box.hidden = false;
  box.focus();
}

function calculate(ev) {
  ev.preventDefault();
  const problems = [];
  for (const id of Object.keys(LABELS)) {
    $(id).removeAttribute('aria-invalid');
    $(id + '-err').hidden = true;
  }
  $('ls-errors').hidden = true;
  const get = (id, optional) => {
    if (optional && !$(id).value.trim()) return null;
    try { return parsePositive($(id).value, LABELS[id]); } catch (e) {
      if (!(e instanceof InputError)) throw e;
      $(id).setAttribute('aria-invalid', 'true');
      $(id + '-err').textContent = e.message;
      $(id + '-err').hidden = false;
      problems.push({ id, message: e.message });
      return null;
    }
  };
  const mode = riskMode();
  const v = {
    mode,
    balance: get('ls-balance', mode !== 'pct'),
    risk: get('ls-risk'),
    stop: get('ls-stop'),
    vpp: get('ls-vpp'),
    step: get('ls-step', true),
  };
  if (mode === 'pct' && v.risk !== null && v.risk > 100) {
    const msg = 'The risk % cannot be more than 100.';
    $('ls-risk').setAttribute('aria-invalid', 'true');
    $('ls-risk-err').textContent = msg; $('ls-risk-err').hidden = false;
    problems.push({ id: 'ls-risk', message: msg });
  }
  if (problems.length) { $('ls-out').hidden = true; showErrors(problems); return; }
  render(v, lotSize(v));
}

function render(v, r) {
  const n = (x, dp = 2) => plain(x, dp);
  const lines = [];
  if (v.mode === 'pct') lines.push(`Risk amount = ${n(v.balance)} × ${n(v.risk, decimalsOf(v.risk))}% = ${n(r.riskAmount)}`);
  lines.push(`Loss for one lot at the stop = ${n(v.stop, Math.max(2, decimalsOf(v.stop)))} points × ${n(v.vpp, Math.max(2, decimalsOf(v.vpp)))} per point = ${n(r.perLot)}`);
  lines.push(`Lots = ${n(r.riskAmount)} ÷ ${n(r.perLot)} = ${n(r.lots, 4)}`);
  const kids = [
    el('h2', { id: 'ls-out-h', tabindex: '-1', text: 'Result' }),
    el('dl', { class: 'stats' },
      el('div', { class: 'stat' }, el('dt', { text: 'Position size' }), el('dd', { 'data-k': 'lots', text: `${n(r.lots, 4)} lots` })),
      r.step ? el('div', { class: 'stat' }, el('dt', { text: `Rounded down to steps of ${v.step}` }), el('dd', { 'data-k': 'rounded', text: `${n(r.rounded, decimalsOf(v.step))} lots` })) : null,
      el('div', { class: 'stat' }, el('dt', { text: r.step ? 'Loss at the stop, rounded size' : 'Loss at the stop' }),
        el('dd', { 'data-k': 'risk_at', text: n(r.step ? r.riskAtRounded : r.riskAmount) })),
      v.balance ? el('div', { class: 'stat' }, el('dt', { text: 'As a % of the balance' }),
        el('dd', { 'data-k': 'risk_pct', text: `${n((100 * (r.step ? r.riskAtRounded : r.riskAmount)) / v.balance, 2)}%` })) : null),
  ];
  if (r.belowMin) {
    kids.push(el('p', { class: 'notice notice-caution', id: 'ls-belowmin' }, el('strong', { text: 'Smaller than one lot step' }),
      `Even ${v.step} lots would lose ${n(v.step * r.perLot)} at this stop, more than the ${n(r.riskAmount)} entered. Rounded down, the size is 0 lots.`));
  }
  kids.push(el('h3', { text: 'The arithmetic, with your numbers' }),
    el('pre', { class: 'formula', tabindex: '0', role: 'region', 'aria-label': 'The formula with your numbers', text: lines.join('\n') }),
    el('p', { class: 'small muted', text: 'Arithmetic on the numbers you entered, in your account currency. It is not a suggestion of what to risk or trade. Spread, commission and slippage are not included.' }));
  $('ls-out').replaceChildren(...kids.filter(Boolean));
  $('ls-out').hidden = false;
  $('ls-out-h').focus();
}

function init() {
  for (const r of document.querySelectorAll('input[name="ls-mode"]')) r.addEventListener('change', syncMode);
  $('ls-form').addEventListener('submit', calculate);
  $('ls-js-needed').hidden = true;
  $('ls-form').hidden = false;
  syncMode();
}

if (typeof document !== 'undefined' && document.getElementById('ls-form')) init();
