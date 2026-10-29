// prop-sim.js — the Challenge Readiness Check, /tools/prop-challenge-simulator/ (ARCHITECT-CHALLENGE-READINESS
// Revision 2: the page batches R4, R4b, R4c, R5, R7).
//
// The trades are read in this tab: a file or a pasted table goes through the shared reader (tool-state.js →
// read-file.js → the engine's runFile / runFiles, with the importer's presets), so every format the site reads
// works here. Days are grouped by the firm's day boundary and the file's time zone (prop-sim-core.js groupDays),
// and only numbers go to the worker: the results of each day's trades and their times within the day.
// The page then shows three plain visuals, "Try a rule" (the same paired replays with one or two rules from a
// fixed list), Expert details with the raw numbers and a results-only CSV/JSON export, and a share card.
// Nothing is stored. With [flags] analytics on, a finished step loads a counting page in a hidden frame (count()).
// Ranked suggestions are not on this page (whatif_ranked); neither is saving.

import { createFileSlot, renderReadError, whileBusy, clearFieldErrors, fieldError, showProblems, revealResult } from './tool-state.js';
import { RUNS, DEFAULT_SEED, NO_LIMIT_CAP, METHOD_VERSION, WHATIF_TEXT, groupDays, simulate, ruleLabel, mcError, unavailableText, personalUnavailable, normRules } from './prop-sim-core.js';
import { presetRules, NOT_STATED } from './challenge-presets.js';
import { HABITS, HABIT_TEXT, itemsFromTrades, isDatesOnly, habitFlags, dayFlags, realBreachDays, simulatedHabits, countFlags, MIN_BREACH_DAYS, MIN_BUSTS } from './habit-flags.js';
import { drawCard, cardBlob, altText } from '../card/readiness-card.js';
import { money, unitNote, pct, intText, el, DASH } from './format.js';
import { parseStrict, parsePositive, parseNonNegative, parseWhole, InputError } from './num.js';
import { SAMPLE_LABEL, FORMAT_NAMES, plural, tableWrap, rowsTable } from './file-tool.js';

const $ = (id) => document.getElementById(id);
const MIN_RULE_BUSTS = 30;   // fewer busts: too few to say which rule broke most (as the old streak line)
const COUNT_PATH = '/tools/prop-challenge-simulator/e/';
let presets = { presets: [], firms: [], rules_lib: '' };
let loaded = null;     // the trades read, in memory only: {trades, label, format, tz_label, beta, unit, datesOnly, flags}
let current = null;    // the preset picked (or null) and the rules it filled in
let last = null;       // the latest check: {p, res, seq, real, sim, ...}
let lastWhatIf = null;
let lastRange = null;
let worker = null;
let slot = null;
const counted = new Set();

const whole = (x) => `${Math.round(x * 100)}%`;
function mode() { return document.querySelector('input[name="ps-mode"]:checked').value; }

// ------------------------------------------------------------------ counting (live analytics only)
function count(name) {
  if ($('ps-form').dataset.stepsCounted !== 'on' || counted.has(name)) return;
  counted.add(name);
  const f = el('iframe', { src: `${COUNT_PATH}${name}/`, hidden: true, 'aria-hidden': 'true', tabindex: '-1', title: 'Count', class: 'rc-count' });
  document.body.append(f);
  setTimeout(() => f.remove(), 15000);
}

// ------------------------------------------------------------------ modes and the trade input
function syncMode() {
  const m = mode();
  $('ps-file-fields').hidden = m !== 'file';
  $('ps-paste-fields').hidden = m !== 'paste';
  $('ps-manual-fields').hidden = m !== 'manual';
  $('ps-tz-fields').hidden = m === 'manual';
  syncTz();
}

function syncTz() {
  const off = $('ps-filetz').value === 'offset';
  $('ps-filetz-offset').closest('.field').hidden = !off;
}

function setFileStatus(text) {
  const s = $('ps-file-status');
  s.textContent = text;
  s.hidden = !text;
}

function clearFile() {
  loaded = null;
  setFileStatus('');
  $('ps-file-error').hidden = true;
  $('ps-map').hidden = true;
  $('ps-map').replaceChildren();
}

// A table whose headings leave a needed column unnamed (TradeLocker's "Amount" was one): one choice per
// missing field, from the file's own headings, then the same table is read again with those columns.
const MAP_NAMES = {
  date: 'Date and time', symbol: 'Symbol', side: 'Buy or sell', qty: 'Quantity (size)', price: 'Price',
  open_time: 'Open time', close_time: 'Close time', direction: 'Long or short', open_price: 'Open price', close_price: 'Close price',
};
function showMapStep(need, choose) {
  const box = $('ps-map');
  const taken = new Set(Object.values(need.chosen));
  const options = need.labels.map((l, i) => [i, l || `Column ${i + 1}`]).filter(([i]) => !taken.has(i));
  const err = el('p', { class: 'error', id: 'ps-map-err', hidden: true });
  const fields = need.missing.map((f) => el('div', { class: 'field' },
    el('label', { for: `ps-map-${f}`, text: MAP_NAMES[f] || f }),
    el('select', { id: `ps-map-${f}`, 'data-field': f, 'aria-describedby': 'ps-map-err' },
      el('option', { value: '', text: 'Choose a column' }), ...options.map(([i, l]) => el('option', { value: String(i), text: l })))));
  const btn = el('button', { class: 'btn btn-secondary', type: 'button', id: 'ps-map-btn', text: 'Read with these columns' });
  btn.addEventListener('click', () => {
    const picked = {};
    const seen = new Set();
    for (const f of need.missing) {
      const v = $(`ps-map-${f}`).value;
      if (v === '' || seen.has(v)) {
        err.textContent = v === '' ? 'Pick a column for each box.' : 'Pick a different column for each box.';
        err.hidden = false;
        $(`ps-map-${f}`).focus();
        return;
      }
      seen.add(v);
      picked[f] = Number(v);
    }
    choose(picked);
  });
  box.replaceChildren(el('strong', { id: 'ps-map-h', text: 'Which column is which?' }),
    el('p', { text: `No heading in your ${need.missing.length === 1 ? 'table names this column' : 'table names these columns'}. Pick ${need.missing.length === 1 ? 'it' : 'each one'} from your headings.` }),
    el('div', { class: 'field-grid' }, ...fields), err, el('p', { class: 'btn-row' }, btn));
  box.hidden = false;
  box.focus();
}

