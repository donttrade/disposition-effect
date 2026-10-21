// trades.js — executions → closed round trips, and the ParseResult tail
// (warnings, currency groups, ordering, ids). Mirrors build_trades(),
// roundtrip_trades(), roundtrip_executions() and the end of parse_file() in
// tests/reference/engine_ref.py, operation for operation, so the floats match.
//
// Trade definition (fixed by the plan): flat to flat per symbol. A fill that
// crosses zero closes the trade at that time and opens the opposite trade with
// the remainder. Positions still open at the end of the file are left out.

import { fail, warning } from './errors.js';

const UNIT = 1e8; // positions tracked in 1e-8 lots, so 0.1 + 0.2 - 0.3 is exactly flat

function roundHalfAway(x) {
  return Math.floor(Math.abs(x) + 0.5) * (x >= 0 ? 1 : -1);
}

function newTrade(e, dir, seq) {
  return { symbol: e.symbol, dir, open_ts: e.ts, close_ts: null, peak: 0, entry_qty: 0, entry_not: 0,
    exit_qty: 0, exit_not: 0, fees: 0, rep_sum: 0, rep_missing: false, fills: 0, multiplier: e.multiplier,
    currency: e.currency, unit: e._unit, fx: null, seq, ks: [], by_reversal: false };
}

// reportedMode: null (compute P&L) | 'gross' (reported profit before fees, MetaTrader)
//             | 'net' (reported P&L after fees, IBKR realized P&L)
//
// Positions opened before the file starts (an export whose date range begins
// mid-position). Formats with open/close codes (IBKR O/C, MT5 in/out) say which
// fills close a position. `inv` counts, per symbol, the units opened in this file
// and not yet closed, direction-blind so hedged legs count too. A closing fill
// bigger than `inv` closes something opened before the file: that fill, and any
// trade in progress on the symbol (it was never flat since before the file), are
// left out and counted once per position in openAtStart (W_OPEN_AT_START). They
// are never turned into an opposite trade. Files without codes are unaffected.
export function buildTrades(execs, reportedMode, detectHedging) {
  const order = chronoOrder(execs);
  const pos = new Map();
  const cur = new Map();
  const inv = new Map();
  const carried = new Map();
  const done = [];
  const excluded = new Set(); // execution indexes left out as part of a pre-file position
  let hedging = 0;
  let openAtStart = 0;
  let seq = 0;
  for (const k of order) {
    const e = execs[k];
    const sym = e.symbol;
    const s = e.side === 'buy' ? 1 : -1;
    const qUnits = roundHalfAway(e.qty * UNIT);
    if (qUnits === 0) continue;
    let p = pos.has(sym) ? pos.get(sym) : 0;
    const have = inv.has(sym) ? inv.get(sym) : 0;
    if (e.oc === 'close') {
      if (qUnits > have) {
        if (!carried.get(sym)) { openAtStart++; carried.set(sym, true); }
        excluded.add(k);
        if (cur.has(sym)) {
          const t = cur.get(sym);
          // A fill that reversed into this trade also closed a finished trade: keep it.
          for (const j of t.by_reversal ? t.ks.slice(1) : t.ks) excluded.add(j);
        }
        cur.delete(sym);
        pos.set(sym, 0);
        inv.set(sym, 0);
        continue;
      }
      inv.set(sym, have - qUnits);
    } else if (e.oc === 'open') {
      inv.set(sym, have + qUnits);
      carried.set(sym, false);
    } else {
      // No code, or both codes (a reversal): the netting walk decides what closes.
      const closing = p !== 0 && (p > 0) !== (s > 0) ? Math.min(qUnits, Math.abs(p)) : 0;
      inv.set(sym, Math.max(0, have - closing) + (qUnits - closing));
    }
    if (detectHedging && e.oc === 'open' && p !== 0 && (p > 0) !== (s > 0)) hedging++;
    if (p === 0 || (p > 0) === (s > 0)) {
      if (p === 0) { cur.set(sym, newTrade(e, s > 0 ? 'long' : 'short', seq)); seq++; }
      const t = cur.get(sym);
      t.ks.push(k);
      t.entry_qty += e.qty;
      t.entry_not += e.qty * e.price;
      t.fees += e.fee;
      t.fills += 1;
      if (e.pnl_reported !== null) t.rep_sum += e.pnl_reported;
      p += s * qUnits;
      t.peak = Math.max(t.peak, Math.abs(p));
      if (e._fx !== null) t.fx = e._fx;
      pos.set(sym, p);
      continue;
    }
    // Reducing: close part (and reverse with any remainder).
    const t = cur.get(sym);
    t.ks.push(k);
    const closeUnits = Math.min(qUnits, Math.abs(p));
    const remUnits = qUnits - closeUnits;
    let cq, cf;
    if (remUnits === 0) { cq = e.qty; cf = e.fee; }
    else { cq = closeUnits / UNIT; cf = e.fee * closeUnits / qUnits; }
    t.exit_qty += cq;
    t.exit_not += cq * e.price;
    t.fees += cf;
    t.fills += 1;
    if (e.pnl_reported === null) t.rep_missing = true;
    else t.rep_sum += e.pnl_reported;
    if (e._fx !== null) t.fx = e._fx;
    p += s * closeUnits;
    if (p === 0) { t.close_ts = e.ts; done.push(t); cur.delete(sym); }
    if (remUnits) {
      const nt = newTrade(e, s > 0 ? 'long' : 'short', seq);
      seq++;
      nt.ks.push(k);
      nt.by_reversal = true;
      const rq = remUnits / UNIT;
      nt.entry_qty += rq;
      nt.entry_not += rq * e.price;
      nt.fees += e.fee * remUnits / qUnits;
      nt.fills += 1;
      nt.peak = remUnits;
      if (e._fx !== null) nt.fx = e._fx;
      cur.set(sym, nt);
      p = s * remUnits;
    }
    pos.set(sym, p);
  }
  let openN = 0;
  for (const v of pos.values()) if (v !== 0) openN++;
  const trades = done.map((t) => {
    const entryVwap = t.entry_not / t.entry_qty;
    const exitVwap = t.exit_not / t.exit_qty;
    const sign = t.dir === 'long' ? 1 : -1;
    let src, gross, pnl;
    if (reportedMode !== null && !t.rep_missing) {
      src = 'reported';
      if (reportedMode === 'gross') { gross = t.rep_sum; pnl = gross - t.fees; }
      else { pnl = t.rep_sum; gross = pnl + t.fees; }
    } else {
      src = 'computed';
      // Total traded quantity, not the peak: with adds after a partial exit the
      // peak understates the quantity that earned the price difference.
      gross = (exitVwap - entryVwap) * t.entry_qty * t.multiplier * sign;
      pnl = gross - t.fees;
    }
    return { symbol: t.symbol, dir: t.dir, open_ts: t.open_ts, close_ts: t.close_ts,
      hold_s: Math.floor((t.close_ts - t.open_ts) / 1000), qty: t.peak / UNIT, entry_vwap: entryVwap,
      exit_vwap: exitVwap, pnl, pnl_gross: gross, fees: t.fees, pnl_source: src, pnl_unit: t.unit,
      fills_n: t.fills, currency: t.currency, _fx: t.fx, _seq: t.seq };
  });
  return { trades, openN, hedging, openAtStart, excluded };
}

