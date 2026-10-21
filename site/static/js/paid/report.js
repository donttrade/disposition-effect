// report.js — /report/ (paid flag only).
//
// 1. The trade file is parsed IN THIS TAB by the same engine as the free tools.
// 2. strip.js reduces it to StrippedRows; pgr.js to four counts. Nothing else is sent.
// 3. POST /analyse with the access token → the Report → rendered here.
// Every number on the page comes from the server's Report or from the file in this
// tab; the wording only describes past trades (NON-ADVISER A3).

import { runFile } from '../engine/index.js';
import { ics, RETEST_LINE } from './retest-copy.js';
import { pgrPlrCounts } from '../engine/pgr.js';
import { stripRows } from './strip.js';
import { api, loadToken, saveToken, tokenFromHash, decodeToken, downloadRestoreFile, OUTAGE } from './token.js';

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
  if (unit === 'account' || unit === 'base') return `${sign}${grouped(n)} (${unit === 'account' ? 'account' : 'base'} currency)`;
  return `${sign}${grouped(n)} ${unit}`;
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

const VERDICT = {
  distinguishable: ['badge badge-real', 'distinguishable from noise'],
  not_distinguishable: ['badge badge-noise', 'not distinguishable from noise'],
  too_few: ['badge badge-few', 'not enough trades to tell'],
  descriptive: ['badge badge-noise', 'described, not tested'],
};

function badge(v) {
  const [cls, text] = VERDICT[v];
  return el('span', { class: cls, text });
}

// What each habit's two measures mean, in plain words.
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

function dollarsLine(h, unit) {
  return `${h.dollars.label}: ${h.dollars.n_trades} trades, totalling ${money(h.dollars.amount, unit)} (historical).`;
}