function showLoaded(out, label) {
  const r = out.result;
  const datesOnly = isDatesOnly(r.trades);
  loaded = { trades: r.trades, label, format: r.format, tz_label: r.tz_label, beta: !r.verified_format,
    unit: r.trades[0].pnl_unit, datesOnly, n: r.trades.length, warnings: r.warnings };
  loaded.flags = habitFlags(itemsFromTrades(r.trades), { datesOnly });
  // the file's zone, preset by format where the format says it (MT4/MT5: the broker's server clock)
  if (label !== 'your pasted table' && !$('ps-filetz').dataset.touched) {
    $('ps-filetz').value = (r.format === 'mt5' || r.format === 'mt4') ? 'broker' : label === SAMPLE_LABEL ? 'UTC' : 'local';
    syncTz();
  }
  const days = groupDays(r.trades, {}).days.length;
  setFileStatus(`Read ${label}: ${plural(loaded.n, 'closed trade', 'closed trades')} on ${plural(days, 'trading day', 'trading days')}` +
    ` (${FORMAT_NAMES[r.format] || 'read by the site’s importer'}${loaded.beta ? ', beta' : ''}). Times are ${r.tz_label}.` +
    (datesOnly ? ' The file has dates but no times.' : ''));
}

// ------------------------------------------------------------------ presets
const NS_DEFAULT = {
  daily_loss: 'none', drawdown: 'the starting balance', trail_stop_at: 'no stop', consistency: 'none', min_days: 'none',
  count_day_if: 'any closed trade', time_limit: 'no time limit', target_check: 'the end of the day',
  day_start: 'your file’s own clock, at midnight',
};
const NS_NAMES = {
  daily_loss: 'daily loss limit', drawdown: 'where the maximum loss is measured from', trail_stop_at: 'where the moving floor stops',
  consistency: 'best-day share', min_days: 'minimum days', count_day_if: 'what counts as a trading day',
  time_limit: 'time limit', target_check: 'when the target counts', day_start: 'when the firm’s day starts',
};
const setVal = (id, v) => { $(id).value = v === null || v === undefined ? '' : String(v); };
const num2 = (x) => String(Math.round(x * 100) / 100);

function applyPreset() {
  const id = $('ps-preset').value;
  const src = $('ps-preset-source');
  for (const n of document.querySelectorAll('.ns-note')) { n.hidden = true; n.textContent = ''; }
  $('ps-ns').hidden = true;
  $('ps-limits-preset').hidden = true;
  if (!id) { current = null; src.hidden = true; src.replaceChildren(); return; }
  const p = presets.presets.find((x) => x.id === id);
  let size = null;
  try { size = $('ps-account').value.trim() ? parsePositive($('ps-account').value, 'the account size') : null; } catch (e) { size = null; }
  if (!size) { size = p.account_size; setVal('ps-account', size); }
  const pr = presetRules(p, size);
  const r = pr.rules;
  setVal('ps-target', num2(r.target));
  setVal('ps-daily', r.daily_loss === null ? '' : num2(r.daily_loss));
  setVal('ps-maxloss', num2(r.max_loss));
  document.querySelector(`input[name="ps-trail"][value="${r.drawdown}"]`).checked = true;
  setVal('ps-days', r.time_limit);
  setVal('ps-mindays', r.min_days || '');
  setVal('ps-mindays-kind', r.min_days_kind);
  setVal('ps-profmin', r.profitable_day_min ? num2(r.profitable_day_min) : '');
  setVal('ps-countday', r.count_day_if);
  setVal('ps-consistency', r.consistency === null ? '' : num2(r.consistency * 100));
  setVal('ps-stopat', r.trail_stop_at === null ? '' : num2(r.trail_stop_at));
  setVal('ps-targetcheck', r.target_check);
  setVal('ps-daytz', pr.dayStart ? pr.dayStart.tz : 'file');
  setVal('ps-dayhour', pr.dayStart ? pr.dayStart.hour : 0);
  src.replaceChildren(`Read on ${p.read_text} from ${p.firm}’s `,
    el('a', { href: p.url, rel: 'nofollow noopener', text: 'rules page' }), '. Check the firm’s current page: rules change.');
  src.hidden = false;
  for (const f of pr.notStated) {
    for (const n of document.querySelectorAll(`.ns-note[data-ns="${f}"]`)) {
      n.textContent = `Not stated by the firm. The check uses ${NS_DEFAULT[f]}.`;
      n.hidden = false;
    }
  }
  if (pr.notStated.length) {
    $('ps-ns').replaceChildren(el('strong', { text: 'Not stated by the firm' }),
      `${p.firm}’s rules page does not state: ${pr.notStated.map((f) => NS_NAMES[f]).join('; ')}. These run with the defaults shown under each box.`);
    $('ps-ns').hidden = false;
  }
  if (p.not_modelled.length) {
    $('ps-limits-preset').replaceChildren(el('p', { text: `For ${p.firm}, ${p.program}, this check does not model:` }),
      el('ul', {}, ...p.not_modelled.map((x) => el('li', { text: x }))));
    $('ps-limits-preset').hidden = false;
  }
  current = { preset: p, snapshot: null };
  current.snapshot = JSON.stringify(readRulesQuiet());
  if (!$('ps-more').open && pr.notStated.some((f) => ['consistency', 'count_day_if', 'trail_stop_at', 'target_check', 'day_start'].includes(f))) {
    $('ps-more').open = true;   // the notes under those boxes are inside "More rules"
  }
}

// ------------------------------------------------------------------ validation
const FIELDS = {
  'ps-account': 'the account size', 'ps-target': 'the profit target', 'ps-daily': 'the daily loss limit', 'ps-maxloss': 'the maximum loss',
  'ps-days': 'the time limit', 'ps-mindays': 'the minimum days', 'ps-profmin': 'the profitable-day amount',
  'ps-consistency': 'the best-day share', 'ps-stopat': 'where the floor stops', 'ps-dayhour': 'the hour', 'ps-seed': 'the starting number',
  'ps-filetz': 'the time zone', 'ps-filetz-offset': 'the hours from UTC', 'ps-paste': 'the table',
  'ps-wr': 'the win rate', 'ps-avgwin': 'the average win', 'ps-avgloss': 'the average loss', 'ps-tpd': 'the trades per day',
};

function clearErrors() { clearFieldErrors(Object.keys(FIELDS), $('ps-errors')); }

function collect(problems) {
  return (id, fn) => {
    try { return fn($(id).value, FIELDS[id]); } catch (e) {
      if (!(e instanceof InputError)) throw e;
      fieldError(id, e.message);
      problems.push({ id, message: e.message });
      return null;
    }
  };
}

