// drawdown.js — /tools/drawdown-calculator/.
//
// Two parts:
//  1. The recovery calculator: the gain that takes an account back to its high after a fall of
//     d%, d ÷ (1 − d). Arithmetic on the number typed in.
//  2. The report from a trade file, read by the same engine and worker path as /tools/trade-stats/
//     (file-tool.js): every drawdown on the closed-trade equity curve, the deepest and longest, the
//     current one, an underwater chart with a table fallback (drawdown-core.js does the counting).
// Descriptive only: no shuffle test or other "real or noise" check runs here (free_badges is a
// separate, redesigned feature). The teaser states only figures computed on this page.

import { recoveryGain, drawdowns, openedAfterLoss } from './drawdown-core.js?v=0bcc5aae';
import { money, pct, plain, day, intText, el } from './format.js?v=acb0db51';
import { parsePositive, InputError } from './num.js?v=8df99e34';
import { clearFieldErrors, fieldError, showProblems, revealResult } from './tool-state.js?v=7534a30f';
import { wireFileTool, readSection, tableWrap, rowsTable, plural, reportLead, SAMPLE_LABEL } from './file-tool.js?v=cea9c740';

const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ 1. recovery calculator
function quick(ev) {
  ev.preventDefault();
  clearFieldErrors(['dd-pct'], $('dd-q-errors'));
  let d;
  try {
    d = parsePositive($('dd-pct').value, 'the drawdown');
    if (d >= 100) throw new InputError('The drawdown has to be less than 100%: at 100% nothing is left to grow back.');
  } catch (e) {
    if (!(e instanceof InputError)) throw e;
    fieldError('dd-pct', e.message);
    showProblems($('dd-q-errors'), [{ id: 'dd-pct', message: e.message }]);
    $('dd-q-out').hidden = true;
    return;
  }
  const g = recoveryGain(d / 100);
  const dp = Math.max(1, Math.min(4, (String(d).split('.')[1] || '').length));
  $('dd-q-out').replaceChildren(
    el('h3', { id: 'dd-q-out-h', tabindex: '-1', text: 'Result' }),
    el('dl', { class: 'stats' },
      el('div', { class: 'stat' }, el('dt', { text: `Gain that recovers a ${plain(d, dp)}% drawdown` }), el('dd', { 'data-k': 'gain', text: pct(g, 2) }))),
    el('pre', { class: 'formula', tabindex: '0', role: 'region', 'aria-label': 'The formula with your number',
      text: `Gain = d ÷ (1 − d) = ${plain(d / 100, dp + 2)} ÷ (1 − ${plain(d / 100, dp + 2)}) = ${plain(g, 4)} = ${pct(g, 2)}` }),
    el('p', { class: 'small muted', text: 'Arithmetic on the number you entered: the gain, on what is left after the fall, that brings the account back to its previous high. Fees, deposits and withdrawals are not included.' }));
  $('dd-q-out').hidden = false;
  revealResult($('dd-q-out-h'));
}

// ------------------------------------------------------------------ 2. the report from a file
let state = null; // {result, unit, fileLabel}; never persisted

function startingBalance() {
  const input = $('dd-balance');
  $('dd-balance-err').hidden = true;
  input.removeAttribute('aria-invalid');
  if (!input.value.trim()) return null;
  try { return parsePositive(input.value, 'the starting balance'); } catch (e) {
    if (!(e instanceof InputError)) throw e;
    fieldError('dd-balance', e.message);
    return null;
  }
}

function clearOutput() {
  state = null;
  $('dd-out').replaceChildren();
  $('dd-out').hidden = true;
  teaser(null);
}

const stat = (label, value, key, cls) => el('div', { class: 'stat' }, el('dt', { text: label }), el('dd', { class: cls || null, 'data-k': key, text: value }));
const daysText = (n) => plural(n, 'calendar day', 'calendar days');
const down = (x) => money(-x, state.unit);
const whenStart = (ep) => (ep.peak_i < 0 ? `the start (${day(ep.start_ts)})` : day(ep.start_ts));

