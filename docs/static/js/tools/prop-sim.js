// prop-sim.js — /tools/prop-challenge-simulator/.
//
// File mode: the trade file is parsed in this tab (in a Web Worker, read-file.js, so a large
// file never freezes the page) by the same engine as the dashboard,
// reduced to one list of realised results per trading day, and only those numbers go to
// the worker. Manual mode: four summary numbers. Either way the page's CSP is
// connect-src 'none', nothing is stored, nothing is logged.

import { createFileSlot, renderReadError, whileBusy, clearFieldErrors, fieldError, showProblems, revealResult } from './tool-state.js?v=7534a30f';
import { RUNS, DEFAULT_SEED, tradingDays } from './prop-sim-core.js?v=ef3c575e';
import { money, unitNote, pct, intText, el, DASH } from './format.js?v=acb0db51';
import { parseStrict, parsePositive, parseWhole, InputError } from './num.js?v=8df99e34';

const $ = (id) => document.getElementById(id);
const MIN_STREAK_BUSTS = 30; // fewer busts than this: too few to describe what led up to them
const plural = (n, one, many) => `${intText(n)} ${n === 1 ? one : many}`;  // "1 day", "2 days" (launch NIT N1)
let loaded = null;           // {days, unit, n, label} — the file's trading days, in memory only
let worker = null;
let slot = null;             // the file being read or on screen (tool-state.js, Tester R1-R3)

function mode() { return document.querySelector('input[name="ps-mode"]:checked').value; }

function syncMode() {
  const file = mode() === 'file';
  $('ps-file-fields').hidden = !file;
  $('ps-manual-fields').hidden = file;
}

// ------------------------------------------------------------------ file input
function setFileStatus(text) {
  const s = $('ps-file-status');
  s.textContent = text;
  s.hidden = !text;
}

function clearFile() {
  loaded = null;
  setFileStatus('');
  $('ps-file-error').hidden = true;
}

function showLoaded(out, label) {
  const r = out.result;
  loaded = { days: tradingDays(r.trades), unit: r.trades[0].pnl_unit, n: r.trades.length, label,
    beta: !r.verified_format };
  setFileStatus(`Read ${label}: ${plural(loaded.n, 'closed trade', 'closed trades')} on ${plural(loaded.days.length, 'trading day', 'trading days')}.` +
    (loaded.beta ? ' This file format is in beta.' : ''));
}

// ------------------------------------------------------------------ validation
const FIELDS = {
  'ps-target': 'the profit target', 'ps-daily': 'the daily loss limit', 'ps-maxloss': 'the maximum loss',
  'ps-days': 'the time limit', 'ps-mindays': 'the minimum trading days', 'ps-seed': 'the seed',
  'ps-wr': 'the win rate', 'ps-avgwin': 'the average win', 'ps-avgloss': 'the average loss', 'ps-tpd': 'the trades per day',
};

function clearErrors() { clearFieldErrors(Object.keys(FIELDS), $('ps-errors')); }

function read() {
  clearErrors();
  const problems = [];
  const get = (id, fn) => {
    try { return fn($(id).value, FIELDS[id]); } catch (e) {
      if (!(e instanceof InputError)) throw e;
      fieldError(id, e.message);
      problems.push({ id, message: e.message });
      return null;
    }
  };
  const optional = (id, fn) => ($(id).value.trim() === '' ? undefined : get(id, fn));
  const timeLimit = get('ps-days', (v, l) => parseWhole(v, l, 1, 365));
  const rules = {
    target: get('ps-target', parsePositive),
    daily_loss: optional('ps-daily', parsePositive) ?? null,
    max_loss: get('ps-maxloss', parsePositive),
    trailing: document.querySelector('input[name="ps-trail"]:checked').value === 'trailing',
    time_limit: timeLimit,
    min_days: optional('ps-mindays', (v, l) => parseWhole(v, l, 0, timeLimit || 365)) ?? 0,
  };
  const seed = get('ps-seed', (v, l) => parseWhole(v, l, 0, 4294967295));
  const p = { rules, seed, runs: RUNS, mode: mode() };
  if (p.mode === 'file') {
    if (!loaded) problems.push({ id: 'ps-file', message: 'Choose a trade file, or try the sample file, or switch to manual numbers.' });
    else p.days = loaded.days;
  } else {
    const wr = get('ps-wr', parseStrict);
    if (wr !== null && (wr < 0 || wr > 100)) {
      fieldError('ps-wr', 'The win rate has to be between 0 and 100.');
      problems.push({ id: 'ps-wr', message: 'The win rate has to be between 0 and 100.' });
    }
    p.win_rate = wr === null ? null : wr / 100;
    p.avg_win = get('ps-avgwin', parsePositive);
    p.avg_loss = get('ps-avgloss', parsePositive);
    p.trades_per_day = get('ps-tpd', (v, l) => parseWhole(v, l, 1, 50));
  }
  if (problems.length) { showProblems($('ps-errors'), problems); return null; }
  return p;
}