function rulesFrom(get) {
  const optional = (id, fn) => ($(id).value.trim() === '' ? undefined : get(id, fn));
  const timeLimit = optional('ps-days', (v, l) => parseWhole(v, l, 1, 365));
  const cons = optional('ps-consistency', (v, l) => {
    const x = parsePositive(v, l);
    if (x > 100) throw new InputError(`Enter ${l} as a percentage up to 100.`);
    return x / 100;
  });
  return {
    target: get('ps-target', parsePositive),
    daily_loss: optional('ps-daily', parsePositive) ?? null,
    max_loss: get('ps-maxloss', parsePositive),
    drawdown: document.querySelector('input[name="ps-trail"]:checked').value,
    trail_stop_at: optional('ps-stopat', parseNonNegative) ?? null,
    consistency: cons ?? null,
    time_limit: timeLimit ?? null,
    min_days: optional('ps-mindays', (v, l) => parseWhole(v, l, 0, 365)) ?? 0,
    min_days_kind: $('ps-mindays-kind').value,
    profitable_day_min: optional('ps-profmin', parseNonNegative) ?? 0,
    count_day_if: $('ps-countday').value,
    target_check: $('ps-targetcheck').value,
  };
}

function readRulesQuiet() {
  const get = (id, fn) => { try { return fn($(id).value, FIELDS[id]); } catch (e) { return null; } };
  return rulesFrom(get);
}

function fileTz(get) {
  const v = $('ps-filetz').value;
  if (v === 'local') return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  if (v === 'offset') {
    const h = get('ps-filetz-offset', (raw, l) => {
      const x = parseStrict(raw, l);
      if (x < -14 || x > 14 || Math.round(x * 4) !== x * 4) throw new InputError(`Enter ${l} between -14 and 14, in quarter hours.`);
      return x;
    });
    return h === null ? null : { offset_min: h * 60 };
  }
  return v;
}

function read() {
  clearErrors();
  const problems = [];
  const get = collect(problems);
  const optional = (id, fn) => ($(id).value.trim() === '' ? undefined : get(id, fn));
  const accountSize = optional('ps-account', parsePositive) ?? null;
  const rules = rulesFrom(get);
  const seed = get('ps-seed', (v, l) => parseWhole(v, l, 0, 4294967295));
  const hour = $('ps-dayhour').value.trim() === '' ? 0 : get('ps-dayhour', (v, l) => parseWhole(v, l, 0, 23));
  const m = mode();
  const p = { rules, seed, runs: RUNS, stream: 'paired', mode: m === 'manual' ? 'manual' : 'file' };
  let grouped = null, dayStart = null, ftz = null;
  if (m === 'manual') {
    const wr = get('ps-wr', parseStrict);
    if (wr !== null && (wr < 0 || wr > 100)) {
      fieldError('ps-wr', 'The win rate has to be between 0 and 100.');
      problems.push({ id: 'ps-wr', message: 'The win rate has to be between 0 and 100.' });
    }
    p.win_rate = wr === null ? null : wr / 100;
    p.avg_win = get('ps-avgwin', parsePositive);
    p.avg_loss = get('ps-avgloss', parsePositive);
    p.trades_per_day = get('ps-tpd', (v, l) => parseWhole(v, l, 1, 50));
  } else {
    if (!loaded && slot.state === 'mapping') {
      problems.push({ id: 'ps-map', message: 'Pick the columns above, then press Read with these columns.' });
    } else if (!loaded) {
      const msg = m === 'paste' ? 'Paste a table and press Read the table, or switch to a file or summary numbers.'
        : 'Choose a trade file, or try the example data, or switch to summary numbers.';
      problems.push({ id: m === 'paste' ? 'ps-paste' : 'ps-file', message: msg });
    }
    if (loaded && !$('ps-filetz').value) {
      const msg = 'Choose the time zone of the times in your trades.';
      fieldError('ps-filetz', msg);
      problems.push({ id: 'ps-filetz', message: msg });
    } else if (loaded) ftz = fileTz(get);
    if (hour !== null) dayStart = { tz: $('ps-daytz').value, hour };
    if (loaded && ftz !== null && hour !== null) {
      grouped = groupDays(loaded.trades, { fileTz: ftz, dayStart });
      Object.assign(p, { days: grouped.days, open_s: grouped.open_s, close_s: grouped.close_s, dates_only: loaded.datesOnly });
    }
  }
  if (problems.length) { showProblems($('ps-errors'), problems); return null; }
  try { normRules(rules); } catch (e) {   // the engine's own check, as a last guard
    showProblems($('ps-errors'), [{ id: 'ps-target', message: e.message }]);
    return null;
  }
  return { p, accountSize, grouped, dayStart, fileTz: ftz };
}

// ------------------------------------------------------------------ the worker
function work(msg, statusEl, text) {
  if (worker) worker.terminate();
  statusEl.textContent = text;
  statusEl.hidden = false;
  return new Promise((resolve) => {
    worker = new Worker(new URL('./prop-sim-worker.js', import.meta.url), { type: 'module' });
    const fail = () => { if (worker) { worker.terminate(); worker = null; } resolve(null); };
    worker.onmessage = (e) => { worker.terminate(); worker = null; resolve(e.data && !e.data.error ? e.data : null); };
    worker.onerror = (e) => { if (e && e.preventDefault) e.preventDefault(); fail(); };
    worker.onmessageerror = fail;
    worker.postMessage(msg);
  });
}

async function run(ev) {
  ev.preventDefault();
  if (mode() !== 'manual' && slot.state === 'reading') await whileBusy($('ps-run'), () => slot.settled());
  const input = read();
  if (!input) return;
  const btn = $('ps-run');
  btn.disabled = true;
  const out = await work(input.p, $('ps-status'), `Running ${intText(RUNS)} replays of your past days…`);
  btn.disabled = false;
  if (!out || !out.result) {
    $('ps-status').textContent = 'The check could not run in this browser. Press Run the check to try again.';
    return;
  }
  $('ps-status').hidden = true;
  const res = out.result;
  const file = input.p.mode === 'file';
  const fd = file ? dayFlags(loaded.flags, input.grouped.index) : null;
  last = {
    ...input, res, file, fd, unit: file ? loaded.unit : 'account', preset: current ? current.preset : null,
    edited: current ? current.snapshot !== JSON.stringify(input.p.rules) : false,
    seq: file ? simulate({ mode: 'sequence', days: input.p.days, rules: input.p.rules }) : null,
    real: file ? realBreachDays(input.p.days, fd, input.p.rules.daily_loss, { datesOnly: loaded.datesOnly }) : null,
    sim: file ? simulatedHabits(res, fd, { datesOnly: loaded.datesOnly }) : null,
    example: file && loaded.label === SAMPLE_LABEL,
  };
  lastWhatIf = null;
  lastRange = null;
  render();
  if (file) count(last.example ? 'ran-sample' : 'ran');   // a finished own-file check, or one on the example data
}