function render(focus = true) {
  const r = state.result;
  const trades = r.trades;
  const bal = startingBalance();
  const d = drawdowns(trades, bal);
  state.dd = d;
  const out = $('dd-out');
  out.replaceChildren(el('h2', { id: 'dd-out-h', tabindex: '-1', text: state.fileLabel === SAMPLE_LABEL ? 'Results: synthetic sample file' : 'Results: your file' }),
    readSection('dd', r, state.fileLabel));

  // Headline numbers
  const deep = d.deepest, longT = d.longest_trades, longD = d.longest_days, cur = d.current;
  const headline = el('dl', { class: 'stats' },
    stat('Largest drawdown', down(d.max_abs), 'max_abs', d.max_abs > 0 ? 'loss' : null),
    stat('Largest drawdown, % of its high', bal === null ? '—' : pct(d.max_pct, 2), 'max_pct'),
    // the gain that recovers the largest drawdown in % (the figure beside it): max_pct ÷ (1 − max_pct)
    stat('Gain that recovers it', bal !== null ? pct(recoveryGain(d.max_pct), 2) : '—', 'recovery_gain'),
    stat('Longest drawdown, in trades', longT ? plural(longT.trades, 'trade', 'trades') : '—', 'longest_trades'),
    stat('Longest drawdown, in calendar days', longD ? daysText(longD.days) : '—', 'longest_days'),
    stat('Current drawdown', cur ? down(cur.peak - d.final_equity) : 'none: at the high', 'current', cur ? 'loss' : null));
  const notes = [];
  if (bal === null) notes.push('Enter a starting balance above to see drawdowns as a percentage and the gain that recovers them.');
  notes.push('Closed-trade equity: open-trade swings between trades are not in a trade file, so a platform that counts them can show a deeper drawdown.');
  out.append(el('section', { 'aria-labelledby': 'dd-head-h' },
    el('h3', { id: 'dd-head-h', text: 'Headline numbers' }), headline,
    ...notes.map((t) => el('p', { class: 'small muted', text: t }))));

  if (!d.episodes.length) {
    out.append(el('p', { class: 'notice', id: 'dd-none' }, el('strong', { text: 'No drawdown in this file' }),
      'Equity never fell below a previous high after any closed trade.'));
  } else {
    // In words
    const words = [`${plural(d.episodes.length, 'drawdown', 'drawdowns')} in ${plural(d.n, 'closed trade', 'closed trades')}; ${intText(d.n_recovered)} recovered to the previous high.`];
    words.push(`The largest fell ${money(deep.depth, state.unit, { sign: false })} from the high set at ${whenStart(deep)}, reached its low ${plural(deep.trades_to_trough, 'trade', 'trades')} later, on ${day(trades[deep.trough_i].close_ts)}, and ${deep.recovered ? `recovered on ${day(deep.end_ts)}, ${plural(deep.trades, 'trade', 'trades')} and ${daysText(deep.days)} after the high` : `has not recovered by the last trade in the file (${plural(deep.trades, 'trade', 'trades')} and ${daysText(deep.days)} so far)`}.`);
    if (d.median_recovery_trades !== null) words.push(`The median recovered drawdown took ${plural(d.median_recovery_trades, 'trade', 'trades')} from high to high.`);
    out.append(el('section', { 'aria-labelledby': 'dd-words-h' }, el('h3', { id: 'dd-words-h', text: 'Your drawdowns in words' }),
      ...words.map((t, i) => el('p', { 'data-k': i ? null : 'summary', text: t }))));
    out.append(chart(d));
    out.append(episodesTable(d, trades, bal));
  }
  out.hidden = false;
  if (focus) revealResult($('dd-out-h'));
  teaser(d);
}

function episodesTable(d, trades, bal) {
  const top = d.episodes.map((e, i) => ({ e, i })).sort((a, b) => (b.e.depth - a.e.depth) || (a.i - b.i)).slice(0, 10);
  const head = ['Rank', 'High', 'Low', 'Recovered', 'Depth', ...(bal !== null ? ['Depth %', 'Gain to recover'] : []), 'Trades to low', 'Trades', 'Days'];
  const rows = top.map(({ e }, k) => [
    `${k + 1}`, whenStart(e), day(trades[e.trough_i].close_ts), e.recovered ? day(e.end_ts) : 'not yet',
    { text: down(e.depth), cls: 'loss', k: k ? null : 'deep_depth' },
    ...(bal !== null ? [pct(e.depth_pct, 2), pct(e.recovery_gain, 2)] : []),
    intText(e.trades_to_trough), { text: intText(e.trades), k: k ? null : 'deep_trades' }, { text: intText(e.days), k: k ? null : 'deep_days' }]);
  const cap = d.episodes.length > 10 ? `The 10 deepest of ${intText(d.episodes.length)} drawdowns` : `All ${plural(d.episodes.length, 'drawdown', 'drawdowns')}, deepest first`;
  return el('section', { 'aria-labelledby': 'dd-list-h' },
    el('h3', { id: 'dd-list-h', text: 'The deepest drawdowns' }),
    Object.assign(tableWrap('The deepest drawdowns', rowsTable(cap, head, rows)), { className: 'table-wrap table-wide' }),
    el('p', { class: 'small muted', text: 'High, Low and Recovered are the close dates of the trade that set the high, the lowest point and the trade that recovered it. “Trades” counts the trades after the high, up to and including the one that recovered it; “Days” are calendar days from the high to the recovery. A drawdown that has not recovered is counted to the last trade in the file.' }));
}

// ------------------------------------------------------------------ underwater chart
const NS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
}

