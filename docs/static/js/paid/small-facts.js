// small-facts.js — batch S4, "Small-file facts and challenge check" (ARCHITECT-SMALL-FILES-ADDENDUM-2026-10-31
// Lever 7 and §3.1; ARCHITECT-BUNDLE-DONTTRADE-TEST-2026-10-31 B3 and §2.3, which S4 absorbs).
//
// Facts about the buyer's own file that need no statistics, so they are definite at any file size. Pure: no DOM,
// no I/O, no network. The report page computes them in the tab, on the trades it already parsed; nothing here is
// sent to the Worker (bundle plan §5).
//
//   fileFacts(trades)            net total, worst day, longest losing run, largest loss, the 3 largest losses' share
//   consistencyShare(dayTotals)  largest winning day ÷ total profit (the prop-firm "consistency" figure)
//   challengeCheck(trades, …)    the Readiness engine (prop-sim-core.js, sequence mode) on the firm's published rules
//                                (challenge-presets.js): the first breach in the real order (rule, day, trade), every
//                                day that reached the daily loss limit, habits on those days with their dollars
//                                (habit-flags.js), and the consistency share against the firm's own threshold.
//
// Conventions, the same in every fact:
//   * trades are taken in closing order (a stable sort on close_ts, as prop-sim-core groupDays); "trade 17" is the
//     17th trade to close, counted from 1;
//   * a loss is a trade with P&L below zero; a break-even trade is neither a win nor a loss and ends a losing run;
//   * ties go to the earliest (the first day, the first run, the first trade);
//   * "loss dollars" is the sum of all losing trades' P&L (a negative number); a share of it is between 0 and 1.

import { groupDays, simulate, NO_LIMIT_CAP } from '../tools/prop-sim-core.js?v=7c28de14';
import { presetRules, NOT_STATED, SCALED } from '../tools/challenge-presets.js?v=2e7fd947';
import { HABITS, BIT, itemsFromTrades, isDatesOnly, habitFlags, dayFlags, realBreachDays } from '../tools/habit-flags.js?v=72b76dd0';
import { MAX_ROWS, SPAN_WEEKS, MAX_HOLD_S } from './strip.js?v=0b3cbecc';

export const TOP_K = 3;

// Trades in closing order; each keeps its place in that order as `n` (1-based) and its own fields.
export function inCloseOrder(trades) {
  const ix = trades.map((t, i) => i).sort((a, b) => (trades[a].close_ts - trades[b].close_ts) || (a - b));
  return ix.map((i) => trades[i]);
}

// Days on the file's own clock (the UTC calendar day of the naive file time: prop-sim-core dayKey with no options).
function fileDays(sorted) {
  const g = groupDays(sorted, {});
  return g.days.map((d, j) => ({ key: g.keys[j], index: g.index[j], total: sum(d), n_trades: d.length,
    loss: d.reduce((s, x) => s + (x < 0 ? x : 0), 0) }));
}

const sum = (a) => a.reduce((s, x) => s + x, 0);

export function fileFacts(trades) {
  const t = inCloseOrder(trades);
  const pnl = t.map((x) => x.pnl);
  const n_win = pnl.filter((x) => x > 0).length;
  const n_loss = pnl.filter((x) => x < 0).length;
  const loss_total = pnl.reduce((s, x) => s + (x < 0 ? x : 0), 0);
  const win_total = pnl.reduce((s, x) => s + (x > 0 ? x : 0), 0);
  const out = { n: t.length, n_win, n_loss, n_flat: t.length - n_win - n_loss, net: sum(pnl), win_total, loss_total,
    worst_day: null, run: null, largest_loss: null, top: null };
  const days = fileDays(t);
  out.n_days = days.length;
  if (!n_loss) return out;

  // Worst day: the day with the lowest total, if any day ended below zero (ties: the first).
  let w = null;
  for (const d of days) if (d.total < 0 && (!w || d.total < w.total)) w = d;
  if (w) {
    const first = t[w.index[0]];
    out.worst_day = { key: w.key, date_ts: first.close_ts, total: w.total, n_trades: w.n_trades, loss: w.loss,
      loss_share: w.loss / loss_total };
  }

  // Longest losing run in closing order (ties: the first); what the next trade did; how many runs had that length.
  let best = null, start = -1, runs = [];
  for (let i = 0; i <= pnl.length; i++) {
    const loss = i < pnl.length && pnl[i] < 0;
    if (loss && start < 0) start = i;
    if (!loss && start >= 0) { runs.push([start, i - 1]); start = -1; }
  }
  for (const r of runs) if (!best || r[1] - r[0] > best[1] - best[0]) best = r;
  const len = best[1] - best[0] + 1;
  const nextI = best[1] + 1;
  out.run = { length: len, total: sum(pnl.slice(best[0], best[1] + 1)), from: best[0] + 1, to: best[1] + 1,
    same_length: runs.filter((r) => r[1] - r[0] + 1 === len).length,
    next: nextI < pnl.length ? { n: nextI + 1, pnl: pnl[nextI] } : null };

  // Largest single loss (ties: the first) and the share of all loss dollars from the TOP_K largest losses.
  let li = -1;
  for (let i = 0; i < pnl.length; i++) if (pnl[i] < 0 && (li < 0 || pnl[i] < pnl[li])) li = i;
  out.largest_loss = { n: li + 1, pnl: pnl[li], close_ts: t[li].close_ts, share: pnl[li] / loss_total };
  const losses = pnl.filter((x) => x < 0).sort((a, b) => a - b);
  const k = Math.min(TOP_K, losses.length);
  const topTotal = sum(losses.slice(0, k));
  out.top = { k, of: losses.length, total: topTotal, share: topTotal / loss_total };
  return out;
}

