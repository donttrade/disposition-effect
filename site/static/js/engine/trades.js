// trades.js — executions → closed round trips, and the ParseResult tail
// (warnings, currency groups, ordering, ids). Mirrors build_trades(),
// roundtrip_trades(), roundtrip_executions() and the end of parse_file() in
// tests/reference/engine_ref.py, operation for operation, so the floats match.
//
// Trade definition (fixed by the plan): flat to flat per symbol. A fill that
// crosses zero closes the trade at that time and opens the opposite trade with
// the remainder. Positions still open at the end of the file are left out.

import { fail, warning } from './errors.js';
import { spansDstNight } from './csv.js';

const UNIT = 1e8; // positions tracked in 1e-8 lots, so 0.1 + 0.2 - 0.3 is exactly flat

function roundHalfAway(x) {
  return Math.floor(Math.abs(x) + 0.5) * (x >= 0 ? 1 : -1);
}

function newTrade(e, dir, seq) {
  return { symbol: e.symbol, dir, open_ts: e.ts, close_ts: null, peak: 0, entry_qty: 0, entry_not: 0,
    exit_qty: 0, exit_not: 0, fees: 0, credit: 0, rep_sum: 0, rep_missing: false, fills: 0, multiplier: e.multiplier,
    currency: e.currency, unit: e._unit, fx: null, seq };
}

// ---------------------------------------------------------------- positions opened before the file
// An export whose date range starts mid-position holds closing fills for lots bought (or
// sold short) before the file. Formats with open/close codes (IBKR O/C, MT5 in/out) say
// which fills close something, so those lots can be found; files without codes cannot
// show them and are unaffected (a leading sell there is a short, as the plan says).
//
// lotWalk keeps, per direction (long, short), the units opened IN THE FILE and not yet
// closed. A close bigger than that closes a lot from before the file ("excess"). The
// plan's trade runs flat to flat, and the real position was not flat from the start of
// the file until that close, so every fill from the start of the file through the LAST
// such close is left out: in-file adds, partial closes and any trade that seemed to
// finish inside it (Tester F-B1: a carried long + an add + two closes made a 1-day trade
// carrying the older lot's FIFO P&L). One count per symbol and direction goes to
// W_OPEN_AT_START.
//
// A netting account (IBKR; MT5 netting) has one position per symbol, so what is left out
// is a stretch of the symbol's timeline from the start of the file to a fill after which
// the count is flat: the fills after it start from flat. An MT5 hedging account keeps long
// and short legs apart; a symbol shows it when a leg opens, or a pre-file lot closes,
// while the other direction is open in the file. There only the fills of the pre-file
// lot's direction are left out and the other legs are kept (W_HEDGING).
//
// A reversal fill (both codes: IBKR "C;O", MT5 "in/out") closes the whole position and
// opens the other way with the rest. Two cases cannot be read from the file, and nothing
// is guessed (Tester F-D2):
//   * The file opened nothing for it to close: it closes a pre-file lot of unknown size,
//     so the new position's size is unknown too ("unknown lot"). It is left out through
//     the next close the file did not open in its direction (any later such close extends
//     what is left out, as for a pre-file lot), or to the end of the file.
//   * The file opened less than the reversal really closed (a pre-file lot plus in-file
//     adds): the new position then looks bigger than it is. That shows later, when a fill
//     opens the first direction again while the new one still looks open, which a netting
//     account cannot do; everything up to that fill is left out.
// Both count in W_AMBIGUOUS_FILLS.
//
// Convention, stated: the file is read as if nothing was open before it unless the file
// itself shows otherwise (a close it did not open, or the contradiction above). A pre-file
// lot that the file only adds to and then closes with a reversal, with nothing later that
// contradicts the count, cannot be seen by any reader of the file alone.

const LONG = 0;
const SHORT = 1;

// What one fill does to the lots: 'open', 'close', 'reverse' (both codes) or 'net' (no
// code: closes the other direction first, like the netting walk).
function lotKind(e) {
  if (e.oc === 'open') return 'open';
  if (e.oc === 'close') return 'close';
  return e._rev ? 'reverse' : 'net';
}

