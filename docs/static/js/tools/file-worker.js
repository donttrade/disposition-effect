// file-worker.js — reads a trade file off the main thread, so a 100,000-row file never
// freezes the page (Tester D7). The engine itself is unchanged: this worker calls the same
// runFile() the page used to call, then (when asked) the same noiseChecks().
//
// Messages in:  {id, bytes: Uint8Array}  read the file
//               {id, paste: string}     read a table pasted from a platform's screen (runFiles)
//               {id, noise: true}       then run the noise checks on the trades just read (the
//                                       page asks once it has drawn the result, so the two never
//                                       compete for the CPU)
// Every message out carries the `id` of the request it answers (Tester R3).
// Messages out: {stage: 'parsing'}                      the file is being read
//               {needsPage: true}                       an HTML report: DOMParser exists only
//                                                       on the page, so the page parses it
//               {error: EngineError JSON}               the file could not be read
//               {result: slim ParseResult}              see slim() below (trades as columns)
//               {noise: noiseChecks(...)}                after {noise: true}
//               {crash: message}                        a bug, not a bad file
//
// Nothing here touches the network, storage or the console. Only what the pages render is
// sent back: the trades and counts, never the raw rows.

import { runFile, runFiles } from '../engine/index.js?v=87619422';
import { decodeBytes, isHtml } from '../engine/csv.js?v=7dca0e6f';
import { noiseChecks } from '../engine/noise.js?v=d0f6a787';

// The pages need a few labels and a few numbers per trade. Copying 50,000 trade objects to the
// page costs the main thread ~0.3 s to unpack, so the trades travel as typed-array columns
// (transferred, not copied) and the executions are only counted. read-file.js rebuilds them.
// open_ts and qty serve the Readiness Check's habit flags; the symbol travels only as an index
// (the same number for the same symbol in this file), never as its text.
export const TRADE_COLUMNS = ['pnl', 'hold_s', 'close_ts', 'open_ts', 'qty'];
function slim(r) {
  const n = r.trades.length;
  const cols = {};
  for (const k of TRADE_COLUMNS) cols[k] = new Float64Array(n);
  const dir = new Int8Array(n);
  const sym = new Int32Array(n);
  const symIndex = new Map();
  r.trades.forEach((t, i) => {
    for (const k of TRADE_COLUMNS) cols[k][i] = t[k];
    dir[i] = t.dir === 'long' ? 1 : -1;
    if (!symIndex.has(t.symbol)) symIndex.set(t.symbol, symIndex.size);
    sym[i] = symIndex.get(t.symbol);
  });
  return {
    format: r.format, verified_format: r.verified_format, tz_label: r.tz_label,
    warnings: r.warnings, skipped: r.skipped, currency_groups: r.currency_groups,
    n_fills: r.executions.length, pnl_unit: n ? r.trades[0].pnl_unit : null, cols, dir, sym,
  };
}

let lastTrades = null; // {pnl, hold_s} of the file just read, kept only for the noise checks

self.onmessage = (ev) => {
  const msg = ev.data || {};
  const id = msg.id;
  const send = (m, transfer) => self.postMessage({ id, ...m }, transfer || []);
  if (msg.noise === true && !msg.bytes) {
    if (!lastTrades) { send({ crash: 'noise asked before a file was read' }); return; }
    try { send({ noise: noiseChecks(lastTrades) }); } catch (e) { send({ crash: String(e && e.message ? e.message : e) }); }
    return;
  }
  const paste = typeof msg.paste === 'string';
  if (!paste && !(msg.bytes instanceof Uint8Array)) { send({ crash: 'bad message' }); return; }
  try {
    if (!paste && typeof DOMParser === 'undefined' && isHtml(decodeBytes(msg.bytes))) {
      send({ needsPage: true });
      return;
    }
    send({ stage: 'parsing' });
    const out = paste ? runFiles([{ paste: msg.paste }]) : runFile(msg.bytes);
    if (out.error) { send({ error: out.error }); return; }
    // Only two numbers per trade are kept for the checks: no symbol, no time, nothing else.
    lastTrades = out.result.trades.map((t) => ({ pnl: Number(t.pnl), hold_s: Number(t.hold_s) }));
    const s = slim(out.result);
    send({ result: s }, [...Object.values(s.cols).map((a) => a.buffer), s.dir.buffer, s.sym.buffer]);
  } catch (e) {
    // decodeBytes can raise an EngineError (E_ENCODING) before runFile catches anything
    if (e && e.name === 'EngineError') { send({ error: e.toJSON() }); return; }
    send({ crash: String(e && e.message ? e.message : e) });
  }
};
