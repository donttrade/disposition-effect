// read-file.js — reads a trade file for the tool pages without freezing them (Tester D7).
//
// The engine's runFile() runs in file-worker.js, off the main thread. Only an HTML report
// (MT5/MT4) is read on the page, because DOMParser, which the engine uses for HTML, does not
// exist inside a worker; those reports are far below the 200,000-row limit in practice.
// Results have the same shape either way: the ParseResult fields the pages use, with the
// number of fills as n_fills instead of the executions themselves. From the worker, each trade
// carries only what the pages read: pnl, hold_s, close_ts, dir and pnl_unit.
//
// A worker that fails is never silent (Tester R2): a script that does not load, throws, sends
// a message that cannot be read, sends something unexpected, or does not answer in time ends
// the read with an error whose code starts with E_WORKER, and the page shows it with a retry.
// Every message carries the request id it answers (Tester R3); an answer to another id is
// ignored. tool-state.js is the only caller.

import { runFile } from '../engine/index.js?v=87619422';

// No answer at all within START_MS: the worker never started (its script or one of the
// engine modules did not load). The worker answers {stage} as soon as it has the bytes, so
// this only has to cover loading the scripts on a slow connection.
export const START_MS = 20000;
// A started read that has not finished after PARSE_MS: 200,000 rows take a few seconds on a
// phone, so this is far past any real file.
export const PARSE_MS = 180000;
// The three noise checks on 20,000 trades take ~25 s on a 2-core laptop.
export const NOISE_MS = 300000;

export const WORKER_MESSAGES = Object.freeze({
  E_WORKER: 'The file could not be read in this browser: the part of the page that reads files stopped working.',
  E_WORKER_TIMEOUT: 'The file could not be read in this browser: the part of the page that reads files did not answer in time.',
  E_FILE_OPEN: 'This browser could not open the file. Check that it is still in the same place on your computer, then choose it again.',
});

export function workerError(code, detail) {
  return { code, row: null, column: null, message: WORKER_MESSAGES[code], detail: detail || null };
}

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

// Reads `bytes` as request `id`. Calls onStage(text) as it goes. `done` resolves {result} or
// {error} and never rejects: a worker failure is an {error} with an E_WORKER… code. With
// noise = true the worker stays alive: call runNoise() once the result is drawn, and it runs
// the noise checks and calls onNoise(noise), or onNoise(null) when they could not run.
// cancel() stops everything; after it, no callback is called again.
export function readTradeFile(bytes, { id = 0, noise = false, onStage = () => {}, onNoise = () => {} } = {}) {
  let worker = new Worker(new URL('./file-worker.js?v=39696582', import.meta.url), { type: 'module' });
  let settled = false;   // `done` has resolved
  let cancelled = false;
  let noiseAsked = false;
  let timer = null;
  let resolveDone;
  const done = new Promise((resolve) => { resolveDone = resolve; });
  const clearTimer = () => { if (timer) { clearTimeout(timer); timer = null; } };
  const stop = () => { clearTimer(); if (worker) { worker.terminate(); worker = null; } };
  const arm = (ms, onFire) => { clearTimer(); timer = setTimeout(onFire, ms); };
  const finish = (value) => {
    if (settled || cancelled) return;
    settled = true;
    clearTimer();
    resolveDone(value);
  };
  // Something went wrong in the worker: before the result it ends the read with an error;
  // after it, only the noise checks are lost.
  const failed = (code, detail) => {
    stop();
    if (cancelled) return;
    if (!settled) finish({ error: workerError(code, detail) });
    else if (noiseAsked) { noiseAsked = false; onNoise(null); }
  };

  worker.onmessage = (ev) => {
    const d = ev.data || {};
    if (cancelled) return;
    if (d.id !== id) { failed('E_WORKER', `answer for request ${String(d.id)}, expected ${id}`); return; }
    if (d.stage) { arm(PARSE_MS, () => failed('E_WORKER_TIMEOUT', 'reading the file')); onStage('Reading the trades in your file…'); return; }
    if (d.needsPage) {
      stop();
      onStage('Reading your report in this tab…');
      // let the status paint before the (synchronous) HTML parse
      setTimeout(() => {
        if (cancelled) return;
        let out;
        try { out = runFile(bytes); } catch (e) {
          // runFile returns bad files as {error}; a throw here is a bug: show it, never hang
          finish({ error: e && e.name === 'EngineError' ? e.toJSON() : workerError('E_WORKER', String(e && e.message ? e.message : e)) });
          return;
        }
        finish(out.error ? { error: out.error } : { result: slimOnPage(out.result), onPage: true });
      }, 30);
      return;
    }
    if (d.error) { stop(); finish({ error: d.error }); return; }
    if (d.result) {
      if (!noise) stop(); else clearTimer();
      finish({ result: fromColumns(d.result) });
      return;
    }
    if (d.noise) { stop(); if (noiseAsked) { noiseAsked = false; onNoise(d.noise); } return; }
    // {crash} is a bug in the worker, not a bad file; anything else is a message we never send
    failed('E_WORKER', d.crash ? String(d.crash) : 'unexpected message');
  };
  worker.onerror = (e) => {
    if (e && e.preventDefault) e.preventDefault(); // shown on the page instead (R2)
    failed('E_WORKER', 'the worker failed to run' + (e && e.message ? ': ' + e.message : ''));
  };
  worker.onmessageerror = () => failed('E_WORKER', 'a message could not be read');

  onStage('Reading your file in this tab…');
  arm(START_MS, () => failed('E_WORKER_TIMEOUT', 'no answer'));
  worker.postMessage({ id, bytes });

  const runNoise = () => {
    if (cancelled) return;
    if (!worker) { onNoise(null); return; }
    noiseAsked = true;
    arm(NOISE_MS, () => failed('E_WORKER_TIMEOUT', 'noise checks'));
    worker.postMessage({ id, noise: true });
  };
  const cancel = () => { cancelled = true; stop(); };
  return { done, cancel, runNoise };
}

// A visible "still working" line: an indeterminate bar and the seconds elapsed. The stage text
// itself lives in the page's role="status" element; this counter is outside it, so screen
// readers hear each stage once, not every second. Returns stop(), safe to call twice.
export function startProgress(box) {
  const t0 = Date.now();
  const secs = box.querySelector('[data-elapsed]');
  const tick = () => { secs.textContent = `${Math.floor((Date.now() - t0) / 1000)} s`; };
  tick();
  box.hidden = false;
  const timer = setInterval(tick, 500);
  return () => { clearInterval(timer); box.hidden = true; };
}
