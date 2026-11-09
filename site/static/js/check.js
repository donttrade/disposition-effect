// check.js - /check/: the visitor's file is read in this tab and counted with the report's own rules (check-core.js). Counts only: no amount,
// no list of trades, no verdict. The page's CSP has connect-src 'none' plus the analytics hosts, and the only calls out are Umami's fixed
// event names with no data (check_start, check_read_ok, check_read_fail_<code>, check_variant_<v>, check_to_report, check_sample_start,
// check_sample_ok). The bars are SVG rects with width attributes, never style attributes.

import { countTrades, MIN_GROUP, MIN_ROWS } from './check-core.js';
import { spanLine, MAX_ROWS } from './paid/strip.js';
import { createFileSlot, renderReadError, revealResult } from './tools/tool-state.js';
import { showMapStep, hideMap, FORMAT_NAMES, SAMPLE_LABEL, tableWrap, warningsNotice, plural } from './tools/file-tool.js';
import { el, intText } from './tools/format.js';

const $ = (id) => document.getElementById(id);
const WEEK_S = 604800;
const dayName = (ts) => new Date(ts).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

function track(name) {
  try { if (window.umami && typeof window.umami.track === 'function') window.umami.track(name); } catch (e) { /* counting never blocks the page */ }
}

const ROWS = [
  { id: 'revenge', short: 'Re-entered within 15 min of a loss', says: 'opened within 15 minutes of a losing trade', pick: (h) => h.n_a, test: true, times: true,
    ask: 're-entering within 15 min of a loss', ga: 'After a loss' },
  { id: 'tilt', short: 'After 2+ losses in a row', says: 'opened after 2 or more losses in a row', pick: (h) => h.n_a, test: true, times: true,
    ask: 'trading after 2 or more losses in a row', ga: 'After 2+ losses' },
  { id: 'size_up', short: 'Bigger size after a loss', says: 'opened at 1.5 times your usual size or more right after a loss', pick: (h) => h.n_set, test: false, times: true },
  { id: 'hold_gap', short: 'Losers held longer than your median win', says: 'losing trades held longer than your median win', pick: (h) => h.n_set, test: false, times: false },
  { id: 'oversized_loss', short: 'Losses over 2× your median loss', says: 'losses over 2 times your median loss', pick: (h) => h.n_set, test: false, times: false },
];
const byId = (id) => ROWS.find((r) => r.id === id);
const SVGNS = 'http://www.w3.org/2000/svg';

function variantOf(c) {
  const groups = ROWS.filter((r) => r.times && c.dates_only ? false : r.pick(c.habits[r.id]) > 0).length;
  if (c.below_min_rows) return { name: 'too_few', groups };
  if (c.dates_only) return { name: groups ? 'dates_only' : 'dates_none', groups };
  if (!groups) return { name: 'zero', groups };
  return { name: c.testable.length ? 'normal' : 'no_test', groups };
}

const blindRow = (row, c) => c.dates_only && row.times;
const countOf = (row, c) => (blindRow(row, c) ? null : row.pick(c.habits[row.id]));
const pctOf = (n, c) => (n === null || !c.n_trades ? null : Math.round((100 * n) / c.n_trades));

function spanOf(trades) {
  const first = Math.min(...trades.map((t) => t.open_ts)), last = Math.max(...trades.map((t) => t.close_ts));
  return { first, last, weeks: Math.max(1, Math.ceil((last - first) / 1000 / WEEK_S)) };
}

