// journal/store.js: the free Trading Journal's storage (ARCHITECT-V3 §d.2, §d.3, §d.6; step J1).
// IndexedDB "donttrade-journal" v1, on this device only. Trades are stored in append-only chunks of at
// most 1,000 per record (one transaction per import; undo deletes that import's chunks); notes, day notes
// and the trader's own lists are sparse stores. Nothing here makes a network request: the page's CSP is
// connect-src 'none'. A versioned JSON backup file (with a SHA-256 of its canonical content) is the real
// safety net; restore can replace everything or merge (existing keys and notes win; conflicts listed).

export const DB_NAME = 'donttrade-journal';
export const VERSION = 1;
export const STORES = ['meta', 'accounts', 'imports', 'chunks', 'notes', 'days', 'lists'];
export const CHUNK = 1000;
export const BACKUP_FORMAT = 'donttrade-journal-backup';
export const BACKUP_VERSION = 1;
export const LIMITS = { trades: 100000, warn: 50000, note: 5000, listValues: 100, value: 40, accounts: 20 };
const TRADE_FIELDS = ['k', 'symbol', 'dir', 'open_ts', 'close_ts', 'hold_s', 'qty', 'entry', 'exit', 'pnl', 'pnl_gross',
  'fees', 'pnl_unit', 'fills_n'];
const CHANNEL = 'donttrade-journal';

// ------------------------------------------------------------------ open / upgrade
// One step per database version, keyed by the version it creates. open() runs every step above the
// browser's current version, in order, inside the one upgrade transaction, so a v1 journal upgrades in
// place and keeps every record. Then meta.schema records the version the data is now in.
// Version 2 is planned, not built: Ghost Trader's `plans` store and accounts.clock_offset_min
// (ARCHITECT-BRAND §6.1b). Its step goes here as MIGRATIONS[2], with VERSION = 2 and STORES + 'plans'.
export const MIGRATIONS = {
  1(db) {   // from no database
    db.createObjectStore('meta');
    db.createObjectStore('accounts', { keyPath: 'id' });
    db.createObjectStore('imports', { keyPath: 'id' }).createIndex('account_id', 'account_id');
    const ch = db.createObjectStore('chunks', { keyPath: 'id' });
    ch.createIndex('account_id', 'account_id');
    ch.createIndex('import_id', 'import_id');
    db.createObjectStore('notes', { keyPath: 'k' }).createIndex('account_id', 'account_id');
    db.createObjectStore('days', { keyPath: ['account_id', 'date'] });
    db.createObjectStore('lists', { keyPath: 'kind' });
  },
};

// version and steps are parameters only so the tests can exercise a later step on a v1 database.
// 'blocked' is not a failure: it fires while another connection (an older tab, or this tab's own connection
// whose last transaction is still finishing) has not closed yet. Every connection this file opens closes on
// versionchange, so the request goes on by itself once they have; rejecting here would report an error for
// an upgrade that then runs anyway (and leak its connection). onBlocked lets the page say "close the
// journal in your other tabs" meanwhile.
export function open(name = DB_NAME, version = VERSION, steps = MIGRATIONS, onBlocked = null) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(name, version);
    req.onupgradeneeded = (ev) => {
      const db = req.result;
      const tx = req.transaction;
      for (let v = ev.oldVersion + 1; v <= version; v++) {
        if (!steps[v]) { tx.abort(); return; }
        steps[v](db, tx);
      }
      if (ev.oldVersion > 0) {   // a fresh database gets meta on its first write (newMeta)
        const m = tx.objectStore('meta');
        const r = m.get('app');
        r.onsuccess = () => { if (r.result) m.put({ ...r.result, schema: version }, 'app'); };
      }
    };
    req.onsuccess = () => {
      const db = req.result;
      db.onversionchange = () => db.close();   // a newer page wants to migrate: let it
      resolve(db);
    };
    req.onerror = () => reject(req.error || new Error('The journal could not be upgraded.'));
    req.onblocked = () => { if (onBlocked) onBlocked(); };
  });
}