// ------------------------------------------------------------------ run and render
async function run(ev) {
  ev.preventDefault();
  // A file still being read: wait for it, whichever way it ends (result, error, a newer pick,
  // an emptied picker), with Run disabled meanwhile and always re-enabled after (R1).
  if (mode() === 'file' && slot.state === 'reading') await whileBusy($('ps-run'), () => slot.settled());
  const p = read();
  if (!p) return;
  if (worker) worker.terminate();
  $('ps-out').hidden = true;
  if ($('ps-teaser')) $('ps-teaser').hidden = true;
  const st = $('ps-status');
  st.textContent = `Running ${intText(p.runs)} simulated challenges…`;
  st.hidden = false;
  const btn = $('ps-run');
  btn.disabled = true;
  const failed = () => {
    if (worker) { worker.terminate(); worker = null; }
    btn.disabled = false;
    st.textContent = 'The simulation could not run in this browser. Press Run to try again.';
    st.hidden = false;
  };
  worker = new Worker(new URL('./prop-sim-worker.js?v=97f872c9', import.meta.url), { type: 'module' });
  worker.onmessage = (e) => {
    worker.terminate(); worker = null;
    btn.disabled = false;
    st.hidden = true;
    if (!e.data || e.data.error || !e.data.result) { failed(); return; }
    render(p, e.data.result);
  };
  worker.onerror = (e) => { if (e && e.preventDefault) e.preventDefault(); failed(); };
  worker.onmessageerror = failed;
  worker.postMessage(p);
}

const NS = 'http://www.w3.org/2000/svg';
function bars(rows) {
  // Three bars from zero, labelled directly; the table below holds the same numbers.
  const W = 400, rowH = 34, x0 = 110, span = W - x0 - 64;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${rowH * rows.length + 8}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', rows.map((r) => `${r.label} ${pct(r.share)}`).join(', '));
  rows.forEach((r, i) => {
    const y = 4 + i * rowH;
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', '0'); t.setAttribute('y', String(y + 17)); t.setAttribute('class', 'bar-label'); t.textContent = r.label;
    const b = document.createElementNS(NS, 'rect');
    b.setAttribute('x', String(x0)); b.setAttribute('y', String(y + 4));
    b.setAttribute('width', String(Math.max(1, r.share * span))); b.setAttribute('height', '18'); b.setAttribute('class', r.cls);
    const v = document.createElementNS(NS, 'text');
    v.setAttribute('x', String(x0 + Math.max(1, r.share * span) + 6)); v.setAttribute('y', String(y + 17));
    v.setAttribute('class', 'bar-label'); v.textContent = pct(r.share);
    svg.append(t, b, v);
  });
  const axis = document.createElementNS(NS, 'line');
  axis.setAttribute('x1', String(x0)); axis.setAttribute('x2', String(x0)); axis.setAttribute('y1', '2');
  axis.setAttribute('y2', String(rowH * rows.length + 6)); axis.setAttribute('class', 'grid-line');
  svg.append(axis);
  return svg;
}

