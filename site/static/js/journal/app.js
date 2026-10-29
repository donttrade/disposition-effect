// journal/app.js: the free Trading Journal's page (ARCHITECT-V3 §d.3-§d.5, steps J3-J8).
//
// Privacy by construction: everything stays in this tab and in IndexedDB on this device (store.js). The
// page's CSP is connect-src 'none' and form-action 'none' and it loads no analytics (build guard
// journal_problem), so nothing here could send a trade anywhere even by mistake. Files are parsed by the
// unchanged engine in journal-worker.js (an HTML report on the page, which a worker cannot parse).
// No localStorage: the theme key is theme.js's alone (J33).
//
// Views are hash routes so Back works: #calendar #trades #stats #imports #backup. Each view is a module
// with render(J, body) (and an optional init(J)); J is the context below. main.js registers the views and
// calls start(); a view never imports this file, so the module graph has no cycle.
import * as store from './store.js';
import { plan, commit, newAccount } from './import.js';
import { forJournal } from './keys.js';
import { runFile } from '../engine/index.js';
import { LIMITS as ELIMITS, MESSAGES } from '../engine/errors.js';
import { renderReadError } from '../tools/tool-state.js';
import { workerError } from '../tools/read-file.js';
import { unitNote } from '../tools/format.js';
import * as M from './model.js';
import { $, el, money, plural, button, confirmInline, debounce } from './ui.js';

export const FORMAT_NAMES = {
  mt5: 'MetaTrader 5 report', mt4: 'MetaTrader 4 statement', ibkr_flex: 'Interactive Brokers Flex Query',
  tradovate_orders: 'Tradovate Orders export', generic: 'donttrade CSV template (one row per fill)',
  generic_roundtrip: 'CSV with one row per round trip',
};
const FORMAT_SHORT = { mt5: 'MT5', mt4: 'MT4', ibkr_flex: 'IBKR', tradovate_orders: 'Tradovate', generic: 'CSV', generic_roundtrip: 'CSV' };
export const SAMPLE_NAME = 'Sample (synthetic trades)';
const PARSE_MS = 180000;

const VIEWS = {};
export function registerView(name, mod) { VIEWS[name] = mod; }
const ORDER = ['calendar', 'trades', 'stats', 'imports', 'backup'];

// ------------------------------------------------------------------ state
const S = {
  db: null, data: null, notes: new Map(), days: new Map(), account: null, view: null, hide: false,
  filter: { ...M.EMPTY_FILTER }, month: null, today: M.dayKey(Date.now() - new Date().getTimezoneOffset() * 60000),
};

export const J = {
  S,
  get db() { return S.db; },
  money: (n, unit) => money(n, unit, S.hide),
  accounts: () => (S.data ? S.data.accounts : []),
  account: (id) => J.accounts().find((a) => a.id === id) || null,
  // "All accounts" only when every account has the same result unit (J18).
  sharedUnit() {
    const u = new Set(J.accounts().map((a) => a.unit));
    return u.size === 1 ? [...u][0] : null;
  },
  unit() { return S.account === 'all' ? J.sharedUnit() : (J.account(S.account) || {}).unit; },
  scope() {
    if (!S.data) return [];
    return S.account === 'all' ? S.data.trades : S.data.trades.filter((t) => t.account_id === S.account);
  },
  visible(dates = true) { return M.applyFilter(J.scope(), S.filter, S.notes, dates); },
  note: (k) => S.notes.get(k) || null,
  render: () => render(),
  refresh: () => refresh(),
  go: (view) => { if (location.hash !== '#' + view) location.hash = view; else render(); },
  toast,
  undoImport: (id, btn) => undoImport(id, btn),
  formatName: (f) => FORMAT_NAMES[f] || f,
  hasView: (v) => !!VIEWS[v],
  scopeLabel() { return S.account === 'all' ? 'All accounts' : (J.account(S.account) || {}).name || ''; },
  tzLabel() {
    const tz = new Set((S.account === 'all' ? J.accounts() : [J.account(S.account)]).filter(Boolean).map((a) => a.tz_label));
    return tz.size === 1 ? [...tz][0] : 'the time in each file';
  },
  hooks: { afterLoad: [], afterImport: [], bar: [], detail: [] },
};

