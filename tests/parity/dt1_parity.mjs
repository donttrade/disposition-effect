// dt1_parity.mjs: runs the PRIVATE engine (habits.mjs analyse) on every window of a corpus and prints its
// habit numbers as JSON on stdout. Read-only: it imports habits.mjs by path and writes no file.
// Usage (Claude Code or plain Terminal): node tests/parity/dt1_parity.mjs <path to habits.mjs> <corpus.json>
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const [enginePath, corpusPath] = process.argv.slice(2);
const { analyse, METHOD_VERSION } = await import(pathToFileURL(enginePath).href);
const corpus = JSON.parse(readFileSync(corpusPath, 'utf8'));
const out = { method_version: METHOD_VERSION, windows: [] };
for (const w of corpus.windows) {
  const rep = analyse({ rows: w.rows, currency: 'USD' }, 'parity', { nPerm: 1 });
  const habits = {};
  for (const h of rep.habits) {
    habits[h.id] = { n_a: h.n_a, n_b: h.n_b, measure_a: h.measure_a, measure_b: h.measure_b, effect: h.effect,
      dollars_n_trades: h.dollars === null ? null : h.dollars.n_trades };
  }
  out.windows.push({ id: w.id, n_trades: rep.n_trades, dates_only: rep.dates_only, habits });
}
process.stdout.write(JSON.stringify(out));
