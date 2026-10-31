// make_dt2_reports.mjs — DT-2 batch S1: the engine's own reports (dt-private analyse(), catch figures included) on dt-private's
// request fixtures, sorted keys. [Claude Code] node tests/fixtures/paid-reports-dt2/make_dt2_reports.mjs <dt-private> tests/fixtures/paid-reports-dt2
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
const PRIV = resolve(process.argv[2]), OUT = resolve(process.argv[3]);
const { analyse } = await import(pathToFileURL(PRIV + '/src/core/habits.mjs').href);
const FIX = PRIV + '/tests/fixtures/';
const list = (d) => readdirSync(FIX + d).filter((f) => f.endsWith('.json') && !f.startsWith('architect')).sort().map((f) => d + '/' + f.replace(/\.json$/, ''));
const names = ['planted', 'planted_revenge', 'too_few', 'random', ...list('stats'), ...list('stats-r2')];
const sortKeys = (v) => Array.isArray(v) ? v.map(sortKeys) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])])) : v;
for (const n of names) {
  const rep = analyse(JSON.parse(readFileSync(FIX + n + '.json', 'utf8')), 'golden');
  writeFileSync(OUT + '/' + n.replace('/', '__') + '.report.json', JSON.stringify(sortKeys(rep), null, 1) + '\n');
}
console.log(names.length, 'written');