function index() {
  S.notes = new Map(S.data.notes.map((n) => [n.k, n]));
  S.days = new Map(S.data.days.map((d) => [d.account_id + '|' + d.date, d]));
  S.data.trades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || (a.k < b.k ? -1 : 1));
  const ids = J.accounts().map((a) => a.id);
  if (S.account === 'all' && !J.sharedUnit()) S.account = null;
  if (S.account !== 'all' && !ids.includes(S.account)) S.account = ids.length > 1 && J.sharedUnit() ? 'all' : ids[0] || null;
}

async function refresh() {
  S.data = await store.loadAll(S.db);
  index();
  for (const f of J.hooks.afterLoad) f(J);
  render();
}

// ------------------------------------------------------------------ top bar
function renderBar() {
  const sel = $('j-account');
  const accs = J.accounts();
  const opts = [];
  if (accs.length > 1 && J.sharedUnit()) opts.push(el('option', { value: 'all', text: 'All accounts' }));
  for (const a of accs) opts.push(el('option', { value: a.id, text: `${a.name} (${a.unit === 'points' ? 'price points' : a.unit})` }));
  sel.replaceChildren(...opts);
  sel.value = S.account || '';
  const meta = S.data.meta || {};
  const n = S.data.trades.length;
  $('j-status').textContent = `${plural(n, 'trade', 'trades')} saved on this device · backup: ${meta.last_backup_at ? ago(meta.last_backup_at) : 'never'}`;
  for (const f of J.hooks.bar) f(J);
}
export function ago(iso) {
  const days = Math.floor((Date.now() - Date.parse(iso)) / 86400000);
  return days <= 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
}

// ------------------------------------------------------------------ routing and rendering
function viewFromHash() {
  const h = location.hash.slice(1);
  if (VIEWS[h]) return h;
  return ORDER.find((v) => VIEWS[v]) || 'trades';
}