// ------------------------------------------------------------------ the three visuals
const NS = 'http://www.w3.org/2000/svg';
function stackBar(res, label) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 1000 28');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('class', 'rc-bar');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', label);
  let x = 0;
  for (const [n, cls] of [[res.pass, 'tp-pass'], [res.bust, 'tp-bust'], [res.timeout, 'tp-time']]) {
    const w = (n / res.runs) * 1000;
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('x', String(x)); r.setAttribute('y', '0'); r.setAttribute('width', String(w)); r.setAttribute('height', '28');
    r.setAttribute('class', cls);
    svg.append(r);
    x += w;
  }
  return svg;
}

function shares(res) {
  return { pass: res.pass / res.runs, bust: res.bust / res.runs, timeout: res.timeout / res.runs };
}

function legend(res) {
  const s = shares(res);
  return el('ul', { class: 'rc-legend' },
    el('li', { class: 'k-pass', text: `Passed ${whole(s.pass)}` }),
    el('li', { class: 'k-bust', text: `Broke a rule ${whole(s.bust)}` }),
    el('li', { class: 'k-time', text: `Out of time ${whole(s.timeout)}` }));
}

function realOrderLine(seq, rules) {
  if (!seq) return null;
  const limit = rules.time_limit === null ? NO_LIMIT_CAP : rules.time_limit;
  if (seq.outcome === 'bust') {
    return `In their real order, your days first broke the ${seq.why === 'daily' ? 'daily loss limit' : 'maximum loss'} on day ${intText(seq.day)}.`;
  }
  if (seq.outcome === 'pass') {
    const held = seq.target_day !== null && seq.target_day < seq.day ? ` (held by a day count or the best-day share until day ${intText(seq.day)})` : '';
    return `In their real order, your days reached the target on day ${intText(seq.target_day || seq.day)}${held}.`;
  }
  const n = seq.outcome === 'end' ? seq.day_pnl.length : limit;
  return `In their real order, your days neither passed nor broke a rule in ${plural(n, 'day', 'days')}.`;
}

function ruleCard(res) {
  const kids = [el('h3', { text: 'Rule that broke most' })];
  if (res.bust === 0) kids.push(el('p', { class: 'rc-big', text: 'None' }), el('p', { text: 'No replay broke a rule.' }));
  else if (res.bust < MIN_RULE_BUSTS) {
    kids.push(el('p', { class: 'rc-big', text: DASH }), el('p', { text: `Too few replays broke a rule (${intText(res.bust)}) to say which broke most.` }));
  } else {
    const daily = res.bust_daily >= res.bust_max;
    const share = (daily ? res.bust_daily : res.bust_max) / res.bust;
    kids.push(el('p', { class: 'rc-big', text: `${daily ? 'Daily loss' : 'Maximum loss'} · ${whole(share)} of busts` }),
      el('p', { text: `Of the replays that broke a rule, ${whole(res.bust_daily / res.bust)} broke the daily loss limit and ${whole(res.bust_max / res.bust)} the maximum loss.` }));
  }
  const held = [];
  if (res.held_consistency) held.push(`${plural(res.held_consistency, 'replay', 'replays')} reached the target but waited on the best-day share`);
  if (res.held_min_days) held.push(`${plural(res.held_min_days, 'replay', 'replays')} reached the target before enough days counted`);
  if (held.length) kids.push(el('p', { class: 'small muted', text: held.join('; ') + '.' }));
  return el('div', { class: 'rc-card', id: 'ps-v-rule' }, ...kids);
}

const PILL = { hit: 'pill pill-hit', muted: 'pill pill-muted', few: 'pill pill-few', not_described: 'pill pill-muted' };
function habitsCard(real, rules) {
  const kids = [el('h3', { text: HABIT_TEXT.heading })];
  if (rules.daily_loss === null) {
    kids.push(el('p', { text: 'These rules have no daily loss limit, so no past day is a breach day.' }));
    return el('div', { class: 'rc-card', id: 'ps-v-habits' }, ...kids);
  }
  kids.push(el('p', { class: 'small muted', text: `${plural(real.n_breach, 'past day', 'past days')} reached the daily loss limit; ${plural(real.n_other_losing, 'other losing day', 'other losing days')}.` }));
  kids.push(el('ul', { class: 'rc-habits' }, ...HABITS.map((h) => {
    const x = real.habits[h];
    let pill, base = null;
    if (x.status === 'not_described') pill = HABIT_TEXT.not_described;
    else if (x.status === 'few') pill = real.n_breach < MIN_BREACH_DAYS ? HABIT_TEXT.few : 'Too few other losing days to compare';
    else {
      pill = `On ${intText(x.on_breach)} of ${intText(real.n_breach)} breach days`;
      base = `${whole(x.base)} of your other losing days`;
    }
    return el('li', { 'data-habit': h, 'data-status': x.status }, el('span', { class: 'h-name', text: HABIT_TEXT[h] }),
      el('span', {}, el('span', { class: PILL[x.status], text: pill })), base ? el('span', { class: 'h-base', text: base }) : null);
  })));
  kids.push(el('p', { class: 'small muted', text: HABIT_TEXT.by_design }));
  return el('div', { class: 'rc-card', id: 'ps-v-habits' }, ...kids);
}

function render() {
  const { res, p } = last;
  const s = shares(res);
  const headline = `Passed in ${whole(s.pass)} of ${intText(res.runs)} replays`;
  const source = last.file
    ? `whole trading days drawn at random from ${last.example ? 'the example data' : loaded.label} (${plural(p.days.length, 'day', 'days')}, ${plural(loaded.n, 'trade', 'trades')})`
    : `${plural(p.trades_per_day, 'trade', 'trades')} a day, each a win or a loss at the rate you entered`;
  const warn = [];
  if (last.file && p.days.length < 30) warn.push(`Your trades cover ${plural(p.days.length, 'trading day', 'trading days')}, so the results lean heavily on a few days.`);
  if (last.file && loaded.beta) warn.push('This file format is in beta: check a few trades by hand on the trade-stats page.');
  const outcome = el('div', { class: 'rc-card rc-card-wide', id: 'ps-v-outcome' },
    el('h3', { text: 'How the replays ended' }),
    stackBar(res, `Passed ${whole(s.pass)}, broke a rule ${whole(s.bust)}, out of time ${whole(s.timeout)}`),
    legend(res),
    el('p', { text: `Of ${intText(res.runs)} replays of ${last.file ? 'your past days' : 'your summary numbers'}, ${whole(s.pass)} passed, ${whole(s.bust)} broke a rule and ${whole(s.timeout)} ran out of time.` }),
    last.seq ? el('p', { id: 'ps-real-order', text: realOrderLine(last.seq, p.rules) }) : null);
  $('ps-out').replaceChildren(...[
    el('h2', { id: 'ps-out-h', tabindex: '-1', text: headline }),
    el('p', { class: 'notice' }, el('strong', { text: 'A replay of past trades, not a prediction' }),
      `Each replay is built from ${source}. ${unitNote(last.unit)}`),
    last.example ? el('p', { class: 'notice notice-caution' }, el('strong', { text: 'Example data' })) : null,
    warn.length ? el('div', { class: 'notice notice-caution' }, el('strong', { text: 'Note' }), el('ul', {}, ...warn.map((w) => el('li', { text: w })))) : null,
    el('div', { class: 'rc-visuals' }, outcome, ruleCard(res), last.file ? habitsCard(last.real, p.rules) : null),
  ].filter(Boolean));
  $('ps-out').hidden = false;
  renderWhatIfForm();
  $('ps-wi-out').hidden = true;
  $('ps-whatif').hidden = false;
  renderExpert();
  $('ps-expert').hidden = false;
  $('ps-share').hidden = false;
  drawShareCard();
  revealResult($('ps-out-h'));
}

