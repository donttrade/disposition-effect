// trade-stats.js — /tools/trade-stats/: free stats from the visitor's own trade file.
//
// Privacy by construction:
//  * The file is read with FileReader APIs in this tab and parsed by the engine
//    (../engine/), which only ever keeps whitelisted columns.
//  * The page's CSP is connect-src 'none', so even a bug here could not send it anywhere.
//  * Nothing is written to storage or cookies; the only stored value on the site is the
//    theme (theme.js). Nothing is logged to the console.
//  * The file is parsed, and the noise checks run, in a Web Worker (read-file.js), so a
//    100,000-row file never freezes the page; an HTML report is parsed on the page.
//
// Every figure shown is computed by the engine (stats.js, noise.js). The teaser line uses
// only those figures. Missing values print as "—", never NaN/Infinity/undefined.

import { readTradeFile, startProgress } from './read-file.js';
import { LIMITS, MESSAGES } from '../engine/errors.js';
import { freeStats, equityCurve, NO_LOSSES } from '../engine/stats.js';
import { LABELS, N_PERM } from '../engine/noise.js';
import { money, unitNote, pct, ratio, duration, day, intText, el, signClass, DASH } from './format.js';
import { parsePositive, InputError } from './num.js';

const $ = (id) => document.getElementById(id);

const FORMAT_NAMES = {
  mt5: 'MetaTrader 5 report', mt4: 'MetaTrader 4 statement', ibkr_flex: 'Interactive Brokers Flex Query',
  tradovate_orders: 'Tradovate Orders export', generic: 'donttrade CSV template (one row per fill)',
  generic_roundtrip: 'CSV with one row per round trip',
};

const CHECK_TEXT = {
  expectancy: ['Mean result per trade', 'Is the average result per trade different from zero, or could random signs give one this far from zero?'],
  hold_gap_s: ['Hold time, losers vs winners', 'Is the gap between how long losing and winning trades were held larger than shuffling the win/loss labels gives?'],
  longest_losing_streak: ['Longest losing streak', 'Is the longest run of losses longer than the same trades in a random order give?'],
};

let state = null; // {result, unit, fileLabel} of the file on screen; never persisted
let worker = null;  // the noise-check worker, used after an HTML report read on the page
let reading = null; // the file being read: {cancel()}
let stopProgress = () => {};
let readSeq = 0;    // which read is the latest; an older result is dropped

// ------------------------------------------------------------------ status / errors
function status(text) {
  const s = $('ts-status');
  s.textContent = text;
  s.hidden = !text;
}

function showError(err) {
  const box = $('ts-error');
  box.replaceChildren(
    el('strong', { text: 'This file could not be read' }),
    el('p', { text: err.message }),
    el('p', { class: 'small', text: `Error code ${err.code}. If your platform is not listed, copy your trades into the CSV template (Date, Time, Symbol, Side, Quantity, Price) and try again.` }));
  box.hidden = false;
  box.focus();
}

function clearOutput() {
  if (worker) { worker.terminate(); worker = null; }
  if (reading) { reading.cancel(); reading = null; }
  stopProgress();
  $('ts-error').hidden = true;
  $('ts-out').replaceChildren();
  $('ts-out').hidden = true;
  $('ts-teaser').hidden = true;
}

// ------------------------------------------------------------------ input
async function fromFile(file) {
  clearOutput();
  if (!file) return;
  if (file.size > LIMITS.MAX_BYTES) { // refuse before reading a huge file into memory
    showError({ code: 'E_TOO_LARGE', message: MESSAGES.E_TOO_LARGE });
    return;
  }
  status('Reading your file in this tab…');
  const bytes = new Uint8Array(await file.arrayBuffer());
  analyse(bytes, 'your file');
}

function fromSample() {
  clearOutput();
  const text = $('ts-sample').textContent.replace(/^\s+/, '');
  analyse(new TextEncoder().encode(text), 'the synthetic sample file');
}