function render() {
  if (!S.data) return;
  const empty = !S.data.trades.length && !S.data.accounts.length;
  $('j-app').classList.toggle('is-empty', empty);
  for (const a of document.querySelectorAll('.j-tabs a[data-view]')) {
    const v = a.dataset.view;
    a.parentElement.hidden = !VIEWS[v] || (empty && v !== 'backup');
    if (v === S.view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  $('j-bar').hidden = empty;
  if (empty) showImport(true, false);
  if (!empty) renderBar();
  for (const sec of document.querySelectorAll('[data-view-panel]')) {
    const v = sec.dataset.viewPanel;
    const on = v === S.view && (!empty || v === 'backup') && !!VIEWS[v];
    sec.hidden = !on;
    if (on) VIEWS[v].render(J, sec.querySelector('[data-body]'));
  }
}

function onHash() {
  const v = viewFromHash();
  const changed = v !== S.view;
  S.view = v;
  render();
  if (changed && location.hash) {
    const h = document.querySelector(`[data-view-panel="${v}"] h2`);
    if (h) { h.tabIndex = -1; h.focus({ preventScroll: false }); }
  }
}

// ------------------------------------------------------------------ toast
function toast(kids, focus = true) {
  const t = $('j-toast');
  if (!kids) { t.hidden = true; t.replaceChildren(); return; }
  t.replaceChildren(...kids);
  t.hidden = false;
  if (focus) t.focus();
}

// ------------------------------------------------------------------ import: read a file
let seq = 0;
function parseBytes(bytes) {
  const id = ++seq;
  return new Promise((resolve) => {
    let w = null, timer = null, settled = false;
    const end = (v) => { if (settled) return; settled = true; clearTimeout(timer); if (w) w.terminate(); resolve(v); };
    const onPage = () => setTimeout(() => {
      try {
        const out = runFile(bytes);
        end(out.error ? { error: out.error } : { result: forJournal(out.result) });
      } catch (e) {
        end({ error: e && e.name === 'EngineError' ? e.toJSON() : workerError('E_WORKER', String(e && e.message ? e.message : e)) });
      }
    }, 30);
    try {
      w = new Worker(new URL('./journal-worker.js', import.meta.url), { type: 'module' });
    } catch (e) { end({ error: workerError('E_WORKER', 'the worker could not start') }); return; }
    timer = setTimeout(() => end({ error: workerError('E_WORKER_TIMEOUT', 'reading the file') }), PARSE_MS);
    w.onmessage = (ev) => {
      const d = ev.data || {};
      if (d.id !== id) { end({ error: workerError('E_WORKER', 'answer for another request') }); return; }
      if (d.needsPage) { clearTimeout(timer); w.terminate(); w = null; status('Reading your report in this tab…'); onPage(); return; }
      if (d.error) { end({ error: d.error }); return; }
      if (d.result) { end({ result: d.result }); return; }
      end({ error: workerError('E_WORKER', d.crash ? String(d.crash) : 'unexpected message') });
    };
    w.onerror = (e) => { if (e && e.preventDefault) e.preventDefault(); end({ error: workerError('E_WORKER', 'the worker failed to run') }); };
    w.onmessageerror = () => end({ error: workerError('E_WORKER', 'a message could not be read') });
    w.postMessage({ id, bytes });
  });
}

function status(text) { const s = $('j-progress'); s.textContent = text || ''; s.hidden = !text; }

let current = null;   // the preview on screen: {parsed, fileName, sample}
async function readBytes(bytes, fileName, sample = false) {
  const mine = seq + 1;
  showImport(true, false);   // a file dropped or picked while the panel is closed opens it
  $('j-error').hidden = true;
  $('j-preview').hidden = true;
  current = null;
  status('Reading your file in this tab…');
  const out = await parseBytes(bytes);
  if (mine !== seq) return;   // a newer file replaced this one
  status('');
  if (out.error) {
    renderReadError($('j-error'), out.error, out.error.code && out.error.code.startsWith('E_WORKER') ? () => readBytes(bytes, fileName, sample) : null);
    return;
  }
  current = { parsed: out.result, fileName, sample };
  preview();
}

async function readFile(file) {
  if (!file) return;
  if (file.size > ELIMITS.MAX_BYTES) {
    renderReadError($('j-error'), { code: 'E_TOO_LARGE', row: null, column: null, message: MESSAGES.E_TOO_LARGE }, null);
    return;
  }
  let bytes;
  try { bytes = new Uint8Array(await file.arrayBuffer()); } catch (e) {
    renderReadError($('j-error'), workerError('E_FILE_OPEN', String(e && e.name ? e.name : e)), () => readFile(file));
    return;
  }
  readBytes(bytes, file.name, false);
}

function readSample() {
  const text = $('j-sample').textContent.replace(/^\s+/, '');
  readBytes(new TextEncoder().encode(text), 'demo-trades.csv', true);
}

// ------------------------------------------------------------------ import: preview and write (§d.4)
function defaultAccount(parsed, sample) {
  const accs = J.accounts();
  if (sample) return accs.find((a) => a.sample) || null;
  const ok = (a) => a && !a.sample && a.unit === parsed.pnl_unit;
  if (ok(J.account(S.account))) return J.account(S.account);
  return accs.find((a) => ok(a) && a.format === parsed.format) || null;
}
function newName(parsed) {
  const base = FORMAT_SHORT[parsed.format] || 'Trading';
  const taken = new Set(J.accounts().map((a) => a.name));
  let i = 1;
  while (taken.has(`${base} account ${i}`)) i++;
  return `${base} account ${i}`;
}

function preview() {
  const { parsed, fileName, sample } = current;
  const box = $('j-preview');
  const chosen = defaultAccount(parsed, sample);
  const sel = el('select', { id: 'j-imp-acc' });
  if (!sample) {
    for (const a of J.accounts()) if (!a.sample) sel.append(el('option', { value: a.id, text: `${a.name} (${a.unit === 'points' ? 'price points' : a.unit})` }));
  } else if (chosen) sel.append(el('option', { value: chosen.id, text: chosen.name }));
  if (!sample || !chosen) sel.append(el('option', { value: 'new', text: sample ? SAMPLE_NAME : 'A new account' }));
  sel.value = chosen ? chosen.id : 'new';
  const name = el('input', { id: 'j-imp-name', type: 'text', maxlength: '40', autocomplete: 'off', value: sample ? SAMPLE_NAME : newName(parsed) });
  const nameField = el('div', { class: 'field', id: 'j-imp-name-f' }, el('label', { for: 'j-imp-name', text: 'Name of the new account' }), name);
  const counts = el('div', { id: 'j-imp-counts' });
  const add = el('button', { class: 'btn', type: 'button', id: 'j-imp-add' });
  const cancel = button('Cancel', () => { current = null; box.hidden = true; box.replaceChildren(); $('j-file').focus(); });
  const first = parsed.date_from, last = parsed.date_to;
  box.replaceChildren(...[
    el('h3', { id: 'j-prev-h', tabindex: '-1', text: sample ? 'Check before adding: the example data' : 'Check before adding' }),
    el('p', {}, `File: ${FORMAT_NAMES[parsed.format] || parsed.format}${parsed.verified_format ? '' : ' (beta)'} · `,
      `${plural(parsed.trades.length, 'closed trade', 'closed trades')}`,
      first !== null ? ` · closed ${M.dayKey(first)} to ${M.dayKey(last)}` : '', ` · times: ${parsed.tz_label}. ${unitNote(parsed.pnl_unit)}`),
    sample ? el('p', { class: 'notice notice-caution' }, el('strong', { text: 'Example data' }), 'These trades go into their own account.') : null,
    (parsed.warnings || []).length ? el('div', { class: 'notice notice-caution', id: 'j-imp-warn' },
      el('strong', { text: parsed.warnings.length === 1 ? '1 note about this file' : `${parsed.warnings.length} notes about this file` }),
      el('ul', {}, ...parsed.warnings.map((w) => el('li', { 'data-code': w.code, text: w.message })))) : null,
    el('div', { class: 'field' }, el('label', { for: 'j-imp-acc', text: 'Add to account' }), sel),
    nameField, counts, el('p', { class: 'btn-row' }, add, ' ', cancel)].filter(Boolean));
  box.hidden = false;
  let p = null;
  const keep = new Set();
  const update = () => {
    const isNew = sel.value === 'new';
    nameField.hidden = !isNew || sample;
    const acc = isNew ? newAccount(parsed, (name.value.trim() || newName(parsed)).slice(0, 40)) : J.account(sel.value);
    if (isNew && sample) acc.sample = true;
    p = plan(S.data, parsed, acc);
    for (const i of [...keep]) if (!p.possible.some((x) => x.i === i)) keep.delete(i);
    const kids = [];
    if (p.problem) kids.push(el('p', { class: 'notice notice-error', role: 'alert', text: p.problem }));
    else {
      kids.push(el('ul', { class: 'j-counts' },
        el('li', {}, el('strong', { text: 'New: ' }), el('span', { 'data-k': 'fresh', text: String(p.fresh.length) })),
        el('li', {}, el('strong', { text: 'Already in your journal (skipped): ' }), el('span', { 'data-k': 'dupes', text: String(p.dupes) })),
        el('li', {}, el('strong', { text: 'Possible duplicates: ' }), el('span', { 'data-k': 'possible', text: String(p.possible.length) }))));
      if (p.possible.length) {
        const u = parsed.pnl_unit;
        kids.push(el('details', { class: 'j-possible' }, el('summary', { text: `Review the ${plural(p.possible.length, 'possible duplicate', 'possible duplicates')}` }),
          el('p', { class: 'small', text: 'Each has the same symbol, side, open and close time as a trade already in this account, but other numbers. They are skipped unless you tick them.' }),
          el('ul', { class: 'j-checks' }, ...p.possible.map((x) => {
            const id = 'j-pd-' + x.i;
            const cb = el('input', { type: 'checkbox', id, 'data-i': String(x.i) });
            cb.checked = keep.has(x.i);
            cb.addEventListener('change', () => { if (cb.checked) keep.add(x.i); else keep.delete(x.i); label(); });
            return el('li', { class: 'check' }, cb, el('label', { for: id,
              text: `Keep: ${x.trade.symbol} ${x.trade.dir}, closed ${M.fmtTs(x.trade.close_ts)}, ${money(x.trade.pnl, u)} (the one already in the journal: ${money(x.existing.pnl, u)})` }));
          }))));
      }
      if (p.warning) kids.push(el('p', { class: 'notice notice-caution', text: p.warning }));
    }
    counts.replaceChildren(...kids);
    label();
  };
  const label = () => {
    const n = p && !p.problem ? p.fresh.length + keep.size : 0;
    add.textContent = `Add ${plural(n, 'trade', 'trades')}`;
    add.disabled = !p || !!p.problem || n === 0;
  };
  sel.addEventListener('change', update);
  name.addEventListener('input', debounce(update, 150));
  add.addEventListener('click', async () => {
    if (!p || p.problem) return;
    add.disabled = true;
    try {
      const res = await commit(S.db, p, parsed, fileName, [...keep]);
      current = null;
      box.hidden = true;
      box.replaceChildren();
      S.account = p.account.id;
      S.month = M.monthKey(parsed.date_to);
      await refresh();
      showImport(false);
      for (const f of J.hooks.afterImport) await f(J, res);
      importedToast(res, p.account);
    } catch (e) {
      counts.prepend(el('p', { class: 'notice notice-error', role: 'alert', text: `The trades were not added: ${e && e.message ? e.message : e}` }));
      add.disabled = false;
    }
  });
  update();
  $('j-prev-h').focus();
}

function importedToast(res, account) {
  const meta = S.data.meta || {};
  const undo = button('Undo this import', async () => {
    if (!await undoImport(res.imp.id, undo)) return;
    toast([el('p', { text: `Removed the ${plural(res.added, 'trade', 'trades')} that import added.` })]);
  });
  const kids = [el('p', {}, `Added ${plural(res.added, 'trade', 'trades')} to ${account.name}. `, undo)];
  const backup = el('p', { class: 'small' }, `Last backup: ${meta.last_backup_at ? ago(meta.last_backup_at) : 'never'}`);
  if (VIEWS.backup) backup.append(' · ', el('a', { href: '#backup', text: 'Save a backup file' }));
  kids.push(backup);
  toast(kids);
}

// Asks first, with the count (§d.4); removes the import's trades and their notes. True when done.
export async function undoImport(importId, returnTo) {
  const imp = S.data.imports.find((i) => i.id === importId);
  if (!imp) return false;
  const n = S.data.trades.filter((t) => t.import_id === importId).length;
  const box = returnTo.closest('p, td, li, div') || returnTo.parentElement;
  const yes = await confirmInline(box, `Remove the ${plural(n, 'trade', 'trades')} this import added? Notes on them are removed too.`,
    'Remove them', 'Keep them', null);
  if (!yes) { if (document.contains(returnTo)) returnTo.focus(); return false; }
  await store.undoImport(S.db, importId);
  // An account made by imports goes when its last import does, unless it holds day notes.
  const left = S.data.imports.filter((i) => i.account_id === imp.account_id && i.id !== importId).length;
  const dayNotes = S.data.days.some((d) => d.account_id === imp.account_id);
  if (!left && !dayNotes) await store.removeAccount(S.db, imp.account_id);
  await refresh();
  return true;
}

export function showImport(open, focus = true) {
  const sec = $('j-import');
  const btn = $('j-import-btn');
  sec.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  if (open && focus) $('j-import-h').focus();
}

// ------------------------------------------------------------------ "Requests sent by this page" (§c.3 #5)
function watchRequests() {
  const line = $('j-requests');
  if (typeof PerformanceObserver === 'undefined') return;
  let other = 0;
  const show = () => { line.textContent = other ? '' : 'Requests sent by this page to other sites since it opened: 0'; };
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) { try { if (new URL(e.name).origin !== location.origin) other++; } catch (x) { other++; } }
      show();
    }).observe({ type: 'resource', buffered: true });
  } catch (e) { return; }
  show();
}