// Execution indexes in time order; same-time fills keep their file order.
export function chronoOrder(execs) {
  const order = execs.map((_, k) => k);
  order.sort((a, b) => (execs[a].ts - execs[b].ts) || (execs[a].row - execs[b].row) || (a - b));
  return order;
}

export function roundtripTrades(rts, startSeq) {
  return rts.map((r, i) => {
    const sign = r.dir === 'long' ? 1 : -1;
    let gross, src;
    if (r.reported) { gross = r.pnl_gross; src = 'reported'; }
    else { gross = (r.exit - r.entry) * r.qty * 1 * sign; src = 'computed'; }
    return { symbol: r.symbol, dir: r.dir, open_ts: r.open_ts, close_ts: r.close_ts,
      hold_s: Math.floor((r.close_ts - r.open_ts) / 1000), qty: r.qty, entry_vwap: r.entry, exit_vwap: r.exit,
      pnl: gross - r.fees, pnl_gross: gross, fees: r.fees, pnl_source: src, pnl_unit: r.unit, fills_n: 2,
      currency: r.currency, _fx: null, _seq: startSeq + i };
  });
}

export function roundtripExecutions(rts) {
  const out = [];
  for (const r of rts) {
    out.push({ row: r.row, ts: r.open_ts, symbol: r.symbol, side: r.dir === 'long' ? 'buy' : 'sell', qty: r.qty,
      price: r.entry, fee: 0, currency: r.currency, oc: 'open', pos_id: r.pos_id, pnl_reported: null, multiplier: 1 });
    out.push({ row: r.row, ts: r.close_ts, symbol: r.symbol, side: r.dir === 'long' ? 'sell' : 'buy', qty: r.qty,
      price: r.exit, fee: r.fees, currency: r.currency, oc: 'close', pos_id: r.pos_id, pnl_reported: r.pnl_gross,
      multiplier: 1 });
  }
  return out;
}

