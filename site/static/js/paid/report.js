// report.js — /report/ (paid flag only).
//
// 1. The trade file is parsed IN THIS TAB by the same engine as the free tools.
// 2. strip.js reduces it to StrippedRows; pgr.js to four counts. Nothing else is sent.
// 3. POST /analyse with the access token → the Report → rendered here.
// Every number on the page comes from the server's Report or from the file in this
// tab; the wording only describes past trades (NON-ADVISER A3).

import { runFile } from '../engine/index.js';
import { ics, retestLine, RETEST_LINE } from './retest-copy.js';
import { pgrPlrCounts } from '../engine/pgr.js';
import { stripRows, spanLine } from './strip.js';
import { api, loadToken, saveToken, tokenFromHash, decodeToken, downloadRestoreFile, OUTAGE } from './token.js';
import { habitSentences, methodLine, page1Lines, coverageLines, mergedLine, checkReport, SENTENCE_HABITS, RESEARCH, RESEARCH_PREFIX, holdDays,
  V_LAUNCH, V_LAUNCH_SIZE, V_NO } from './wording.js';

const $ = (id) => document.getElementById(id);
const MINUS = '−';

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
const wordingFmt = (unit) => ({ money: (x) => money(x, unit), duration, ratio: (x) => num(x), count });

// The habits shown with wording.js sentences (hold_gap: M1, V-launch, M3 under stats2b; size_up: M1,
// V-launch-size under stats2c); the descriptive
// oversized_loss shows its measures list.
const TESTED = SENTENCE_HABITS;

// 29 Oct (owner): every habit in two layers, "What happened" and "Real or luck?". A habit whose luck check is not
// calibrated yet (withheld as not_calibrated, or the descriptive oversized_loss) carries the neutral "Luck check
// coming"; a habit that cannot be checked on this particular file (dates only, the spread rule) says so.
// The words "described" and "not tested" are never shown (plain() below rewords wording.js's lines for display).
const VERDICT = {
  distinguishable: ['badge badge-real', 'distinguishable from noise'],
  not_distinguishable: ['badge badge-noise', 'not distinguishable from noise'],
  too_few: ['badge badge-few', 'not enough trades to tell'],
  withheld: ['badge badge-few', 'can’t check on this file'],
  coming: ['badge badge-coming', 'Luck check coming'],
};

const luckComing = (h) => h.verdict === 'descriptive' || (h.verdict === 'withheld' && h.withheld === 'not_calibrated');

function badge(v, h) {
  if (h && luckComing(h)) v = 'coming';
  if (!VERDICT[v]) throw new Error(`report: unknown verdict ${v}`);
  const [cls, text] = VERDICT[v];
  return el('span', { class: cls, text });
}

// Visible labels (owner, 29 Oct): the engine's name for oversized_loss is shown as "Large losses".
const NAMES = { oversized_loss: 'Large losses' };
export const nameOf = (h) => NAMES[h.id] || h.name;

// wording.js's sentences, as shown: its exports stay word for word (the wording tests pin them); the page drops
// the "described …" sentences and rewords the "Not tested" / "Not described" openings.
const LAUNCH_TAIL = ' So this pattern is described here without a verdict.';
export function plain(s) {
  return s.replace(LAUNCH_TAIL, '')
    .replace('Some are described below without a verdict.', 'Some are shown below without a verdict.')
    .replace(/^Not tested: /, 'No luck check on this file: ')
    .replace(/^Not described: /, 'No figure for this file: ')
    .replace(', so it is not tested on files like that.', ', so files like that get no luck check.')
    .replace(', so it is not described for files like that.', ', so files like that get no figure.')
    .replace('are not tested, and size after a loss is not described.', 'get no luck check, and size after a loss gets no figure.');
}
// Why a habit's luck check is not on yet (the tap-to-open line), from V_LAUNCH / V_LAUNCH_SIZE.
function whyComing(h) {
  if (h.id === 'hold_gap') return plain(V_LAUNCH);
  if (h.id === 'size_up') return plain(V_LAUNCH_SIZE);
  return 'A luck check for this habit is still being designed.';
}
// A wording.js line that belongs to "Real or luck?" (the verdict, or why there is none) rather than "What happened".
const isVerdictLine = (s) => s === V_LAUNCH || s === V_LAUNCH_SIZE || s === V_NO || s.startsWith('This gap is distinguishable')
  || s.startsWith('Not enough trades to tell') || s.startsWith('Not tested');

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

