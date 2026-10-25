// welcome.js — /welcome/?session_id=cs_… (the Stripe Payment Link redirect).
// session_id → POST /redeem → token saved (localStorage + IndexedDB, both optional)
// → session_id removed from the address bar → restore link and restore file offered.
import { api, saveToken, downloadRestoreFile, restoreLink, OUTAGE } from './token.js?v=16f6dd26';

const $ = (id) => document.getElementById(id);

function show(id) { for (const s of document.querySelectorAll('[data-state]')) s.hidden = s.id !== id; }

async function redeem(sessionId) {
  show('w-working');
  const r = await api('/redeem', { session_id: sessionId });
  if (r.status === 0 || r.status >= 500) { $('w-error-msg').textContent = OUTAGE; show('w-error'); return; }
  if (!r.ok) { $('w-error-msg').textContent = (r.json && r.json.error && r.json.error.message) || 'This checkout could not be confirmed.'; show('w-error'); return; }
  const token = r.json.token;
  const saved = await saveToken(token);
  $('w-saved').textContent = saved.local || saved.indexeddb
    ? 'Access is saved in this browser.'
    : 'This browser blocks saving, so access lasts only for this visit. Save the restore file or link below.';
  $('w-report').href = '/report/#t=' + token;
  $('w-link').value = restoreLink(token);
  $('w-download').onclick = () => downloadRestoreFile(token);
  $('w-copy').onclick = async () => {
    try { await navigator.clipboard.writeText($('w-link').value); $('w-copy-msg').textContent = 'Copied.'; }
    catch (e) { $('w-link').select(); $('w-copy-msg').textContent = 'Select the link and copy it.'; }
  };
  show('w-ready');
}

const params = new URLSearchParams(location.search);
const sid = params.get('session_id');
if (!sid) {
  // NIT 13: it is UNVERIFIED that a Stripe receipt carries this page's link, so the message
  // does not rely on it: email is the one path that always exists. Round-2 NIT 8: nor does it
  // assume a receipt was sent (Stripe customer emails are a dashboard setting): the date and
  // amount are on the buyer's card statement either way.
  $('w-error-msg').textContent = 'No checkout was found in this link. If you paid, email us (address below) with the date and amount of your payment.';
  $('w-retry-row').hidden = true; // NIT 7: with no checkout id there is nothing to try again
  show('w-error');
} else {
  history.replaceState(null, '', location.pathname); // the session id never stays in the address bar
  $('w-retry').onclick = () => redeem(sid);
  redeem(sid);
}
