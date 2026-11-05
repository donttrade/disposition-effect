// form-errors.js — the error summary and per-field messages every tool page shares. Its own small module so a
// calculator that never reads a trade file (lot size, risk-reward) does not load the file parsers through tool-state.js.

import { el } from './format.js';

export function clearFieldErrors(ids, summaryBox) {
  for (const id of ids) {
    const input = document.getElementById(id);
    if (input) input.removeAttribute('aria-invalid');
    const box = document.getElementById(id + '-err');
    if (box) { box.hidden = true; box.textContent = ''; }
  }
  if (summaryBox) summaryBox.hidden = true;
}

export function fieldError(id, message) {
  document.getElementById(id).setAttribute('aria-invalid', 'true');
  const box = document.getElementById(id + '-err');
  box.textContent = message;
  box.hidden = false;
}

// problems: [{id, message}] — a summary that links each message to its field
export function showProblems(box, problems) {
  box.replaceChildren(el('strong', { text: problems.length === 1 ? 'One input needs a change' : `${problems.length} inputs need a change` }),
    el('ul', {}, ...problems.map((x) => el('li', {}, el('a', { href: '#' + x.id, text: x.message })))));
  box.hidden = false;
  box.focus();
}

// ------------------------------------------------------------------ announcing a result
// Focus moves to the result heading, which a screen reader reads alone. A polite live region also says the heading and
// the first row of figures (the dl.stats under it), so the answer is heard without hunting for it.
function liveRegion() {
  let live = document.getElementById('tool-live');
  if (!live) {
    live = el('div', { id: 'tool-live', class: 'visually-hidden', role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true' });
    document.body.append(live);
  }
  return live;
}
if (typeof document !== 'undefined' && document.body) liveRegion();   // present before the first result, so the change is announced

export function announce(text) {
  const live = liveRegion();
  live.textContent = '';
  setTimeout(() => { live.textContent = text; }, 60);   // a changed region is announced; an unchanged one is not
}

// root: the container that holds the result heading and its figures.
// extra: more words to say after the figures (a prompt, or the key figures of a result that has no dl.stats).
export function announceResult(root, heading, extra = '') {
  const h = heading || root.querySelector('h2, h3');
  const parts = [h ? h.textContent.trim() : 'Result'];
  const dl = root.querySelector('dl.stats');
  if (dl) {
    for (const row of dl.querySelectorAll('.stat')) {
      const dt = row.querySelector('dt'), dd = row.querySelector('dd');
      const v = dd ? dd.textContent.trim() : '';
      if (dt && dd && v !== '—') parts.push(`${dt.textContent.trim()}: ${v}`);   // a dash says nothing aloud
    }
  }
  if (extra) parts.push(extra.replace(/[.]$/, ''));
  announce(parts.join('. ') + '.');
}
