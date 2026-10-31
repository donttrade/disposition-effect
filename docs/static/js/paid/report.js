// report.js — /report/ (paid flag only).
//
// 1. The trade file is parsed IN THIS TAB by the same engine as the free tools.
// 2. strip.js reduces it to StrippedRows; pgr.js to four counts. Nothing else is sent.
// 3. POST /analyse with the access token → the Report → rendered here.
// Every number on the page comes from the server's Report or from the file in this
// tab; the wording only describes past trades (NON-ADVISER A3).

import { runFile } from '../engine/index.js?v=8410d06a';
import { ics, retestLine, RETEST_LINE } from './retest-copy.js?v=b3748546';
import { pgrPlrCounts } from '../engine/pgr.js?v=4c675fe5';
import { stripRows, spanLine } from './strip.js?v=03137080';
import { api, loadToken, saveToken, tokenFromHash, decodeToken, downloadRestoreFile, OUTAGE } from './token.js?v=16f6dd26';
import * as DT2 from './wording.js?v=bda30e6a';
import * as S2F from './verdict-stats2f.js?v=47600b9f';
import { factsSection, challengeSection, smallLayout, presetsFromPage } from './small-facts-view.js?v=7385cba9';
import { reportTrades } from './small-facts.js?v=78faeb32';

// DT-2 (ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §7 S1): the report's method_version picks its wording. wording.js
// words DT-2 reports; verdict-stats2f.js words a DT-1 report (2026-10-23.stats2f) for one release with the same
// interface (dual accept). Any other method goes to wording.js, whose checkReport refuses it (REPORT_ERROR).
const wordingFor = (report) => (report && report.method_version === S2F.METHOD_VERSION ? S2F : DT2);
let V = DT2;   // the wording of the report being drawn (renderReport sets it first)
const checkReport = (report) => wordingFor(report).checkReport(report);
const page1Lines = (report, fmt) => wordingFor(report).page1Lines(report, fmt);
const coverageLines = (report) => wordingFor(report).coverageLines(report);
const mergedLine = (report, fmt) => wordingFor(report).mergedLine(report, fmt);

const $ = (id) => document.getElementById(id);
const MINUS = '−';
const holdDays = DT2.holdDays;

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}

function grouped(n) {
  const [i, d] = Math.abs(n).toFixed(2).split('.');
  return i.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + '.' + d;
}

export function money(n, unit) {
  if (n === null || n === undefined) return '—';
  const sign = n < 0 ? MINUS : n > 0 ? '+' : '';
  if (unit === 'USD') return `${sign}$${grouped(n)}`;
  if (unit === 'points') return `${sign}${grouped(n)} pts`;
  // sweep 2: the unit is named once on the summary (unitLine), not after every amount
  if (unit === 'account' || unit === 'base') return `${sign}${grouped(n)}`;
  return `${sign}${grouped(n)} ${unit}`;
}

function unitLine(unit) {
  return unit === 'account' ? ' Amounts are in your account currency.' : unit === 'base' ? ' Amounts are in your base currency.' : '';
}

