// restore.js — /restore/#t=<token> (restore link or file), or restore by email.
import { api, saveToken, tokenFromHash, OUTAGE } from './token.js';

const $ = (id) => document.getElementById(id);

async function fromToken(token) {
  $('r-status').textContent = 'Checking your access…';
  const r = await api('/refresh', { token });
  if (r.status === 0 || r.status >= 500) { $('r-status').textContent = OUTAGE; return; }
  if (!r.ok) { $('r-status').textContent = r.json && r.json.error ? r.json.error.message : 'This link is not valid.'; return; }
  const saved = await saveToken(r.json.token);
  $('r-status').textContent = saved.local || saved.indexeddb ? 'Access restored in this browser.' : 'Access restored for this visit (this browser blocks saving).';
  const a = $('r-open');
  a.href = '/report/#t=' + r.json.token;
  a.hidden = false;
}

const token = tokenFromHash();
if (token) fromToken(token);

$('r-form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const email = $('r-email').value.trim();
  const err = $('r-email-err');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    err.textContent = 'Enter the email address you paid with, like name@example.com.';
    err.hidden = false;
    $('r-email').setAttribute('aria-invalid', 'true');
    return;
  }
  err.hidden = true;
  $('r-email').removeAttribute('aria-invalid');
  const r = await api('/restore', { email });
  $('r-sent').textContent = r.status === 0 || r.status >= 500
    ? OUTAGE
    : 'If that email paid for a report, a restore link is on its way. It works for 15 minutes.';
});
