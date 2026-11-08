// Runs site/static/js/check-core.js and paid/strip.js for tests/test_check_core.py. Prints JSON; writes nothing.
//   node check_core_run.mjs fixtures   -> {name: countTrades(trades)} for every trade list in fixtures/check_parity/make_inputs.mjs
//   node check_core_run.mjs strip      -> {"name perm": sha256 of JSON.stringify(await stripRows(trades, "SALT-C1", perm))}
//   node check_core_run.mjs torows     -> {name: {keys, same_as_strip, n}}: toRows rows against stripRows rows without f
//   node check_core_run.mjs rows       < {cases: [rows, ...]}  -> [countRows(rows), ...]
//   node check_core_run.mjs exports    -> the module's export names
//   node check_core_run.mjs csv        -> {name: the fixture's trades as a one-row-per-round-trip CSV the page can read}
import crypto from 'node:crypto';
import * as core from '../../site/static/js/check-core.js';
import { stripRows, toRows } from '../../site/static/js/paid/strip.js';
import { buildFixtures } from '../fixtures/check_parity/make_inputs.mjs';

const idp = (n) => Array.from({ length: n }, (_, i) => i);
const perms = { id: idp, rev: (n) => idp(n).reverse() };
const mode = process.argv[2];
const out = {};
if (mode === 'fixtures') {
  for (const [name, trades] of Object.entries(buildFixtures())) out[name] = core.countTrades(trades);
} else if (mode === 'strip') {
  for (const [name, trades] of Object.entries(buildFixtures())) {
    for (const [pn, perm] of Object.entries(perms)) {
      const r = await stripRows(trades, 'SALT-C1', perm);
      out[name + ' ' + pn] = crypto.createHash('sha256').update(JSON.stringify(r)).digest('hex');
    }
  }
} else if (mode === 'torows') {
  for (const [name, trades] of Object.entries(buildFixtures())) {
    const a = toRows(trades, perms.rev);
    const b = await stripRows(trades, 'SALT-C1', perms.rev);
    const dropF = b.rows.map(({ f, ...rest }) => rest);
    out[name] = { keys: [...new Set(a.rows.flatMap((r) => Object.keys(r)))].sort(), same_as_strip: JSON.stringify(a.rows) === JSON.stringify(dropF),
      n: a.rows.length, key_order: Object.keys(a.rows[0]).join('') };
  }
} else if (mode === 'csv') {
  // Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees; the close price is set so (close - open) x qty = pnl.
  const stamp = (ms) => new Date(ms).toISOString().slice(0, 19).replace('T', ' ');
  for (const [name, trades] of Object.entries(buildFixtures())) {
    const lines = ['Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees'];
    for (const t of trades) {
      const long = t.dir === 'long';
      const close = 1000 + (long ? 1 : -1) * (t.pnl / t.qty);
      lines.push([stamp(t.open_ts), stamp(t.close_ts), t.symbol, long ? 'Long' : 'Short', t.qty, 1000, close, 0].join(','));
    }
    out[name] = lines.join('\n') + '\n';
  }
} else if (mode === 'exports') {
  out.names = Object.keys(core).sort();
  out.types = Object.fromEntries(Object.entries(core).map(([k, v]) => [k, typeof v]));
} else if (mode === 'rows') {
  let s = '';
  for await (const d of process.stdin) s += d;
  process.stdout.write(JSON.stringify(JSON.parse(s).cases.map((rows) => core.countRows(rows))));
  process.exit(0);
}
process.stdout.write(JSON.stringify(out));