// Two bars from zero with direct labels; the table below it holds the same numbers.
function twoBarChart(h, unit) {
  if (h.measure_a === null || h.measure_b === null || h.id === 'oversized_loss') return null;
  const isMoney = h.id === 'revenge' || h.id === 'tilt';
  const fmt = (v) => (h.id === 'hold_gap' ? duration(v) : isMoney ? money(v, unit) : num(v));
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
  svg.setAttribute('aria-label', `${h.name}: ${labels[0]} ${fmt(vals[0])}, ${labels[1]} ${fmt(vals[1])}`);
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
    el('caption', { class: 'visually-hidden', text: h.name + ' as a table' }),
    el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Group' }), el('th', { scope: 'col', class: 'num', text: 'Trades' }), el('th', { scope: 'col', class: 'num', text: 'Value' }))),
    el('tbody', {},
      el('tr', {}, el('th', { scope: 'row', text: labels[0] }), el('td', { class: 'num', text: String(h.n_a) }), el('td', { class: 'num', text: fmt(vals[0]) })),
      el('tr', {}, el('th', { scope: 'row', text: labels[1] }), el('td', { class: 'num', text: String(h.n_b) }), el('td', { class: 'num', text: fmt(vals[1]) }))));
  return el('figure', { class: 'chart chart-bars' }, svg,
    el('figcaption', { text: `n = ${h.n_a} and ${h.n_b} trades · from your file · historical` }),
    el('details', {}, el('summary', { text: 'Show as a table' }), el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': h.name + ' table' }, table)));
}

function habitSection(h, unit) {
  const sec = el('section', { class: 'habit', id: 'habit-' + h.id, 'aria-labelledby': 'h-' + h.id });
  sec.append(el('h3', { id: 'h-' + h.id, text: h.name }), el('p', { class: 'muted', text: h.question }), el('p', {}, badge(h.verdict)));
  const ul = el('ul');
  for (const line of measures(h, unit)) if (line) ul.append(el('li', { text: line }));
  sec.append(ul, el('p', { text: dollarsLine(h, unit) }));
  if (h.p_holm !== null) sec.append(el('p', { class: 'small muted', text: `Permutation test on past data, 10,000 shuffles: p = ${h.p_raw.toPrecision(3)}, ${h.p_holm.toPrecision(3)} after the Holm correction for testing four habits.` }));
  const chart = twoBarChart(h, unit);
  if (chart) sec.append(chart);
  if (h.research_ref) {
    const cite = el('p', { class: 'small' }, 'Published research on this pattern: ');
    cite.append(h.research_ref.url ? el('a', { href: h.research_ref.url, rel: 'noopener', text: h.research_ref.cite }) : h.research_ref.cite);
    sec.append(cite);
  }
  return sec;
}

export { ics };  // moved to retest-copy.js with the re-test wording (fix D2)

function download(name, type, text) {
  const a = el('a', { download: name });
  a.href = URL.createObjectURL(new Blob([text], { type }));
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}

export function renderReport(report, out, meta) {
  const unit = report.currency;
  out.replaceChildren();
  out.append(el('p', { class: 'disclaimer notice', text: report.disclaimer }));
  // Page 1: the focus habit, or the plain statement that nothing stands out.
  const focus = report.habits.find((h) => h.id === report.focus) || null;
  const p1 = el('section', { class: 'section', id: 'focus', 'aria-labelledby': 'focus-h' });
  p1.append(el('h2', { id: 'focus-h', text: 'Page 1' }));
  if (focus) {
    p1.append(el('div', { class: 'notice notice-gap' }, el('strong', { text: focus.name }),
      el('p', { text: focus.question }), el('p', {}, badge(focus.verdict)), el('p', { text: dollarsLine(focus, unit) })));
  } else {
    p1.append(el('div', { class: 'notice' }, el('p', { text: 'No pattern in this file is distinguishable from noise.' })));
  }
  p1.append(el('p', { class: 'small muted', text: `${report.n_trades} trades over about ${report.period_weeks} week${report.period_weeks === 1 ? '' : 's'}.${meta && meta.limited ? ' Only the most recent 20,000 trades were used.' : ''}` }));
  out.append(p1);

  // Summary table of all habits.
  const tbody = el('tbody');
  for (const h of report.habits) {
    tbody.append(el('tr', {}, el('th', { scope: 'row' }, el('a', { href: '#habit-' + h.id, text: h.name })),
      el('td', {}, badge(h.verdict)), el('td', { class: 'num', text: money(h.dollars.amount, unit) }), el('td', { class: 'num', text: String(h.dollars.n_trades) })));
  }
  out.append(el('section', { class: 'section', 'aria-labelledby': 'all-h' }, el('h2', { id: 'all-h', text: 'All habits measured' }),
    el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': 'All habits table' },
      el('table', {}, el('thead', {}, el('tr', {}, el('th', { scope: 'col', text: 'Habit' }), el('th', { scope: 'col', text: 'Result' }),
        el('th', { scope: 'col', class: 'num', text: 'Matching trades totalled (historical)' }), el('th', { scope: 'col', class: 'num', text: 'Trades' }))), tbody))));

  const details = el('section', { class: 'section', 'aria-labelledby': 'det-h' }, el('h2', { id: 'det-h', text: 'Each habit' }));
  for (const h of report.habits) details.append(habitSection(h, unit));
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
  out.append(lib);

  const ics_ = el('button', { class: 'btn btn-secondary', type: 'button', text: 'Add a re-test reminder (.ics)' });
  ics_.addEventListener('click', () => download('donttrade-retest.ics', 'text/calendar', ics()));
  const print = el('button', { class: 'btn btn-secondary', type: 'button', text: 'Print or save as PDF' });
  print.addEventListener('click', () => window.print());
  const body = 'I ran a donttrade habit report on my own trades. Your firm can measure the same on its own records: https://donttrade.ca/for-firms/?ref=report';
  const mail = el('a', { class: 'btn btn-secondary', href: 'mailto:?subject=' + encodeURIComponent('A trading-habit measurement for your firm') + '&body=' + encodeURIComponent(body), text: 'Send to your firm' });
  out.append(el('section', { class: 'section no-print' }, el('h2', { text: 'Next' }),
    el('p', { text: RETEST_LINE }),
    el('p', {}, ics_, ' ', print, ' ', mail)));
  out.append(el('p', { class: 'small muted', text: `Engine ${report.engine_commit} · rule library ${report.rule_library_version}.` }));
}

// ---------------------------------------------------------------- page wiring

let token = null;

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
  status(`Sending ${stripped.rows.length} stripped trade rows (no names, accounts or symbols)…`);
  const r = await api('/analyse', body);
  if (r.status === 0 || r.status >= 500) { status(OUTAGE, 'error'); return; }
  if (!r.ok) { status(r.json && r.json.error ? r.json.error.message : 'The report could not be made.', 'error'); return; }
  $('rp-status').hidden = true;
  renderReport(r.json.report, $('rp-out'), { limited: stripped.limited });
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
