// file-tool.js — shared wiring for the trade-file tools added in batch 2 (drawdown, heatmap).
//
// The file is read exactly as on /tools/trade-stats/: tool-state.js's file slot (one pick at a
// time, the latest wins, a failed worker shows an error with "Try again") and read-file.js's
// worker parse path. Nothing is stored, logged or sent: these pages' CSP is connect-src 'none'.
// No noise checks run here (noise: false), whatever the build's free_badges flag.

import { createFileSlot, renderReadError } from './tool-state.js?v=7534a30f';
import { el, unitNote, day, intText } from './format.js?v=acb0db51';

export const SAMPLE_LABEL = 'the synthetic sample file';

export const FORMAT_NAMES = {
  mt5: 'MetaTrader 5 report', mt4: 'MetaTrader 4 statement', ibkr_flex: 'Interactive Brokers Flex Query',
  tradovate_orders: 'Tradovate Orders export', tradingview: 'TradingView Order History export',
  generic: 'donttrade CSV template (one row per fill)',
  generic_roundtrip: 'CSV with one row per round trip',
};

export const plural = (n, one, many) => `${intText(n)} ${n === 1 ? one : many}`;

// "We're building a habit report that" / "The habit report" (partials/trader_offer.html lead()).
export const reportLead = (teaser) => (teaser.dataset.onSale === 'true' ? 'The habit report' : "We're building a habit report that");

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
    el('p', {}, `Format: ${FORMAT_NAMES[r.format] || r.format}${r.verified_format ? '' : ' (beta)'}. `,
      `${plural(r.trades.length, 'closed trade', 'closed trades')} from ${plural(r.n_fills, 'fill', 'fills')}, closed ${day(first.close_ts)} to ${day(last.close_ts)}. `,
      `Times are ${r.tz_label}. ${unitNote(unit)}`));
  if (fileLabel === SAMPLE_LABEL) {
    sec.append(el('p', { class: 'notice notice-caution' }, el('strong', { text: 'Sample data' }), 'Demo file, not a real trader.'));
  }
  if (r.warnings.length) {
    sec.append(el('div', { class: 'notice notice-caution', id: `${prefix}-warnings` },
      el('strong', { text: r.warnings.length === 1 ? '1 note about this file' : `${r.warnings.length} notes about this file` }),
      el('ul', {}, ...r.warnings.map((w) => el('li', { 'data-code': w.code, text: w.message })))));
  }
  return sec;
}

// Wires the drop zone, picker and sample button of a file tool whose ids start with `prefix`.
// onResult(result, fileLabel, job) draws the page; onClear() empties it.
export function wireFileTool(prefix, { onResult, onClear }) {
  const $ = (id) => document.getElementById(id);
  const status = (text) => { const s = $(`${prefix}-status`); s.textContent = text; s.hidden = !text; };
  const slot = createFileSlot({
    progressBox: $(`${prefix}-progress`), noise: false, onStage: status,
    onClear: () => { $(`${prefix}-error`).hidden = true; onClear(); },
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