// The consistency share: the largest winning day ÷ the file's total profit (the sum of every day).
//   kind 'no_win_day'  no day ended above zero
//   kind 'no_profit'   the days add up to zero or less, so there is no total profit to divide
//   kind 'share'       share = best / net; over = the share is above the firm's limit (when one is given)
// limit: a share in (0, 1], null (the rules have none) or NOT_STATED (the firm's page does not state one).
export function consistencyShare(dayTotals, limit = null) {
  const net = sum(dayTotals);
  let bi = -1;
  for (let i = 0; i < dayTotals.length; i++) if (dayTotals[i] > 0 && (bi < 0 || dayTotals[i] > dayTotals[bi])) bi = i;
  const base = { net, limit, best: bi < 0 ? null : dayTotals[bi], best_day: bi < 0 ? null : bi + 1, n_days: dayTotals.length };
  if (bi < 0) return { kind: 'no_win_day', ...base };
  if (!(net > 0)) return { kind: 'no_profit', ...base };
  const share = dayTotals[bi] / net;
  return { kind: 'share', ...base, share, over: typeof limit === 'number' ? share > limit + 1e-12 : null };
}

// The trades the report itself is about: the same selection as strip.js stripRows (trades opened within 519 weeks
// of the latest open and held at most 3,650 days; then the latest MAX_ROWS), so the facts and the report count the
// same trades (Tester S4 M3).
export function reportTrades(trades) {
  let maxOpen = -Infinity;
  for (const t of trades) if (t.open_ts > maxOpen) maxOpen = t.open_ts;
  const keep = (SPAN_WEEKS - 1) * 7 * 86400000;
  const inSpan = trades.filter((t) => t.open_ts >= maxOpen - keep && t.hold_s <= MAX_HOLD_S);
  return inSpan.length > MAX_ROWS ? inSpan.slice(inSpan.length - MAX_ROWS) : inSpan;
}

// Whether a firm's rules can be applied to a file in this unit (Tester S4 B2). Rules are money: a file in points
// never gets the check. A 'fixed' preset states amounts in its own currency, so the file must be in that currency.
// A 'percent' preset states shares of the account, so it applies in the file's own money unit, whatever it is.
//   null: the check runs; otherwise {why: 'points' | 'currency', unit, currency}
export function unitMismatch(unit, preset) {
  if (unit === 'points') return { why: 'points', unit, currency: preset.currency || null };
  if (preset.scale === 'percent') return null;
  return unit === preset.currency ? null : { why: 'currency', unit, currency: preset.currency || null };
}

const cents = (x) => Math.round(x * 100) / 100;

// The time zone a file's times are read in, by default (as the free Readiness Check: MetaTrader reports carry the
// broker's server clock; the example report's own data is read as UTC; anything else as the computer's own zone).
export function defaultFileTz(format, sample = false) {
  return format === 'mt5' || format === 'mt4' ? 'broker' : sample ? 'UTC' : 'local';
}
export function resolveTz(v) {
  if (v === 'local') {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch (e) { return 'UTC'; }
  }
  return v;
}

// The presets a buyer can pick: those the library can quote (not_quotable ones have no rules to run).
export function usablePresets(lib) {
  return ((lib && lib.presets) || []).filter((p) => p.status !== 'not_quotable' && p.rules);
}