async function analyse(bytes, fileLabel) {
  stopProgress = startProgress($('ts-progress'));
  const mine = ++readSeq;
  const job = readTradeFile(bytes, {
    noise: true,
    onStage: status,
    onNoise: (noise) => {
      if (mine !== readSeq) return; // a newer file replaced this one
      reading = null;
      if (!noise) { $('ts-noise-status').textContent = 'The checks could not run in this browser.'; return; }
      renderNoise(noise, state.result.trades.length);
    },
  });
  reading = job;
  let out;
  try { out = await job.done; } finally { if (mine === readSeq) { stopProgress(); status(''); } }
  if (mine !== readSeq) return; // a newer file replaced this one
  if (out.error) { reading = null; showError(out.error); return; }
  const r = out.result;
  state = { result: r, unit: r.trades[0].pnl_unit, fileLabel };
  await render();
  if (mine !== readSeq) return;
  if (out.onPage) { reading = null; runNoise(r.trades); } // an HTML report was read on the page
  else job.runNoise();
}

// Hand the main thread back between the heavy steps, so a 50,000-trade file never blocks it
// for long (Tester D7): the browser paints and handles input in between.
const breathe = () => new Promise((resolve) => setTimeout(resolve, 0));
const BIG = 5000;

function startingBalance() {
  const input = $('ts-balance');
  const err = $('ts-balance-err');
  err.hidden = true;
  input.removeAttribute('aria-invalid');
  if (!input.value.trim()) return null;
  try {
    return parsePositive(input.value, 'the starting balance');
  } catch (e) {
    if (!(e instanceof InputError)) throw e;
    err.textContent = e.message;
    err.hidden = false;
    input.setAttribute('aria-invalid', 'true');
    return null;
  }
}

// ------------------------------------------------------------------ rendering
function statRow(label, value, cls, key) {
  return el('div', { class: 'stat' }, el('dt', { text: label }), el('dd', { class: cls, text: value, 'data-k': key }));
}

function tableWrap(label, table) {
  return el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': label }, table);
}

