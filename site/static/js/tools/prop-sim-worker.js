// prop-sim-worker.js — runs the 10,000 simulated challenges off the main thread so the
// page stays responsive. Receives only numbers (per-day results or the manual summary
// figures and the rules): no symbols, no times, nothing identifying.

import { simulate } from './prop-sim-core.js';

self.onmessage = (ev) => {
  try {
    self.postMessage({ result: simulate(ev.data) });
  } catch (e) {
    self.postMessage({ error: String(e && e.message ? e.message : e) });
  }
};