function render(p, res) {
  const unit = p.mode === 'file' ? loaded.unit : 'account';
  const m = (n) => money(n, unit, { sign: false });
  const rows = [
    { key: 'pass', label: 'Passed', n: res.pass, share: res.pass / res.runs, cls: 'bar-gain' },
    { key: 'bust', label: 'Busted', n: res.bust, share: res.bust / res.runs, cls: 'bar-loss' },
    { key: 'timeout', label: 'Ran out of time', n: res.timeout, share: res.timeout / res.runs, cls: 'bar-plain' },
  ];
  const source = p.mode === 'file'
    ? `whole trading days drawn at random from ${loaded.label} (${plural(loaded.days.length, 'day', 'days')}, ${plural(loaded.n, 'trade', 'trades')})`
    : `${plural(p.trades_per_day, 'trade', 'trades')} a day, each a win of ${m(p.avg_win)} with probability ${pct(p.win_rate)} or a loss of ${m(p.avg_loss)}`;
  const r = p.rules;
  const rulesText = `Profit target ${m(r.target)}; daily loss limit ${r.daily_loss === null ? 'none' : m(r.daily_loss)}; ` +
    `maximum loss ${m(r.max_loss)} (${r.trailing ? 'trailing the highest end-of-day balance' : 'static, from the starting balance'}); ` +
    `${plural(r.time_limit, 'trading day', 'trading days')}; at least ${plural(r.min_days, 'trading day', 'trading days')} to pass; seed ${p.seed}.`;
  const table = el('table', {},
    el('caption', { text: `Outcome of ${intText(res.runs)} simulated challenges` }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Outcome' }), el('th', { scope: 'col', class: 'num', text: 'Runs' }), el('th', { scope: 'col', class: 'num', text: 'Share' }))),
    el('tbody', {}, ...rows.map((x) => el('tr', { 'data-outcome': x.key },
      el('th', { scope: 'row', text: x.label }), el('td', { class: 'num', text: intText(x.n) }), el('td', { class: 'num', text: pct(x.share) })))));
  const facts = [
    ['Busted on the daily loss limit', intText(res.bust_daily), 'bust_daily'],
    ['Busted on the maximum loss', intText(res.bust_max), 'bust_max'],
    ['Median trading days to pass (passed runs)', res.median_pass_days === null ? DASH : intText(res.median_pass_days), 'median_pass_days'],
  ];
  const out = $('ps-out');
  const warn = [];
  if (p.mode === 'file' && loaded.days.length < 30) warn.push(`Your file has ${plural(loaded.days.length, 'trading day', 'trading days')}, so the results lean heavily on a few days.`);
  if (p.mode === 'file' && loaded.beta) warn.push('This file format is in beta: check a few trades by hand on the trade-stats page.');
  out.replaceChildren(...[
    el('h2', { id: 'ps-out-h', tabindex: '-1', text: `Results: ${intText(res.runs)} simulated challenges` }),
    el('p', { class: 'notice' }, el('strong', { text: 'A simulation of past trades, not a prediction' }),
      `Each run is built from ${source}. ${unitNote(unit)}`),
    warn.length ? el('div', { class: 'notice notice-caution' }, el('strong', { text: 'Note' }), el('ul', {}, ...warn.map((w) => el('li', { text: w })))) : null,
    el('figure', { class: 'chart chart-bars' }, bars(rows),
      el('figcaption', { text: `n = ${intText(res.runs)} runs · ${p.mode === 'file' && loaded.label === 'the synthetic sample file' ? 'synthetic sample data, not a real trader' : 'from your inputs'}` })),
    el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': 'Outcomes as a table' }, table),
    el('dl', { class: 'stats' }, ...facts.map(([l, v, k]) => el('div', { class: 'stat' }, el('dt', { text: l }), el('dd', { text: v, 'data-k': k })))),
    el('p', { id: 'ps-streak', 'data-busts': String(res.bust), text: streakLine(res) }),
    el('p', { class: 'small muted', text: `Rules used: ${rulesText}` })].filter(Boolean)); // no empty slot becomes the text "null"
  out.hidden = false;
  revealResult($('ps-out-h'));
  if (!$('ps-teaser')) return; // paid_report on: partials/tool_next_step.html is the one offer
  $('ps-teaser-text').textContent = teaser(res);
  $('ps-teaser').hidden = false;
}

function streakLine(res) {
  if (res.bust < MIN_STREAK_BUSTS) return `Too few runs busted (${intText(res.bust)}) to say what led up to them.`;
  return `${pct(res.bust_after_streak / res.bust)} of the busted runs broke a limit on a trade that came after 2 or more losses in a row (${intText(res.bust_after_streak)} of ${intText(res.bust)}).`;
}

// R5: the teaser box says data-on-sale="true" when the build sells the report (partials/trader_offer.html).
const reportLead = () => ($('ps-teaser').dataset.onSale === 'true' ? 'The habit report' : "We're building a habit report that");

function teaser(res) {
  if (res.bust < MIN_STREAK_BUSTS) {
    return `${reportLead()} looks at what you do after a loss in your real record.`;
  }
  return `${pct(res.bust_after_streak / res.bust)} of the busted runs began after 2 or more losses in a row. ${reportLead()} tests whether your trading changes after losses in your real record, and what that cost.`;
}

// ------------------------------------------------------------------ wiring
function init() {
  for (const r of document.querySelectorAll('input[name="ps-mode"]')) r.addEventListener('change', syncMode);
  slot = createFileSlot({
    progressBox: $('ps-progress'), onStage: setFileStatus, onClear: clearFile, onResult: showLoaded,
    onError: (err, retry) => renderReadError($('ps-file-error'), err, retry),
  });
  $('ps-file').addEventListener('change', (e) => slot.pickFile(e.target.files[0], 'your file'));
  $('ps-sample-btn').addEventListener('click', () => {
    // QA 25 Oct: the sample also fills example rules (only boxes still empty), so Run works at once
    for (const [id, v] of [['ps-target', '600'], ['ps-daily', '250'], ['ps-maxloss', '500'], ['ps-days', '60']]) {
      if ($(id).value.trim() === '') $(id).value = v;
    }
    slot.readBytes(new TextEncoder().encode($('ps-sample').textContent.replace(/^\s+/, '')), 'the synthetic sample file');
  });
  $('ps-form').addEventListener('submit', run);
  if (!$('ps-seed').value) $('ps-seed').value = String(DEFAULT_SEED);
  $('ps-js-needed').hidden = true;
  $('ps-form').hidden = false;
  syncMode();
}

init();
