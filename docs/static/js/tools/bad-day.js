// bad-day.js — /tools/bad-day-check/: one or more days of the visitor's own file beside the visitor's typical day.
//
// The file is read by the same engine and worker path as the other file tools (file-tool.js); bad-day-core.js does the counting.
// A date list in the address (?d=2026-11-05,2026-11-06) or in the box picks the days; an empty box picks the day with the lowest
// net result. Counts only: nothing is scored, tested or called a mistake. Nothing is stored or sent (connect-src 'none').

import { badDay, parseDays, MEASURES, MIN_OTHER_DAYS } from './bad-day-core.js?v=ca834630';
import { money, intText, el } from './format.js?v=35164924';
import { revealResult, announce } from './tool-state.js?v=473c7e9d';
import { wireFileTool, readSection, tableWrap, rowsTable, plural, SAMPLE_LABEL } from './file-tool.js?v=f7fa7d5d';

const $ = (id) => document.getElementById(id);
let state = null; // {result, unit, fileLabel}; never persisted

const shiftOf = () => Number($('bd-shift').value);
const requested = () => parseDays($('bd-days').value);
const dayName = (iso) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });

function clearOutput() {
  state = null;
  $('bd-out').replaceChildren();
  $('bd-out').hidden = true;
}

function cell(m, v, unit) {
  if (v === null || v === undefined) return '—';
  if (m.key === 'net') return { text: money(v, unit), cls: v < 0 ? 'neg' : v > 0 ? 'pos' : '' };
  if (m.key === 'largest_loss') return v ? money(-v, unit) : 'none';
  return intText(Math.round(v * 10) / 10);
}

function render(focus = true) {
  const r = state.result, unit = state.unit;
  const b = badDay(r.trades, { shiftHours: shiftOf(), requested: requested() });
  state.b = b;
  const out = $('bd-out');
  out.replaceChildren(el('h2', { id: 'bd-out-h', tabindex: '-1', text: state.fileLabel === SAMPLE_LABEL ? 'Results: real public data' : 'Results: your file' }),
    readSection('bd', r, state.fileLabel));
  const notes = [];
  if (b.missing.length) notes.push(`No closed trades in this file on ${b.missing.map(dayName).join(', ')}. The file runs ${dayName(b.first_day)} to ${dayName(b.last_day)}.`);
  if (b.fellBack) notes.push(b.requested.length ? 'None of the days you asked for has trades, so this shows the day with the lowest net result in the file instead.'
    : 'No day was chosen, so this shows the day with the lowest net result in the file.');
  if (notes.length) out.append(el('div', { class: 'notice notice-caution', id: 'bd-notes' }, ...notes.map((t) => el('p', { text: t }))));
  out.append(table(b, unit));
  out.hidden = false;
  // First result: focus moves to the heading and the figures are read out. A later change of days or shift is read out too, without moving focus.
  if (focus) revealResult($('bd-out-h'), keyFigures(b, unit));
  else announce(`Updated. ${keyFigures(b, unit)}.${notes.length ? ' ' + notes.join(' ') : ''}`);
}

function table(b, unit) {
  const cols = b.chosen.map((d) => d.date);
  const head = ['Measure', ...cols.map(dayName), 'Your typical day'];
  const rows = [];
  for (const m of MEASURES) {
    if (m.times && b.datesOnly) continue;
    rows.push([m.label, ...b.chosen.map((d) => cell(m, d[m.key], unit)), b.typical ? cell(m, b.typical[m.key], unit) : '—']);
  }
  const sec = el('section', { 'aria-labelledby': 'bd-table-h' },
    el('h3', { id: 'bd-table-h', text: b.chosen.length === 1 ? `${dayName(cols[0])}, beside your typical day` : 'The days you chose, beside your typical day' }),
    tableWrap('Counts for each chosen day and for a typical day', rowsTable('Counts for each chosen day and your typical day', head, rows)));
  const small = [];
  small.push(b.typical ? `Your typical day is, for each row, the median of your other ${plural(b.n_other, 'day', 'days')} with trades. A trade counts on the day it closed.`
    : `A typical day needs at least ${MIN_OTHER_DAYS} other days with trades. This file has ${b.n_other}, so no typical day is shown.`);
  if (b.datesOnly) small.push('This file has dates but no times of day, so re-entries and trade sizes after a loss cannot be counted and those rows are left out.');
  small.push('Counted, not judged: these are numbers from your own file, not a verdict on the day and not a reason to change anything.');
  for (const t of small) sec.append(el('p', { class: 'small muted', text: t }));
  return sec;
}

// What a screen reader hears after the heading.
function keyFigures(b, unit) {
  const parts = b.chosen.map((d) => `${dayName(d.date)}: ${plural(d.n, 'trade', 'trades')}, net ${money(d.net, unit)}`);
  return parts.join('. ');
}

function init() {
  const params = new URLSearchParams(location.search);
  const fromUrl = parseDays(params.get('d') || '');
  if (fromUrl.length) $('bd-days').value = fromUrl.join(', ');
  wireFileTool('bd', {
    onClear: clearOutput,
    onResult: (result, fileLabel) => { state = { result, unit: result.trades[0].pnl_unit, fileLabel }; render(); },
  });
  $('bd-shift').addEventListener('change', () => { if (state) render(false); });
  $('bd-days').addEventListener('change', () => { if (state) render(false); });
  $('bd-days-form').addEventListener('submit', (e) => { e.preventDefault(); if (state) render(false); });
}

init();
