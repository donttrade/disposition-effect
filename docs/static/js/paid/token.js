// token.js — access token storage and the API client for the paid pages.
//
// The token is kept in localStorage AND IndexedDB, each inside try/catch: Safari
// private mode, blocked site data or a full disk must not break the report. When
// both fail, the pages still work for this visit (the token travels in the URL
// #fragment, which never reaches a server log) and offer the restore file.

const LS_KEY = 'donttrade-access';
const DB = 'donttrade';
const STORE = 'kv';

function idb() {
  return new Promise((resolve, reject) => {
    let req;
    try { req = indexedDB.open(DB, 1); } catch (e) { reject(e); return; }
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbSet(value) {
  const db = await idb();
  await new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(value, 'access');
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

async function idbGet() {
  const db = await idb();
  const v = await new Promise((resolve, reject) => {
    const r = db.transaction(STORE, 'readonly').objectStore(STORE).get('access');
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => reject(r.error);
  });
  db.close();
  return v;
}

export async function saveToken(token) {
  const saved = { local: false, indexeddb: false };
  try { localStorage.setItem(LS_KEY, token); saved.local = localStorage.getItem(LS_KEY) === token; } catch (e) { /* blocked */ }
  try { await idbSet(token); saved.indexeddb = true; } catch (e) { /* blocked */ }
  return saved;
}

export async function loadToken() {
  try { const t = localStorage.getItem(LS_KEY); if (t) return t; } catch (e) { /* blocked */ }
  try { return await idbGet(); } catch (e) { return null; }
}

// #t=<token> → token, and the fragment is removed from the address bar.
export function tokenFromHash() {
  const m = /(?:^#|&)t=([A-Za-z0-9._-]+)/.exec(location.hash);
  if (!m) return null;
  history.replaceState(null, '', location.pathname + location.search);
  return m[1];
}

export function decodeToken(token) {
  try {
    const b = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(b + '==='.slice((b.length + 3) % 4)));
  } catch (e) { return null; }
}

export function apiBase() {
  const m = document.querySelector('meta[name="dt-api"]');
  if (!m) throw new Error('dt-api meta tag missing');
  return m.content.replace(/\/$/, '');
}

// Never throws for network trouble: {ok, status, json}. status 0 = could not reach the server.
export async function api(path, body) {
  try {
    const res = await fetch(apiBase() + path, { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body), credentials: 'omit', cache: 'no-store', referrerPolicy: 'no-referrer' });
    let json = null;
    try { json = await res.json(); } catch (e) { /* not JSON */ }
    return { ok: res.ok, status: res.status, json };
  } catch (e) {
    return { ok: false, status: 0, json: null };
  }
}

export const OUTAGE = 'Your purchase is safe and nothing was counted. The report service did not answer; please try again in a few minutes.';

export function restoreLink(token) {
  return location.origin + '/restore/#t=' + token;
}

// A tiny local HTML file that reopens access on any browser. Built in the page, no network.
export function restoreFileHtml(token) {
  const link = restoreLink(token);
  return '<!doctype html><meta charset="utf-8"><title>donttrade restore</title>' +
    '<p>Open your donttrade report access: <a href="' + link + '">' + location.origin + '/restore/</a></p>' +
    '<p>Keep this file private: it opens your purchase.</p>';
}

export function downloadRestoreFile(token) {
  const blob = new Blob([restoreFileHtml(token)], { type: 'text/html' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'donttrade-restore.html';
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
}