// ------------------------------------------------------------------ wiring
async function init() {
  $('j-nojs').hidden = true;
  $('j-app').hidden = false;
  try {
    S.db = await store.open();
  } catch (e) {
    $('j-app').replaceChildren(el('p', { class: 'notice notice-error', role: 'alert' },
      el('strong', { text: 'This browser does not let the page save a journal' }),
      'The journal needs the browser’s storage (IndexedDB), which this window does not allow, for example in some private windows. Open the page in a normal window.'));
    return;
  }
  const input = $('j-file');
  input.addEventListener('change', () => { readFile(input.files[0]); input.value = ''; });
  $('j-sample-btn').addEventListener('click', readSample);
  $('j-import-btn').addEventListener('click', () => showImport($('j-import').hidden));
  $('j-account').addEventListener('change', (e) => { S.account = e.target.value; render(); });
  const dz = $('j-drop');
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('is-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('is-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('is-over');
    if (e.dataTransfer && e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]);
  });
  store.onChange(() => refresh());   // another tab changed the journal (J1)
  window.addEventListener('hashchange', onHash);
  S.view = viewFromHash();
  watchRequests();
  for (const v of ORDER) if (VIEWS[v] && VIEWS[v].init) VIEWS[v].init(J);
  await refresh();
  document.documentElement.dataset.journal = 'ready';
}

export function start() { init(); }
