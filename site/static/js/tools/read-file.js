// read-file.js — reads a trade file for the tool pages without freezing them (Tester D7).
//
// The engine's runFile() runs in file-worker.js, off the main thread. Only an HTML report
// (MT5/MT4) is read on the page, because DOMParser, which the engine uses for HTML, does not
// exist inside a worker; those reports are far below the 200,000-row limit in practice.
// Results have the same shape either way: the ParseResult fields the pages use, with the
// number of fills as n_fills instead of the executions themselves. From the worker, each trade
// carries only what the pages read: pnl, hold_s, close_ts, dir and pnl_unit.

import { runFile } from '../engine/index.js';

function slimOnPage(r) {
  return {
    format: r.format, verified_format: r.verified_format, tz_label: r.tz_label,
    warnings: r.warnings, skipped: r.skipped, currency_groups: r.currency_groups,
    trades: r.trades, n_fills: r.executions.length,
  };
}

// The worker sends trades as columns; the pages use these five fields of each trade.
function fromColumns(d) {
  const { pnl, hold_s, close_ts } = d.cols;
  const trades = new Array(pnl.length);
  for (let i = 0; i < pnl.length; i++) {
    trades[i] = { pnl: pnl[i], hold_s: hold_s[i], close_ts: close_ts[i], dir: d.dir[i] === 1 ? 'long' : 'short', pnl_unit: d.pnl_unit };
  }
  const { cols, dir, pnl_unit, ...rest } = d;
  return { ...rest, trades };
}

// Reads `bytes`. Calls onStage(text) as it goes. Resolves {result} or {error}. With
// noise = true the worker stays alive: call runNoise() once the result is drawn, and it runs
// the noise checks and calls onNoise(noise), or onNoise(null) when they could not run.
// cancel() stops everything.
export function readTradeFile(bytes, { noise = false, onStage = () => {}, onNoise = () => {} } = {}) {
  let worker = new Worker(new URL('./file-worker.js', import.meta.url), { type: 'module' });
  let settled = false;
  const stop = () => { if (worker) { worker.terminate(); worker = null; } };
  const done = new Promise((resolve, reject) => {
    worker.onmessage = (ev) => {
      const d = ev.data || {};
      if (d.stage) { onStage('Reading the trades in your file…'); return; }
      if (d.needsPage) {
        stop();
        onStage('Reading your report in this tab…');
        // let the status paint before the (synchronous) HTML parse
        setTimeout(() => {
          const out = runFile(bytes);
          settled = true;
          resolve(out.error ? { error: out.error } : { result: slimOnPage(out.result), onPage: true });
        }, 30);
        return;
      }
      if (d.error) { settled = true; stop(); resolve({ error: d.error }); return; }
      if (d.result) {
        settled = true;
        if (!noise) stop();
        resolve({ result: fromColumns(d.result) });
        return;
      }
      if (d.noise) { stop(); onNoise(d.noise); return; }
      if (d.crash) {
        stop();
        const err = new Error('trade file worker: ' + d.crash); // a bug, not a bad file: fail loudly
        if (!settled) reject(err); else { onNoise(null); throw err; }
      }
    };
    worker.onerror = (e) => {
      stop();
      const err = new Error('trade file worker failed to run' + (e && e.message ? ': ' + e.message : ''));
      if (!settled) reject(err); else onNoise(null);
    };
  });
  onStage('Reading your file in this tab…');
  worker.postMessage({ bytes });
  const runNoise = () => { if (worker) worker.postMessage({ noise: true }); else onNoise(null); };
  return { done, cancel: stop, runNoise };
}

// A visible "still working" line: an indeterminate bar and the seconds elapsed. The stage text
// itself lives in the page's role="status" element; this counter is outside it, so screen
// readers hear each stage once, not every second.
export function startProgress(box) {
  const t0 = Date.now();
  const secs = box.querySelector('[data-elapsed]');
  const tick = () => { secs.textContent = `${Math.floor((Date.now() - t0) / 1000)} s`; };
  tick();
  box.hidden = false;
  const id = setInterval(tick, 500);
  return () => { clearInterval(id); box.hidden = true; };
}
