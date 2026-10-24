// journal/ui.js: small DOM helpers shared by the journal's views. Text goes in with textContent only
// (format.js el()), never innerHTML, so a symbol, a file name or a note cannot become markup.
import { el, money as fmtMoney, intText, MINUS } from '../tools/format.js';

export { el, intText, MINUS };
export const $ = (id) => document.getElementById(id);

// Hide amounts (§d.1, J26): every currency figure becomes "•••", with its sign kept, so the calendar
// still shows the sign and the colour. ctx.hide is the toggle's state.
export const HIDDEN = '•••';
export function money(n, unit, hide) {
  if (!hide || typeof n !== 'number' || !Number.isFinite(n)) return fmtMoney(n, unit);
  return (n < 0 ? MINUS : n > 0 ? '+' : '') + HIDDEN;
}
// An ISO instant as the date on this computer's clock (when a backup or import happened, not a trade time).
export function localDay(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export const plural = (n, one, many) => `${intText(n)} ${n === 1 ? one : many}`;

export function tableWrap(label, table) {
  return el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': label }, table);
}

export function button(text, onClick, cls = 'btn btn-secondary', attrs = {}) {
  const b = el('button', { type: 'button', class: cls, text, ...attrs });
  b.addEventListener('click', onClick);
  return b;
}

// An inline "are you sure" (no modal dialog): the question and two buttons replace `box`'s content until
// one is pressed. Resolves true or false; focus goes to the question, then back to `returnTo`.
export function confirmInline(box, question, yes, no, returnTo) {
  return new Promise((resolve) => {
    const before = [...box.childNodes];
    const q = el('p', { class: 'j-confirm-q', tabindex: '-1', text: question });
    const end = (v) => { box.replaceChildren(...before); box.classList.remove('j-confirming'); if (returnTo && document.contains(returnTo)) returnTo.focus(); resolve(v); };
    box.classList.add('j-confirming');
    box.replaceChildren(q, el('p', { class: 'btn-row' }, button(yes, () => end(true), 'btn'), ' ', button(no, () => end(false))));
    q.focus();
  });
}

// A file the trader keeps: a Blob behind <a download> (as token.js does). No network: a blob: URL is local.
export function saveFile(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = el('a', { href: url, download: name, hidden: true });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function debounce(fn, ms) {
  let t = null;
  const d = (...args) => { clearTimeout(t); t = setTimeout(() => { t = null; fn(...args); }, ms); };
  d.flush = (...args) => { if (t) { clearTimeout(t); t = null; fn(...args); } };
  return d;
}
