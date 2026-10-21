// restore.js — /restore/#t=<token>: the restore link or file saved after payment. There is no
// restore by email in v1 (decision 20 Oct): the link on the welcome screen is the only way back.
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
else $('r-status').textContent = 'Open the restore link or the restore file you saved after payment. Restore by email is not offered.';