function done(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('The change was not saved.'));
    tx.onerror = () => {};   // onabort follows
  });
}
function all(store, query) {
  return new Promise((resolve, reject) => {
    const r = query === undefined ? store.getAll() : store.getAll(query);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
function one(store, key) {
  return new Promise((resolve, reject) => {
    const r = store.get(key);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export function rid(prefix) {
  const a = new Uint8Array(8);
  crypto.getRandomValues(a);
  return prefix + Array.from(a, (b) => (b % 36).toString(36)).join('').slice(0, 10);
}

// ------------------------------------------------------------------ change notices between tabs
let channel = null;
function ch() {
  if (!channel && typeof BroadcastChannel !== 'undefined') channel = new BroadcastChannel(CHANNEL);
  return channel;
}
export function notify(changed) { const c = ch(); if (c) c.postMessage({ changed }); }
const listening = [];   // kept here so a listener's channel is never garbage-collected
export function onChange(cb) {
  if (typeof BroadcastChannel === 'undefined') return () => {};
  const c = new BroadcastChannel(CHANNEL);   // its own channel object: a tab never hears its own posts
  c.onmessage = (e) => cb(e.data && e.data.changed);
  listening.push(c);
  return () => { c.close(); listening.splice(listening.indexOf(c), 1); };
}

// ------------------------------------------------------------------ writes
export function cleanTrade(t) {
  const o = {};
  for (const f of TRADE_FIELDS) o[f] = t[f] === undefined ? null : t[f];
  return o;
}

// One transaction: the account (when new), every chunk, the import record and meta. All or nothing (J2).
export async function addImport(db, { account, imp, trades }) {
  const tx = db.transaction(['accounts', 'imports', 'chunks', 'meta'], 'readwrite');
  const ok = done(tx);
  try {
    if (account) tx.objectStore('accounts').put(account);
    const chunkIds = [];
    for (let i = 0, n = 0; i < trades.length; i += CHUNK, n++) {
      const part = trades.slice(i, i + CHUNK).map(cleanTrade);
      const id = `${imp.account_id}:${imp.id}:${String(n).padStart(4, '0')}`;
      chunkIds.push(id);
      tx.objectStore('chunks').put({ id, account_id: imp.account_id, import_id: imp.id,
        from_ts: Math.min(...part.map((t) => t.close_ts)), to_ts: Math.max(...part.map((t) => t.close_ts)),
        keys: part.map((t) => t.k), trades: part });
    }
    tx.objectStore('imports').put({ ...imp, chunk_ids: chunkIds, n_added: trades.length });
    const m = tx.objectStore('meta');
    const r = m.get('app');
    r.onsuccess = () => m.put({ ...(r.result || newMeta()), last_change_at: new Date().toISOString() }, 'app');
  } catch (e) {
    tx.abort();
    await ok.catch(() => {});
    throw e;
  }
  await ok;
  notify('import');
}

export function newMeta() {
  return { schema: VERSION, created: new Date().toISOString(), last_backup_at: null, last_backup_trades: 0,
    persist: 'unknown', persist_asked_at: null, reminder_snoozed_until: null };
}

// Removes exactly that import's chunks, its record, and the notes on its trades (J9).
export async function undoImport(db, importId) {
  const tx = db.transaction(['imports', 'chunks', 'notes'], 'readwrite');
  const ok = done(tx);
  const chunks = await all(tx.objectStore('chunks').index('import_id'), IDBKeyRange.only(importId));
  for (const c of chunks) {
    tx.objectStore('chunks').delete(c.id);
    for (const k of c.keys) tx.objectStore('notes').delete(k);
  }
  tx.objectStore('imports').delete(importId);
  await ok;
  notify('import');
  return chunks.reduce((n, c) => n + c.keys.length, 0);
}

async function putIn(db, store, value, key) {
  const tx = db.transaction(store, 'readwrite');
  const ok = done(tx);
  if (key === undefined) tx.objectStore(store).put(value); else tx.objectStore(store).put(value, key);
  await ok;
  notify(store);
}
export function putNote(db, note) {
  if ((note.note || '').length > LIMITS.note) throw new Error(`A note holds at most ${LIMITS.note} characters.`);
  const empty = !note.setup && !(note.tags || []).length && !(note.mistakes || []).length && !note.note;
  if (empty) return delIn(db, 'notes', note.k);   // sparse: an emptied note is removed
  return putIn(db, 'notes', { ...note, updated: new Date().toISOString() });
}
export function putDay(db, day) {
  if (!day.note) return delIn(db, 'days', [day.account_id, day.date]);
  return putIn(db, 'days', { ...day, updated: new Date().toISOString() });
}
export function putList(db, kind, values) {
  if (values.length > LIMITS.listValues) throw new Error(`A list holds at most ${LIMITS.listValues} values.`);
  if (values.some((v) => !v || v.length > LIMITS.value)) throw new Error(`A value is 1 to ${LIMITS.value} characters.`);
  return putIn(db, 'lists', { kind, values });
}
export function putAccount(db, account) { return putIn(db, 'accounts', account); }
export function removeAccount(db, id) { return delIn(db, 'accounts', id); }
export async function putMeta(db, patch) {
  const tx = db.transaction('meta', 'readwrite');
  const ok = done(tx);
  const m = tx.objectStore('meta');
  const r = m.get('app');
  r.onsuccess = () => m.put({ ...(r.result || newMeta()), ...patch }, 'app');
  await ok;
}
async function delIn(db, store, key) {
  const tx = db.transaction(store, 'readwrite');
  const ok = done(tx);
  tx.objectStore(store).delete(key);
  await ok;
  notify(store);
}

export async function wipe(db) {
  const tx = db.transaction(STORES, 'readwrite');
  const ok = done(tx);
  for (const s of STORES) tx.objectStore(s).clear();
  await ok;
  notify('wipe');
}

// ------------------------------------------------------------------ read
export async function loadAll(db) {
  const tx = db.transaction(STORES, 'readonly');
  const [meta, accounts, imports, chunks, notes, days, lists] = await Promise.all([
    one(tx.objectStore('meta'), 'app'), all(tx.objectStore('accounts')), all(tx.objectStore('imports')),
    all(tx.objectStore('chunks')), all(tx.objectStore('notes')), all(tx.objectStore('days')), all(tx.objectStore('lists'))]);
  const trades = [];
  chunks.sort((a, b) => (a.id < b.id ? -1 : 1));
  for (const c of chunks) for (const t of c.trades) trades.push({ ...t, account_id: c.account_id, import_id: c.import_id });
  const L = { setup: [], tag: [], mistake: [] };
  for (const l of lists) L[l.kind] = l.values;
  return { meta: meta || null, accounts, imports, trades, notes, days, lists: L };
}

// ------------------------------------------------------------------ persistence (§d.3)
export async function persist() {
  try {
    if (!navigator.storage || !navigator.storage.persist) return 'unknown';
    if (await navigator.storage.persisted()) return 'granted';
    return (await navigator.storage.persist()) ? 'granted' : 'denied';
  } catch (e) { return 'unknown'; }
}
export async function persisted() {
  try { return navigator.storage && navigator.storage.persisted ? ((await navigator.storage.persisted()) ? 'granted' : 'denied') : 'unknown'; } catch (e) { return 'unknown'; }
}

// ------------------------------------------------------------------ backup and restore (§d.6)
export function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') {
    return '{' + Object.keys(v).sort().filter((k) => v[k] !== undefined).map((k) => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  }
  return JSON.stringify(v === undefined ? null : v);
}
export async function sha256(text) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, '0')).join('');
}

export async function serialize(state, now = new Date()) {
  const trades = state.trades.map((t) => ({ ...cleanTrade(t), import_id: t.import_id }));
  const notes = state.notes;
  const body = {
    format: BACKUP_FORMAT, version: BACKUP_VERSION, created: now.toISOString().replace(/\.\d{3}Z$/, 'Z'),
    app: 'https://donttrade.ca/journal/',
    counts: { accounts: state.accounts.length, imports: state.imports.length, trades: trades.length,
      notes: notes.length, days: state.days.length },
    accounts: state.accounts, imports: state.imports.map(({ chunk_ids, ...i }) => i), trades, notes, days: state.days,
    lists: { setup: state.lists.setup || [], tag: state.lists.tag || [], mistake: state.lists.mistake || [] },
  };
  return { ...body, sha256: await sha256(canonical(body)) };
}

export function backupName(now = new Date()) {
  return `donttrade-journal-${now.toISOString().slice(0, 10)}.json`;
}

// Backup files: one step per file version, keyed by the version it produces, run on an older file before
// it is checked (a v1 file then restores into a later journal). Planned, not built: BACKUP_STEPS[2] adds
// `plans: []` (ARCHITECT-BRAND §6.1b). The SHA is checked on the file as written, before any step.
export const BACKUP_STEPS = {};

const isStr = (x) => typeof x === 'string';
const isNum = (x) => typeof x === 'number' && Number.isFinite(x);
// Parse + check a backup file's text. {ok, data, problems[], shaOk, newer}. Never throws on bad input.
export async function validate(text, current = BACKUP_VERSION, steps = BACKUP_STEPS) {   // the last two: for the tests
  if (text.length > 100 * 1024 * 1024) return { ok: false, problems: ['This file is larger than 100 MB, so it is not a journal backup.'] };
  let d;
  try { d = JSON.parse(text); } catch (e) {
    return { ok: false, problems: ['This file is not a journal backup: it is not readable JSON.'] };
  }
  if (!d || typeof d !== 'object' || d.format !== BACKUP_FORMAT) {
    return { ok: false, problems: ['This file is not a donttrade journal backup.'] };
  }
  if (!Number.isInteger(d.version) || d.version < 1) return { ok: false, problems: ['This backup has no valid version number.'] };
  if (d.version > current) {
    return { ok: false, newer: true, problems: ['This backup was made by a newer version of this page. Reload the page and try again.'] };
  }
  const { sha256: claimed, ...written } = d;
  const shaOk = isStr(claimed) && claimed === await sha256(canonical(written));
  for (let v = d.version; v < current; v++) {
    if (!steps[v + 1]) return { ok: false, problems: ['This backup is from an older version that this page cannot read.'] };
    d = steps[v + 1](d);
  }
  const p = [];
  for (const k of ['accounts', 'imports', 'trades', 'notes', 'days']) if (!Array.isArray(d[k])) p.push(`“${k}” is missing or not a list.`);
  if (!d.lists || typeof d.lists !== 'object') p.push('“lists” is missing.');
  if (p.length) return { ok: false, problems: p };
  d.accounts.forEach((a, i) => { if (!isStr(a.id) || !isStr(a.name)) p.push(`Account ${i + 1} has no id or name.`); });
  d.trades.forEach((t, i) => {
    if (p.length > 20) return;
    if (!isStr(t.k) || !isStr(t.symbol) || !isNum(t.close_ts) || !isNum(t.pnl) || !isStr(t.import_id)) p.push(`Trade ${i + 1} is damaged.`);
  });
  d.notes.forEach((n, i) => { if (!isStr(n.k)) p.push(`Note ${i + 1} has no trade key.`); });
  d.days.forEach((x, i) => { if (!isStr(x.account_id) || !/^\d{4}-\d{2}-\d{2}$/.test(x.date || '')) p.push(`Day note ${i + 1} is damaged.`); });
  for (const k of ['setup', 'tag', 'mistake']) if (d.lists[k] && !Array.isArray(d.lists[k])) p.push(`The ${k} list is damaged.`);
  if (p.length) return { ok: false, problems: p.slice(0, 20) };
  return { ok: true, data: d, problems: [], shaOk };
}

// mode "replace": everything is replaced by the file. mode "merge": accounts, imports and trades whose
// key is new are added; an existing note or day note is kept when both have one (listed as a conflict);
// lists are united. One transaction either way.
export async function restore(db, d, mode) {
  const cur = mode === 'merge' ? await loadAll(db) : null;
  const tx = db.transaction(STORES, 'readwrite');
  const ok = done(tx);
  const S = (n) => tx.objectStore(n);
  const res = { trades: 0, notes: 0, days: 0, conflicts: [] };
  const m = S('meta').get('app');   // read before any clear; its put below is queued after the clears
  m.onsuccess = () => S('meta').put({ ...(m.result || newMeta()), last_change_at: new Date().toISOString() }, 'app');
  if (mode === 'replace') for (const s of STORES) if (s !== 'meta') S(s).clear();
  const haveAcc = new Set(cur ? cur.accounts.map((a) => a.id) : []);
  const haveImp = new Set(cur ? cur.imports.map((a) => a.id) : []);
  const haveKey = new Set(cur ? cur.trades.map((t) => t.k) : []);
  const notesNow = new Map(cur ? cur.notes.map((n) => [n.k, n]) : []);
  const daysNow = new Map(cur ? cur.days.map((x) => [x.account_id + '|' + x.date, x]) : []);
  for (const a of d.accounts) if (!haveAcc.has(a.id)) S('accounts').put(a);
  const byImport = new Map();
  for (const t of d.trades) {
    if (haveKey.has(t.k)) continue;
    haveKey.add(t.k);
    if (!byImport.has(t.import_id)) byImport.set(t.import_id, []);
    byImport.get(t.import_id).push(t);
  }
  const imps = new Map(d.imports.map((i) => [i.id, i]));
  for (const [iid, ts] of byImport) {
    const imp = imps.get(iid) || { id: iid, account_id: ts[0].k.split(':')[0], file_name: '(restored)', imported_at: d.created };
    const prefix = haveImp.has(iid) ? 'r' + Date.now().toString(36) : '';
    const chunkIds = [];
    for (let i = 0, n = 0; i < ts.length; i += CHUNK, n++) {
      const part = ts.slice(i, i + CHUNK).map(cleanTrade);
      const id = `${imp.account_id}:${iid}:${prefix}${String(n).padStart(4, '0')}`;
      chunkIds.push(id);
      S('chunks').put({ id, account_id: imp.account_id, import_id: iid, from_ts: Math.min(...part.map((t) => t.close_ts)),
        to_ts: Math.max(...part.map((t) => t.close_ts)), keys: part.map((t) => t.k), trades: part });
    }
    if (!haveImp.has(iid)) S('imports').put({ ...imp, chunk_ids: chunkIds });
    res.trades += ts.length;
  }
  for (const n of d.notes) {
    const old = notesNow.get(n.k);
    if (old) { if (canonical(old) !== canonical(n)) res.conflicts.push({ kind: 'note', k: n.k }); continue; }
    S('notes').put({ ...n, account_id: n.account_id || n.k.split(':')[0] });
    res.notes++;
  }
  for (const x of d.days) {
    const old = daysNow.get(x.account_id + '|' + x.date);
    if (old) { if (old.note !== x.note) res.conflicts.push({ kind: 'day', account_id: x.account_id, date: x.date }); continue; }
    S('days').put(x);
    res.days++;
  }
  for (const kind of ['setup', 'tag', 'mistake']) {
    const vals = [...new Set([...(cur ? cur.lists[kind] : []), ...(d.lists[kind] || [])])].slice(0, LIMITS.listValues);
    S('lists').put({ kind, values: vals });
  }
  await ok;
  notify('restore');
  return res;
}
