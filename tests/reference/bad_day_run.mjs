// Runs site/static/js/tools/bad-day-core.js on {trades, shiftHours, requested} read from stdin; prints the result as JSON.
import { badDay } from '../../site/static/js/tools/bad-day-core.js';
let s = '';
process.stdin.on('data', (d) => { s += d; });
process.stdin.on('end', () => {
  const inp = JSON.parse(s);
  const out = inp.cases.map((c) => badDay(c.trades, { shiftHours: c.shiftHours, requested: c.requested }));
  process.stdout.write(JSON.stringify(out));
});