function strip(o) {
  const out = {};
  for (const [k, v] of Object.entries(o)) if (!k.startsWith('_')) out[k] = v;
  return out;
}

const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

// Everything after parsing: trades, warnings, currency groups, order, ids.
export function finish(fmt, verified, res, mode, tzLabel) {
  const extra = res.extra;
  const warnings = [];
  if (!verified) warnings.push(warning('W_UNVERIFIED_FORMAT', 0));
  const skipped = res.skipped;
  const skipKeys = Object.keys(skipped);
  if (skipKeys.length) {
    let n = 0;
    for (const k of skipKeys) n += skipped[k];
    warnings.push(warning('W_SKIPPED_ROWS', n, skipKeys.map((k) => `${k.replace(/_/g, ' ')}: ${skipped[k]}`).join(', ') + '.'));
  }
  let executions = res.executions;
  let openN = extra.open_positions || 0;
  let hedging = 0;
  let openAtStart = 0;
  let trades;
  if (fmt === 'mt5' && extra.has_closed_positions) {
    trades = roundtripTrades(res.roundtrips, 0);
  } else if (res.roundtrips.length) {
    trades = roundtripTrades(res.roundtrips, 0);
    executions = roundtripExecutions(res.roundtrips);
  } else {
    const b = buildTrades(executions, mode, fmt === 'mt5');
    trades = b.trades;
    openN += b.openN;
    hedging = b.hedging;
    openAtStart = b.openAtStart;
    // Fills of positions opened before the file are left out of every later step (PGR/PLR too).
    if (b.excluded.size) executions = executions.filter((_, k) => !b.excluded.has(k));
  }
  if (hedging) warnings.push(warning('W_HEDGING', hedging));
  if (openN) warnings.push(warning('W_OPEN_POSITIONS', openN, `${openN} left out.`));
  if (openAtStart) warnings.push(warning('W_OPEN_AT_START', openAtStart, `${openAtStart} left out.`));
  if (fmt === 'tradovate_orders') {
    let pts = 0;
    for (const t of trades) if (t.pnl_unit === 'points') pts++;
    if (pts) warnings.push(warning('W_POINTS_ONLY', pts));
  }

  const currencies = [];
  for (const t of trades) if (!currencies.includes(t.pnl_unit)) currencies.push(t.pnl_unit);
  if (currencies.length > 1 && trades.length && executions.every((e) => e._fx !== undefined && e._fx !== null) &&
      trades.every((t) => t._fx !== null)) {
    // An FX-to-base rate is on every row: convert each trade with its closing fill's rate.
    for (const t of trades) {
      const f = t._fx;
      t.pnl = t.pnl * f;
      t.pnl_gross = t.pnl_gross * f;
      t.fees = t.fees * f;
      t.pnl_unit = 'base';
      t.currency = 'base';
    }
    warnings.push(warning('W_MIXED_CURRENCY', 0, 'Every row had an FX rate, so results are in your base currency.'));
  }
  const groups = {};
  for (const t of trades) groups[t.pnl_unit] = (groups[t.pnl_unit] || 0) + 1;
  const keys = Object.keys(groups);
  if (keys.length > 1) {
    const keep = keys.slice().sort((a, b) => (groups[b] - groups[a]) || cmpStr(a, b))[0];
    const excluded = trades.length - groups[keep];
    trades = trades.filter((t) => t.pnl_unit === keep);
    warnings.push(warning('W_MIXED_CURRENCY', excluded, `Only the ${keep} trades are analysed; ${excluded} trades in other currencies were left out.`));
  }
  trades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || cmpStr(a.symbol, b.symbol) || (a._seq - b._seq));
  if (!trades.length) fail('E_NO_CLOSED_TRADES');
  return {
    format: fmt,
    verified_format: verified,
    executions: executions.map(strip),
    trades: trades.map((t, i) => Object.assign({ id: 't' + (i + 1) }, strip(t))),
    skipped,
    warnings,
    tz_label: tzLabel,
    currency_groups: groups,
  };
}
