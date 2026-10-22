// journal/import.js: the import preview and write (ARCHITECT-V3 §d.4, J2). Nothing is written until the
// trader confirms. Exact repeats of trades already in the chosen account are skipped; a trade with the same
// symbol, side and times as an existing one but other numbers is a "possible duplicate", skipped by default
// (a double-counted day is the worse error for a P&L calendar) and listed so the trader can keep it.
// An account keeps one result unit (USD, EUR, points…): a file in another unit goes to another account.
import { looseStr } from './keys.js';
import { rid, addImport, LIMITS } from './store.js';

export function newAccount(parsed, name) {
  return { id: rid('a_'), name: name || 'Account', unit: parsed.pnl_unit, format: parsed.format, tz_label: parsed.tz_label,
    created: new Date().toISOString(), archived: false };
}

// state: loadAll() result; parsed: forJournal() result; account: an existing account or newAccount().
export function plan(state, parsed, account) {
  const out = { account, isNew: !state.accounts.some((a) => a.id === account.id), fresh: [], dupes: 0, possible: [],
    total: parsed.trades.length, problem: null, warning: null };
  if (!parsed.trades.length) { out.problem = 'This file has no closed trades to add.'; return out; }
  if (account.unit && parsed.pnl_unit && account.unit !== parsed.pnl_unit) {
    out.problem = `This account’s results are in ${account.unit} and this file’s are in ${parsed.pnl_unit}. Add it to another account.`;
    return out;
  }
  const mine = state.trades.filter((t) => t.account_id === account.id);
  const keys = new Set(mine.map((t) => t.k));
  const loose = new Map(mine.map((t) => [looseStr(t), t]));
  parsed.trades.forEach((t, i) => {
    const k = account.id + ':' + t.h;
    const { h, ...rest } = t;
    const trade = { ...rest, k };
    if (keys.has(k)) { out.dupes++; return; }
    const m = loose.get(looseStr(t));
    if (m) { out.possible.push({ i, trade, existing: m }); return; }
    keys.add(k);
    out.fresh.push(trade);
  });
  const after = state.trades.length + out.fresh.length;
  if (after > LIMITS.trades) {
    out.problem = `The journal holds at most ${LIMITS.trades.toLocaleString('en-US')} trades in this browser; this file would bring it to ${after.toLocaleString('en-US')}.`;
  } else if (after >= LIMITS.warn) {
    out.warning = 'Backups above this size get large (about 13 MB per 50,000 trades).';
  }
  return out;
}

// keep: indexes (plan.possible[].i) of possible duplicates the trader ticked to keep.
export async function commit(db, p, parsed, fileName, keep = []) {
  if (p.problem) throw new Error(p.problem);
  const kept = p.possible.filter((x) => keep.includes(x.i)).map((x) => x.trade);
  const trades = p.fresh.concat(kept);
  const iso = (ms) => (ms == null ? null : new Date(ms).toISOString().slice(0, 10));
  const imp = { id: rid('i_'), account_id: p.account.id, file_name: String(fileName || '').slice(0, 200),
    format: parsed.format, verified_format: parsed.verified_format, imported_at: new Date().toISOString(),
    n_trades_in_file: p.total, n_skipped_dupe: p.dupes, n_possible_dupe_kept: kept.length,
    n_possible_dupe_skipped: p.possible.length - kept.length,
    warnings: (parsed.warnings || []).map((w) => ({ code: w.code, count: w.count || 1 })),
    date_from: iso(parsed.date_from), date_to: iso(parsed.date_to) };
  await addImport(db, { account: p.isNew ? { ...p.account, unit: p.account.unit || parsed.pnl_unit } : null, imp, trades });
  return { imp, added: trades.length };
}