function rowsTable(caption, head, rows) {
  return el('table', {},
    el('caption', { text: caption }),
    el('thead', {}, el('tr', {}, ...head.map((h, i) => el('th', { scope: 'col', class: i ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows.map((r) => el('tr', {},
      el('th', { scope: 'row', text: r[0] }),
      ...r.slice(1).map((c) => (c instanceof Node ? el('td', { class: 'num' }, c) :
        el('td', { class: 'num ' + (c && c.cls ? c.cls : ''), text: c && c.text !== undefined ? c.text : c, 'data-k': c && c.k ? c.k : null })))))));
}

// "8 trades, −$195.40" in two unbreakable pieces, so a phone never wraps after the minus.
const streak = (st, k) => el('span', { 'data-k': k },
  el('span', { class: 'nowrap', text: `${intText(st.n)} trades,` }), ' ', el('span', { class: 'nowrap', text: money(st.pnl, state.unit) }));

const m = (n, k) => ({ text: money(n, state.unit), cls: signClass(n) || '', k });

async function render(focus = true) {
  const r = state.result;
  // A big file is drawn in steps; a normal one (up to BIG trades) at once, with no await.
  const big = r.trades.length > BIG;
  const s = freeStats(r.trades, startingBalance());
  if (big) await breathe();
  const points = equityCurve(r.trades);
  if (big) await breathe();
  if (state.result !== r) return; // another file arrived meanwhile
  state.stats = s; // the hold-time figures do not depend on the balance; the teaser reuses them
  const out = $('ts-out');
  out.replaceChildren(el('h2', { id: 'ts-out-h', tabindex: '-1', text: state.fileLabel === 'the synthetic sample file' ? 'Results: synthetic sample file' : 'Results: your file' }));

  // What was read
  const first = r.trades[0], last = r.trades[r.trades.length - 1];
  const read = el('section', { 'aria-labelledby': 'ts-read-h' },
    el('h3', { id: 'ts-read-h', text: 'What was read' }),
    el('p', {}, `Format: ${FORMAT_NAMES[r.format] || r.format}${r.verified_format ? '' : ' (beta)'}. `,
      `${intText(r.trades.length)} closed trades from ${intText(r.n_fills)} fills, closed ${day(first.close_ts)} to ${day(last.close_ts)}. `,
      `Times are ${r.tz_label}. ${unitNote(state.unit)}`),
  );
  if (state.fileLabel === 'the synthetic sample file') {
    read.append(el('p', { class: 'notice notice-caution' }, el('strong', { text: 'Sample data' }), 'Synthetic trades made up for this demo, not a real trader.'));
  }
  if (r.warnings.length) {
    read.append(el('div', { class: 'notice notice-caution', id: 'ts-warnings' },
      el('strong', { text: r.warnings.length === 1 ? '1 note about this file' : `${r.warnings.length} notes about this file` }),
      el('ul', {}, ...r.warnings.map((w) => el('li', { 'data-code': w.code, text: w.message })))));
  }
  out.append(read);

  // Headline numbers
  const pf = s.profit_factor === NO_LOSSES ? NO_LOSSES : ratio(s.profit_factor).replace('×', '');
  out.append(el('section', { 'aria-labelledby': 'ts-head-h' },
    el('h3', { id: 'ts-head-h', text: 'Headline numbers' }),
    el('dl', { class: 'stats' },
      statRow('Closed trades', intText(s.n), null, 'n'),
      statRow('Net result', money(s.net_pnl, state.unit), signClass(s.net_pnl), 'net_pnl'),
      statRow('Win rate', pct(s.win_rate), null, 'win_rate'),
      statRow('Profit factor', pf, null, 'profit_factor'),
      statRow('Mean result per trade', money(s.expectancy, state.unit), signClass(s.expectancy), 'expectancy'),
      statRow('Largest drawdown', money(-s.max_drawdown_abs, state.unit, { sign: true }), s.max_drawdown_abs > 0 ? 'loss' : null, 'max_drawdown_abs'))));

  // Equity and drawdown chart
  out.append(chart(points));

  // Full stats table
  const ddPct = s.max_drawdown_pct === null ? 'enter a starting balance above' : pct(s.max_drawdown_pct);
  out.append(el('section', { 'aria-labelledby': 'ts-all-h' },
    el('h3', { id: 'ts-all-h', text: 'All statistics' }),
    tableWrap('All statistics', rowsTable('Closed trades, net of fees where the file has them', ['Statistic', 'Value'], [
      ['Winning / losing / break-even trades', { text: `${intText(s.wins)} / ${intText(s.losses)} / ${intText(s.scratch)}`, k: 'wls' }],
      ['Win rate (break-even trades left out)', { text: pct(s.win_rate), k: 'win_rate' }],
      ['Gross profit', m(s.gross_profit, 'gross_profit')],
      ['Gross loss', m(s.gross_loss, 'gross_loss')],
      ['Profit factor (gross profit ÷ gross loss)', { text: pf, k: 'profit_factor' }],
      ['Mean result per trade (expectancy)', m(s.expectancy, 'expectancy')],
      ['Average winning trade', m(s.avg_win, 'avg_win')],
      ['Average losing trade', m(s.avg_loss, 'avg_loss')],
      ['Largest winning trade', m(s.largest_win, 'largest_win')],
      ['Largest losing trade', m(s.largest_loss, 'largest_loss')],
      ['Longest winning streak', streak(s.max_consec_wins, 'max_consec_wins')],
      ['Longest losing streak', streak(s.max_consec_losses, 'max_consec_losses')],
      ['Largest drawdown (closed-trade equity)', { text: money(-s.max_drawdown_abs, state.unit), k: 'max_drawdown_abs' }],
      ['Largest drawdown, % of balance', { text: ddPct, k: 'max_drawdown_pct' }],
      ['Median hold, winning trades', { text: duration(s.hold_median_win_s), k: 'hold_median_win_s' }],
      ['Median hold, losing trades', { text: duration(s.hold_median_loss_s), k: 'hold_median_loss_s' }],
      ['Losing hold ÷ winning hold', { text: ratio(s.hold_ratio), k: 'hold_ratio' }],
    ])),
    tableWrap('Long and short trades', rowsTable('Long and short trades', ['Side', 'Trades', 'Win rate', 'Net result'], [
      ['Long', intText(s.long.n), pct(s.long.win_rate), m(s.long.pnl)],
      ['Short', intText(s.short.n), pct(s.short.win_rate), m(s.short.pnl)],
    ]))));

  // Noise checks: filled in by the worker
  out.append(el('section', { 'aria-labelledby': 'ts-noise-h', id: 'ts-noise' },
    el('h3', { id: 'ts-noise-h', text: 'Real or noise?' }),
    el('p', { text: `Three checks, each repeated ${intText(N_PERM)} times on shuffled copies of your own trades. A figure is "${LABELS.real}" when fewer than 5% of the shuffles come out as far from zero as your real trades; otherwise it "${LABELS.noise}". Under 30 trades in a group the check is not run, and the result says "${LABELS.tooFew}".` }),
    el('p', { id: 'ts-noise-status', role: 'status', text: 'Running the checks…' })));

  out.hidden = false;
  if (focus) $('ts-out-h').focus();
}

// ------------------------------------------------------------------ chart
const NS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  return e;
}

function chart(points) {
  // viewBox width = the width it will be drawn at (320–760 px), so the 12 px axis labels
  // stay 12 px on a phone and on a desktop instead of scaling with the SVG.
  const W = Math.round(Math.max(320, Math.min(760, $('ts-drop').clientWidth || 640)));
  const H = 300, L = 92, R = 8, T = 10, eqH = 180, gap = 24, ddH = H - T - eqH - gap - 22;
  const n = points.length;
  const eqs = points.map((p) => p.equity), dds = points.map((p) => p.drawdown);
  const hi = Math.max(0, ...eqs), lo = Math.min(0, ...eqs), ddLo = Math.min(...dds, 0);
  const x = (i) => L + (n === 1 ? 0 : (i * (W - L - R)) / (n - 1));
  const yEq = (v) => T + (hi === lo ? eqH / 2 : ((hi - v) * eqH) / (hi - lo));
  const ddTop = T + eqH + gap;
  const yDd = (v) => ddTop + (ddLo === 0 ? 0 : (v / ddLo) * ddH);
  // At most ~600 points in the path: enough for a 640-wide chart; extremes kept per bucket.
  const step = Math.max(1, Math.ceil(n / 600));
  const idx = [];
  for (let i = 0; i < n; i += step) {
    let a = i, b = i;
    for (let j = i; j < Math.min(n, i + step); j++) { if (eqs[j] > eqs[a]) a = j; if (eqs[j] < eqs[b]) b = j; }
    idx.push(...(a < b ? [a, b] : a > b ? [b, a] : [a]));
  }
  if (idx[idx.length - 1] !== n - 1) idx.push(n - 1);
  const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-labelledby': 'ts-chart-t' });
  svg.append(Object.assign(svgEl('title', { id: 'ts-chart-t' }), { textContent: `Equity and drawdown after each of ${n} closed trades` }));
  const ticks = [hi, lo];
  // zero gets its own gridline only inside the range and when its label would not collide
  if (lo < 0 && hi > 0 && Math.abs(yEq(0) - yEq(lo)) > 16 && Math.abs(yEq(0) - yEq(hi)) > 16) ticks.push(0);
  for (const v of ticks) {
    const y = yEq(v);
    svg.append(svgEl('line', { class: 'grid-line', x1: L, x2: W - R, y1: y, y2: y }));
    svg.append(Object.assign(svgEl('text', { class: 'axis', x: L - 6, y: y + 4, 'text-anchor': 'end' }), { textContent: money(v, state.unit) }));
  }
  svg.append(svgEl('polyline', { class: 'line-actual', points: idx.map((i) => `${x(i).toFixed(1)},${yEq(eqs[i]).toFixed(1)}`).join(' ') }));
  svg.append(Object.assign(svgEl('text', { class: 'axis', x: L, y: ddTop - 6 }), { textContent: 'Drawdown from the previous high' }));
  svg.append(svgEl('line', { class: 'grid-line', x1: L, x2: W - R, y1: ddTop, y2: ddTop }));
  svg.append(svgEl('path', { class: 'area-dd', d: `M${x(0)},${ddTop} ` + idx.map((i) => `L${x(i).toFixed(1)},${yDd(dds[i]).toFixed(1)}`).join(' ') + ` L${x(n - 1)},${ddTop} Z` }));
  svg.append(Object.assign(svgEl('text', { class: 'axis', x: L - 6, y: ddTop + ddH + 4, 'text-anchor': 'end' }), { textContent: money(ddLo, state.unit) }));
  // one rust annotation: where the largest drawdown bottomed out
  const worst = dds.indexOf(ddLo);
  if (ddLo < 0) {
    svg.append(svgEl('circle', { cx: x(worst), cy: yDd(ddLo), r: 4, class: 'annot' }));
    svg.append(Object.assign(svgEl('text', { class: 'annot', x: Math.min(x(worst) + 8, W - 150), y: Math.min(yDd(ddLo) - 8, H - 24) }), { textContent: 'largest drawdown' }));
  }
  svg.append(Object.assign(svgEl('text', { class: 'axis', x: L, y: H - 2 }), { textContent: `trade 1` }));
  svg.append(Object.assign(svgEl('text', { class: 'axis', x: W - R, y: H - 2, 'text-anchor': 'end' }), { textContent: `trade ${intText(n)}` }));

  // Table fallback: at most 40 rows (every k-th trade, always the last one and the low point).
  const k = Math.max(1, Math.ceil(n / 40));
  const rows = [];
  for (let i = k - 1; i < n; i += k) rows.push(i);
  if (rows[rows.length - 1] !== n - 1) rows.push(n - 1);
  if (ddLo < 0 && !rows.includes(worst)) { rows.push(worst); rows.sort((a, b) => a - b); }
  const table = rowsTable(k === 1 ? 'Equity after each trade' : `Equity after every ${k}th trade, the last trade and the low point`,
    ['Trade', 'Closed', 'Equity', 'Drawdown'],
    rows.map((i) => [`${i + 1}`, day(points[i].ts), money(eqs[i], state.unit), money(dds[i], state.unit)]));
  return el('section', { 'aria-labelledby': 'ts-chart-h' },
    el('h3', { id: 'ts-chart-h', text: 'Equity and drawdown' }),
    el('figure', { class: 'chart' }, svg,
      el('figcaption', { text: `n = ${intText(n)} closed trades, in closing order · ${state.fileLabel === 'the synthetic sample file' ? 'synthetic sample data, not a real trader' : 'from your file'} · equity starts at 0` }),
      el('details', {}, el('summary', { text: 'Show the chart as a table' }), tableWrap('Equity and drawdown as a table', table))));
}

// ------------------------------------------------------------------ noise checks
function runNoise(trades) {
  worker = new Worker(new URL('../engine/noise-worker.js', import.meta.url), { type: 'module' });
  const started = trades.length;
  worker.onmessage = (ev) => {
    worker.terminate(); worker = null;
    if (ev.data.error || !ev.data.noise) { $('ts-noise-status').textContent = 'The checks could not run in this browser.'; return; }
    renderNoise(ev.data.noise, started);
  };
  worker.onerror = () => { $('ts-noise-status').textContent = 'The checks could not run in this browser.'; };
  // Only two numbers per trade go to the worker: no symbol, no time, nothing else.
  worker.postMessage({ trades: trades.map((t) => ({ pnl: t.pnl, hold_s: t.hold_s })) });
}

function badge(label) {
  const cls = label === LABELS.real ? 'badge badge-real' : label === LABELS.tooFew ? 'badge badge-few' : 'badge badge-noise';
  return el('span', { class: cls, text: label });
}

function observed(c) {
  if (c.value === null) return DASH;
  if (c.stat === 'expectancy') return money(c.value, state.unit);
  if (c.stat === 'hold_gap_s') return (c.value < 0 ? 'losers shorter by ' : 'losers longer by ') + duration(Math.abs(c.value));
  return `${intText(c.value)} losses in a row`;
}

function renderNoise(noise, total) {
  const st = $('ts-noise-status');
  st.textContent = noise.limited ? `Checked on your most recent ${intText(noise.n_used)} of ${intText(total)} trades (the limit for these checks).` : 'Done.';
  const rows = noise.checks.map((c) => {
    const [name, q] = CHECK_TEXT[c.stat];
    const n = c.n_b === null ? intText(c.n_a) : `${intText(c.n_a)} losing, ${intText(c.n_b)} winning`;
    return el('tr', { 'data-check': c.stat },
      el('th', { scope: 'row' }, el('span', { text: name }), el('br'), el('span', { class: 'small muted', text: q })),
      el('td', { class: 'num', text: n }),
      el('td', { class: 'num', text: observed(c) }),
      el('td', { class: 'num', text: c.p === null ? DASH : c.p.toFixed(4) }),
      el('td', {}, badge(c.label)));
  });
  const table = el('table', {},
    el('caption', { text: 'Real-or-noise checks on this file' }),
    el('thead', {}, el('tr', {}, ...['Check', 'Trades', 'In your file', 'p', 'Result'].map((h, i) => el('th', { scope: 'col', class: i && i < 4 ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows));
  $('ts-noise').append(tableWrap('Real-or-noise checks', table),
    el('p', { class: 'small muted', text: 'p is the share of shuffles at least as extreme as your file. A small p says the pattern is unlikely to be luck in this file; it does not say it will continue.' }));
  teaser(noise);
}

// The teaser states only figures computed above: the hold gap and its check result.
function teaser(noise) {
  const s = state.stats || freeStats(state.result.trades);
  const gap = noise.checks.find((c) => c.stat === 'hold_gap_s');
  const text = $('ts-teaser-text');
  if (s.hold_ratio !== null && gap) {
    text.textContent = `In this file, losing trades were held ${ratio(s.hold_ratio)} as long as winning trades (median ${duration(s.hold_median_loss_s)} against ${duration(s.hold_median_win_s)}), and the check above says: ${gap.label}. We're building a habit report that tests five habits like this one and shows what the matching trades totalled in your file.`;
  } else {
    text.textContent = "We're building a habit report that looks for patterns in what you do after a loss, and tests each one for noise.";
  }
  $('ts-teaser').hidden = false;
}

// ------------------------------------------------------------------ wiring
function init() {
  const input = $('ts-file');
  input.addEventListener('change', () => { fromFile(input.files[0]); input.value = ''; });
  $('ts-sample-btn').addEventListener('click', fromSample);
  $('ts-balance').addEventListener('change', async () => {
    if (!state) { startingBalance(); return; }
    const keep = $('ts-noise');
    await render(false);
    if ($('ts-noise') !== keep) $('ts-noise').replaceWith(keep);
  });
  const dz = $('ts-drop');
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('is-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('is-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('is-over');
    if (e.dataTransfer && e.dataTransfer.files[0]) fromFile(e.dataTransfer.files[0]);
  });
  $('ts-js-needed').hidden = true;
  $('ts-controls').hidden = false;
}

init();