// "after adjusting for the N patterns tested": the count is the report's own n_tested (at most 2 under stats2c).
const testedPhrase = (n) => `the ${n} pattern${n === 1 ? '' : 's'} tested`;

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
    r.setAttribute('class', i === 0 && h.verdict === 'distinguishable' ? 'bar-flag' : (v < 0 ? 'bar-loss' : 'bar-plain'));
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

// Layer 2, "Real or luck?": the result pill with its plain gloss, the verdict line; or "Luck check coming" with why.
const GLOSS = { distinguishable: 'unlikely to be luck', not_distinguishable: 'could be luck' };
function luckLayer(h, lines) {
  const box = el('div', { class: 'layer layer-luck' }, el('h4', { text: 'Real or luck?' }));
  const pill = el('p', { class: 'luck-pill' }, badge(h.verdict, h));
  if (GLOSS[h.verdict]) pill.append(' ', el('span', { class: 'luck-gloss', text: GLOSS[h.verdict] }));
  box.append(pill);
  const shown = lines.filter((s) => s !== V_LAUNCH && s !== V_LAUNCH_SIZE);   // those two are the "Why not yet" text
  for (const s of shown) box.append(el('p', { class: 'habit-sentence', text: plain(s) }));
  if (luckComing(h)) {
    box.append(el('details', { class: 'how-more luck-why' }, el('summary', { text: 'Why not yet' }), el('p', { class: 'small', text: whyComing(h) })));
  }
  return box;
}

function habitSection(h, unit, report) {
  const sec = el('section', { class: 'habit', id: 'habit-' + h.id, 'aria-labelledby': 'h-' + h.id });
  const lines = TESTED.includes(h.id) ? habitSentences(h, report, wordingFmt(unit)) : [];
  const verdictLines = lines.filter(isVerdictLine), happenedLines = lines.filter((x) => !isVerdictLine(x));
  if (report.dates_only && ['revenge', 'tilt', 'size_up'].includes(h.id)) {
    // R-D3 addendum 3: no question with its 15-minute figure, no measure, no dollars, no chart, no research line
    const what = el('div', { class: 'layer layer-what' }, el('h4', { text: 'What happened' }));
    if (happenedLines.length) for (const x of happenedLines) what.append(el('p', { class: 'habit-sentence', text: plain(x) }));
    else what.append(el('p', { class: 'muted', text: 'No figure for this file.' }));
    sec.append(el('h3', { id: 'h-' + h.id, text: nameOf(h) }), what, luckLayer(h, verdictLines));
    return sec;
  }
  sec.append(el('h3', { id: 'h-' + h.id, text: nameOf(h) }), el('p', { class: 'muted', text: h.question }));
  const what = el('div', { class: 'layer layer-what' }, el('h4', { text: 'What happened' }));
  const chart = twoBarChart(h, unit, report);
  if (chart) what.append(chart);
  const list = happenedList(h, unit, report);
  if (list) what.append(list);
  for (const x of happenedLines) what.append(el('p', { class: 'habit-sentence', text: plain(x) }));
  const extra = detailLine(h, unit);
  if (extra) what.append(el('p', { text: extra }));
  sec.append(what, luckLayer(h, verdictLines));
  const how = el('div', {});
  // The method line carries the habit's own n_perm (it scales with the file size, D-4).
  const method = methodLine(h, wordingFmt(unit));
  if (method && h.p_raw !== null && h.p_holm !== null) {
    how.append(el('p', { class: 'small muted habit-method', text: `${method} On past data: p = ${h.p_raw.toPrecision(3)}, or ${h.p_holm.toPrecision(3)} after adjusting for ${testedPhrase(report.n_tested)} (Holm).` }));
  }
  // R-D3 addendum I-6: the page's own related-research line (wording.js RESEARCH), never the report's
  // research_ref; oversized_loss has none.
  const res = Object.prototype.hasOwnProperty.call(RESEARCH, h.id) ? RESEARCH[h.id] : null;
  if (res) {
    const cite = el('p', { class: 'small research' }, RESEARCH_PREFIX + res.line + ' ');
    cite.append(el('a', { href: res.url, rel: 'noopener', text: res.cite }));
    how.append(cite);
  }
  if (how.childNodes.length) sec.append(el('details', { class: 'how-more habit-how' }, el('summary', { text: 'How this was measured' }), how));
  return sec;
}

