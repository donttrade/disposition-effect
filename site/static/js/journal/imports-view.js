// journal/imports-view.js: #imports (ARCHITECT-V3 §d.4 "Imports panel", §d.5 screen 6). Every import with
// its dates and counts, each with Undo; the confirmation names the count (J9).
import { el, tableWrap, button, intText, localDay } from './ui.js';

export function render(J, body) {
  const imps = J.S.data.imports.slice().sort((a, b) => (a.imported_at < b.imported_at ? 1 : -1));
  if (!imps.length) {
    body.replaceChildren(el('p', { text: 'No imports yet.' }));
    return;
  }
  const count = new Map();
  for (const t of J.S.data.trades) count.set(t.import_id, (count.get(t.import_id) || 0) + 1);
  const rows = imps.map((i) => {
    const acc = J.account(i.account_id);
    const undo = button('Undo', () => J.undoImport(i.id, undo), 'btn btn-secondary',
      { 'aria-label': `Undo the import of ${i.file_name || 'a file'} on ${localDay(i.imported_at)}` });
    const dupes = [i.n_skipped_dupe ? `${intText(i.n_skipped_dupe)} already in the journal` : null,
      i.n_possible_dupe_skipped ? `${intText(i.n_possible_dupe_skipped)} possible duplicates skipped` : null,
      i.n_possible_dupe_kept ? `${intText(i.n_possible_dupe_kept)} possible duplicates kept` : null].filter(Boolean).join('; ') || 'none';
    return el('tr', {},
      el('th', { scope: 'row', text: i.file_name || '(no name)' }), el('td', { text: acc ? acc.name : '' }),
      el('td', { text: J.formatName(i.format) + (i.verified_format ? '' : ' (beta)') }),
      el('td', { class: 'nowrap', text: localDay(i.imported_at) }),
      el('td', { class: 'nowrap', text: i.date_from ? `${i.date_from} to ${i.date_to}` : '' }),
      el('td', { class: 'num', text: intText(count.get(i.id) || 0) }), el('td', { text: dupes }), el('td', {}, undo));
  });
  const table = el('table', {}, el('caption', { text: 'Your imports, newest first' }),
    el('thead', {}, el('tr', {}, ...['File', 'Account', 'Format', 'Imported', 'Trades closed', 'Trades', 'Skipped or kept', 'Undo']
      .map((h, i) => el('th', { scope: 'col', class: i === 5 ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows));
  body.replaceChildren(el('p', { class: 'small', text: 'Undo removes exactly the trades that import added, and the notes on them.' }), tableWrap('Imports', table));
}
