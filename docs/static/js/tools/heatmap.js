// heatmap.js — /tools/trading-heatmap/: the visitor's own trades by weekday and hour opened.
//
// The file is read by the same engine and worker path as /tools/trade-stats/ (file-tool.js);
// heatmap-core.js does the counting. Changing the time shift or the block size redraws from the
// trades already read; nothing is read again, stored or sent.
//
// Descriptive only. A grid of 24 hours × 5 weekdays is 120 comparisons at once, so a few cells
// will look unusually good or bad by chance alone: the page says so next to the grid and does
// not test, rank or name any cell as a pattern (no "real or noise" verdicts; free_badges is a
// separate, redesigned feature). The teaser states only figures computed on this page.

import { heatmap, level, WEEKDAYS, MIN_CELL, blockLabel } from './heatmap-core.js?v=e62634a0';
import { money, pct, intText, el, signClass, MINUS } from './format.js?v=acb0db51';
import { revealResult } from './tool-state.js?v=fd4af716';
import { wireFileTool, readSection, tableWrap, rowsTable, plural, reportLead, SAMPLE_LABEL } from './file-tool.js?v=54629050';

const $ = (id) => document.getElementById(id);
let state = null; // {result, unit, fileLabel}; never persisted

const opts = () => ({ shiftHours: Number($('hm-shift').value), block: Number($('hm-block').value) });
const stamp = (ms) => { const s = new Date(ms).toISOString(); return `${WEEKDAYS[(new Date(ms).getUTCDay() + 6) % 7]} ${s.slice(0, 10)} ${s.slice(11, 16)}`; };
const shiftText = (h) => (h === 0 ? 'as written in the file' : `shifted ${h > 0 ? '+' : MINUS}${Math.abs(h)} h from the file`);

function clearOutput() {
  state = null;
  $('hm-out').replaceChildren();
  $('hm-out').hidden = true;
  teaser(null);
}

function render(focus = true) {
  const r = state.result;
  const o = opts();
  const h = heatmap(r.trades, o);
  state.hm = h;
  const out = $('hm-out');
  out.replaceChildren(el('h2', { id: 'hm-out-h', tabindex: '-1', text: state.fileLabel === SAMPLE_LABEL ? 'Results: example data' : 'Results: your file' }),
    readSection('hm', r, state.fileLabel));
  out.append(el('p', { id: 'hm-range', 'data-k': 'range' },
    `Open times ${shiftText(o.shiftHours)}: first trade opened ${stamp(h.first_open)}, last opened ${stamp(h.last_open)}. If these do not match what you remember, change the shift above.`));
  out.append(grid(h), noteSection(h), marginals(h), allCells(h));
  out.hidden = false;
  if (focus) revealResult($('hm-out-h'));
  teaser(h);
}