// The Readiness engine on one firm's published rules, in the trades' real order (sequence mode: one replay, no
// random draw). accountSize scales a 'percent' preset (prop-sim-core / challenge-presets, unchanged).
export function challengeCheck(trades, preset, opts = {}) {
  const t = inCloseOrder(trades);
  const pr = presetRules(preset, opts.accountSize || preset.account_size);
  const rules = pr.rules;
  // scaled amounts to the cent, as the free tool's boxes (3% of 7,000 is 210, not 210.00000000000003: Tester S4 M1)
  for (const f of SCALED) if (typeof rules[f] === 'number') rules[f] = cents(rules[f]);
  const fileTz = opts.fileTz === undefined ? 'UTC' : opts.fileTz;
  // a day start the firm does not state: midnight on the file's own clock, as the free tool (Tester S4 B4)
  const dayStart = pr.dayStart || { tz: 'file', hour: 0 };
  const g = groupDays(t, { fileTz, dayStart });
  const seq = simulate({ mode: 'sequence', days: g.days, rules });
  const datesOnly = isDatesOnly(t);
  const tradeAt = (di, i) => { const n = g.index[di][i]; return { n: n + 1, close_ts: t[n].close_ts, pnl: t[n].pnl }; };

  // the first breach in the real order: which rule, which day of the run, which trade
  const first = { outcome: seq.outcome, why: seq.why, day: seq.day, target_day: seq.target_day, n_days: g.days.length,
    limit_days: rules.time_limit === null ? null : rules.time_limit, cap: NO_LIMIT_CAP, trade: null, day_at: null };
  if (seq.outcome === 'bust' && seq.bust_at && seq.bust_at.length) {
    const [di, i] = seq.bust_at[0];
    first.trade = tradeAt(di, i);
    first.day_at = seq.day_pnl[seq.day_pnl.length - 1];
  }

  // every file day whose running closed-trade P&L reached the daily loss limit (habit-flags.realBreachDays' rule)
  const daily = rules.daily_loss;
  const breaches = [];
  if (daily !== null && daily !== undefined) {
    g.days.forEach((d, j) => {
      let run = 0;
      for (let i = 0; i < d.length; i++) {
        run += d[i];
        if (run <= -daily) { breaches.push({ day: j + 1, at: i, trade: tradeAt(j, i), running: run, day_total: sum(d) }); break; }
      }
    });
  }

  // habits on breach days (bundle §2.3 step 3), in fixed order, under the free tool's own rule (habit-flags
  // realBreachDays): its status ('few' under MIN_BREACH_DAYS breach days, 'not_described' for the habits that need
  // times on a dates-only file) decides what is shown. Counts and totals for both groups, the same way: breach days
  // up to and including the breaching trade (as the free tool's presence), other losing days whole.
  const flags = habitFlags(itemsFromTrades(t), { datesOnly });
  const fd = dayFlags(flags, g.index);
  const real = realBreachDays(g.days, fd, daily, { datesOnly });
  const isBreach = new Set(breaches.map((b) => b.day - 1));
  const otherDays = [];
  g.days.forEach((d, j) => { if (!isBreach.has(j) && sum(d) < 0) otherDays.push(j); });
  const tally = (j, last, bit) => {
    let n = 0, total = 0;
    for (let i = 0; i <= last; i++) if (fd[j][i] & bit) { n++; total += g.days[j][i]; }
    return [n, total];
  };
  const habits = HABITS.map((h) => {
    const r = real.habits[h];
    let n = 0, total = 0, on = 0, ot = 0;
    for (const b of breaches) { const [k, x] = tally(b.day - 1, b.at, BIT[h]); n += k; total += x; }
    for (const j of otherDays) { const [k, x] = tally(j, g.days[j].length - 1, BIT[h]); on += k; ot += x; }
    return { id: h, status: r.status, on_breach: r.on_breach, n_breach: real.n_breach,
      on_other_losing: r.on_other_losing, n_other_losing: real.n_other_losing, n_trades: n, total, n_trades_other: on, total_other: ot };
  });

  const dayTotals = g.days.map(sum);
  const consLimit = pr.notStated.includes('consistency') ? NOT_STATED : rules.consistency;
  return { preset: { id: preset.id, firm: preset.firm, program: preset.program, read_text: preset.read_text || null,
    url: preset.url || null, urls: preset.urls || (preset.url ? [preset.url] : []), account_size: pr.accountSize,
    own_size: preset.account_size, scale: preset.scale, currency: preset.currency || null },
    rules, day_start: dayStart, day_start_stated: !!pr.dayStart, file_tz: fileTz, not_stated: pr.notStated, not_modelled: pr.notModelled, dates_only: datesOnly, n_trades: t.length,
    first, breaches, habits, days: dayTotals, consistency: consistencyShare(dayTotals, consLimit) };
}
