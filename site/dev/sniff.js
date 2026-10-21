// sniff.js — logic for dev/sniff.html (kept out of the page so the CSP can forbid inline script).
import { decodeBytes, isHtml, parseCsv, sniffDelimiter, normHeader } from '../static/js/engine/csv.js';
import { detectCsv, detectHtml, SIGNATURES } from '../static/js/engine/detect.js';
import { htmlRows } from '../static/js/engine/mt.js';

const out = document.getElementById('out');

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text; // textContent only: nothing from the file is parsed as HTML
  if (cls) e.className = cls;
  return e;
}

function table(headers, rows) {
  const t = el('table');
  const tr = el('tr');
  for (const h of headers) { const th = el('th', h); th.scope = 'col'; tr.append(th); }
  t.append(tr);
  for (const r of rows) {
    const row = el('tr');
    for (const c of r) row.append(c instanceof Node ? c : el('td', String(c)));
    t.append(row);
  }
  return t;
}

// One sniffed table: header row + map → summary rows.
function describe(header, map, dataRows, sigName) {
  const mappedIdx = new Map(Object.entries(map).map(([f, i]) => [i, f]));
  const mapped = Object.entries(map).map(([f, i]) => `${f} ← "${header.cells[i]}"`);
  const unmapped = header.cells.map((h, i) => [h, i]).filter(([h, i]) => h !== '' && !mappedIdx.has(i)).map(([h]) => h);
  // Sample only trade rows: on a MetaTrader balance row the comment cell spans the
  // whitelisted columns (colspan), and the engine skips such rows by their Type anyway.
  const isTrade = (r) => !('type' in map) || ['buy', 'sell'].includes((r.cells[map.type] || '').toLowerCase());
  const samples = dataRows.filter((r) => r.cells.some((c) => c !== '') && isTrade(r)).slice(0, 2).map((r) =>
    header.cells.map((h, i) => (mappedIdx.has(i) ? el('td', r.cells[i] ?? '') : el('td', '[skipped]', 'skipped'))));
  return { sigName, mapped, unmapped, header: header.cells.map((h) => h || '(blank)'), samples };
}

function show(name, bytes) {
  const box = el('section');
  box.dataset.file = name;
  box.append(el('h2', name));
  try {
    const text = decodeBytes(bytes);
    let fmt, parts = [], closed = 'n/a';
    if (isHtml(text)) {
      const det = detectHtml(htmlRows(text));
      fmt = det.format;
      if (fmt === 'mt5') closed = det.tables.some((t) => t.kind === 'mt5_positions_closed') ? 'yes' : 'no';
      for (const t of det.tables) parts.push(describe(t.header, t.map, t.rows, t.kind));
    } else {
      const rows = parseCsv(text, sniffDelimiter(text));
      const det = detectCsv(rows);
      fmt = det.format === 'mt5_deals' ? 'mt5' : det.format;
      if (fmt === 'mt5') closed = 'no (CSV deals only)';
      parts.push(describe(rows[det.headerIndex], det.map, rows.slice(det.headerIndex + 1), det.format));
    }
    const verified = SIGNATURES[parts[0].sigName === 'mt5_positions_closed' || parts[0].sigName === 'mt5_positions_open'
      ? 'mt5_positions' : parts[0].sigName].verified;
    const summary = table(['format', 'verified columns', 'closed-positions table', 'tables found'],
      [[fmt, verified ? 'yes' : 'no (UNVERIFIED)', closed, parts.map((p) => p.sigName).join(', ')]]);
    summary.dataset.role = 'summary';
    box.append(summary);
    for (const p of parts) {
      box.append(el('h3', p.sigName));
      box.append(table(['mapped (whitelist)', 'not read'], [[p.mapped.join('\n'), p.unmapped.join(', ') || '—']]));
      box.append(table(p.header, p.samples));
    }
  } catch (e) {
    if (e.name !== 'EngineError') throw e;
    const p = el('p', `${e.code}: ${e.message}`, 'err');
    p.dataset.code = e.code;
    box.append(p);
  }
  out.append(box);
}

document.getElementById('file').addEventListener('change', async (ev) => {
  out.replaceChildren();
  for (const f of ev.target.files) show(f.name, new Uint8Array(await f.arrayBuffer()));
  out.dataset.done = String(ev.target.files.length);
});