// sweep 3 (29 Oct, owner): "All habits measured" as a picture. On top, each tested habit's result as a big pill
// with a plain gloss; then one row per habit (its result pill, a bar for its dollar total scaled to the largest,
// the trade count as a badge), each row a link to its section below. Still a table (the rows' cells are the
// numbers screen readers and the tests read); CSS lays each row out as a card. The verdict labels are report.js's
// own (VERDICT); the totals are the habits' dollars, historical, as the sections below say.
function habitsSummary(report, unit) {
  const sec = el('section', { class: 'section habits-sum', id: 'all-habits', 'aria-labelledby': 'all-h' }, el('h2', { id: 'all-h', text: 'All habits measured' }));
  const tested = report.habits.filter((h) => GLOSS[h.verdict]);
  if (tested.length) {
    const top = el('div', { class: 'hs-top' });
    for (const h of tested) {
      top.append(el('p', { class: 'hs-verdict' + (h.verdict === 'distinguishable' ? ' is-hit' : '') },
        badge(h.verdict, h), ' ', el('span', { class: 'hs-gloss', text: GLOSS[h.verdict] }), el('span', { class: 'hs-of', text: nameOf(h) })));
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
      const fill = el('span', { class: 'hs-fill ' + (h.verdict === 'distinguishable' ? 'is-flag' : h.dollars.amount < 0 ? 'is-loss' : 'is-gain') });
      fill.style.width = (100 * Math.abs(h.dollars.amount) / maxAbs).toFixed(1) + '%';   // CSSOM, allowed by the CSP
      amt.append(el('span', { class: 'hs-bar', 'aria-hidden': 'true' }, fill));
    } else amt.textContent = '—';
    tbody.append(el('tr', { class: 'hs-row' }, el('th', { scope: 'row' }, el('a', { href: '#habit-' + h.id, text: nameOf(h) })),
      el('td', { class: 'hs-res' }, badge(h.verdict, h)), amt,
      el('td', { class: 'num hs-n' }, h.dollars ? el('span', { class: 'hs-count', text: String(h.dollars.n_trades) }) : '—')));
  }
  sec.append(el('table', { class: 'hs-table' },
    el('caption', { class: 'visually-hidden', text: 'All habits: result, dollar total of the matching trades, and trade count' }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Habit' }), el('th', { scope: 'col', text: 'Result' }),
      el('th', { scope: 'col', class: 'num', text: 'Total' }), el('th', { scope: 'col', class: 'num', text: 'Trades' }))), tbody));
  sec.append(el('details', { class: 'how-more hs-note' }, el('summary', { text: 'What “Total” means' }),
    el('p', { text: 'The dollar total of the trades that match each habit, from your file. Historical: it shows what happened. Tap a habit to see it in detail.' })));
  return sec;
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
  checkReport(report);   // method, the hold_gap and size_up shapes and the row counts, before anything is drawn
  out.replaceChildren();
  out.classList.add('report-out');
  wirePrint();
  out.append(el('p', { class: 'disclaimer notice', text: report.disclaimer }));
  // Page 1 (ARCHITECT-STATS-AMENDMENT-R2 §9.1): the headline, the focus habit or why none is
  // shown first (one reason line per distinguishable habit), then the coverage line. All
  // sentences come from wording.js, which refuses a report of another method version.
  const focus = report.habits.find((h) => h.id === report.focus) || null;
  const p1 = el('section', { class: 'section', id: 'focus', 'aria-labelledby': 'focus-h' });
  p1.append(el('h2', { id: 'focus-h', text: 'Summary' }));   // sweep 2: a heading that says what it is
  const head = el('div', { class: focus ? 'notice notice-gap' : 'notice', id: 'focus-lines' });
  for (const line of page1Lines(report, wordingFmt(unit))) head.append(el('p', { text: plain(line) }));
  if (focus) head.append(el('p', { class: 'muted', text: focus.question }), el('p', {}, badge(focus.verdict, focus)));
  p1.append(head);
  // 29 Oct (owner): the coverage line says how many habits could be checked for luck, then which ones have a luck
  // check coming; wording.js's fixed "… is described, not tested …" lines are not shown.
  const cov = el('div', { id: 'coverage' });
  cov.append(el('p', { class: 'small', text: coverageLines(report)[0] }));
  const coming = report.habits.filter(luckComing).map(nameOf);
  if (coming.length) cov.append(el('p', { class: 'small', text: `Luck check coming: ${coming.join(', ')}.` }));
  p1.append(cov);
  p1.append(el('p', { class: 'small muted', text: `${report.n_trades} trades over about ${report.period_weeks} week${report.period_weeks === 1 ? '' : 's'}.${unitLine(unit)}${meta && meta.span_left_out ? ' ' + spanLine(meta.span_left_out) : ''}${meta && meta.limited ? ' Only the most recent 20,000 trades were used.' : ''}` }));
  const merged = mergedLine(report, wordingFmt(unit));   // R-D3 addendum I-5: only when rows were merged
  if (merged) p1.append(el('p', { class: 'small', id: 'merged-rows', text: merged }));
  out.append(p1);

  out.append(habitsSummary(report, unit));

  const details = el('section', { class: 'section', 'aria-labelledby': 'det-h' }, el('h2', { id: 'det-h', text: 'Each habit' }));
  for (const h of report.habits) details.append(habitSection(h, unit, report));
  out.append(details);

  if (report.pgr_plr) {
    const c = report.pgr_plr;
    out.append(el('section', { class: 'section', 'aria-labelledby': 'pgr-h' }, el('h2', { id: 'pgr-h', text: c.label }),
      el('p', { text: `Proportion of gains realised (PGR): ${pct(c.pgr)} · proportion of losses realised (PLR): ${pct(c.plr)}.` }),
      el('p', { class: 'small muted', text: `Counts: ${c.rg} realised gains, ${c.pg} paper gains, ${c.rl} realised losses, ${c.pl} paper losses. Coverage: ${c.coverage_pct === null ? 'no open positions on sale days' : c.coverage_pct.toFixed(1) + '% of open position-days had a same-day price in your file'}. This is not the full Odean (1998) measure, which needs a price for every open position every day.` })));
  }

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
    out.append(el('p', { class: 'small muted', text: `Engine ${report.engine_commit} · rule library ${report.rule_library_version}.` }));
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
  out.append(el('section', { class: 'section no-print' }, el('h2', { text: 'Next' }),
    firstReport ? el('p', { id: 'rp-retest', text: win ? retestLine(win) : RETEST_LINE }) : null,
    el('p', {}, ...(ics_ ? [ics_, ' '] : []), print, ' ', mail)));
  out.append(el('p', { class: 'small muted', text: `Engine ${report.engine_commit} · rule library ${report.rule_library_version}.` }));
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
    renderReport(r.json.report, $('rp-out'), { limited: stripped.limited, span_left_out: stripped.span_left_out, retest: r.json.retest || null, uses_left: r.json.uses_left });
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
