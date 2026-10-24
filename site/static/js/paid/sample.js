// sample.js — /sample-report/ in paid builds (delivery plan C-12 final): renders the committed sample report
// (a real analyse() output, embedded by the build) with the report page's own renderer, in static mode.
import { renderReport } from './report.js';

const data = document.getElementById('sample-data');
const out = document.getElementById('sample-out');
if (data && out) renderReport(JSON.parse(data.textContent), out, { sample: true });
