// tool-state.js — the one state helper every tool page uses (Tester R1, R2, R3, NIT 6).
//
//  * Form errors: clearFieldErrors / fieldError / showProblems give the three tools the same
//    error summary and per-field messages.
//  * whileBusy(button, fn): the button is disabled while fn runs and is re-enabled however fn
//    ends (result, error, a cancelled read), so a control can never stay greyed out (R1).
//  * createFileSlot(): the trade file a page is working on, as a small state machine:
//
//        empty ──pick──▶ reading ──result──▶ ready
//          ▲               │  ▲  └──error───▶ error ──retry──▶ reading
//          └──empty pick───┘  └──pick (a newer file replaces this one)
//
//    Each pick gets a request id. Only the latest pick may change the page: a result, error or
//    stage message from an older pick is dropped, and its worker is terminated as soon as it is
//    replaced, even while the file is still being loaded into memory (R3). A worker that fails
//    or does not answer ends the read with a visible error and a "Try again" button, never a
//    blank page or an endless "Reading…" (R2). settled() resolves when no read is in flight,
//    whichever way the latest one ended, so "Run" can wait for it without hanging (R1).

import { readTradeFile, startProgress, workerError } from './read-file.js?v=6970c985';
import { LIMITS, MESSAGES } from '../engine/errors.js?v=3327687b';
import { el } from './format.js?v=acb0db51';

// ------------------------------------------------------------------ form errors
export function clearFieldErrors(ids, summaryBox) {
  for (const id of ids) {
    const input = document.getElementById(id);
    if (input) input.removeAttribute('aria-invalid');
    const box = document.getElementById(id + '-err');
    if (box) { box.hidden = true; box.textContent = ''; }
  }
  if (summaryBox) summaryBox.hidden = true;
}

// QA 25 Oct: after a run, move focus to the result heading and bring the result's top into view
// (a plain jump, no smooth scroll, under reduced motion).
export function revealResult(heading) {
  heading.focus({ preventScroll: true });
  const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  heading.scrollIntoView({ block: 'start', behavior: still ? 'auto' : 'smooth' });
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

// ------------------------------------------------------------------ busy controls
export async function whileBusy(button, fn) {
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

// ------------------------------------------------------------------ a failed read, on screen
export const isWorkerFailure = (err) => !!err && typeof err.code === 'string' && (err.code.startsWith('E_WORKER') || err.code === 'E_FILE_OPEN');

// Fills `box` (a role="alert" element) with the error. A bad file gets the platform hint; a
// failure of this browser gets a "Try again" button when `retry` is given.
export function renderReadError(box, err, retry) {
  const kids = [el('strong', { text: 'This file could not be read' }), el('p', { text: err.message })];
  if (isWorkerFailure(err)) {
    kids.push(el('p', { class: 'small', text: `Error code ${err.code}${err.detail ? ` (${err.detail})` : ''}. This is a problem in this browser tab, not in your file. Try again; if it happens again, reload the page or use a recent Chrome, Firefox, Safari or Edge.` }));
    if (retry) {
      const btn = el('button', { class: 'btn btn-secondary', type: 'button', 'data-retry': '', text: 'Try again' });
      btn.addEventListener('click', retry);
      kids.push(el('p', {}, btn));
    }
  } else {
    kids.push(el('p', { class: 'small', text: `Error code ${err.code}. If your platform is not listed, copy your trades into the CSV template (Date, Time, Symbol, Side, Quantity, Price) and try again.` }));
  }
  box.replaceChildren(...kids);
  box.hidden = false;
  box.focus();
}

// ------------------------------------------------------------------ the file slot
// Callbacks (all optional except onResult and onError):
//   onStage(text)                  the status line ('' clears it)
//   onResult(out, label, job)      the latest read finished: out = {result, onPage?}
//   onError(err, retry|null)       the latest read failed; retry() reads the same bytes again
//   onNoise(noise|null)            noise checks of the latest read (noise: true only)
//   onClear()                      a new pick started or the pick was emptied: clear old output
export function createFileSlot({ progressBox, noise = false, onStage = () => {}, onResult, onError, onNoise = () => {}, onClear = () => {} }) {
  let seq = 0;            // the latest request id; anything older is stale
  let job = null;         // the latest read's {cancel, runNoise}
  let state = 'empty';
  let stopProgress = () => {};
  let waiters = [];

  const setState = (s) => {
    state = s;
    if (s !== 'reading') { const w = waiters; waiters = []; w.forEach((resolve) => resolve(s)); }
  };
  const supersede = () => {
    if (job) { job.cancel(); job = null; }
    stopProgress();
    stopProgress = () => {};
    onStage('');
    return ++seq;
  };
  const begin = () => {
    const id = supersede();
    onClear();
    setState('reading');
    stopProgress = startProgress(progressBox);
    return id;
  };
  // The latest read is over: hide the progress line and clear the stage text. False when `id`
  // is not the latest read (its outcome is dropped).
  const end = (id) => {
    if (id !== seq) return false;
    stopProgress();
    stopProgress = () => {};
    onStage('');
    return true;
  };

  async function read(id, bytes, label) {
    const thisJob = readTradeFile(bytes, {
      id, noise,
      onStage: (t) => { if (id === seq) onStage(t); },
      onNoise: (n) => { if (id === seq) onNoise(n); },
    });
    job = thisJob;
    const out = await thisJob.done; // never rejects: a worker failure is an {error}
    if (!end(id)) return;
    if (out.error) {
      job = null;
      try {
        onError(out.error, isWorkerFailure(out.error) ? () => readBytes(bytes, label) : null);
      } finally { setState('error'); }
      return;
    }
    // the page takes the result before anyone waiting on settled() runs
    let drawn;
    try {
      drawn = onResult(out, label, { runNoise: () => { if (id === seq) thisJob.runNoise(); }, isCurrent: () => id === seq });
    } finally { setState('ready'); }
    await drawn;
  }

  function readBytes(bytes, label) {
    const id = begin();
    return read(id, bytes, label);
  }

  async function pickFile(file, label = 'your file') {
    if (!file) { // the picker was emptied or cancelled
      supersede();
      onClear();
      setState('empty');
      return;
    }
    if (file.size > LIMITS.MAX_BYTES) { // refuse before reading a huge file into memory (NIT 6: no stale status)
      supersede();
      onClear();
      try {
        onError({ code: 'E_TOO_LARGE', row: null, column: null, message: MESSAGES.E_TOO_LARGE }, null);
      } finally { setState('error'); }
      return;
    }
    const id = begin();
    onStage('Reading your file in this tab…');
    let bytes;
    try {
      bytes = new Uint8Array(await file.arrayBuffer());
    } catch (e) {
      if (!end(id)) return;
      try {
        onError(workerError('E_FILE_OPEN', String(e && e.name ? e.name : e)), () => pickFile(file, label));
      } finally { setState('error'); }
      return;
    }
    if (id !== seq) return; // a newer pick arrived while this file was loading (R3)
    await read(id, bytes, label);
  }

  return {
    pickFile,
    readBytes,
    get state() { return state; },
    // resolves with the final state once no read is in flight
    settled: () => (state === 'reading' ? new Promise((resolve) => waiters.push(resolve)) : Promise.resolve(state)),
    clear: () => { supersede(); onClear(); setState('empty'); },
  };
}