// One symbol's fills (execution indexes, in walk order) →
// {excluded: Set, carried: [long, short], ambiguous, hedges}.
// allowHedging: the format can hold hedged legs (MT5). hedges counts pre-file lots closed
// while the other direction was open in the file (W_HEDGING).
function lotWalk(execs, list, allowHedging) {
  const inv = [0, 0];
  const spans = [[], []];       // per direction: [first, last] positions in `list` to leave out
  const unknownFrom = [-1, -1]; // per direction: where an unknown lot opened, or -1
  const revAt = [-1, -1];       // per direction: the reversal that opened the in-file lot, or -1
  const carried = [false, false];
  const flat = new Array(list.length).fill(true); // the count is flat after fill i
  let ambiguous = false;
  let hedged = false;
  let hedges = 0;
  let signs = 0; // fills that show something open before the file (or a reversal too big)
  const excess = (d, i) => {
    signs++;
    if (unknownFrom[d] >= 0) { spans[d].push([unknownFrom[d], i]); unknownFrom[d] = -1; }
    else {
      spans[d].push([0, i]);
      carried[d] = true;
      if (allowHedging && inv[1 - d] > 0) { hedged = true; hedges++; }
    }
    inv[d] = 0;
    revAt[d] = -1;
  };
  for (let i = 0; i < list.length; i++) {
    const e = execs[list[i]];
    const q = roundHalfAway(e.qty * UNIT);
    if (q === 0) { flat[i] = i === 0 || flat[i - 1]; continue; }
    const opens = e.side === 'buy' ? LONG : SHORT;
    const closes = 1 - opens;
    const kind = lotKind(e);
    if (kind === 'open' && (inv[closes] > 0 || unknownFrom[closes] >= 0)) {
      if (revAt[closes] >= 0 || unknownFrom[closes] >= 0) {
        // A netting account cannot open this way while the other way is open: the lot a
        // reversal opened was smaller than the count says, and ended before this fill.
        spans[opens].push([0, i - 1]);
        spans[closes].push([0, i - 1]);
        if (revAt[closes] >= 0) carried[opens] = true;
        signs++;
        inv[closes] = 0;
        revAt[closes] = -1;
        unknownFrom[closes] = -1;
        ambiguous = true;
      } else if (allowHedging) hedged = true;
    }
    if (kind === 'open') inv[opens] += q;
    else if (kind === 'close') {
      if (q <= inv[closes]) {
        inv[closes] -= q;
        if (inv[closes] === 0) revAt[closes] = -1;
      } else excess(closes, i);
    } else if (kind === 'reverse' && inv[closes] === 0) {
      excess(closes, i);
      if (unknownFrom[opens] < 0) unknownFrom[opens] = i;
      ambiguous = true;
    } else {
      const c = Math.min(q, inv[closes]);
      inv[closes] -= c;
      if (inv[closes] === 0) revAt[closes] = -1;
      if (kind === 'reverse' && q > c && inv[opens] === 0) revAt[opens] = i;
      inv[opens] += q - c;
    }
    // An unknown lot never makes the count flat: its size is not known.
    flat[i] = inv[LONG] === 0 && inv[SHORT] === 0 && unknownFrom[LONG] < 0 && unknownFrom[SHORT] < 0;
  }
  for (const d of [LONG, SHORT]) if (unknownFrom[d] >= 0) ambiguous = true;
  const excluded = new Set();
  if (hedged) {
    // Hedging legs: only the fills of the pre-file lot's own direction.
    for (const d of [LONG, SHORT]) {
      if (unknownFrom[d] >= 0) spans[d].push([unknownFrom[d], list.length - 1]);
    }
    for (let i = 0; i < list.length; i++) {
      const e = execs[list[i]];
      const opens = e.side === 'buy' ? LONG : SHORT;
      const kind = lotKind(e);
      for (const d of [LONG, SHORT]) {
        const touches = kind === 'open' ? opens === d : kind === 'close' ? opens !== d : true;
        if (touches && spans[d].some(([a, b]) => i >= a && i <= b)) excluded.add(list[i]);
      }
    }
  } else {
    // Netting: from the start of the file to the first flat count at or after the last
    // span (an unknown lot still open runs to the end of the file).
    let last = -1;
    for (const d of [LONG, SHORT]) for (const [, b] of spans[d]) last = Math.max(last, b);
    if (last >= 0) {
      while (last < list.length - 1 && !flat[last]) last++;
      for (let i = 0; i <= last; i++) excluded.add(list[i]);
    }
  }
  return { excluded, carried, ambiguous, hedges, signs };
}