// ------------------------------------------------------------------ Try a rule
const WI = {
  stop_after_losses: { label: 'Losing trades', hint: 'A whole number from 1 to 10.', dflt: '2' },
  stop_at_day_loss: { label: 'Share of the daily loss limit (%)', hint: 'From 10 to 95.', dflt: '50' },
  stop_at_day_loss_amount: { label: 'A day loss of', hint: 'An amount above zero, in your account currency.', dflt: '' },
  max_trades: { label: 'Trades a day', hint: 'A whole number from 1 to 50.', dflt: '3' },
  cooldown_s: { label: 'Minutes after a loss', hint: 'A whole number from 1 to 240.', dflt: '15' },
};

function rowKind(n) {
  const v = $(`ps-wi-rule${n}`).value;
  if (v === 'stop_at_day_loss' && last && last.p.rules.daily_loss === null) return 'stop_at_day_loss_amount';
  return v;
}

function syncWiRow(n, reset) {
  const row = document.querySelector(`[data-wi-row="${n}"]`);
  const k = rowKind(n);
  const isFactor = k === 'after_loss_factor';
  row.querySelector('[data-wi-num]').hidden = !k || isFactor;
  row.querySelector('[data-wi-factor]').hidden = !isFactor;
  if (k && !isFactor) {
    $(`ps-wi-n${n}-label`).textContent = WI[k].label;
    $(`ps-wi-n${n}-hint`).textContent = WI[k].hint;
    if (reset) $(`ps-wi-n${n}`).value = WI[k].dflt;
  }
}

function renderWhatIfForm() {
  syncWiRow(1, false);
  syncWiRow(2, false);
  const noTimes = !last.file || loaded.datesOnly;
  for (const n of [1, 2]) {
    const opt = $(`ps-wi-rule${n}`).querySelector('option[value="cooldown_s"]');
    opt.disabled = noTimes;
    opt.textContent = noTimes ? `Pause after a loss (${last.file ? 'needs times' : 'needs a file'})` : 'Pause N minutes after a loss';
    if (noTimes && $(`ps-wi-rule${n}`).value === 'cooldown_s') { $(`ps-wi-rule${n}`).value = n === 1 ? 'stop_after_losses' : ''; syncWiRow(n, true); }
  }
}

function readPersonal() {
  clearFieldErrors(['ps-wi-n1', 'ps-wi-n2'], $('ps-wi-errors'));
  const problems = [];
  const get = (id, fn, label) => {
    try { return fn($(id).value, label); } catch (e) {
      if (!(e instanceof InputError)) throw e;
      fieldError(id, e.message); problems.push({ id, message: e.message }); return null;
    }
  };
  const personal = {};
  const kinds = [];
  for (const n of [1, 2]) {
    const k = rowKind(n);
    if (!k) continue;
    if (kinds.includes(k)) { problems.push({ id: `ps-wi-rule${n}`, message: 'Pick two different rules.' }); continue; }
    kinds.push(k);
    const id = `ps-wi-n${n}`;
    if (k === 'after_loss_factor') personal[k] = Number($(`ps-wi-f${n}`).value);
    else if (k === 'stop_after_losses') personal[k] = get(id, (v, l) => parseWhole(v, l, 1, 10), 'the number of losing trades');
    else if (k === 'max_trades') personal[k] = get(id, (v, l) => parseWhole(v, l, 1, 50), 'the number of trades');
    else if (k === 'cooldown_s') { const m = get(id, (v, l) => parseWhole(v, l, 1, 240), 'the minutes'); personal[k] = m === null ? null : m * 60; }
    else if (k === 'stop_at_day_loss') personal[k] = get(id, (v, l) => { const x = parseWhole(v, l, 10, 95); return x / 100; }, 'the share');
    else if (k === 'stop_at_day_loss_amount') personal[k] = get(id, parsePositive, 'the day loss');
  }
  if (problems.length) { showProblems($('ps-wi-errors'), problems); return null; }
  return personal;
}

async function runWhatIf() {
  if (!last) return;
  const personal = readPersonal();
  if (!personal) return;
  const why = personalUnavailable(last.p, personal);
  if (why) { showProblems($('ps-wi-errors'), [{ id: 'ps-wi-rule1', message: unavailableText(why) }]); return; }
  const btn = $('ps-wi-run');
  btn.disabled = true;
  const out = await work({ op: 'whatif', p: last.p, personal }, $('ps-wi-status'), `Running the same ${intText(RUNS)} replays with your rule…`);
  btn.disabled = false;
  if (!out || !out.whatif || out.whatif.unavailable) {
    $('ps-wi-status').textContent = out && out.whatif && out.whatif.unavailable ? out.whatif.message : 'The rule could not run in this browser. Press Try this rule again.';
    return;
  }
  $('ps-wi-status').hidden = true;
  lastWhatIf = { personal, ...out.whatif };
  renderWhatIf();
  renderExpert();
  drawShareCard();
  count('whatif');
}

function renderWhatIf() {
  const { before, after, personal } = lastWhatIf;
  const b = shares(before), a = shares(after);
  const leftShare = after.trades_seen ? after.trades_left_out / after.trades_seen : 0;
  const line = `On your past days, with this rule: passed ${whole(b.pass)} → ${whole(a.pass)}, broke a rule ${whole(b.bust)} → ${whole(a.bust)}, ` +
    `out of time ${whole(b.timeout)} → ${whole(a.timeout)}. ${whole(leftShare)} of your trades were left out.`;
  $('ps-wi-out').replaceChildren(...[
    el('h3', { id: 'ps-wi-h', tabindex: '-1', text: 'Your past days with this rule' }),
    el('p', { id: 'ps-wi-rule-name', class: 'rc-big-sm', text: ruleLabel(personal, (x) => money(x, last.unit, { sign: false })) }),
    el('div', { class: 'wi-pair' },
      el('span', { class: 'wi-k', text: 'Before' }), stackBar(before, `Before: passed ${whole(b.pass)}, broke a rule ${whole(b.bust)}, out of time ${whole(b.timeout)}`),
      el('span', { class: 'wi-k', text: 'With this rule' }), stackBar(after, `With this rule: passed ${whole(a.pass)}, broke a rule ${whole(a.bust)}, out of time ${whole(a.timeout)}`)),
    el('p', { id: 'ps-wi-line', text: line }),
    el('p', { class: 'small muted', id: 'ps-wi-caveat', text: WHATIF_TEXT.caveat }),
    personal.after_loss_factor ? el('p', { class: 'small muted', text: WHATIF_TEXT.factor_caveat }) : null,
  ].filter(Boolean));
  $('ps-wi-out').hidden = false;
  revealResult($('ps-wi-h'));
}

