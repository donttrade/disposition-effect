// journal/trades-view.js: #trades (ARCHITECT-V3 §d.5 screen 4). A sortable table of the trades in the
// current account and filter, 100 a page, newest close first; a row opens its detail panel, where the
// numbers from the file are read-only (v1 never edits them) and the annotation editors sit (J5 hook).
import * as M from './model.js';
import { el, $, plural, tableWrap, button, intText } from './ui.js';
import { duration } from '../tools/format.js';

const PAGE = 100;
const V = { sort: 'close_ts', dir: -1, page: 0, open: null, sig: '' };
const price = (x) => (typeof x === 'number' && Number.isFinite(x) ? x.toLocaleString('en-US', { maximumFractionDigits: 6 }) : '—');

const COLS = [
  { key: 'close_ts', label: 'Closed', get: (t) => t.close_ts },
  { key: 'symbol', label: 'Symbol', get: (t) => t.symbol },
  { key: 'dir', label: 'Side', get: (t) => t.dir },
  { key: 'open_ts', label: 'Opened', get: (t) => t.open_ts },
  { key: 'hold_s', label: 'Hold', get: (t) => t.hold_s, num: true },
  { key: 'qty', label: 'Size', get: (t) => t.qty, num: true },
  { key: 'entry', label: 'Entry', get: (t) => t.entry, num: true },
  { key: 'exit', label: 'Exit', get: (t) => t.exit, num: true },
  { key: 'fees', label: 'Fees', get: (t) => t.fees, num: true },
  { key: 'pnl', label: 'Net result', get: (t) => t.pnl, num: true },
  { key: 'setup', label: 'Setup', note: true },
  { key: 'tags', label: 'Tags', note: true },
  { key: 'note', label: 'Note', note: true },
];

function sorted(J, trades) {
  const c = COLS.find((x) => x.key === V.sort);
  if (!c || c.note) return trades.slice().reverse();
  const out = trades.slice();
  out.sort((a, b) => {
    const x = c.get(a), y = c.get(b);
    const r = typeof x === 'string' ? x.localeCompare(y) : (x - y);
    return V.dir * (r || (a.close_ts - b.close_ts));
  });
  return out;
}

export function openTrade(J, k) {
  V.open = k;
  J.go('trades');
  J.render();
  const h = $('j-detail-h');
  if (h) h.focus();
}

