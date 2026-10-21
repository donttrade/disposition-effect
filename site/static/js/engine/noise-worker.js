// noise-worker.js — runs the noise checks off the main thread so the page stays
// responsive (10,000 permutations × up to 20,000 trades). Receives only
// {pnl, hold_s} per trade: no symbols, no times, nothing identifying.

import { noiseChecks } from './noise.js';

self.onmessage = (ev) => {
  const trades = ev.data && ev.data.trades;
  if (!Array.isArray(trades)) { self.postMessage({ error: 'bad message' }); return; }
  self.postMessage({ noise: noiseChecks(trades.map((t) => ({ pnl: Number(t.pnl), hold_s: Number(t.hold_s) }))) });
};
