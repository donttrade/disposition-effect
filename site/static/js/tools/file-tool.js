// file-tool.js — shared wiring for the trade-file tools added in batch 2 (drawdown, heatmap).
//
// The file is read exactly as on /tools/trade-stats/: tool-state.js's file slot (one pick at a
// time, the latest wins, a failed worker shows an error with "Try again") and read-file.js's
// worker parse path. Nothing is stored, logged or sent: these pages' CSP is connect-src 'none'.
// No noise checks run here (noise: false), whatever the build's free_badges flag.

import { createFileSlot, renderReadError } from './tool-state.js';
import { el, unitNote, day, intText } from './format.js';

export const SAMPLE_LABEL = 'the synthetic sample file';

export const FORMAT_NAMES = {
  mt5: 'MetaTrader 5 report', mt4: 'MetaTrader 4 statement', ibkr_flex: 'Interactive Brokers Flex Query',
  tradovate_orders: 'Tradovate Orders export', tradingview: 'TradingView Order History export',
  generic: 'donttrade CSV template (one row per fill)',
  generic_roundtrip: 'CSV with one row per round trip',
};

export const plural = (n, one, many) => `${intText(n)} ${n === 1 ? one : many}`;

// "We're building a test that" / "The donttrade test" (partials/trader_offer.html lead()).
export const reportLead = (teaser) => (teaser.dataset.onSale === 'true' ? 'The donttrade test' : "We're building a test that");

