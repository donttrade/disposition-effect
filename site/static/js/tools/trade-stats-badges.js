// trade-stats-badges.js — the free "real or noise" badges of /tools/trade-stats/.
//
// Loaded only when the build has [flags] free_badges = true: the build leaves this file out
// otherwise (free-launch condition C1: the badges and their footnote are being redesigned by
// the Architect), and trade-stats.js then shows only the descriptive numbers. The statistics
// themselves are in ../engine/noise.js, unchanged; this file only draws their results.

import { NO_LOSSES } from '../engine/stats.js';
import { LABELS, N_PERM, guardSentence, FREE_CHECKS_FOOTNOTE } from '../engine/noise.js';
import { money, ratio, duration, intText, el, DASH } from './format.js';

const CHECK_TEXT = {
  // a bootstrap-t (noise.js), not a sign flip: the question names no method it does not use
  expectancy: ['Mean result per trade', 'Is the average result per trade different from zero, or could chance alone give one this far from zero with trades like these?'],
  hold_gap_s: ['Hold time, losers vs winners', 'Is the gap between how long losing and winning trades were held larger than shuffling the win/loss labels gives?'],
  longest_losing_streak: ['Longest losing streak', 'Is the longest run of losses longer than the same trades in a random order give?'],
};

export const FAILED = 'The checks could not run in this browser.';

// The section drawn with the results; the worker's answer fills it in (render below).
export function section() {
  return el('section', { 'aria-labelledby': 'ts-noise-h', id: 'ts-noise' },
    el('h3', { id: 'ts-noise-h', text: 'Real or noise?' }),
    el('p', { text: `Three checks, each repeated ${intText(N_PERM)} times on random copies of your own trades: resampled for the mean result, shuffled for the other two. A figure is "${LABELS.real}" when fewer than 5% of the copies come out as extreme as your real trades; otherwise it "${LABELS.noise}". Under 30 trades in a group the check is not run, and the result says "${LABELS.tooFew}". The mean result also says so when a few very large trades make up most of a short file's gains or losses.` }),
    el('p', { id: 'ts-noise-status', role: 'status', text: 'Running the checks…' }));
}

// The checks for an HTML report read on the page: a worker of their own.
export function runOnPage(trades, onDone) {
  const worker = new Worker(new URL('../engine/noise-worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = (ev) => {
    worker.terminate();
    onDone(ev.data.error || !ev.data.noise ? null : ev.data.noise);
  };
  const failed = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    worker.terminate();
    onDone(null);
  };
  worker.onerror = failed;
  worker.onmessageerror = failed;
  // Only two numbers per trade go to the worker: no symbol, no time, nothing else.
  worker.postMessage({ trades: trades.map((t) => ({ pnl: t.pnl, hold_s: t.hold_s })) });
  return worker;
}

function badge(label) {
  const cls = label === LABELS.real ? 'badge badge-real' : (label === LABELS.tooFew || label === NO_LOSSES) ? 'badge badge-few' : 'badge badge-noise';
  return el('span', { class: cls, text: label });
}

function observed(c, unit) {
  if (c.value === null) return DASH;
  if (c.stat === 'expectancy') return money(c.value, unit);
  if (c.stat === 'hold_gap_s') return (c.value < 0 ? 'losers shorter by ' : 'losers longer by ') + duration(Math.abs(c.value));
  return `${intText(c.value)} losses in a row`;
}

// box: the #ts-noise section; tableWrap: the page's scrolling table wrapper.
export function render(box, noise, total, unit, tableWrap) {
  const st = box.querySelector('#ts-noise-status');
  st.textContent = noise.limited ? `Checked on your most recent ${intText(noise.n_used)} of ${intText(total)} trades (the limit for these checks).` : 'Done.';
  const rows = noise.checks.map((c) => {
    const [name, q] = CHECK_TEXT[c.stat];
    // NIT 5: a streak of 0 losses has nothing to test; say so rather than "may be noise"
    const noLosses = c.stat === 'longest_losing_streak' && c.value === 0;
    const n = c.n_b === null ? intText(c.n_a) : `${intText(c.n_a)} losing, ${intText(c.n_b)} winning`;
    return el('tr', { 'data-check': c.stat },
      el('th', { scope: 'row' }, el('span', { text: name }), el('br'), el('span', { class: 'small muted', text: q })),
      el('td', { class: 'num', text: n }),
      el('td', { class: 'num', text: observed(c, unit) }),
      el('td', { class: 'num', text: c.p === null || noLosses ? DASH : c.p.toFixed(4) }),
      el('td', {}, badge(noLosses ? NO_LOSSES : c.label)));
  });
  const table = el('table', {},
    el('caption', { text: 'Real-or-noise checks on this file' }),
    el('thead', {}, el('tr', {}, ...['Check', 'Trades', 'In your file', 'p', 'Result'].map((h, i) => el('th', { scope: 'col', class: i && i < 4 ? 'num' : null, text: h })))),
    el('tbody', {}, ...rows));
  // ARCHITECT-STATS-AMENDMENT §7.2: a guarded expectancy check says why it withholds a verdict.
  // Only the expectancy check carries a guard field (the other two have none, not null).
  const guarded = noise.checks.filter((c) => c.stat === 'expectancy')
    .map((c) => guardSentence(c, (x) => money(x, unit))).filter((s) => s);
  box.append(tableWrap('Real-or-noise checks', table),
    ...guarded.map((s) => el('p', { class: 'ts-guard', text: s })),
    el('p', { class: 'small muted', text: 'p is the share of random copies at least as extreme as your file. A small p says the pattern is unlikely to be luck in this file; it does not say it will continue.' }),
    el('p', { class: 'small muted', id: 'ts-noise-footnote', text: FREE_CHECKS_FOOTNOTE }));
}

// teaserText (the hold-gap check's result next to the offer) was deleted: bundle plan B7, a luck result is never paired
// with the paid test.