// ------------------------------------------------------------------ Expert details
function rulesText() {
  const r = last.p.rules;
  const m = (n) => money(n, last.unit, { sign: false });
  const dd = { static: 'from the starting balance', trailing_eod: 'from the highest end-of-day balance', trailing_trade: 'from the highest balance after any trade' }[r.drawdown];
  const from = last.preset ? `${last.edited ? 'Edited from' : 'As'} ${last.preset.firm}, ${last.preset.program} (rules_lib ${presets.rules_lib}). ` : 'Custom rules. ';
  return from + `Profit target ${m(r.target)}${r.target_check === 'intraday' ? ' (counts as soon as reached)' : ''}; daily loss limit ${r.daily_loss === null ? 'none' : m(r.daily_loss)}; ` +
    `maximum loss ${m(r.max_loss)} ${dd}${r.trail_stop_at !== null && r.drawdown !== 'static' ? `, stopping at ${m(r.trail_stop_at)}` : ''}; ` +
    `${r.time_limit === null ? `no time limit (stopped at ${NO_LIMIT_CAP} trading days)` : plural(r.time_limit, 'trading day', 'trading days')}; ` +
    (r.min_days ? `at least ${plural(r.min_days, r.min_days_kind === 'profitable' ? 'profitable day' : 'trading day', r.min_days_kind === 'profitable' ? 'profitable days' : 'trading days')}` : 'no minimum days') +
    `${r.consistency === null ? '' : `; best day at most ${Math.round(r.consistency * 1000) / 10}% of the profit`}.`;
}

function settingsRows() {
  const p = last.p;
  const tz = last.fileTz && typeof last.fileTz === 'object' ? `UTC${last.fileTz.offset_min >= 0 ? '+' : ''}${last.fileTz.offset_min / 60}` : (last.fileTz || DASH);
  const ds = last.dayStart ? `${last.dayStart.tz === 'file' ? 'the file’s own clock' : last.dayStart.tz}, hour ${last.dayStart.hour}` : DASH;
  return [
    ['Replays', intText(p.runs)], ['Seed', String(p.seed)], ['Stream', `paired (method ${METHOD_VERSION.paired})`],
    ['Draw unit', last.file ? 'one whole past trading day, with replacement' : 'one trade at a time, win or loss'],
    ['Day boundary', last.file ? ds : DASH], ['File time zone used', last.file ? tz : DASH],
    ['No-limit cap', `${NO_LIMIT_CAP} trading days`],
    ['Trades read', last.file ? intText(loaded.n) : DASH], ['Days read', last.file ? intText(p.days.length) : DASH],
    ['Dates but no times', last.file ? (loaded.datesOnly ? 'yes' : 'no') : DASH], ['Rules library', presets.rules_lib || DASH],
  ];
}

