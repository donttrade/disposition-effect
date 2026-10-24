// journal/keys.js: the stable content key of a trade (ARCHITECT-V3 D9, §d.2). The engine's ids (t1, t2…)
// are positions in one file, so they change between exports; the key is a hash of what the trade IS:
//   hash = cyrb53([symbol, dir, open_ts, close_ts, qty, entry, exit, pnl].join('|') + '#' + occurrence)
// where occurrence counts identical trades earlier in the SAME file: re-importing a file gives the same
// keys, and two identical trades inside one file stay two. The stored key is account_id + ':' + hash.
// 53 bits: about 2 in a million that any two of 200,000 trades collide; a collision is reported as a
// duplicate, so it is visible.

export function cyrb53(str, seed = 0) {
  let h1 = 0xdeadbeef ^ seed, h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < str.length; i++) {
    const ch = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

const f8 = (x) => Number(x).toFixed(8);
export function keyStr(t) {
  return [t.symbol, t.dir, t.open_ts, t.close_ts, f8(t.qty), f8(t.entry), f8(t.exit), Number(t.pnl).toFixed(2)].join('|');
}
// The "possible duplicate" signature: same symbol, side and times (§d.4).
export function looseStr(t) { return [t.symbol, t.dir, t.open_ts, t.close_ts].join('|'); }

// Hash part of each trade's key, in file order (account-independent: the account is chosen after parsing).
export function hashes(trades) {
  const seen = new Map();
  return trades.map((t) => {
    const s = keyStr(t);
    const n = seen.get(s) || 0;
    seen.set(s, n + 1);
    return cyrb53(s + '#' + n);
  });
}

// The engine's trade (trades.js finish()), whitelisted to what the journal keeps (§d.2).
export function journalTrade(t) {
  return { symbol: t.symbol, dir: t.dir, open_ts: t.open_ts, close_ts: t.close_ts, hold_s: t.hold_s, qty: t.qty,
    entry: t.entry_vwap, exit: t.exit_vwap, pnl: t.pnl, pnl_gross: t.pnl_gross, fees: t.fees, pnl_unit: t.pnl_unit,
    fills_n: t.fills_n };
}

// A parsed file → what the import preview needs. Shared by the worker and the on-page HTML path.
export function forJournal(r) {
  const trades = r.trades.map(journalTrade);
  const h = hashes(trades);
  trades.forEach((t, i) => { t.h = h[i]; });
  const ts = trades.map((t) => t.close_ts);
  return { format: r.format, verified_format: r.verified_format, tz_label: r.tz_label, warnings: r.warnings,
    skipped: r.skipped, pnl_unit: trades.length ? trades[0].pnl_unit : null, trades,
    date_from: ts.length ? Math.min(...ts) : null, date_to: ts.length ? Math.max(...ts) : null };
}
