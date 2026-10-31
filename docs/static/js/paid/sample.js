// sample.js — /sample-report/ in paid builds (delivery plan C-12 final): renders the committed sample report
// (a real analyse() output, embedded by the build) with the report page's own renderer, in static mode.
// S4: the build also embeds the committed trade file the sample report was made from
// (tests/fixtures/paid/sample-report.csv); it is read here by the same engine as the report page, so the
// facts and the rule check are worked out exactly as for a buyer's file.
import { renderReport } from './report.js?v=a069a31f';
import { runFile } from '../engine/index.js?v=8410d06a';

const data = document.getElementById('sample-data');
const out = document.getElementById('sample-out');
function sampleTrades() {
  const n = document.getElementById('sample-trades');
  if (!n) return null;
  const parsed = runFile(new TextEncoder().encode(n.textContent));
  return parsed.error ? null : parsed.result;
}
if (data && out) {
  const r = sampleTrades();
  renderReport(JSON.parse(data.textContent), out, { sample: true, trades: r ? r.trades : null, format: r ? r.format : null });
}