function bar(vw, vh, w, cls) {
  const svg = document.createElementNS(SVGNS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${vw} ${vh}`);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.setAttribute('class', 'ck-svg ' + cls);
  for (const [k, width] of [['ck-track', vw], ['ck-bar', w]]) {
    const r = document.createElementNS(SVGNS, 'rect');
    r.setAttribute('class', k);
    r.setAttribute('x', '0'); r.setAttribute('y', '0');
    r.setAttribute('width', String(width)); r.setAttribute('height', String(vh));
    svg.append(r);
  }
  return svg;
}

function headline(c, v, span) {
  const first = el('p', { class: 'ck-head' }, el('strong', { text: `${plural(c.n_trades, 'trade', 'trades')} read` }), ` over ${plural(span.weeks, 'week', 'weeks')}. `);
  if (c.dates_only) {
    first.append('Your file has dates but no times of day, so re-entries and size after a loss cannot be counted.');
  } else {
    const row = c.testable.length ? byId(c.testable[0]) : ROWS.reduce((m, r) => (countOf(r, c) > countOf(m, c) ? r : m), ROWS[0]);
    const n = countOf(row, c);
    if (n === 0) first.append(`None were ${row.says}.`);
    else first.append(el('strong', { text: `${intText(n)} (${pctOf(n, c)}%)` }), ` were ${row.says}.`);
  }
  const out = [first];
  if (v.name === 'normal' || v.name === 'no_test') {
    out.push(el('p', { class: 'ck-sub' }, 'The report can total the dollars on ', el('strong', { text: String(v.groups) }), ' of these groups and test ',
      el('strong', { text: `${c.testable.length} of 2` }), ' habits against chance' + (c.testable.length ? '.' : ' (too few trades).')));
  }
  return out;
}

function shareChart(c) {
  const list = (rows) => el('div', { class: 'ck-group' }, el('ul', { class: 'ck-bars' }, ...rows.map((row) => {
    const n = countOf(row, c), pct = pctOf(n, c);
    return el('li', {}, el('span', { class: 'ck-bl', text: row.short }), el('span', { class: 'ck-bv', text: pct === null ? 'needs times of day' : `${intText(n)} · ${pct}%` }),
      pct === null ? bar(100, 6, 0, 'ck-none') : bar(100, 6, pct, 'ck-share'));
  })));
  return el('div', { class: 'ck-chart', role: 'group', 'aria-label': 'Share of all trades in each habit' },
    list(ROWS.slice(0, 2)),
    list(ROWS.slice(2)),
    el('p', { class: 'small muted', text: `Share of all ${plural(c.n_trades, 'trade', 'trades')}. The two habits above the line are the ones the report tests against chance. A trade can be in more than one row.` }));
}

function meter(row, h) {
  const one = (label, n) => el('div', { class: 'ck-mrow' }, el('span', { class: 'ck-ml', text: label }), bar(MIN_GROUP, 4, Math.min(n, MIN_GROUP), 'ck-m'),
    el('span', { class: 'ck-mv', text: `${intText(n)} / ${MIN_GROUP}${n >= MIN_GROUP ? ' ✓' : ''}` }));
  const status = h.enough ? 'Can be tested against chance in the report.'
    : `Too few to test (${intText(Math.min(h.n_a, h.n_b))} of the ${MIN_GROUP} needed). A longer export may reach ${MIN_GROUP}.`;
  return el('div', { class: 'ck-meter' }, one(row.ga, h.n_a), one('Other trades', h.n_b), el('p', { class: 'ck-ms small', text: status }));
}

function habitTable(c) {
  const head = ['Habit', 'Trades', 'Share of trades'];
  const link = el('a', { href: '#offer', text: 'In the report' });
  const th = (t, i) => el('th', { scope: 'col', class: i ? 'num' : null, text: t });
  const rows = ROWS.map((row) => {
    const h = c.habits[row.id], blind = blindRow(row, c), n = countOf(row, c), pct = pctOf(n, c);
    let rep;
    if (blind) rep = 'Needs times of day';
    else if (n === 0) rep = 'Nothing to total';
    else rep = row.test && h.enough ? 'Dollar total · test against chance' : 'Dollar total';
    const first = el('th', { scope: 'row' }, el('span', { text: row.short }), row.test && !blind ? meter(row, h) : null);
    const cells = [blind ? '—' : intText(n), pct === null ? '—' : `${pct}%`, rep];
    const labels = [head[1], head[2], 'In the report'];
    return el('tr', {}, first, ...cells.map((t, i) => el('td', { class: i < 2 ? 'num' : 'ck-text', 'data-label': labels[i], text: t })));
  });
  const tbl = el('table', { class: 'ck-table stack-table' }, el('caption', { text: 'Each habit, counted in your file' }),
    el('thead', {}, el('tr', {}, ...head.map(th), el('th', { scope: 'col', class: 'ck-text' }, link))), el('tbody', {}, ...rows));
  return tableWrap('Each habit, counted in your file', tbl);
}

function readBlock(r, c, trades) {
  const { first, last } = spanOf(trades);
  const skipped = Object.values(r.skipped || {}).reduce((a, b) => a + b, 0);
  const lines = [el('p', { class: 'ck-did' }, el('strong', { text: 'What we did: ' }),
    `${plural(r.n_fills, 'fill', 'fills')} → ${plural(c.n_trades, 'closed trade', 'closed trades')}${c.n_merged ? ` (${c.n_merged} joined: same symbol, direction and open minute)` : ''} → 5 habits counted, with the report's rules. Nothing left this tab.`),
    el('p', { class: 'small muted', text: `${dayName(first)} – ${dayName(last)}. Format: ${FORMAT_NAMES[r.format] || r.format}. Times are ${r.tz_label}.` })];
  if (c.limited) lines.push(el('p', { class: 'small', text: `Only the latest ${intText(MAX_ROWS)} trades are counted, as in the report.` }));
  if (c.span_left_out) lines.push(el('p', { class: 'small', text: spanLine(c.span_left_out) }));
  if (skipped) lines.push(el('p', { class: 'small', text: `${plural(skipped, 'row', 'rows')} skipped${r.warnings && r.warnings.length ? '; the notes say why' : ''}.` }));
  return lines;
}