function chart(d) {
  const pts = d.curve, n = pts.length;
  const W = Math.round(Math.max(320, Math.min(760, $('dd-drop').clientWidth || 640)));
  const H = 200, L = 92, R = 8, T = 10, B = 22, h = H - T - B;
  const lo = Math.min(0, ...pts.map((p) => p.drawdown));
  const x = (i) => L + (n === 1 ? 0 : (i * (W - L - R)) / (n - 1));
  const y = (v) => T + (lo === 0 ? 0 : (v / lo) * h);
  const step = Math.max(1, Math.ceil(n / 600));
  const idx = [];
  for (let i = 0; i < n; i += step) {        // the lowest point of each bucket, so no low is skipped
    let b = i;
    for (let j = i; j < Math.min(n, i + step); j++) if (pts[j].drawdown < pts[b].drawdown) b = j;
    idx.push(b);
  }
  if (idx[idx.length - 1] !== n - 1) idx.push(n - 1);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-labelledby': 'dd-chart-t' });
  svg.append(svgEl('title', { id: 'dd-chart-t' }, `Drawdown from the previous high after each of ${intText(n)} closed trades`));
  svg.append(svgEl('line', { class: 'grid-line', x1: L, x2: W - R, y1: T, y2: T }));
  svg.append(svgEl('text', { class: 'axis', x: L - 6, y: T + 4, 'text-anchor': 'end' }, money(0, state.unit)));
  svg.append(svgEl('path', { class: 'area-dd', d: `M${x(0)},${T} ` + idx.map((i) => `L${x(i).toFixed(1)},${y(pts[i].drawdown).toFixed(1)}`).join(' ') + ` L${x(n - 1)},${T} Z` }));
  svg.append(svgEl('line', { class: 'grid-line', x1: L, x2: W - R, y1: T + h, y2: T + h }));
  svg.append(svgEl('text', { class: 'axis', x: L - 6, y: T + h + 4, 'text-anchor': 'end' }, money(lo, state.unit)));
  if (d.deepest) {
    const wi = d.deepest.trough_i;
    svg.append(svgEl('circle', { cx: x(wi), cy: y(lo), r: 4, class: 'annot' }));
    svg.append(svgEl('text', { class: 'annot', x: Math.min(x(wi) + 8, W - 130), y: Math.max(T + 14, y(lo) - 8) }, 'largest drawdown'));
  }
  svg.append(svgEl('text', { class: 'axis', x: L, y: H - 2 }, 'trade 1'));
  svg.append(svgEl('text', { class: 'axis', x: W - R, y: H - 2, 'text-anchor': 'end' }, `trade ${intText(n)}`));
  // Table fallback: at most 40 rows (every k-th trade, the last trade and the low point).
  const k = Math.max(1, Math.ceil(n / 40));
  const rows = [];
  for (let i = k - 1; i < n; i += k) rows.push(i);
  if (rows[rows.length - 1] !== n - 1) rows.push(n - 1);
  if (d.deepest && !rows.includes(d.deepest.trough_i)) { rows.push(d.deepest.trough_i); rows.sort((a, b) => a - b); }
  const table = rowsTable(k === 1 ? 'Drawdown after each trade' : `Drawdown after every ${k}th trade, the last trade and the low point`,
    ['Trade', 'Closed', 'Equity', 'Drawdown'],
    rows.map((i) => [`${i + 1}`, day(pts[i].ts), money(pts[i].equity, state.unit), money(pts[i].drawdown, state.unit)]));
  return el('section', { 'aria-labelledby': 'dd-chart-h' },
    el('h3', { id: 'dd-chart-h', text: 'Underwater chart' }),
    el('figure', { class: 'chart' }, svg,
      el('figcaption', { text: `Distance below the previous high after each closed trade · n = ${plural(n, 'closed trade', 'closed trades')} · ${state.fileLabel === SAMPLE_LABEL ? 'synthetic sample data, not a real trader' : 'from your file'}` }),
      el('details', {}, el('summary', { text: 'Show the chart as a table' }), tableWrap('Drawdown as a table', table))));
}

// ------------------------------------------------------------------ teaser (true figures only)
function teaser(d) {
  const box = $('dd-teaser');
  // paid_report on: no teaser box (partials/tool_next_step.html is the one offer, never next to a result)
  if (!box) return;
  const lead = reportLead(box);
  const text = $('dd-teaser-text');
  if (d && d.deepest && d.n >= 30) {
    const a = openedAfterLoss(state.result.trades, d.deepest);
    if (a.hits > 0) {
      text.textContent = `Your deepest drawdown ran ${plural(a.n, 'trade', 'trades')}, and ${pct(a.hits / a.n, 0)} of the trades inside it were opened within 15 minutes of a loss. ${lead} tests whether trades opened within 15 minutes of a loss turned out differently from the rest, and what they totalled in your file.`;
      text.dataset.live = 'true';
      return;
    }
  }
  text.textContent = `${lead} looks at what you do after a loss and after a run of losses, in your own trade file.`;
  delete text.dataset.live;
}

// ------------------------------------------------------------------ wiring
function init() {
  $('dd-q-form').addEventListener('submit', quick);
  $('dd-q-js-needed').hidden = true;
  $('dd-q-form').hidden = false;
  wireFileTool('dd', {
    onClear: clearOutput,
    onResult: (result, fileLabel) => { state = { result, unit: result.trades[0].pnl_unit, fileLabel }; render(); },
  });
  $('dd-balance').addEventListener('change', () => { if (state) render(false); else startingBalance(); });
}

init();