export function tableWrap(label, table) {
  return el('div', { class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': label }, table);
}

// rows: [[rowHeader, cell, ...]]; a cell is text, a Node, or {text, cls, k}
export function rowsTable(caption, head, rows) {
  return el('table', {},
    el('caption', { text: caption }),
    el('thead', {}, el('tr', {}, ...head.map((h, i) => el('th', { scope: 'col', class: i ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows.map((r) => el('tr', {},
      el('th', { scope: 'row', text: r[0] }),
      ...r.slice(1).map((c) => (c instanceof Node ? el('td', { class: 'num' }, c) :
        el('td', { class: 'num ' + (c && c.cls ? c.cls : ''), text: c && c.text !== undefined ? c.text : c, 'data-k': c && c.k ? c.k : null })))))));
}

// The "What was read" block, the same facts as on /tools/trade-stats/.
export function readSection(prefix, r, fileLabel) {
  const first = r.trades[0], last = r.trades[r.trades.length - 1];
  const unit = first.pnl_unit;
  const sec = el('section', { 'aria-labelledby': `${prefix}-read-h` },
    el('h3', { id: `${prefix}-read-h`, text: 'What was read' }),
    el('p', {}, `Format: ${FORMAT_NAMES[r.format] || r.format}${r.verified_format ? '' : ' (not yet tested on a real export)'}. `,
      `${plural(r.trades.length, 'closed trade', 'closed trades')} from ${plural(r.n_fills, 'fill', 'fills')}, closed ${day(first.close_ts)} to ${day(last.close_ts)}. `,
      `Times are ${r.tz_label}. ${unitNote(unit)}`));
  if (fileLabel === SAMPLE_LABEL) {
    sec.append(el('p', { class: 'notice notice-caution' }, el('strong', { text: 'Example data' })));
  }
  const notes = warningsNotice(prefix, r.warnings);
  if (notes) sec.append(notes);
  return sec;
}

// The "N notes about this file" box (mixed currencies, skipped rows, ...), shared by every tool that reads a file.
export function warningsNotice(prefix, warnings) {
  if (!warnings || !warnings.length) return null;
  return el('div', { class: 'notice notice-caution', id: `${prefix}-warnings` },
    el('strong', { text: warnings.length === 1 ? '1 note about this file' : `${warnings.length} notes about this file` }),
    el('ul', {}, ...warnings.map((w) => el('li', { 'data-code': w.code, text: w.message }))));
}

// A table whose headings leave a needed column unnamed (TradeLocker's "Amount" was one): one choice per missing
// field, from the file's own headings, then the same table is read again with those columns. The box is
// `#<prefix>-map`; its select ids are `<prefix>-map-<field>`. Shared by the Challenge Readiness Check and the file tools.
const MAP_NAMES = {
  date: 'Date and time', symbol: 'Symbol', side: 'Buy or sell', qty: 'Quantity (size)', price: 'Price',
  open_time: 'Open time', close_time: 'Close time', direction: 'Long or short', open_price: 'Open price', close_price: 'Close price',
};
export function showMapStep(prefix, need, choose) {
  const $ = (id) => document.getElementById(id);
  const box = $(`${prefix}-map`);
  const taken = new Set(Object.values(need.chosen));
  const options = need.labels.map((l, i) => [i, l || `Column ${i + 1}`]).filter(([i]) => !taken.has(i));
  const err = el('p', { class: 'error', id: `${prefix}-map-err`, hidden: true });
  const fields = need.missing.map((f) => el('div', { class: 'field' },
    el('label', { for: `${prefix}-map-${f}`, text: MAP_NAMES[f] || f }),
    el('select', { id: `${prefix}-map-${f}`, 'data-field': f, 'aria-describedby': `${prefix}-map-err` },
      el('option', { value: '', text: 'Choose a column' }), ...options.map(([i, l]) => el('option', { value: String(i), text: l })))));
  const btn = el('button', { class: 'btn btn-secondary', type: 'button', id: `${prefix}-map-btn`, text: 'Read with these columns' });
  btn.addEventListener('click', () => {
    const picked = {};
    const seen = new Set();
    for (const f of need.missing) {
      const v = $(`${prefix}-map-${f}`).value;
      if (v === '' || seen.has(v)) {
        err.textContent = v === '' ? 'Pick a column for each box.' : 'Pick a different column for each box.';
        err.hidden = false;
        $(`${prefix}-map-${f}`).focus();
        return;
      }
      seen.add(v);
      picked[f] = Number(v);
    }
    choose(picked);
  });
  box.replaceChildren(el('strong', { id: `${prefix}-map-h`, text: 'Which column is which?' }),
    el('p', { text: `No heading in your ${need.missing.length === 1 ? 'table names this column' : 'table names these columns'}. Pick ${need.missing.length === 1 ? 'it' : 'each one'} from your headings.` }),
    el('div', { class: 'field-grid' }, ...fields), err, el('p', { class: 'btn-row' }, btn));
  box.hidden = false;
  box.focus();
}

export function hideMap(prefix) {
  const box = document.getElementById(`${prefix}-map`);
  if (box) { box.hidden = true; box.replaceChildren(); }
}

// Wires the drop zone, picker and sample button of a file tool whose ids start with `prefix`.
// onResult(result, fileLabel, job) draws the page; onClear() empties it.
export function wireFileTool(prefix, { onResult, onClear }) {
  const $ = (id) => document.getElementById(id);
  const status = (text) => { const s = $(`${prefix}-status`); s.textContent = text; s.hidden = !text; };
  const slot = createFileSlot({
    progressBox: $(`${prefix}-progress`), noise: false, onStage: status,
    onClear: () => { $(`${prefix}-error`).hidden = true; hideMap(prefix); onClear(); },
    onMapNeeded: (need, choose) => showMapStep(prefix, need, choose),
    onResult: (out, label, job) => onResult(out.result, label, job),
    onError: (err, retry) => renderReadError($(`${prefix}-error`), err, retry),
  });
  const input = $(`${prefix}-file`);
  input.addEventListener('change', () => { slot.pickFile(input.files[0], 'your file'); input.value = ''; });
  $(`${prefix}-sample-btn`).addEventListener('click', () => {
    const text = $(`${prefix}-sample`).textContent.replace(/^\s+/, '');
    slot.readBytes(new TextEncoder().encode(text), SAMPLE_LABEL);
  });
  const dz = $(`${prefix}-drop`);
  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('is-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('is-over'));
  dz.addEventListener('drop', (e) => {
    e.preventDefault();
    dz.classList.remove('is-over');
    if (e.dataTransfer && e.dataTransfer.files[0]) slot.pickFile(e.dataTransfer.files[0], 'your file');
  });
  $(`${prefix}-js-needed`).hidden = true;
  $(`${prefix}-controls`).hidden = false;
  return slot;
}