export function render(J, body) {
  const all = J.visible(true);
  const sig = [J.S.account, JSON.stringify(J.S.filter), J.S.data.trades.length].join('|');
  if (sig !== V.sig) { V.sig = sig; V.page = 0; }
  const list = sorted(J, all);
  const pages = Math.max(1, Math.ceil(list.length / PAGE));
  V.page = Math.min(V.page, pages - 1);
  const rows = list.slice(V.page * PAGE, V.page * PAGE + PAGE);
  const unit = J.unit();
  const head = el('tr', {}, ...COLS.map((c) => {
    const th = el('th', { scope: 'col', class: c.num ? 'num' : null });
    if (c.note) { th.textContent = c.label; return th; }
    const on = V.sort === c.key;
    if (on) th.setAttribute('aria-sort', V.dir > 0 ? 'ascending' : 'descending');
    th.append(button(c.label + (on ? (V.dir > 0 ? ' ▲' : ' ▼') : ''), () => {
      if (V.sort === c.key) V.dir = -V.dir; else { V.sort = c.key; V.dir = c.key === 'symbol' || c.key === 'dir' ? 1 : -1; }
      V.page = 0;
      J.render();
      const again = body.querySelector(`th [data-sort="${c.key}"]`);
      if (again) again.focus();
    }, 'j-sort', { 'data-sort': c.key }));
    return th;
  }));
  const tbody = el('tbody', {}, ...rows.map((t) => {
    const n = J.note(t.k) || {};
    const u = t.pnl_unit || unit;
    const open = button(M.fmtTs(t.close_ts), () => openTrade(J, t.k), 'j-rowbtn',
      { 'aria-label': `${t.symbol} ${t.dir}, closed ${M.fmtTs(t.close_ts)}, ${J.money(t.pnl, u)}: open the details`, 'data-k': t.k });
    if (V.open === t.k) open.setAttribute('aria-current', 'true');
    return el('tr', { class: V.open === t.k ? 'is-open' : null },
      el('th', { scope: 'row' }, open), el('td', { text: t.symbol }), el('td', { text: t.dir === 'long' ? 'Long' : 'Short' }),
      el('td', { class: 'nowrap', text: M.fmtTs(t.open_ts) }), el('td', { class: 'num', text: duration(t.hold_s) }),
      el('td', { class: 'num', text: price(t.qty) }), el('td', { class: 'num', text: price(t.entry) }),
      el('td', { class: 'num', text: price(t.exit) }), el('td', { class: 'num', text: J.money(-(t.fees || 0), u).replace(/^\+/, '') }),
      el('td', { class: 'num ' + (t.pnl > 0 ? 'gain' : t.pnl < 0 ? 'loss' : ''), 'data-k': 'pnl', text: J.money(t.pnl, u) }),
      el('td', { text: n.setup || '' }), el('td', { text: (n.tags || []).join(', ') }),
      el('td', {}, n.note ? el('span', { text: 'Yes' }) : el('span', { class: 'muted', text: '—' })));
  }));
  const first = list.length ? V.page * PAGE + 1 : 0;
  const pager = el('nav', { class: 'j-pager', 'aria-label': 'Pages of trades' },
    el('p', { class: 'small', 'aria-live': 'polite', id: 'j-trades-count', text: list.length ? `Showing ${intText(first)}–${intText(first + rows.length - 1)} of ${plural(list.length, 'trade', 'trades')}` : 'No trades match.' }),
    pages > 1 ? el('p', { class: 'btn-row' },
      button('Previous 100', () => { V.page--; J.render(); $('j-trades-count').focus(); }, 'btn btn-secondary', V.page === 0 ? { disabled: true } : {}),
      ' ',
      button('Next 100', () => { V.page++; J.render(); $('j-trades-count').focus(); }, 'btn btn-secondary', V.page >= pages - 1 ? { disabled: true } : {})) : null);
  pager.firstChild.tabIndex = -1;
  const table = el('table', { class: 'j-trades' },
    el('caption', { text: `${J.scopeLabel()}: trades by close time (${J.tzLabel()})` }), el('thead', {}, head), tbody);
  const t = V.open ? J.S.data.trades.find((x) => x.k === V.open) : null;
  if (V.open && !t) V.open = null;
  body.replaceChildren(el('div', { class: 'j-split' + (t ? ' has-detail' : '') },
    el('div', { class: 'j-split-main' }, tableWrap('Trades', table), pager),
    t ? detail(J, t) : null));
}

function detail(J, t) {
  const u = t.pnl_unit || J.unit();
  const acc = J.account(t.account_id);
  const dl = el('dl', { class: 'j-dl' },
    ...[['Account', acc ? acc.name : ''], ['Symbol', t.symbol], ['Side', t.dir === 'long' ? 'Long' : 'Short'],
      ['Opened', M.fmtTs(t.open_ts)], ['Closed', M.fmtTs(t.close_ts)], ['Hold', duration(t.hold_s)],
      ['Size', price(t.qty)], ['Entry (average)', price(t.entry)], ['Exit (average)', price(t.exit)],
      ['Fills', intText(t.fills_n)], ['Gross result', J.money(t.pnl_gross, u)], ['Fees', J.money(-(t.fees || 0), u).replace(/^\+/, '')],
      ['Net result', J.money(t.pnl, u)]].flatMap(([k, v]) => [el('dt', { text: k }), el('dd', { class: 'num', text: v })]));
  const close = button('Close the details', () => {
    const k = V.open;
    V.open = null;
    J.render();
    const b = document.querySelector(`.j-rowbtn[data-k="${CSS.escape(k)}"]`);
    if (b) b.focus();
  });
  const box = el('section', { class: 'j-detail', id: 'j-detail', 'aria-labelledby': 'j-detail-h' },
    el('h3', { id: 'j-detail-h', tabindex: '-1', text: `${t.symbol} ${t.dir === 'long' ? 'long' : 'short'}, closed ${M.fmtTs(t.close_ts)}` }),
    el('p', { class: 'small muted', text: 'The numbers come from your file and cannot be edited here.' }), dl);
  for (const f of J.hooks.detail || []) f(J, t, box);
  box.append(el('p', {}, close));
  return box;
}