function notesBlock(r) {
  const n = warningsNotice('ck', r.warnings);
  if (!n) return null;
  n.querySelector('strong').remove();
  const k = r.warnings.length, skipped = Object.values(r.skipped || {}).reduce((a, b) => a + b, 0);
  return el('details', { class: 'ck-notes', open: skipped > 0 }, el('summary', { text: `${k} ${k === 1 ? 'note' : 'notes'} about how the file was read` }), n);
}

// 8 Nov: the largest count by the buy button (memo action 6). Counts only; words in #ck-largest-words. Ties keep the first row.
function largest(p, c) {
  let b;
  for (const r of ROWS) { const n = countOf(r, c); if (n && !(b && b.n >= n)) b = { r, n }; }
  if (!p || !b) return;
  const w = $('ck-largest-words').content, d = w.querySelector(`[data-h=${b.r.id}]`).dataset, k = b.n === 1 ? '1' : 'n';
  p.replaceChildren(el('strong', { text: `${intText(b.n)} ${k === '1' ? d.one : d.many}.` }),
    ' ' + w.firstElementChild.dataset[(b.r.test && c.habits[b.r.id].enough ? 't' : 'd') + k]);
  p.hidden = false;
}

function offerFor(v, c) {
  const t = $('ck-t-' + v.name);
  const node = t.content.firstElementChild.cloneNode(true);
  for (const s of node.querySelectorAll('[data-k="groups"]')) s.textContent = String(v.groups);
  largest(node.querySelector('[data-k="largest"]'), c);
  const gap1 = node.querySelector('[data-k="gap1"]'), gap2 = node.querySelector('[data-k="gap2"]');
  if (gap1) {
    const [a, b] = c.testable.map(byId);
    gap1.textContent = `What these ${intText(c.habits[a.id].n_a)} trades came to in dollars, and whether ${a.ask} is more than chance in your file.`;
    if (b) gap2.textContent = `The same for the ${intText(c.habits[b.id].n_a)} trades after 2+ losses in a row.`;
    else gap2.textContent = 'The other habit it tests has too few trades on this file.';
  }
  return node;
}

const HANDOFF = 'dt_check_v1';
const MAX_KEEP = 2500000;
const forget = () => { try { sessionStorage.removeItem(HANDOFF); } catch (e) { /* blocked */ } };
async function keep(file, c, first, last) {
  try {
    if (!file) return false;
    if (file.size > MAX_KEEP) return 'big';
    const u = new Uint8Array(await file.arrayBuffer());
    let bin = '';
    for (let i = 0; i < u.length; i += 8192) bin += String.fromCharCode(...u.subarray(i, i + 8192));
    sessionStorage.setItem(HANDOFF, JSON.stringify({ v: 1, b64: btoa(bin), n_trades: c.n_trades, first, last, ts: Date.now(), fp: `${c.n_trades}:${first}:${last}` }));
    return 'ok';
  } catch (e) { forget(); return false; }
}

let lastFile = null;
let mapped = false;      // the visitor chose columns for this file: /report/ has no such step, so no hand-off is offered

let previewing = false;
let fileName = '';
let userRead = false;

