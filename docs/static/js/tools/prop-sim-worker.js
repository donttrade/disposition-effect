// prop-sim-worker.js — runs the 10,000 simulated challenges off the main thread so the
// page stays responsive. Receives only numbers (per-day results, per-trade times within the day
// for the cool-down rule, or the manual summary figures and the rules): no symbols, no dates,
// nothing identifying.
//
// Messages: the simulate() parameters (as before), or {op: 'whatif', p, personal}, or
// {op: 'rank', p}, or {op: 'range', p, personal}. Ranking loads prop-sim-rank.js only while WHATIF_RANKED is on (off).

import { simulate, whatIf, dayResampleRange, WHATIF_RANKED } from './prop-sim-core.js?v=7c28de14';

self.onmessage = (ev) => {
  try {
    const m = ev.data || {};
    if (m.op === 'whatif') self.postMessage({ whatif: whatIf(m.p, m.personal) });
    else if (m.op === 'rank') {
      // prop-sim-rank.js is in the build only with [flags] whatif_ranked = true
      if (!WHATIF_RANKED) self.postMessage({ rank: { enabled: false } });
      else import('./prop-sim-rank.js').then((r) => self.postMessage({ rank: r.rankRules(m.p, { enabled: true }) }),
        (e) => self.postMessage({ error: String(e && e.message ? e.message : e) }));
    }
    else if (m.op === 'range') self.postMessage({ range: dayResampleRange(m.p, { personal: m.personal || null }) });
    else self.postMessage({ result: simulate(m) });
  } catch (e) {
    self.postMessage({ error: String(e && e.message ? e.message : e) });
  }
};