function renderExpert() {
  const { res } = last;
  const n = res.runs;
  const s = shares(res);
  const rows = [
    { key: 'pass', label: 'Passed', n: res.pass, share: s.pass },
    { key: 'bust', label: 'Busted', n: res.bust, share: s.bust },
    { key: 'timeout', label: 'Ran out of time', n: res.timeout, share: s.timeout },
  ];
  const table = el('table', {},
    el('caption', { text: `Outcome of ${intText(n)} replays` }),
    el('thead', {}, el('tr', {}, ...['Outcome', 'Runs', 'Share', '± (95%)'].map((h, i) => el('th', { scope: 'col', class: i ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows.map((x) => el('tr', { 'data-outcome': x.key },
      el('th', { scope: 'row', text: x.label }), el('td', { class: 'num', text: intText(x.n) }), el('td', { class: 'num', text: pct(x.share) }),
      el('td', { class: 'num', text: `± ${pct(mcError(x.share, n))}` })))));
  const facts = [
    ['Busted on the daily loss limit', intText(res.bust_daily), 'bust_daily'],
    ['Busted on the maximum loss', intText(res.bust_max), 'bust_max'],
    ['Held by the best-day share', intText(res.held_consistency), 'held_consistency'],
    ['Held by the minimum days', intText(res.held_min_days), 'held_min_days'],
    ['Median trading days to pass', res.median_pass_days === null ? DASH : intText(res.median_pass_days), 'median_pass_days'],
    ['Median trading days to bust', res.median_bust_days === null ? DASH : intText(res.median_bust_days), 'median_bust_days'],
    ['Stopped at the no-limit cap', res.capped ? 'yes' : 'no', 'capped'],
  ];
  const body = [
    el('h3', { text: 'Simulation settings' }),
    tableWrap('Simulation settings', rowsTable('Simulation settings', ['Setting', 'Value'], settingsRows())),
    el('p', { class: 'small muted', id: 'ps-rules-used', text: `Rules used: ${rulesText()}` }),
    el('h3', { text: 'Uncertainty' }),
    el('p', { text: `Monte Carlo error: the ± column above is 1.96 × √(p(1 − p) / ${intText(n)}), about ±1 point for a 50% share.` }),
    tableWrap('Outcomes', table),
  ];
  if (last.file) {
    body.push(el('p', { class: 'small muted', text: 'File uncertainty: 200 resamples of your days with replacement, 1,000 replays each; 90% percentile intervals.' }),
      el('p', { class: 'btn-row' }, el('button', { class: 'btn btn-secondary', type: 'button', id: 'ps-range-btn', text: 'Compute range' })),
      el('p', { id: 'ps-range-status', class: 'muted', role: 'status', hidden: true }),
      lastRange ? rangeTable() : el('div', { id: 'ps-range-out', hidden: true }));
  }
  body.push(el('h3', { text: 'Per-rule counts' }),
    el('dl', { class: 'stats' }, ...facts.map(([l, v, k]) => el('div', { class: 'stat' }, el('dt', { text: l }), el('dd', { text: v, 'data-k': k })))),
    el('p', { id: 'ps-streak', 'data-busts': String(res.bust), text: streakLine(res) }));
  if (last.file) {
    const c = countFlags(loaded.flags);
    const r = last.real, sm = last.sim;
    body.push(el('h3', { text: 'Habits, raw' }),
      tableWrap('Habits, raw', rowsTable(`Habit counts (breach days: ${intText(r.n_breach)}; fewer than ${MIN_BREACH_DAYS} is too few; replays: fewer than ${MIN_BUSTS} busts is too few)`,
        ['Habit', 'Flagged trades', 'Breach days', 'Other losing days', 'Replay busts', 'Drawn losing days'],
        HABITS.map((h) => [HABIT_TEXT[h], intText(c[h]),
          `${intText(r.habits[h].on_breach)} / ${intText(r.n_breach)}`, `${intText(r.habits[h].on_other_losing)} / ${intText(r.n_other_losing)}`,
          `${intText(sm.habits[h].on_busts)} / ${intText(sm.busts)}`, `${intText(sm.habits[h].on_drawn_losing)} / ${intText(sm.drawn_losing)}`]))));
    body.push(el('h3', { text: 'Your days in their real order' }), el('p', { text: realOrderLine(last.seq, last.p.rules) }), timeline(last.seq));
  }
  if (lastWhatIf) {
    const { before, after } = lastWhatIf;
    body.push(el('h3', { text: 'What-if, raw' }),
      tableWrap('What-if, raw', rowsTable(`${ruleLabel(lastWhatIf.personal, (x) => money(x, last.unit, { sign: false }))}, ${intText(after.runs)} paired replays`,
        ['Outcome', 'Before', 'With the rule'],
        [['Passed', intText(before.pass), intText(after.pass)], ['Busted', intText(before.bust), intText(after.bust)],
          ['Ran out of time', intText(before.timeout), intText(after.timeout)],
          ['Trades left out', intText(before.trades_left_out), `${intText(after.trades_left_out)} of ${intText(after.trades_seen)}`]])));
  }
  body.push(el('h3', { text: 'Export' }),
    el('p', { class: 'small muted', text: 'Results only: the rules, the settings and the numbers above. No trades, no daily results, no symbols, no times.' }),
    el('p', { class: 'btn-row' }, el('button', { class: 'btn btn-secondary', type: 'button', id: 'ps-csv', text: 'Download CSV' }),
      el('button', { class: 'btn btn-secondary', type: 'button', id: 'ps-json', text: 'Download JSON' })));
  $('ps-expert-body').replaceChildren(...body);
  if ($('ps-range-btn')) $('ps-range-btn').addEventListener('click', runRange);
  $('ps-csv').addEventListener('click', () => download('csv'));
  $('ps-json').addEventListener('click', () => download('json'));
}

function streakLine(res) {
  if (res.bust < MIN_RULE_BUSTS) return `Too few runs busted (${intText(res.bust)}) to say what led up to them.`;
  return `${pct(res.bust_after_streak / res.bust)} of the busted runs broke a limit on a trade that came after 2 or more losses in a row (${intText(res.bust_after_streak)} of ${intText(res.bust)}).`;
}

function timeline(seq) {
  const n = seq.day_pnl.length;
  const cell = 10, W = Math.max(1, n) * cell;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${cell}`);
  svg.setAttribute('class', 'rc-timeline tp-heat');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', realOrderLine(seq, last.p.rules));
  const max = Math.max(1e-9, ...seq.day_pnl.map((x) => Math.abs(x)));
  seq.day_pnl.forEach((x, i) => {
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('x', String(i * cell)); r.setAttribute('y', '0'); r.setAttribute('width', String(cell - 1)); r.setAttribute('height', String(cell));
    const lvl = Math.min(4, 1 + Math.floor((Math.abs(x) / max) * 3.999));
    const breach = seq.outcome === 'bust' && i === n - 1;
    r.setAttribute('class', breach ? 'hn4' : x > 0 ? `hp${lvl}` : x < 0 ? `hn${lvl}` : 'h0');
    svg.append(r);
  });
  return el('figure', { class: 'chart' }, svg, el('figcaption', { text: 'One cell per day, in order; the darkest red cell is the day a rule broke.' }));
}

async function runRange() {
  const btn = $('ps-range-btn');
  btn.disabled = true;
  const out = await work({ op: 'range', p: last.p, personal: lastWhatIf ? lastWhatIf.personal : null }, $('ps-range-status'), 'Computing the range: 200 resamples of your days…');
  btn.disabled = false;
  if (!out || !out.range) { $('ps-range-status').textContent = 'The range could not be computed in this browser.'; return; }
  $('ps-range-status').hidden = true;
  lastRange = out.range;
  $('ps-range-out').replaceWith(rangeTable());
}

function rangeTable() {
  const r = lastRange;
  const rows = [['Passed', 'pass'], ['Busted', 'bust'], ['Ran out of time', 'timeout']].map(([l, k]) => {
    const row = [l, `${pct(r.shares[k][0])} to ${pct(r.shares[k][1])}`];
    if (r.change) row.push(`${pct(r.change[k][0])} to ${pct(r.change[k][1])}`);
    return row;
  });
  return el('div', { id: 'ps-range-out' }, tableWrap('Range', rowsTable(`90% range over ${intText(r.B)} resamples of your days`,
    r.change ? ['Outcome', 'Share', 'Change with the rule'] : ['Outcome', 'Share'], rows)));
}

// The export: results only, never the trades, days, symbols or times (tested).
function exportData() {
  const { res, p } = last;
  const pick = (o, ks) => Object.fromEntries(ks.map((k) => [k, o[k]]));
  const outKeys = ['runs', 'pass', 'bust', 'timeout', 'bust_daily', 'bust_max', 'bust_after_streak', 'held_consistency', 'held_min_days', 'capped', 'median_pass_days', 'median_bust_days', 'trades_seen', 'trades_left_out'];
  const data = {
    schema: 'donttrade.readiness-check.results.v1', method: METHOD_VERSION.paired, rules_lib: presets.rules_lib,
    preset_id: last.preset ? last.preset.id : 'custom', edited_from_preset: last.edited,
    settings: { runs: p.runs, seed: p.seed, stream: 'paired', mode: last.file ? (last.example ? 'example' : 'file') : 'manual',
      day_start: last.dayStart, file_time_zone: last.fileTz, no_limit_cap: NO_LIMIT_CAP },
    rules: p.rules, account_size: last.accountSize,
    out: pick(res, outKeys),
    mc_error_95: { pass: mcError(res.pass / res.runs, res.runs), bust: mcError(res.bust / res.runs, res.runs), timeout: mcError(res.timeout / res.runs, res.runs) },
    habits: last.file ? Object.fromEntries(HABITS.map((h) => [h, { real: last.real.habits[h], replays: last.sim.habits[h] }])) : null,
    real: last.file ? { breach_days: last.real.n_breach, other_losing_days: last.real.n_other_losing, outcome: last.seq.outcome,
      rule: last.seq.why, day: last.seq.day, target_day: last.seq.target_day } : null,
    whatif: lastWhatIf ? { rule: lastWhatIf.personal, before: pick(lastWhatIf.before, outKeys), after: pick(lastWhatIf.after, outKeys) } : null,
    range: lastRange,
  };
  if (data.habits) for (const h of HABITS) for (const v of ['real', 'replays']) data.habits[h][v] = { ...data.habits[h][v] };
  return data;
}

function flatten(o, prefix = '', out = []) {
  if (o === null || typeof o !== 'object') { out.push([prefix, o === null ? '' : String(o)]); return out; }
  for (const [k, v] of Object.entries(o)) flatten(v, prefix ? `${prefix}.${k}` : k, out);
  return out;
}

function exportText(kind) {
  const data = exportData();
  if (kind === 'json') return JSON.stringify(data, null, 2) + '\n';
  const q = (s) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  return 'key,value\n' + flatten(data).map(([k, v]) => `${q(k)},${q(v)}`).join('\n') + '\n';
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function download(kind) {
  const text = exportText(kind);
  saveBlob(new Blob([text], { type: kind === 'json' ? 'application/json' : 'text/csv' }), `readiness-check-results.${kind}`);
  count('export');
}

// ------------------------------------------------------------------ the share card
function cardData() {
  const { res, p } = last;
  const s = shares(res);
  const size = last.accountSize;
  const r = p.rules;
  const pctOf = (x) => Math.round((x / size) * 1000) / 10;
  // the habit whose breach-day share is furthest above its losing-day share, among the "hit" pills
  const hits = last.file && r.daily_loss !== null ? HABITS.filter((h) => last.real.habits[h].status === 'hit') : [];
  const gap = (h) => last.real.habits[h].share - last.real.habits[h].base;
  const hit = hits.length ? hits.reduce((x, h) => (gap(h) > gap(x) ? h : x)) : null;
  return {
    ...s, runs: res.runs,
    rule: res.bust >= MIN_RULE_BUSTS ? (res.bust_daily >= res.bust_max ? 'daily' : 'max') : null,
    habit: hit ? HABIT_TEXT[hit] : null,
    rulesPct: size ? { t: pctOf(r.target), d: r.daily_loss === null ? null : pctOf(r.daily_loss), m: pctOf(r.max_loss), kind: r.drawdown === 'static' ? 'static' : 'moving' } : null,
    whatif: lastWhatIf && $('ps-wi-card').checked ? { personal: lastWhatIf.personal, a: lastWhatIf.before.pass / lastWhatIf.before.runs, b: lastWhatIf.after.pass / lastWhatIf.after.runs } : null,
    example: !!last.example,
  };
}

async function drawShareCard() {
  const c = $('ps-card-canvas');
  await drawCard(c, cardData(), $('ps-card-size').value);
  c.hidden = false;
}

async function cardFile() {
  const c = $('ps-card-canvas');
  await drawCard(c, cardData(), $('ps-card-size').value);
  const blob = await cardBlob(c);
  return new File([blob], 'readiness-check-card.png', { type: 'image/png' });
}

// ------------------------------------------------------------------ wiring
function init() {
  try { presets = JSON.parse($('ps-presets').textContent); } catch (e) { presets = { presets: [], firms: [], rules_lib: '' }; }
  for (const r of document.querySelectorAll('input[name="ps-mode"]')) r.addEventListener('change', syncMode);
  $('ps-filetz').addEventListener('change', () => { $('ps-filetz').dataset.touched = '1'; syncTz(); });
  $('ps-preset').addEventListener('change', applyPreset);
  $('ps-account').addEventListener('change', () => { if (current && current.preset.scale === 'percent') applyPreset(); });
  slot = createFileSlot({
    progressBox: $('ps-progress'), onStage: setFileStatus, onClear: clearFile, onResult: showLoaded,
    onError: (err, retry) => renderReadError($('ps-file-error'), err, retry),
    onMapNeeded: showMapStep,
  });
  $('ps-file').addEventListener('change', (e) => slot.pickFile(e.target.files[0], 'your file'));
  $('ps-sample-btn').addEventListener('click', () => {
    // the example data also fills example rules where the boxes are empty, not any firm's
    for (const [id, v] of [['ps-target', '600'], ['ps-daily', '250'], ['ps-maxloss', '500'], ['ps-days', '60']]) {
      if ($(id).value.trim() === '') $(id).value = v;
    }
    slot.readBytes(new TextEncoder().encode($('ps-sample').textContent.replace(/^\s+/, '')), SAMPLE_LABEL);
  });
  $('ps-paste-btn').addEventListener('click', () => {
    clearFieldErrors(['ps-paste', 'ps-filetz'], $('ps-errors'));
    const problems = [];
    if (!$('ps-paste').value.trim()) { fieldError('ps-paste', 'Paste the rows of your history table first.'); problems.push({ id: 'ps-paste', message: 'Paste the rows of your history table first.' }); }
    if (!$('ps-filetz').value) { fieldError('ps-filetz', 'Choose the time zone of the times in your trades.'); problems.push({ id: 'ps-filetz', message: 'Choose the time zone of the times in your trades.' }); }
    if (problems.length) { showProblems($('ps-errors'), problems); return; }
    slot.readPaste($('ps-paste').value, 'your pasted table');
  });
  $('ps-form').addEventListener('submit', run);
  for (const n of [1, 2]) $(`ps-wi-rule${n}`).addEventListener('change', () => syncWiRow(n, true));
  $('ps-wi-run').addEventListener('click', runWhatIf);
  $('ps-wi-card').addEventListener('change', () => { if (last) drawShareCard(); });
  $('ps-expert').addEventListener('toggle', () => { if ($('ps-expert').open) count('expert'); });
  $('ps-card-size').addEventListener('change', () => { if (last) drawShareCard(); });
  $('ps-card-dl').addEventListener('click', async () => { saveBlob(await cardFile(), 'readiness-check-card.png'); count('card'); });
  const share = $('ps-card-share');
  if (navigator.canShare && navigator.share) {
    share.hidden = false;
    share.addEventListener('click', async () => {
      const f = await cardFile();
      if (!navigator.canShare({ files: [f] })) { saveBlob(f, f.name); count('card'); return; }
      try { await navigator.share({ files: [f], text: altText(cardData()) }); count('card'); } catch (e) { /* the person closed the sheet */ }
    });
  }
  if (!$('ps-seed').value) $('ps-seed').value = String(DEFAULT_SEED);
  $('ps-js-needed').hidden = true;
  $('ps-form').hidden = false;
  syncMode();
  syncWiRow(1, false);
  syncWiRow(2, false);
}

init();