function draw(r, label) {
  const trades = r.trades;
  const c = countTrades(trades);
  const v = variantOf(c);
  const real = label === SAMPLE_LABEL;
  const out = $(real ? 'ck-ex' : 'ck-out');
  const head = el(real ? 'h3' : 'h2', { id: real ? 'ck-ex-h' : 'ck-out-h', tabindex: '-1', text: real ? (previewing ? 'Example: real public data, counted' : 'Real public data, counted') : 'Your file, counted' });
  out.replaceChildren(head);
  if (real) out.append(el('p', { class: 'small muted ck-caption', text: 'Real public data: one anonymous investor, not picked by result.' }));
  out.append(...headline(c, v, spanOf(trades)), shareChart(c));
  out.append(real ? el('p', { class: 'ck-else' }, el('strong', { text: "This is someone else's file. " }), el('button', { class: 'btn btn-secondary', type: 'button', id: 'ck-own', text: 'Check your own file ↑' })) : offerFor(v, c));
  const notes = notesBlock(r);
  if (real) { if (notes) out.append(notes); }
  else { $('ck-notes').replaceChildren(...(notes ? [notes] : [])); $('ck-notes').hidden = !notes; }
  out.append(el(real ? 'h4' : 'h3', { text: 'Each habit, counted' }), habitTable(c), ...readBlock(r, c, trades));
  out.append(el('p', { class: 'small muted', text: 'Counts come from your file only, with the same rules the report uses. A count says how often something happened. It does not say whether it cost you money or whether it is more than chance.' }));
  if (out.querySelector('[data-pay]')) out.append(el('p', { class: 'small' }, el('a', { href: '#offer', text: 'Back to what the report adds ↑' })));
  out.hidden = false;
  out.dataset.variant = v.name;
  const line = out.querySelector('[data-handoff]');
  if (line) {
    const { first, last } = spanOf(trades);
    const say = (t) => { if (line.isConnected) { line.textContent = t; line.hidden = false; } };
    if (mapped) say('You chose columns for this file, so re-select your file on the report page.');
    else keep(lastFile, c, first, last).then((ok) => {
      if (ok === 'big') say('This file is too large to carry over, so re-select it on the report page.');
      else if (ok) say(`Uses the ${plural(c.n_trades, 'trade', 'trades')} you just checked. No second upload.`);
    });
  }
  if (real) {
    $('ck-example').hidden = false;
    $('ck-example').open = !previewing || window.matchMedia('(min-width: 1024px)').matches;
  } else {
    $('ck-controls').hidden = true;
    $('ck-fname').textContent = fileName;
    $('ck-fwhat').textContent = `${plural(c.n_trades, 'trade', 'trades')} · ${dayName(spanOf(trades).first)} – ${dayName(spanOf(trades).last)}`;
    $('ck-filebar').hidden = false;
  }
  if (!previewing) {
    revealResult(head, `${plural(c.n_trades, 'closed trade', 'closed trades')} counted.`);
    if (real) track('check_sample_ok');
    else { track('check_read_ok'); track('check_variant_' + v.name); }
  }
  previewing = false;
}

function clear() {
  for (const id of ['ck-out', 'ck-ex']) { const o = $(id); o.replaceChildren(); delete o.dataset.variant; }
  $('ck-out').hidden = true;
  $('ck-example').hidden = true;
  $('ck-filebar').hidden = true;
  $('ck-controls').hidden = false;
  $('ck-notes').replaceChildren();
  $('ck-notes').hidden = true;
  $('ck-error').hidden = true;
  $('ck-error-note').hidden = true;
  hideMap('ck');
}

function init() {
  const STEPS = { 'Reading your file in this tab…': 'Step 1 of 2: reading your file in this tab', 'Reading the trades in your file…': 'Step 2 of 2: joining fills into trades' };
  const status = (text) => { const s = $('ck-status'); s.textContent = STEPS[text] || text; s.hidden = !text; };
  const slot = createFileSlot({
    progressBox: $('ck-progress'), noise: false, onStage: status, onClear: clear,
    onMapNeeded: (need, choose) => { mapped = true; showMapStep('ck', need, choose); },
    onResult: (out, label) => draw(out.result, label),
    onError: (err, retry) => {
      if (previewing) { previewing = false; clear(); return; }
      renderReadError($('ck-error'), err, retry);
      $('ck-error-note').hidden = false;
      track('check_read_fail_' + String(err.code || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '_'));
    },
  });
  const started = (sample) => { previewing = false; if (!sample) { forget(); mapped = false; } if (!userRead) userRead = true; track(sample ? 'check_sample_start' : 'check_start'); };
  const input = $('ck-file');
  input.addEventListener('change', () => { if (input.files[0]) { lastFile = input.files[0]; fileName = lastFile.name; started(); } slot.pickFile(input.files[0], 'your file'); input.value = ''; });
  const sampleBytes = () => new TextEncoder().encode($('ck-sample').textContent.replace(/^\s+/, ''));
  $('ck-sample-btn').addEventListener('click', () => { started(true); slot.readBytes(sampleBytes(), SAMPLE_LABEL); });
  const dz = $('ck-drop');
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('is-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('is-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('is-over');
    if (e.dataTransfer && e.dataTransfer.files[0]) { lastFile = e.dataTransfer.files[0]; fileName = lastFile.name; started(); slot.pickFile(e.dataTransfer.files[0], 'your file'); }
  });
  $('ck-out').addEventListener('click', (e) => { if (e.target.closest && e.target.closest('[data-offer] a[data-pay]')) track('check_to_report'); });
  const again = () => { $('ck-filebar').hidden = true; $('ck-controls').hidden = false; input.focus(); };
  $('ck-another').addEventListener('click', again);
  $('ck-example').addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#ck-own')) again(); });
  $('ck-js-needed').hidden = true;
  $('ck-controls').hidden = false;
  $('ck-controls').removeAttribute('data-js-show');
  previewing = true;
  slot.readBytes(sampleBytes(), SAMPLE_LABEL);
}

init();
