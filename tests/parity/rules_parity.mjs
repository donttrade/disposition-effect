// rules_parity.mjs: runs the Challenge Readiness engine (prop-sim-core.js simulate, sequence mode) on every
// sequence of a corpus and prints outcome, why, day and the bust position as JSON. Writes no file.
// Usage (Claude Code or plain Terminal): node tests/parity/rules_parity.mjs <path to prop-sim-core.js> <corpus.json>
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const [corePath, corpusPath] = process.argv.slice(2);
const { simulate } = await import(pathToFileURL(corePath).href);
const corpus = JSON.parse(readFileSync(corpusPath, 'utf8'));
const out = [];
for (const s of corpus.sequences) {
  const r = simulate({ mode: 'sequence', days: s.days, rules: s.rules });
  out.push({ id: s.id, outcome: r.outcome, why: r.why, day: r.day, bust_at: r.bust_at });
}
process.stdout.write(JSON.stringify(out));