// All symbols, in one walk order → {excluded: Set of execution indexes, openAtStart,
// ambiguousSyms: Set, hedges, signs: Map symbol → n}. openAtStart: symbol-directions with
// a lot from before the file.
export function preFileLots(execs, order, allowHedging) {
  const bySym = new Map();
  for (const k of order) {
    const sym = execs[k].symbol;
    if (!bySym.has(sym)) bySym.set(sym, []);
    bySym.get(sym).push(k);
  }
  const excluded = new Set();
  const ambiguousSyms = new Set();
  const signs = new Map();
  let openAtStart = 0;
  let hedges = 0;
  for (const [sym, list] of bySym) {
    const w = lotWalk(execs, list, allowHedging);
    for (const k of w.excluded) excluded.add(k);
    for (const c of w.carried) if (c) openAtStart++;
    if (w.ambiguous) ambiguousSyms.add(sym);
    hedges += w.hedges;
    signs.set(sym, w.signs);
  }
  return { excluded, openAtStart, ambiguousSyms, hedges, signs };
}

// The netting walk (flat to flat per symbol) over `order`, skipping `excluded`.
function nettingWalk(execs, order, excluded, detectHedging) {
  const pos = new Map();
  const cur = new Map();
  const done = [];
  let hedging = 0;
  let seq = 0;
  for (const k of order) {
    if (excluded.has(k)) continue;
    const e = execs[k];
    const sym = e.symbol;
    const s = e.side === 'buy' ? 1 : -1;
    const qUnits = roundHalfAway(e.qty * UNIT);
    if (qUnits === 0) continue;
    let p = pos.has(sym) ? pos.get(sym) : 0;
    if (detectHedging && e.oc === 'open' && p !== 0 && (p > 0) !== (s > 0)) hedging++;
    if (p === 0 || (p > 0) === (s > 0)) {
      if (p === 0) { cur.set(sym, newTrade(e, s > 0 ? 'long' : 'short', seq)); seq++; }
      const t = cur.get(sym);
      t.entry_qty += e.qty;
      t.entry_not += e.qty * e.price;
      t.fees += e.fee;
      if (e._credit) t.credit += e._credit;
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
    const closeUnits = Math.min(qUnits, Math.abs(p));
    const remUnits = qUnits - closeUnits;
    let cq, cf;
    if (remUnits === 0) { cq = e.qty; cf = e.fee; }
    else { cq = closeUnits / UNIT; cf = e.fee * closeUnits / qUnits; }
    t.exit_qty += cq;
    t.exit_not += cq * e.price;
    t.fees += cf;
    if (e._credit) t.credit += remUnits === 0 ? e._credit : e._credit * closeUnits / qUnits;
    t.fills += 1;
    if (e.pnl_reported === null) t.rep_missing = true;
    else t.rep_sum += e.pnl_reported;
    if (e._fx !== null) t.fx = e._fx;
    p += s * closeUnits;
    if (p === 0) { t.close_ts = e.ts; done.push(t); cur.delete(sym); }
    if (remUnits) {
      const nt = newTrade(e, s > 0 ? 'long' : 'short', seq);
      seq++;
      const rq = remUnits / UNIT;
      nt.entry_qty += rq;
      nt.entry_not += rq * e.price;
      nt.fees += e.fee * remUnits / qUnits;
      if (e._credit) nt.credit += e._credit * remUnits / qUnits;
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
  return { done, openN, hedging };
}

// Fills of one symbol with the same time to the second have no order in the file. When
// that order changes the trades (Tester F-D2: a carried close and a new open in one second
// made a 0-second trade), nothing is guessed: the file is also read with same-second
// closes first and with opens first. A reading that needs more signs of a pre-file lot
// than another is not a fair reading of the file (it would close something the file never
// opened), so per symbol only the readings with the fewest signs count. The file-order
// trades all of them agree on are kept; if the file order is not among them, none are.
// A symbol that loses trades this way counts in W_AMBIGUOUS_FILLS, and its fills are left
// out of `executions` too (PGR/PLR).
const TIE_RANK = { close: 0, reverse: 1, net: 1, open: 2 };

function tieOrder(execs, order, opensFirst) {
  const sign = opensFirst ? -1 : 1;
  return order.slice().sort((a, b) => (execs[a].ts - execs[b].ts) ||
    sign * (TIE_RANK[lotKind(execs[a])] - TIE_RANK[lotKind(execs[b])]));
}

function sameOrder(a, b) {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

// Everything that defines a finished trade, rounded so two summation orders compare equal.
function tradeKey(t) {
  const r = (x) => Math.floor(x * 1e6 + 0.5);
  return [t.symbol, t.dir, t.open_ts, t.close_ts, t.peak, t.fills, r(t.entry_qty), r(t.entry_not), r(t.exit_qty),
    r(t.exit_not), r(t.fees), r(t.credit), r(t.rep_sum), t.rep_missing].join('\u0001');
}

// reportedMode: null (compute P&L) | 'gross' (reported profit before fees, MetaTrader)
//             | 'net' (reported P&L after fees, IBKR realized P&L)
export function buildTrades(execs, reportedMode, detectHedging) {
  const order = chronoOrder(execs);
  const lots = preFileLots(execs, order, detectHedging);
  const walk = nettingWalk(execs, order, lots.excluded, detectHedging);
  let done = walk.done;
  const excluded = new Set(lots.excluded);
  const ambiguousSyms = new Set(lots.ambiguousSyms);
  const others = [];
  for (const o of [tieOrder(execs, order, false), tieOrder(execs, order, true)]) {
    if (sameOrder(o, order) || others.some((x) => sameOrder(o, x.order))) continue;
    const l = preFileLots(execs, o, detectHedging);
    others.push({ order: o, lots: l, done: nettingWalk(execs, o, l.excluded, detectHedging).done });
  }
  if (others.length) {
    const keysOf = (list) => {
      const m = new Map();
      for (const t of list) {
        if (!m.has(t.symbol)) m.set(t.symbol, new Set());
        m.get(t.symbol).add(tradeKey(t));
      }
      return m;
    };
    const mine = keysOf(done);
    for (const x of others) x.keys = keysOf(x.done);
    const none = new Set();
    const lost = new Set();   // symbols whose fair readings do not agree
    const dropAll = new Set(); // symbols where the file order is not a fair reading
    const fairOf = new Map();
    for (const sym of lots.signs.keys()) {
      const fewest = Math.min(lots.signs.get(sym), ...others.map((x) => x.lots.signs.get(sym)));
      const fair = others.filter((x) => x.lots.signs.get(sym) === fewest);
      fairOf.set(sym, fair);
      for (const x of fair) {
        for (const k of x.order) if (execs[k].symbol === sym && x.lots.excluded.has(k)) excluded.add(k);
      }
      if (lots.signs.get(sym) > fewest) { lost.add(sym); dropAll.add(sym); continue; }
      const a = mine.get(sym) || none;
      for (const x of fair) {
        const b = x.keys.get(sym) || none;
        if (a.size !== b.size || [...a].some((key) => !b.has(key))) lost.add(sym);
      }
    }
    if (lost.size) {
      done = done.filter((t) => !lost.has(t.symbol) || (!dropAll.has(t.symbol) &&
        fairOf.get(t.symbol).every((x) => (x.keys.get(t.symbol) || none).has(tradeKey(t)))));
      for (const sym of lost) ambiguousSyms.add(sym);
      execs.forEach((e, k) => { if (lost.has(e.symbol)) excluded.add(k); });
    }
  }
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
      // A commission rebate (TradingView: a negative Commission) is a credit, not a negative fee:
      // fees stay >= 0 and the credit is part of the gross result, as mt.js does for a net credit.
      if (t.credit) gross += t.credit;
      pnl = gross - t.fees;
    }
    return { symbol: t.symbol, dir: t.dir, open_ts: t.open_ts, close_ts: t.close_ts,
      hold_s: Math.floor((t.close_ts - t.open_ts) / 1000), qty: t.peak / UNIT, entry_vwap: entryVwap,
      exit_vwap: exitVwap, pnl, pnl_gross: gross, fees: t.fees, pnl_source: src, pnl_unit: t.unit,
      fills_n: t.fills, currency: t.currency, _fx: t.fx, _seq: t.seq };
  });
  return { trades, openN: walk.openN, hedging: (detectHedging ? lots.hedges : 0) + walk.hedging,
    openAtStart: lots.openAtStart, ambiguous: ambiguousSyms.size, excluded };
}

// Execution indexes in time order. Fills with the same time keep their file order,
// read in the file's own direction: in a newest-first file (times mostly falling down
// the rows) same-second fills are newest first too, so they are taken bottom-up
// (Tester D7: a buy and a sell in one second came out as a short).
export function chronoOrder(execs) {
  let up = 0;
  let down = 0;
  for (let k = 1; k < execs.length; k++) {
    const d = execs[k].ts - execs[k - 1].ts;
    if (d > 0) up++; else if (d < 0) down++;
  }
  const dir = down > up ? -1 : 1;
  const order = execs.map((_, k) => k);
  order.sort((a, b) => (execs[a].ts - execs[b].ts) || dir * (execs[a].row - execs[b].row) || dir * (a - b));
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
      currency: r.currency, _fx: null, _seq: startSeq + i, _reordered: r.reordered === true };
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

// Why nothing closed, from what the file did contain (Tester D8: the old message always
// said "every position is still open", even when the real cause was skipped rows).
function noTradesReason(openN, openAtStart, ambiguous, skipped) {
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const parts = [];
  let nSkipped = 0;
  for (const k of Object.keys(skipped)) nSkipped += skipped[k];
  if (nSkipped) {
    const why = Object.keys(skipped).map((k) => `${k.replace(/_/g, ' ')}: ${skipped[k]}`).join(', ');
    parts.push(`${plural(nSkipped, 'row was', 'rows were')} skipped (${why}), so a position may never return to flat`);
  }
  if (openN) parts.push(`${plural(openN, 'position is', 'positions are')} still open at the end of the file`);
  if (openAtStart) parts.push(`${plural(openAtStart, 'position was', 'positions were')} already open when the file starts`);
  if (ambiguous) parts.push(`${plural(ambiguous, 'symbol has', 'symbols have')} fills whose order or split the file does not show`);
  if (!parts.length) return 'The file has no buy and sell that open and close a position.';
  return parts.join('; ') + '.';
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
  if (extra.duplicate_rows) warnings.push(warning('W_DUPLICATE_ROWS', extra.duplicate_rows, `${extra.duplicate_rows} found.`));
  if (extra.currency_ignored) warnings.push(warning('W_CURRENCY_IGNORED', 0));
  let executions = res.executions;
  let openN = extra.open_positions || 0;
  let hedging = 0;
  let openAtStart = 0;
  let ambiguous = 0;
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
    ambiguous = b.ambiguous;
    // Fills of positions opened before the file are left out of every later step (PGR/PLR too).
    if (b.excluded.size) executions = executions.filter((_, k) => !b.excluded.has(k));
  }
  if (hedging) warnings.push(warning('W_HEDGING', hedging));
  if (openN) warnings.push(warning('W_OPEN_POSITIONS', openN, `${openN} left out.`));
  if (openAtStart) warnings.push(warning('W_OPEN_AT_START', openAtStart, `${openAtStart} left out.`));
  if (ambiguous) warnings.push(warning('W_AMBIGUOUS_FILLS', ambiguous, `${ambiguous} ${ambiguous === 1 ? 'symbol' : 'symbols'} affected.`));
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
  let dst = 0;
  for (const t of trades) if (spansDstNight(t.open_ts, t.close_ts)) dst++;
  if (dst) warnings.push(warning('W_DST', dst, `${dst} found.`));
  let reordered = 0;
  for (const t of trades) if (t._reordered) reordered++;
  if (reordered) warnings.push(warning('W_CLOSE_BEFORE_OPEN', reordered, `${reordered} found.`));
  trades.sort((a, b) => (a.close_ts - b.close_ts) || (a.open_ts - b.open_ts) || cmpStr(a.symbol, b.symbol) || (a._seq - b._seq));
  if (!trades.length) fail('E_NO_CLOSED_TRADES', noTradesReason(openN, openAtStart, ambiguous, skipped));
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