function duration(s) {
  if (s === null || s === undefined) return '—';
  s = Math.round(s);
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m ${s % 60}s`;
}

const pct = (x) => (x === null || x === undefined ? '—' : (100 * x).toFixed(1) + '%');
const num = (x, dp = 2) => (x === null || x === undefined ? '—' : x.toFixed(dp));
const count = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

// The formatters wording.js fills its sentences with (ARCHITECT-STATS-AMENDMENT-R2 §9: money as now).
const wordingFmt = (unit) => ({ money: (x) => money(x, unit), amount: (x) => money(Math.abs(x), unit).replace(/^\+/, ''), duration, ratio: (x) => num(x), count });

// DT-2 (plan §10 row 31): the pill is the habit's step ('Clear sign', 'Some sign', 'No sign'), or 'Too few trades', or
// 'No check on this file'; the words are the wording module's PILL map, never typed here, and never hold a digit.
// Only Clear uses the flag colour; Some sign is outlined at the same weight as No sign (§2.4 items 1–6).
const PILL_CLASS = { clear: 'badge badge-clear', some: 'badge badge-some', none: 'badge badge-none', too_few: 'badge badge-few',
  dates_only: 'badge badge-few', distinguishable: 'badge badge-none', not_distinguishable: 'badge badge-none' };
const pillClass = (h, key) => (V.isClear(h) ? 'badge badge-clear' : PILL_CLASS[key]);

// Habits with no check against chance (the hold gap and large losses; size after a loss in this release) are shown as
// "Your numbers": Layer 1 only, no pill (plan §10 row 29).
export const FACTS_ONLY = Object.freeze(['hold_gap', 'oversized_loss', 'size_up']);
const factsOnly = (h) => V.factsOnly(h);

function badge(h) {
  const key = V.pillOf(h);
  if (key === null) return null;
  if (!V.PILL[key] || !PILL_CLASS[key]) throw new Error(`report: unknown step ${key}`);
  return el('span', { class: pillClass(h, key), text: V.PILL[key] });
}

// Visible labels (owner, 29 Oct): the engine's name for oversized_loss is shown as "Large losses".
const NAMES = { oversized_loss: 'Large losses' };
export const nameOf = (h) => NAMES[h.id] || h.name;

// What each habit's two measures mean, in plain words. Only the descriptive habit
// (oversized_loss) shows this list; a tested habit shows the §7.1 sentences and detailLine().
function measures(h, unit) {
  switch (h.id) {
    case 'hold_gap': return [`Median hold of losing trades: ${duration(h.measure_a)}`, `Median hold of winning trades: ${duration(h.measure_b)}`, h.effect === null ? null : `Losers were held ${num(h.effect)} times as long as winners.`];
    case 'revenge': return [`Mean result, trades opened within 15 minutes of a losing trade's close: ${money(h.measure_a, unit)}`, `Mean result, other trades: ${money(h.measure_b, unit)}`, null];
    case 'size_up': return [`Median size after a loss (× your usual size): ${num(h.measure_a)}`, `Median size after a win: ${num(h.measure_b)}`, h.effect === null ? null : `Size after a loss was ${num(h.effect)} times size after a win.`];
    case 'tilt': return [`Mean result after 2 or more losses in a row: ${money(h.measure_a, unit)}`, `Mean result, other trades: ${money(h.measure_b, unit)}`,
      h.detail && h.detail.streak3_n ? `After 3 or more losses in a row: ${h.detail.streak3_n} trades, mean ${money(h.detail.streak3_mean, unit)}.` : null];
    case 'oversized_loss': return [`Share of all trades: ${pct(h.measure_a)}`, `Share of all loss dollars: ${pct(h.measure_b)}`, h.effect === null ? null : `Your median loss was ${money(-h.effect, unit)}.`];
    default: return [];
  }
}

// The one extra measure a tested habit's sentences leave out (hold_gap's ratio, tilt's 3-loss runs),
// or null. Shown only when the habit was tested (not too_few, not withheld).
function detailLine(h, unit) {
  if (h.p_raw === null) return null;
  if (h.id === 'hold_gap' || h.id === 'tilt') return measures(h, unit)[2];
  return null;
}

