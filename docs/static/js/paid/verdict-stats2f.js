// verdict-stats2f.js — dual accept for one release (ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §7 S1): a report of
// the previous method (2026-10-23.stats2f, DT-1 of the donttrade test) shown on the DT-2 page. Its sentences are the
// frozen wording-stats2f.js, word for word; this module gives them the interface report.js uses for DT-2 (wording.js):
// the same exports, the same layers. Two things differ from the 9d4bdde page, because their words are retired:
//   * the pills say what a DT-1 result was in that method's own terms ("Beyond chance" for a gap the method calls
//     distinguishable from noise, "Within chance" for one within what chance alone produces), never a DT-2 step: a
//     DT-1 result is not a DT-2 step and is not shown as one;
//   * the frozen lines that say "not tested" or "described" are reworded for display (shown()), as 9d4bdde's plain()
//     did, without the retired display words. Habits DT-1 did not check are facts, as in DT-2.
// Delete this module and wording-stats2f.js one release after DT-2 is live.
import * as F from './wording-stats2f.js?v=e96bc0a0';
import { CHECK_HEADING, FACTS_LINE, RESEARCH, RESEARCH_PREFIX, holdDays } from './wording.js?v=bda30e6a';

export { CHECK_HEADING, FACTS_LINE, RESEARCH, RESEARCH_PREFIX, holdDays };
export const METHOD_VERSION = F.METHOD_VERSION;
export const METHOD_LABEL = 'DT-1';
export const PILL = Object.freeze({
  distinguishable: 'Beyond chance',
  not_distinguishable: 'Within chance',
  too_few: 'Too few trades',
  dates_only: 'No check on this file',
});

export function shown(s) {
  return s.replace(' So this pattern is described here without a verdict.', '')
    .replace('Some are described below without a verdict.', 'Some are shown below without a verdict.')
    .replace(/^Not tested: /, 'No check on this file: ')
    .replace(/^Not described: /, 'No figure for this file: ')
    .replace(', so it is not tested on files like that.', ', so files like that get no check against chance.')
    .replace(', so it is not described for files like that.', ', so files like that get no figure.')
    .replace('are not tested, and size after a loss is not described.', 'get no check against chance, and size after a loss gets no figure.');
}

export const checkReport = F.checkReport;

export function pillOf(h) {
  if (h.verdict === 'distinguishable' || h.verdict === 'not_distinguishable' || h.verdict === 'too_few') return h.verdict;
  if (h.verdict === 'withheld' && h.withheld === 'dates_only' && (h.id === 'revenge' || h.id === 'tilt')) return 'dates_only';
  return null;
}
export const factsOnly = (h) => pillOf(h) === null;
export const isClear = (h) => h.verdict === 'distinguishable' && h.direction === 'habit';
export const smallFile = () => false;
export const tooFewCollapsed = () => null;
export const retestReasons = () => [];
export const retestLines = () => [];
export const catchHow = () => null;

const isCheckLine = (s) => s === F.V_NO || s.startsWith('This gap is distinguishable') || s.startsWith('Not enough trades to tell') || s.startsWith('Not tested');

export function habitLines(h, report, fmt) {
  F.checkReport(report);
  if (!F.SENTENCE_HABITS.includes(h.id)) return { what: [], check: [] };
  const lines = F.habitSentences(h, report, fmt).filter((s) => s !== F.V_LAUNCH && s !== F.V_LAUNCH_SIZE);
  const out = { what: [], check: [] };
  for (const s of lines) (isCheckLine(s) && !factsOnly(h) ? out.check : out.what).push(shown(s));
  return out;
}

export const page1Lines = (report, fmt) => F.page1Lines(report, fmt).map(shown);
export function coverageLines(report) {
  const c = F.coverageLines(report);
  const out = [c[0]];
  if (c[1] && c[1].startsWith('Not tested: ')) out.push('No check against chance: ' + c[1].slice('Not tested: '.length));
  return out;
}
export const mergedLine = F.mergedLine;
// The method line as the 9d4bdde page showed it: the frozen method sentence, then the p-values.
export function methodLine(h, fmt, report) {
  const m = factsOnly(h) ? null : F.methodLine(h, fmt);
  if (!m || h.p_raw === null || h.p_holm === null) return null;
  return `${m} On past data: p = ${h.p_raw.toPrecision(3)}, or ${h.p_holm.toPrecision(3)} after adjusting for the ${report.n_tested} pattern${report.n_tested === 1 ? '' : 's'} tested (Holm).`;
}
export const expertLine = () => null;