function grid(h) {
  const days = h.weekend ? [0, 1, 2, 3, 4, 5, 6] : [0, 1, 2, 3, 4];
  const rows = [];
  for (let b = 0; b < h.nb; b++) if (h.byBlock[b].n) rows.push(b);
  const cell = (c, wd, b) => {
    if (!c.n) return el('td', { class: 'heat heat-empty', 'data-cell': `${wd}-${b}` }, el('span', { class: 'visually-hidden', text: 'no trades' }), '·');
    const lv = level(c.total, h.maxAbs);
    return el('td', { class: `heat heat-${lv > 0 ? 'g' : lv < 0 ? 'l' : 'z'}${Math.abs(lv) || ''}`, 'data-cell': `${wd}-${b}` },
      el('span', { class: 'heat-total', 'data-k': 'total', text: money(c.total, state.unit) }),
      el('span', { class: 'heat-n', 'data-k': 'n', text: plural(c.n, 'trade', 'trades') }));
  };
  const table = el('table', { class: 'heatmap', id: 'hm-grid' },
    el('caption', { text: `Total result of the trades opened in each hour block (rows) and weekday (columns). Hours with no trades are left out.` }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Opened' }), ...days.map((wd) => el('th', { scope: 'col', class: 'num', text: WEEKDAYS[wd].slice(0, 3), title: WEEKDAYS[wd] })))),
    el('tbody', {}, ...rows.map((b) => el('tr', {}, el('th', { scope: 'row', text: blockLabel(b, h.block) }), ...days.map((wd) => cell(h.grid[wd][b], wd, b))))));
  return el('section', { 'aria-labelledby': 'hm-grid-h' },
    el('h3', { id: 'hm-grid-h', text: 'By hour and weekday' }),
    tableWrap('Trades by hour and weekday', table),
    el('p', { class: 'small muted', id: 'hm-legend', text: `Shading: green cells closed with a gain in total and red cells with a loss; the darker the shade, the larger the total, relative to the largest cell (${money(h.maxAbs, state.unit, { sign: false })}). Every cell also shows its total with its sign and its number of trades.` }));
}

function noteSection(h) {
  const k = h.cells.length;
  return el('div', { class: 'notice notice-caution', id: 'hm-many' },
    el('strong', { text: 'Many cells, compared at once' }),
    el('p', { text: `This grid has ${plural(k, 'cell', 'cells')} with trades. When this many cells are compared at once, a few will look unusually good or unusually bad by chance alone, even if the hour or the day made no difference to how the trades turned out. This page describes each cell; it does not test them, so no cell here is shown to be a pattern.` }),
    el('p', { 'data-k': 'n_small', text: h.n_small === k ? `All ${plural(k, 'cell holds', 'cells hold')} fewer than ${MIN_CELL} trades, where one trade can move a total a long way. Wider blocks put more trades in each cell.` :
      `${intText(h.n_small)} of the ${plural(k, 'cell', 'cells')} ${h.n_small === 1 ? 'holds' : 'hold'} fewer than ${MIN_CELL} trades, where one trade can move a total a long way.` }));
}

function marginals(h) {
  const m = (c, k) => ({ text: money(c.total, state.unit), cls: signClass(c.total) || '', k });
  const line = (label, c, k) => [label, intText(c.n), m(c, k), { text: money(c.avg, state.unit) }, pct(c.win_rate)];
  const days = (h.weekend ? [0, 1, 2, 3, 4, 5, 6] : [0, 1, 2, 3, 4]).map((wd) => line(WEEKDAYS[wd], h.byDay[wd], `day-${wd}`));
  const blocks = [];
  for (let b = 0; b < h.nb; b++) if (h.byBlock[b].n) blocks.push(line(blockLabel(b, h.block), h.byBlock[b], `block-${b}`));
  const head = ['', 'Trades', 'Total result', 'Average result', 'Win rate'];
  return el('section', { 'aria-labelledby': 'hm-marg-h' },
    el('h3', { id: 'hm-marg-h', text: 'By weekday and by hour' }),
    tableWrap('By weekday', rowsTable('By weekday opened', ['Weekday', ...head.slice(1)], days)),
    tableWrap('By hour', rowsTable('By hour opened', ['Hour', ...head.slice(1)], blocks)),
    el('p', { class: 'small muted', text: 'Win rate leaves out break-even trades, as on the trade-stats page.' }));
}

function allCells(h) {
  const rows = h.cells.map((c) => [c.label, intText(c.n), { text: money(c.total, state.unit), cls: signClass(c.total) || '' }, money(c.avg, state.unit), pct(c.win_rate)]);
  return el('section', { 'aria-labelledby': 'hm-cells-h' },
    el('h3', { id: 'hm-cells-h', text: 'Every cell' }),
    el('details', {}, el('summary', { text: `Show all ${plural(h.cells.length, 'cell', 'cells')} as a list, with average result and win rate` }),
      tableWrap('Every cell', rowsTable('Each weekday and hour block with trades, in weekday order', ['Cell', 'Trades', 'Total result', 'Average result', 'Win rate'], rows))));
}

// ------------------------------------------------------------------ teaser (true figures only)
function teaser(h) {
  const box = $('hm-teaser');
  // paid_report on: no teaser box (partials/tool_next_step.html is the one offer, never next to a result)
  if (!box) return;
  const lead = reportLead(box);
  const text = $('hm-teaser-text');
  if (h && h.lowest) {
    const c = h.lowest;
    text.textContent = `Your ${WEEKDAYS[c.wd]} ${blockLabel(c.b, h.block)} trades (${intText(c.n)} of them) closed at ${money(c.total, state.unit)} in total. ${lead} looks at what you do after a loss, such as trades opened within 15 minutes of one, rather than at the clock.`;
    text.dataset.live = 'true';
    return;
  }
  text.textContent = h
    ? `None of your cells has ${MIN_CELL} or more trades yet. ${lead} looks at what you do after a loss rather than at the clock.`
    : `${lead} looks at what you do after a loss rather than at the clock.`;
  delete text.dataset.live;
}

// ------------------------------------------------------------------ wiring
function init() {
  wireFileTool('hm', {
    onClear: clearOutput,
    onResult: (result, fileLabel) => { state = { result, unit: result.trades[0].pnl_unit, fileLabel }; render(); },
  });
  for (const id of ['hm-shift', 'hm-block']) $(id).addEventListener('change', () => { if (state) render(false); });
}

init();