// Two bars from zero with direct labels; the table below it holds the same numbers.
function twoBarChart(h, unit, report) {
  if (h.measure_a === null || h.measure_b === null || h.id === 'oversized_loss') return null;
  const isMoney = h.id === 'revenge' || h.id === 'tilt';
  // T-3 T3-C: a dates-only file's holds are counted from dates: days, never minutes
  const fmt = (v) => (h.id === 'hold_gap' ? (report && report.dates_only ? holdDays(v) : duration(v)) : isMoney ? money(v, unit) : num(v));
  const labels = { hold_gap: ['Losing trades', 'Winning trades'], revenge: ['Soon after a loss', 'Other trades'],
    size_up: ['After a loss', 'After a win'], tilt: ['After 2+ losses', 'Other trades'] }[h.id];
  const vals = [h.measure_a, h.measure_b];
  const maxAbs = Math.max(Math.abs(vals[0]), Math.abs(vals[1])) || 1;
  // viewBox close to the rendered width (CSS caps .chart-bars at 420 px), so the
  // 12 px labels render at about 12–13 px on a phone and on a desktop.
  const W = 400, rowH = 34, x0 = 130, span = W - x0 - 10;
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${rowH * 2 + 10}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${nameOf(h)}: ${labels[0]} ${fmt(vals[0])}, ${labels[1]} ${fmt(vals[1])}`);
  const hasNeg = vals.some((v) => v < 0);
  const zero = hasNeg ? x0 + span / 2 : x0;
  const scale = (hasNeg ? span / 2 : span) / maxAbs;
  vals.forEach((v, i) => {
    const y = 6 + i * rowH;
    const t = document.createElementNS(ns, 'text');
    t.setAttribute('x', '0'); t.setAttribute('y', String(y + 15)); t.setAttribute('class', 'bar-label'); t.textContent = labels[i];
    const r = document.createElementNS(ns, 'rect');
    const w = Math.abs(v) * scale;
    r.setAttribute('x', String(v < 0 ? zero - w : zero)); r.setAttribute('y', String(y + 2));
    r.setAttribute('width', String(Math.max(w, 1))); r.setAttribute('height', '18');
    r.setAttribute('class', i === 0 && V.isClear(h) ? 'bar-flag' : (v < 0 ? 'bar-loss' : 'bar-plain'));
    svg.append(t, r);
  });
  const axis = document.createElementNS(ns, 'line');
  axis.setAttribute('x1', String(zero)); axis.setAttribute('x2', String(zero)); axis.setAttribute('y1', '4');
  axis.setAttribute('y2', String(rowH * 2 + 6)); axis.setAttribute('class', 'grid-line');
  svg.append(axis);
  const table = el('table', {},
    el('caption', { class: 'visually-hidden', text: nameOf(h) + ' as a table' }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Group' }), el('th', { scope: 'col', class: 'num', text: 'Trades' }), el('th', { scope: 'col', class: 'num', text: 'Value' }))),
    el('tbody', {},
      el('tr', {}, el('th', { scope: 'row', text: labels[0] }), el('td', { class: 'num', text: String(h.n_a) }), el('td', { class: 'num', text: fmt(vals[0]) })),
      el('tr', {}, el('th', { scope: 'row', text: labels[1] }), el('td', { class: 'num', text: String(h.n_b) }), el('td', { class: 'num', text: fmt(vals[1]) }))));
  return el('figure', { class: 'chart chart-bars' }, svg,
    el('figcaption', { text: `n = ${h.n_a} and ${h.n_b} trades · from your file · historical` }),
    el('details', {}, el('summary', { text: 'Show as a table' }), el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': nameOf(h) + ' table' }, table)));
}

// Layer 1, "What happened": the figures the server already computed (matching trades and their total, the two
// group values and the gap between them), as a short list; the chart shows the same two values.
function happenedList(h, unit, report) {
  const items = [];
  if (h.dollars) items.push([h.dollars.label, `${count(h.dollars.n_trades)} trades, totalling ${money(h.dollars.amount, unit)} (historical)`]);
  const a = h.measure_a, b = h.measure_b;
  if (a !== null && b !== null && h.id !== 'oversized_loss') {
    const lab = { hold_gap: ['Median hold, losing trades', 'Median hold, winning trades'],
      revenge: ['Average, trades soon after a loss', 'Average, other trades'], size_up: ['Median size after a loss (× usual)', 'Median size after a win (× usual)'],
      tilt: ['Average after 2+ losses in a row', 'Average, other trades'] }[h.id];
    const f = (v) => (h.id === 'hold_gap' ? (report.dates_only ? holdDays(v) : duration(v)) : (h.id === 'size_up' ? num(v) : money(v, unit)));
    items.push([lab[0], f(a)], [lab[1], f(b)]);
    if (h.id === 'revenge' || h.id === 'tilt') items.push(['Gap per trade', money(a - b, unit)]);
    else if (h.id === 'hold_gap') items.push(['Gap', (a >= b ? '' : MINUS) + (report.dates_only ? holdDays(Math.abs(a - b)) : duration(Math.abs(a - b)))]);
    else if (h.effect !== null) items.push(['Gap', `${num(h.effect)}× size after a win`]);
  } else if (h.id === 'oversized_loss') {
    items.push(['Share of all trades', pct(h.measure_a)], ['Share of all loss dollars', pct(h.measure_b)]);
    if (h.effect !== null) items.push(['Your median loss', money(-h.effect, unit)]);
  }
  if (!items.length) return null;
  const dl = el('dl', { class: 'happened' });
  for (const [k, v] of items) dl.append(el('div', {}, el('dt', { text: k }), el('dd', { text: v })));
  return dl;
}

// Layer 2, "Habit or chance?" (plan §9.4 item 2): the step pill, then the step line, the guard line under every
// Some sign and Clear sign number, and the catch line under every No sign and Some sign (§2.4, §5.2); or the
// too-few or dates-only line. Every line is the wording module's own.
function checkLayer(h, lines, figure = null) {
  const box = el('div', { class: 'layer layer-check' }, el('h4', { text: V.CHECK_HEADING }));
  box.append(el('p', { class: 'check-pill' }, badge(h)));
  for (const s of lines) box.append(el('p', { class: s === DT2.GUARD_LINE ? 'small habit-guard' : 'habit-sentence', text: s }));
  if (figure) box.append(catchTable(figure));
  return box;
}

// The catch figure (§5.2; buyer read-through, 31 Oct): the lead line, then a table, one row per file size, each with
// a bar filled to the engine's lower bound (tenths, never more) and the same words beside it, so the bar is never the
// only carrier. A real table with a caption and headers for screen readers.
function catchTable(g) {
  const tbody = el('tbody');
  for (const r of g.rows) {
    const fill = el('span', { class: 'catch-fill' });
    fill.style.width = (10 * r.tenths) + '%';   // CSSOM, allowed by the CSP
    tbody.append(el('tr', {}, el('th', { scope: 'row', text: r.size }),
      el('td', {}, el('span', { class: 'catch-bar', 'aria-hidden': 'true' }, fill), el('span', { class: 'catch-val', text: r.value }))));
  }
  return el('div', { class: 'catch' }, el('p', { class: 'habit-sentence habit-catch', text: g.lead }),
    el('table', { class: 'catch-table' }, el('caption', { class: 'visually-hidden', text: DT2.CATCH_CAPTION }),
      el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: DT2.CATCH_HEAD[0] }), el('th', { scope: 'col', text: DT2.CATCH_HEAD[1] }))), tbody));
}

function habitSection(h, unit, report) {
  const sec = el('section', { class: 'habit', id: 'habit-' + h.id, 'aria-labelledby': 'h-' + h.id });
  const lines = V.habitLines(h, report, wordingFmt(unit));
  if (report.dates_only && ['revenge', 'tilt', 'size_up'].includes(h.id)) {
    // R-D3 addendum 3: no question with its 15-minute figure, no measure, no dollars, no chart, no research line
    const what = el('div', { class: 'layer layer-what' }, el('h4', { text: 'What happened' }));
    if (lines.what.length) for (const x of lines.what) what.append(el('p', { class: 'habit-sentence', text: x }));
    else what.append(el('p', { class: 'muted', text: 'No figure for this file.' }));
    sec.append(el('h3', { id: 'h-' + h.id, text: nameOf(h) }), what);
    if (!factsOnly(h)) sec.append(checkLayer(h, lines.check, lines.figure));
    return sec;
  }
  sec.append(el('h3', { id: 'h-' + h.id, text: nameOf(h) }), el('p', { class: 'muted', text: h.question }));
  const what = el('div', { class: 'layer layer-what' }, el('h4', { text: 'What happened' }));
  for (const x of lines.what) what.append(el('p', { class: 'habit-sentence', text: x }));   // the fact line first (§2.4)
  const chart = twoBarChart(h, unit, report);
  if (chart) what.append(chart);
  const list = happenedList(h, unit, report);
  if (list) what.append(list);
  const extra = detailLine(h, unit);
  if (extra) what.append(el('p', { text: extra }));
  sec.append(what);
  if (!factsOnly(h)) sec.append(checkLayer(h, lines.check, lines.figure));
  // Expert details (plan §10 row 37): the method line with the habit's own n_perm, the reshuffle count and the
  // adjusted p, and the catch figure's premise in full (§5.2).
  const how = el('div', {});
  const method = V.methodLine(h, wordingFmt(unit), report);
  if (method) how.append(el('p', { class: 'small muted habit-method', text: method }));
  const expert = V.expertLine(h, report, wordingFmt(unit));
  if (expert) how.append(el('p', { class: 'small muted habit-expert', text: expert }));
  const ch = !factsOnly(h) && h.step !== 'clear' ? V.catchHow(h, wordingFmt(unit)) : null;
  if (ch) how.append(el('p', { class: 'small muted catch-how', text: ch }));
  // R-D3 addendum I-6: the page's own related-research line (wording.js RESEARCH), never the report's
  // research_ref; oversized_loss has none.
  const res = Object.prototype.hasOwnProperty.call(V.RESEARCH, h.id) ? V.RESEARCH[h.id] : null;
  if (res) {
    const cite = el('p', { class: 'small research' }, V.RESEARCH_PREFIX + res.line + ' ');
    cite.append(el('a', { href: res.url, rel: 'noopener', text: res.cite }));
    how.append(cite);
  }
  if (how.childNodes.length) sec.append(el('details', { class: 'how-more habit-how' }, el('summary', { text: 'How this was measured' }), how));
  return sec;
}

// sweep 3 (29 Oct, owner): "All habits measured" as a picture. On top, each checked habit's step as a big pill;
// then one row per habit, dollars first and the step second (plan §9.4 item 1): its dollar total with a bar scaled to
// the largest, the trade count as a badge, then its pill. Each row is a link to its section below. Still a table (the
// rows' cells are the numbers screen readers and the tests read); CSS lays each row out as a card. Only a Clear sign
// is flagged; Some sign is neutral, like No sign, and is never the focus (§2.4 items 2–3).
function habitsSummary(report, unit) {
  const sec = el('section', { class: 'section habits-sum', id: 'all-habits', 'aria-labelledby': 'all-h' }, el('h2', { id: 'all-h', text: 'All habits measured' }));
  const checked = report.habits.filter((h) => ['clear', 'some', 'none', 'distinguishable', 'not_distinguishable'].includes(V.pillOf(h)));
  if (checked.length) {
    const top = el('div', { class: 'hs-top' });
    for (const h of checked) {
      top.append(el('p', { class: 'hs-verdict' + (V.isClear(h) ? ' is-hit' : '') }, badge(h), el('span', { class: 'hs-of', text: nameOf(h) })));
    }
    sec.append(top);
  }
  const amounts = report.habits.filter((h) => h.dollars).map((h) => Math.abs(h.dollars.amount));
  const maxAbs = Math.max(...amounts, 0) || 1;
  const tbody = el('tbody');
  for (const h of report.habits) {
    const amt = el('td', { class: 'num hs-total' });
    if (h.dollars) {
      amt.append(el('span', { class: 'hs-amt', text: money(h.dollars.amount, unit) }));
      const fill = el('span', { class: 'hs-fill ' + (V.isClear(h) ? 'is-flag' : h.dollars.amount < 0 ? 'is-loss' : 'is-gain') });
      fill.style.width = (100 * Math.abs(h.dollars.amount) / maxAbs).toFixed(1) + '%';   // CSSOM, allowed by the CSP
      amt.append(el('span', { class: 'hs-bar', 'aria-hidden': 'true' }, fill));
    } else amt.textContent = '—';
    tbody.append(el('tr', { class: 'hs-row' }, el('th', { scope: 'row' }, el('a', { href: '#habit-' + h.id, text: nameOf(h) })), amt,
      el('td', { class: 'num hs-n' }, h.dollars ? el('span', { class: 'hs-count', text: String(h.dollars.n_trades) }) : '—'),
      el('td', { class: 'hs-res' }, badge(h) || el('span', { class: 'small muted', text: 'Your numbers' }))));
  }
  sec.append(el('table', { class: 'hs-table' },
    el('caption', { class: 'visually-hidden', text: 'All habits: dollar total of the matching trades, trade count, and result' }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Habit' }), el('th', { scope: 'col', class: 'num', text: 'Total' }),
      el('th', { scope: 'col', class: 'num', text: 'Trades' }), el('th', { scope: 'col', text: 'Result' }))), tbody));
  sec.append(el('details', { class: 'how-more hs-note' }, el('summary', { text: 'What “Total” means' }),
    el('p', { text: 'The dollar total of the trades that match each habit, from your file. Historical: it shows what happened. Tap a habit to see it in detail.' })));
  return sec;
}

// Addendum §3.1 item 3: on a small file, every "Too few trades" habit is one line at the top of "Each habit", not a
// grey card each.
function collapseTooFew(details, report) {
  const line = V.tooFewCollapsed(report, nameOf, wordingFmt(report.currency));
  if (!line) return;
  for (const h of report.habits) if (h.status === 'too_few') { const s = details.querySelector('#habit-' + h.id); if (s) s.remove(); }
  details.querySelector('h2').after(el('p', { class: 'notice too-few-all', id: 'too-few-all', text: line }));
}

// Print shows every folded part (method lines, totals note, chart tables), then folds them back.
let printWired = false;
function wirePrint() {
  if (printWired || typeof window === 'undefined') return;
  printWired = true;
  let opened = [];
  window.addEventListener('beforeprint', () => {
    opened = [...document.querySelectorAll('.report-out details:not([open])')];
    opened.forEach((d) => { d.open = true; });
  });
  window.addEventListener('afterprint', () => { opened.forEach((d) => { d.open = false; }); opened = []; });
}

// The foot of the report names the method version, so a re-test can say which steps the first report used (§11).
const footLine = (report) => `Method ${V.METHOD_LABEL} of the donttrade test (${report.method_version}) · engine ${report.engine_commit} · rule library ${report.rule_library_version}.`;

export { ics };  // in retest-copy.js with the re-test wording (fix D2); takes the server's window (delta D1)

function download(name, type, text) {
  const a = el('a', { download: name });
  a.href = URL.createObjectURL(new Blob([text], { type }));
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

export function renderReport(report, out, meta) {
  const unit = report.currency;
  V = wordingFor(report);   // DT-2 or, for one release, a DT-1 report (dual accept)
  checkReport(report);   // method, the hold_gap and size_up shapes and the row counts, before anything is drawn
  out.replaceChildren();
  out.classList.add('report-out');
  wirePrint();
  out.append(el('p', { class: 'disclaimer notice', text: report.disclaimer }));
  // S4 (small-file facts and challenge check): facts from the trades parsed in this tab, never sent anywhere.
  // Small files lead with them (addendum §3.1); otherwise the facts follow the habit totals and the rule check
  // follows the habits (bundle plan §2: part c).
  const sf = smallFactsParts(report, meta);
  if (sf && sf.small) out.append(sf.facts, sf.rules);
  // Page 1 (ARCHITECT-STATS-AMENDMENT-R2 §9.1): the headline, the focus habit or why none is
  // shown first (one reason line per distinguishable habit), then the coverage line. All
  // sentences come from wording.js, which refuses a report of another method version.
  const focus = report.habits.find((h) => h.id === report.focus) || null;
  const p1 = el('section', { class: 'section', id: 'focus', 'aria-labelledby': 'focus-h' });
  p1.append(el('h2', { id: 'focus-h', text: 'Summary' }));   // sweep 2: a heading that says what it is
  const head = el('div', { class: focus ? 'notice notice-gap' : 'notice', id: 'focus-lines' });
  for (const line of page1Lines(report, wordingFmt(unit))) head.append(el('p', { text: line }));
  if (focus) head.append(el('p', { class: 'muted', text: focus.question }), el('p', {}, badge(focus)));
  p1.append(head);
  // DT-2 (plan §10 rows 27–28): how many habits were checked against chance, which had too few trades, and that size
  // after a loss is facts in this release.
  const cov = el('div', { id: 'coverage' });
  for (const line of coverageLines(report)) cov.append(el('p', { class: 'small', text: line }));
  p1.append(cov);
  // The re-test's own report (both runs used): the two-look promise and the fixed lines (plan §5.4, §2.4 item 5, §11).
  const again = meta && meta.uses_left === 0 ? V.retestLines() : [];
  if (again.length) p1.append(el('div', { id: 'retest-lines', class: 'notice' }, ...again.map((t) => el('p', { class: 'small', text: t }))));
  p1.append(el('p', { class: 'small muted', text: `${report.n_trades} trades over about ${report.period_weeks} week${report.period_weeks === 1 ? '' : 's'}.${unitLine(unit)}${meta && meta.span_left_out ? ' ' + spanLine(meta.span_left_out) : ''}${meta && meta.limited ? ' Only the most recent 20,000 trades were used.' : ''}` }));
  const merged = mergedLine(report, wordingFmt(unit));   // R-D3 addendum I-5: only when rows were merged
  if (merged) p1.append(el('p', { class: 'small', id: 'merged-rows', text: merged }));
  out.append(p1);

  out.append(habitsSummary(report, unit));
  if (sf && !sf.small) out.append(sf.facts);

  const details = el('section', { class: 'section', 'aria-labelledby': 'det-h' }, el('h2', { id: 'det-h', text: 'Each habit' }));
  for (const h of report.habits) if (!factsOnly(h)) details.append(habitSection(h, unit, report));
  out.append(details);
  if (V.smallFile(report)) collapseTooFew(details, report);
  // the habits with no check against chance in this version, as plain facts, below the checked ones
  const facts = report.habits.filter(factsOnly);
  if (facts.length) {
    const yn = el('section', { class: 'section your-numbers', id: 'your-numbers', 'aria-labelledby': 'yn-h' }, el('h2', { id: 'yn-h', text: 'Your numbers' }),
      el('details', { class: 'how-more yn-why' }, el('summary', { text: 'About these numbers' }), el('p', { class: 'small', text: V.FACTS_LINE })));
    for (const h of facts) yn.append(habitSection(h, unit, report));
    out.append(yn);
  }

  if (report.pgr_plr) {
    const c = report.pgr_plr;
    out.append(el('section', { class: 'section', 'aria-labelledby': 'pgr-h' }, el('h2', { id: 'pgr-h', text: c.label }),
      el('p', { text: `Proportion of gains realised (PGR): ${pct(c.pgr)} · proportion of losses realised (PLR): ${pct(c.plr)}.` }),
      el('p', { class: 'small muted', text: `Counts: ${c.rg} realised gains, ${c.pg} paper gains, ${c.rl} realised losses, ${c.pl} paper losses. Coverage: ${c.coverage_pct === null ? 'no open positions on sale days' : c.coverage_pct.toFixed(1) + '% of open position-days had a same-day price in your file'}. This is not the full Odean (1998) measure, which needs a price for every open position every day.` })));
  }

  if (sf && !sf.small) out.append(sf.rules);

  // The rule library: identical for everyone, in its fixed order, never matched to the habits above.
  const lib = el('section', { class: 'section', id: 'rules', 'aria-labelledby': 'rules-h' },
    el('h2', { id: 'rules-h', text: 'Rule library' }),
    el('p', { text: 'Rules other traders use, the same list for everyone. Pick one, or write your own. Your choice stays on this device.' }));
  const fs = el('fieldset', {}, el('legend', { class: 'visually-hidden', text: 'Pick a rule' }));
  report.rule_library.forEach((rule, i) => {
    fs.append(el('div', { class: 'check' }, el('input', { type: 'radio', name: 'rule', id: 'rule-' + i, value: rule }), el('label', { for: 'rule-' + i, text: rule })));
  });
  fs.append(el('div', { class: 'check' }, el('input', { type: 'radio', name: 'rule', id: 'rule-own', value: 'own' }), el('label', { for: 'rule-own', text: 'My own rule' })));
  lib.append(fs, el('div', { class: 'field' }, el('label', { for: 'own-rule', text: 'Your own rule' }), el('textarea', { id: 'own-rule', maxlength: '300' })));
  if (meta && meta.sample) {
    // sweep 3: the sample shows the library folded; the paid report keeps it open
    const body = [...lib.childNodes].slice(1);
    lib.replaceChildren(lib.firstChild, el('details', { class: 'how-more' }, el('summary', { text: 'Show the rule library' }), ...body));
  }
  out.append(lib);

  // Delta D1: the re-test line and the .ics come from the window the server returned with the
  // first report (to the second). The re-test's own report has no window and shows neither (N8).
  // C-12 final: the sample page shows the report only (no re-test line, reminder, print or firm buttons).
  if (meta && meta.sample) {
    out.append(el('p', { class: 'small muted', text: footLine(report) }));
    return;
  }
  const win = meta && meta.retest ? meta.retest : null;
  const firstReport = !!win || (meta && meta.uses_left === 1);
  let ics_ = null;
  if (win && ics(win)) {
    ics_ = el('button', { class: 'btn btn-secondary', type: 'button', text: 'Add a re-test reminder (.ics)' });
    ics_.addEventListener('click', () => download('donttrade-retest.ics', 'text/calendar', ics(win)));
  }
  const print = el('button', { class: 'btn btn-secondary', type: 'button', text: 'Print or save as PDF' });
  print.addEventListener('click', () => window.print());
  const body = 'I took the donttrade test on my own trades. Firms can test their own records too: https://donttrade.ca/for-firms/?ref=report';
  const mail = el('a', { class: 'btn btn-secondary', href: 'mailto:?subject=' + encodeURIComponent('A trading-habit measurement for your firm') + '&body=' + encodeURIComponent(body), text: 'Send to your firm' });
  // Addendum §3.1 item 4: on a small file, the catch line's larger sizes are the reason to come back.
  const reasons = firstReport && V.smallFile(report) ? V.retestReasons(report, wordingFmt(unit)) : [];
  out.append(el('section', { class: 'section no-print' }, el('h2', { text: 'Next' }),
    firstReport ? el('p', { id: 'rp-retest', text: win ? retestLine(win) : RETEST_LINE }) : null, ...reasons.map((t) => el('p', { class: 'retest-reason', text: t })),
    el('p', {}, ...(ics_ ? [ics_, ' '] : []), print, ' ', mail)));
  out.append(el('p', { class: 'small muted', text: footLine(report) }));
}

// S4: the two fact sections, when the page has the file's trades (meta.trades: the report page after a run, the
// example report from its committed file). Kept here as one call so the habit layer above stays untouched.
// The trades are the ones the report itself is about (strip.js's selection: Tester S4 M3). Anything that goes wrong
// here leaves the two sections out and the rest of the paid report as it is (Tester S4 M4).
function smallFactsParts(report, meta) {
  if (!meta || !Array.isArray(meta.trades) || !meta.trades.length) return null;
  try {
    const trades = reportTrades(meta.trades);
    if (!trades.length) return null;
    const opts = { money: (x) => money(x, report.currency), unit: report.currency, presets: presetsFromPage(), format: meta.format || null, sample: !!meta.sample };
    return { small: smallLayout(report), facts: factsSection(trades, opts), rules: challengeSection(trades, opts) };
  } catch (e) {
    return null;
  }
}

// ---------------------------------------------------------------- page wiring

let token = null;
// R-D1 D-2: the line shown when wording.js refuses a report. The address is site.toml's contact_email, written into
// the page at build time (<meta name="dt-contact">), never typed here.
export const REPORT_ERROR = 'This report could not be shown, so nothing from it is displayed. To tell us, email {contact_email} from the address you paid with.';
export function reportError(doc = document) {
  const m = doc.querySelector('meta[name="dt-contact"]');
  const email = m && m.getAttribute('content');
  return email ? REPORT_ERROR.replace('{contact_email}', email)
    : 'This report could not be shown, so nothing from it is displayed. To tell us, email us from the address you paid with.';
}

function status(msg, kind = '') {
  const s = $('rp-status');
  s.className = 'notice' + (kind ? ' notice-' + kind : '');
  s.replaceChildren(el('p', { text: msg }));
  s.hidden = false;
}

async function run(file) {
  if (!token) { status('No access found on this device. Open the restore link or restore file you saved after paying.', 'error'); return; }
  const payload = decodeToken(token);
  if (!payload) { status('This access link is damaged. Use your restore link.', 'error'); return; }
  status('Reading your file in this tab…');
  const parsed = runFile(new Uint8Array(await file.arrayBuffer()));
  if (parsed.error) { status(parsed.error.message, 'error'); return; }
  const trades = parsed.result.trades;
  const stripped = await stripRows(trades, payload.salt);
  const counts = pgrPlrCounts(parsed.result.executions);
  const firm = $('rp-firm').value.trim();
  const body = { v: 1, token, rows: stripped.rows, currency: trades[0].pnl_unit, pgr_plr: counts,
    firm_name: firm ? firm.slice(0, 80) : null, firm_consent: $('rp-firm-consent').checked };
  const span = stripped.span_left_out ? spanLine(stripped.span_left_out) + ' ' : '';
  status(`${span}Sending ${stripped.rows.length} stripped trade rows (no names, accounts or symbols)…`);
  const r = await api('/analyse', body);
  if (r.status === 0 || r.status >= 500) { status(OUTAGE, 'error'); return; }
  if (!r.ok) { status(r.json && r.json.error ? r.json.error.message : 'The report could not be made.', 'error'); return; }
  $('rp-status').hidden = true;
  try {
    renderReport(r.json.report, $('rp-out'), { limited: stripped.limited, span_left_out: stripped.span_left_out, retest: r.json.retest || null, uses_left: r.json.uses_left,
      trades, format: parsed.result.format });
  } catch (e) {
    // wording.js throws rather than print a sentence that is not true of this report (R2-3).
    $('rp-out').replaceChildren();
    status(reportError(), 'error');
    return;
  }
  if (r.json.uses_left !== null) $('rp-uses').textContent = r.json.uses_left === 1 ? 'One re-test left on this purchase.' : r.json.uses_left === 0 ? 'Both runs on this purchase are used.' : '';
}

async function init() {
  const fromHash = tokenFromHash();
  if (fromHash) { token = fromHash; await saveToken(fromHash); } else token = await loadToken();
  $('rp-restore-file').addEventListener('click', () => { if (token) downloadRestoreFile(token); });
  $('rp-access').textContent = token ? 'Access found on this device.' : 'No access found on this device yet.';
  $('rp-file').addEventListener('change', (ev) => { if (ev.target.files[0]) run(ev.target.files[0]); });
  const dz = $('rp-drop');
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('is-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('is-over'));
  dz.addEventListener('drop', (e) => { e.preventDefault(); dz.classList.remove('is-over'); if (e.dataTransfer.files[0]) run(e.dataTransfer.files[0]); });
}

if (document.getElementById('rp-file')) init();
