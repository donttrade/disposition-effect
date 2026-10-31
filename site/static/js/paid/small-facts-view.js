// small-facts-view.js — batch S4's two report sections, drawn from small-facts.js (pure) on the trades this tab
// already parsed. Nothing here makes a network request or stores anything.
//
//   factsSection(trades, opts)       "Your N trades, in dollars": four definite facts (addendum §3.1 item 1)
//   challengeSection(trades, opts)   "Your file against your firm's rules": the firm preset, the real-order result,
//                                    every day at the daily loss limit, the best-day share against the firm's own
//                                    limit, and habits on breach days with their dollars (§3.1 item 2; bundle §2.3)
//   smallLayout(report)              whether the report uses the small-file order (§3.1): fewer than 100 trades and
//                                    no habit with a sign
//
// opts: { money(x) → text (the report's own formatter), presets (the firm-rules library the build embedded),
//         format (the engine's file format), sample (the example report) }.
//
// Wording: definite statements only, numbers first (addendum §3; plan §10). Every fixed string is in SF_TEXT or is
// built by the SF_LINES functions, so the lint and the hedge-word test see all of them (tests/test_small_facts.py).
// The firm library's quotes are data, not page copy (challenge_rules.json "about"): the page shows each rule's value,
// the date it was read and a link to the firm's page, and "Not stated by {firm}" where the firm's page is silent.

import { fileFacts, challengeCheck, usablePresets, defaultFileTz, resolveTz, unitMismatch } from './small-facts.js';
import { HABIT_TEXT, MIN_BREACH_DAYS } from '../tools/habit-flags.js';
import { NOT_STATED } from '../tools/challenge-presets.js';

const NS = 'http://www.w3.org/2000/svg';

// The verdict values that count as "a sign" for the small-file order. The habit verdict layer is being replaced in
// another batch (E1/S1: Clear / Some / No sign); its merge maps its own step values here, in this one place.
export const SIGN_VERDICTS = Object.freeze(['distinguishable']);   // stats2f reports (frozen, one release)
export const SIGN_STEPS = Object.freeze(['some', 'clear']);         // DT-2 reports
export const SMALL_FILE_TRADES = 100;
const hasSign = (h) => SIGN_STEPS.includes(h.step) || SIGN_VERDICTS.includes(h.verdict);
export function smallLayout(report) {
  return report.n_trades < SMALL_FILE_TRADES && !report.habits.some(hasSign);
}

export const SF_TEXT = Object.freeze({
  net: 'Net total',
  worst: 'Worst day',
  no_losing_day: 'No losing day',
  no_losing_day_sub: 'Every day ended at zero or above.',
  loss_dollars: 'of your total loss',
  run: 'Longest losing run',
  no_losses: 'No losing trades in this file.',
  last_trade: 'It was the file’s last trade.',
  facts_note: 'Worked out in this tab from your file. Days follow your file’s clock. Trades are counted in the order they closed.',
  rules_h: 'Your file against your firm’s rules',
  rules_lead: 'Your trades, replayed once in their real order against the rules your firm publishes.',
  pick: 'Firm rules',
  pick_none: 'Choose a firm',
  account: 'Account size',
  account_pct: 'These rules are shares of the account, so they scale to this size.',
  account_fixed: 'These rules are fixed amounts.',
  tz: 'Times in your file are in',
  tz_local: 'My computer’s time zone',
  tz_utc: 'UTC',
  tz_broker: 'Broker server time (GMT+2, GMT+3 in summer)',
  waiting: 'Choose a firm to replay your trades against its rules.',
  account_bad: 'Enter the account size as an amount above zero.',
  no_rules: 'This firm’s rules cannot be replayed here.',
  r_target: 'Profit target',
  r_daily: 'Daily loss limit',
  r_max: 'Maximum loss',
  r_best: 'Best-day limit',
  r_days: 'Minimum days',
  none: 'None',
  breach_h: 'Days at the daily loss limit, whole file',
  no_daily: 'These rules have no daily loss limit.',
  strip_caption: 'Each bar is one day, in order. Marked days reached the daily loss limit.',
  cons_h: 'Best day against total profit',
  cons_no_win: 'No day ended in profit, so there is no best day.',
  cons_none: 'These rules have no best-day limit.',
  habits_h: 'Habit trades on breach days and other losing days: counts and totals',
  habits_breach: 'Breach days',
  habits_other: 'Other losing days',
  habits_up_to: 'Breach days are counted up to the trade that reached the limit; other losing days whole.',
  habits_not_cause: 'A count and a total, not a cause.',
  few: HABIT_TEXT.few,
  not_described: HABIT_TEXT.not_described,
  by_design: HABIT_TEXT.by_design,
  leaves_out: 'What this check leaves out',
  closed_only: 'Closed trades only: what happens inside an open trade is not in the file.',
  source: 'Source',
  sources: 'Sources:',
  points_refused: 'This file’s results are in price points, and firm rules are amounts of money, so this file gets no rule check.',
});

// The habit names the report shows (report.js nameOf: oversized_loss is "Large losses").
export const HABIT_NAMES = Object.freeze({ reentry: HABIT_TEXT.reentry, streak: HABIT_TEXT.streak,
  size_after_loss: HABIT_TEXT.size_after_loss, large_loss: 'Large losses' });

// What the check runs with when a firm leaves a rule unstated (challenge-presets DEFAULTS), in words.
const NS_NAMES = Object.freeze({ target_check: ['when the target counts', 'at the end of the day'],
  daily_loss: ['daily loss limit', 'none'], drawdown: ['how the maximum loss moves', 'fixed at the start'],
  trail_stop_at: ['where the trailing floor stops', 'no stop'], consistency: ['best-day limit', 'none'],
  min_days: ['minimum days', 'none'], count_day_if: ['which days count', 'any day with a trade'],
  time_limit: ['time limit', 'none'], day_start: ['when a day starts', 'midnight on your file’s clock'] });

const plural = (n, one, many) => `${count(n)} ${n === 1 ? one : many}`;
const count = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
const share = (x) => `${Math.round(100 * x)}%`;
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// Engine times are naive (the file's own wall clock read as UTC), so UTC getters give the time written in the file.
export function dateText(ts, year = false) {
  const d = new Date(ts);
  return `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}${year ? ' ' + d.getUTCFullYear() : ''}`;
}
const timeText = (ts) => new Date(ts).toISOString().slice(11, 16);

// The sentences with numbers in them. Each takes formatted pieces only, so the tests can lint every shape.
export const SF_LINES = Object.freeze({
  facts_h: (n, unit) => `Your ${plural(n, 'trade', 'trades')}, ${unit === 'USD' ? 'in dollars' : unit === 'points' ? 'in points' : 'in your currency'}`,
  won: (m, n) => `${m} won in ${plural(n, 'trade', 'trades')}`,
  lost: (m, n) => `${m} lost in ${plural(n, 'trade', 'trades')}`,
  flat: (n) => `${plural(n, 'trade', 'trades')} at break-even`,
  worst_sub: (date, n) => `${date} · ${plural(n, 'trade', 'trades')}`,
  top_label: (k, of) => (k === of ? (of === 1 ? 'Your one loss' : `All ${count(of)} losses`) : `${count(k)} largest losses`),
  top_all: 'your whole total loss',
  largest: (m, n) => `Largest: ${m}, trade ${count(n)}`,
  run_value: (len) => (len === 1 ? '1 loss' : `${count(len)} in a row`),
  run_trades: (from, to) => (from === to ? `trade ${count(from)}` : `trades ${count(from)}–${count(to)}`),
  run_next: (m) => `Next trade: ${m}`,
  run_next_flat: 'Next trade: break-even',
  run_ties: (k) => `The first of ${count(k)} runs this long.`,
  first_bust: (rule, day, n, of) => `In the real order, your trades broke the ${rule} on day ${count(day)}, at trade ${count(n)} of ${count(of)}.`,
  bust_sub_daily: (when, m) => `${when} · the day stood at ${m}.`,
  bust_sub_max: (when, m) => `${when} · that trade: ${m}.`,
  closed_at: (n, d, t) => `Trade ${count(n)} closed ${d} at ${t}`,
  closed_on: (n, d) => `Trade ${count(n)} closed ${d}`,
  first_pass: (day) => `In the real order, your trades reached the target on day ${count(day)}, with no rule broken.`,
  first_pass_held: (t, day) => `In the real order, your trades reached the target on day ${count(t)} and met the day count and best-day rules on day ${count(day)}, with no rule broken.`,
  first_end: (days) => `In the real order, your trades reached neither the target nor a loss limit in ${plural(days, 'day', 'days')}.`,
  first_time: (days) => `In the real order, your trades reached neither the target nor a loss limit in the ${plural(days, 'day', 'days')} these rules allow.`,
  first_cap: (days) => `In the real order, your trades reached neither the target nor a loss limit in the first ${plural(days, 'day', 'days')} (the check stops there).`,
  rules_for: (firm, program, size) => `${firm}, ${program} · ${size} account`,
  rules_scaled: (firm, program, size) => `${firm}’s rules (${program}), scaled to ${size}`,
  percent_unit: (firm) => `${firm}’s rules are shares of the account, so they apply in your file’s own currency.`,
  currency_refused: (unit, firm, cur) => `This file’s results are in ${unit}, and ${firm}’s rules are fixed amounts in ${cur}, so this file gets no rule check against them.`,
  max_kind: (m, kind) => `${m}, ${kind}`,
  day_start: (firm, hour, zone, file) => `Days start at ${String(hour).padStart(2, '0')}:00 ${zone}, as ${firm} states; your file’s times are read as ${file}.`,
  not_stated: (firm, parts) => `Not stated by ${firm}: ${parts}.`,
  not_stated_one: (firm) => `Not stated by ${firm}`,
  ns_part: (name, used) => `${name} (the check uses ${used})`,
  breach_count: (k, of) => `${count(k)} of ${plural(of, 'day', 'days')} in your file`,
  no_breach: (m) => `No day reached the daily loss limit of ${m}.`,
  breach_row: (day, n, date) => `Day ${count(day)} · trade ${count(n)}, closed ${date} · the day at`,
  breach_more: (k) => `And ${plural(k, 'more day', 'more days')}.`,
  cons_line: (best, net) => `Best day ${best} of total profit ${net}.`,
  cons_over: (firm, pct) => `${firm}’s limit: ${pct}. This file is over it.`,
  cons_within: (firm, pct) => `${firm}’s limit: ${pct}. This file is within it.`,
  cons_no_profit: (net, best) => `Your days add up to ${net}, so there is no total profit to compare with. Best day: ${best}.`,
  habit_group: (on, of, n, m) => `on ${count(on)} of ${plural(of, 'day', 'days')} · ${plural(n, 'trade', 'trades')} · ${m}`,
  habit_group_none: 'no such days',
  few_count: (k, min) => `${HABIT_TEXT.few}: ${plural(k, 'breach day', 'breach days')} in this file; the free Readiness Check describes ${count(min)} or more.`,
  read_on: (firm, date) => `Rules as published by ${firm}, read on ${date}.`,
  strip_label: (n, k) => `${plural(n, 'day', 'days')} in order; ${count(k)} reached the daily loss limit.`,
});

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids) if (k !== null && k !== undefined) e.append(k instanceof Node ? k : String(k));
  return e;
}
const signCls = (x) => (x > 0 ? 'gain' : x < 0 ? 'loss' : '');

// A thin bar: fill = share (0..1, drawn up to 100%), optional marker at another share (a firm's limit).
function shareBar(x, cls = 'is-loss', marker = null) {
  const bar = el('span', { class: 'sf-bar', 'aria-hidden': 'true' });
  const fill = el('span', { class: 'sf-fill ' + cls });
  fill.style.width = (100 * Math.max(0, Math.min(1, x))).toFixed(1) + '%';   // CSSOM, allowed by the CSP
  bar.append(fill);
  if (marker !== null) {
    const m = el('span', { class: 'sf-mark' });
    m.style.left = (100 * Math.max(0, Math.min(1, marker))).toFixed(1) + '%';
    bar.append(m);
  }
  return bar;
}

function tile(label, value, valueCls, ...rest) {
  return el('div', { class: 'sf-tile' }, el('p', { class: 'sf-k', text: label }),
    el('p', { class: 'sf-v' + (valueCls ? ' ' + valueCls : ''), text: value }), ...rest);
}
const sub = (text, cls = '') => el('p', { class: 'sf-s' + (cls ? ' ' + cls : ''), text });

// One square per losing trade of the run (up to 12), then the next trade's square.
function runSquares(run) {
  const box = el('span', { class: 'sf-run', 'aria-hidden': 'true' });
  for (let i = 0; i < Math.min(run.length, 12); i++) box.append(el('span', { class: 'sf-sq is-loss' }));
  if (run.length > 12) box.append(el('span', { class: 'sf-more', text: '+' + count(run.length - 12) }));
  if (run.next) box.append(el('span', { class: 'sf-sq is-next ' + (run.next.pnl > 0 ? 'is-gain' : run.next.pnl < 0 ? 'is-loss' : 'is-flat') }));
  return box;
}

// An amount never splits between its sign and the currency symbol at a line end (a word joiner after the sign).
const keepSign = (money) => (x) => money(x).replace(/^([−+])/, '$1\u2060');

export function factsSection(trades, opts) {
  const m = keepSign(opts.money);
  const f = fileFacts(trades);
  const years = new Set(trades.map((t) => new Date(t.close_ts).getUTCFullYear())).size > 1;
  const sec = el('section', { class: 'section sf-facts', id: 'file-facts', 'aria-labelledby': 'file-facts-h' },
    el('h2', { id: 'file-facts-h', text: SF_LINES.facts_h(f.n, opts.unit) }));
  const grid = el('div', { class: 'sf-grid' });
  // 1. net total, with what was won and lost
  const gross = f.win_total - f.loss_total;
  const net = tile(SF_TEXT.net, m(f.net), signCls(f.net),
    sub(SF_LINES.won(m(f.win_total), f.n_win)), sub(SF_LINES.lost(m(f.loss_total), f.n_loss)),
    gross > 0 ? (() => { const b = shareBar(f.win_total / gross, 'is-gain'); b.classList.add('sf-split'); return b; })() : null,
    f.n_flat ? sub(SF_LINES.flat(f.n_flat), 'muted') : null);
  net.id = 'sf-net';
  grid.append(net);
  if (!f.n_loss) {
    grid.append(el('div', { class: 'sf-tile sf-wide', id: 'sf-no-losses' }, el('p', { class: 'sf-v', text: SF_TEXT.no_losses })));
  } else {
    // 2. worst day
    const w = f.worst_day;
    const worst = w
      ? tile(SF_TEXT.worst, m(w.total), 'loss', sub(SF_LINES.worst_sub(dateText(w.date_ts, years), w.n_trades)),
        shareBar(w.loss_share), sub(`${share(w.loss_share)} ${SF_TEXT.loss_dollars}`))
      : tile(SF_TEXT.worst, SF_TEXT.no_losing_day, '', sub(SF_TEXT.no_losing_day_sub, 'muted'));
    worst.id = 'sf-worst';
    // 3. the largest losses' share of all loss dollars
    const t = f.top;
    const all = t.k === t.of;
    const top = tile(SF_LINES.top_label(t.k, t.of), all ? m(t.total) : share(t.share), all ? 'loss' : '',
      all ? sub(SF_LINES.top_all) : el('div', {}, shareBar(t.share), sub(SF_TEXT.loss_dollars)),
      sub(SF_LINES.largest(m(f.largest_loss.pnl), f.largest_loss.n)));
    top.id = 'sf-top';
    // 4. longest losing run and what the next trade did
    const r = f.run;
    const run = tile(SF_TEXT.run, SF_LINES.run_value(r.length), '', runSquares(r), sub(m(r.total), signCls(r.total)), sub(SF_LINES.run_trades(r.from, r.to)),
      sub(r.next ? (r.next.pnl === 0 ? SF_LINES.run_next_flat : SF_LINES.run_next(m(r.next.pnl))) : SF_TEXT.last_trade),
      r.same_length > 1 ? sub(SF_LINES.run_ties(r.same_length), 'muted') : null);
    run.id = 'sf-run';
    grid.append(worst, top, run);
  }
  sec.append(grid, el('p', { class: 'small muted', text: SF_TEXT.facts_note }));
  return sec;
}

// ------------------------------------------------------------------ the challenge check

function dayStrip(c, m) {
  const n = c.days.length;
  const breach = new Set(c.breaches.map((b) => b.day - 1));
  const W = Math.max(400, n + 4), H = 90, mid = 46, pad = 2;   // every day gets a bar, however many (Tester S4 M2)
  const max = Math.max(1e-9, ...c.days.map((x) => Math.abs(x)), c.rules.daily_loss || 0);
  const bw = (W - 2 * pad) / Math.max(n, 1);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('class', 'sf-strip');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', SF_LINES.strip_label(n, breach.size));
  const scale = (mid - 6) / max;
  const firstBust = c.first.outcome === 'bust' ? c.first.day - 1 : -1;
  c.days.forEach((x, i) => {
    const h = Math.max(1, Math.abs(x) * scale);
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('x', String(pad + i * bw + bw * 0.12)); r.setAttribute('width', String(Math.max(0.8, bw * 0.76)));
    r.setAttribute('y', String(x >= 0 ? mid - h : mid)); r.setAttribute('height', String(h));
    r.setAttribute('class', breach.has(i) ? 'sf-d-breach' : x < 0 ? 'sf-d-loss' : 'sf-d-gain');
    svg.append(r);
    if (breach.has(i) || i === firstBust) {
      const t = document.createElementNS(NS, 'path');
      const cx = pad + i * bw + bw / 2;
      t.setAttribute('d', `M${cx - 4} ${H - 1} L${cx + 4} ${H - 1} L${cx} ${H - 8} Z`);
      t.setAttribute('class', 'sf-d-mark');
      svg.append(t);
    }
  });
  const axis = document.createElementNS(NS, 'line');
  axis.setAttribute('x1', '0'); axis.setAttribute('x2', String(W)); axis.setAttribute('y1', String(mid)); axis.setAttribute('y2', String(mid));
  axis.setAttribute('class', 'grid-line');
  svg.append(axis);
  if (c.rules.daily_loss) {
    const y = mid + c.rules.daily_loss * scale;
    const l = document.createElementNS(NS, 'line');
    l.setAttribute('x1', '0'); l.setAttribute('x2', String(W)); l.setAttribute('y1', String(y)); l.setAttribute('y2', String(y));
    l.setAttribute('class', 'sf-d-limit');
    svg.append(l);
  }
  return el('figure', { class: 'chart sf-strip-fig' }, svg, el('figcaption', { text: SF_TEXT.strip_caption }));
}

function firstLine(c, m, years) {
  const f = c.first;
  if (f.outcome === 'bust') {
    const rule = f.why === 'daily' ? 'daily loss limit' : 'maximum loss';
    const lead = SF_LINES.first_bust(rule, f.day, f.trade.n, c.n_trades);
    const when = c.dates_only ? SF_LINES.closed_on(f.trade.n, dateText(f.trade.close_ts, true))
      : SF_LINES.closed_at(f.trade.n, dateText(f.trade.close_ts, years), timeText(f.trade.close_ts));
    const subline = f.why === 'daily' ? SF_LINES.bust_sub_daily(when, m(f.day_at)) : SF_LINES.bust_sub_max(when, m(f.trade.pnl));
    return [lead, subline];
  }
  if (f.outcome === 'pass') {
    return [f.target_day !== null && f.target_day < f.day ? SF_LINES.first_pass_held(f.target_day, f.day) : SF_LINES.first_pass(f.target_day || f.day), null];
  }
  if (f.outcome === 'end') return [SF_LINES.first_end(f.n_days), null];
  // no time limit in these rules: the replay stops at the engine's cap, and says so (Tester S4 B3)
  return [f.limit_days === null ? SF_LINES.first_cap(f.cap) : SF_LINES.first_time(f.limit_days), null];
}

// A money unit in words: an ISO code as the code, MetaTrader's account currency and IBKR's base currency by name.
function unitName(u) {
  return u === 'USD' ? 'US dollars' : u === 'account' ? 'your account currency' : u === 'base' ? 'your base currency' : u === 'points' ? 'price points' : String(u);
}

// A rule's amount, without the + a P&L figure carries.
const unsigned = (m, x) => m(x).replace(/^\+/, '');

function rulesList(c, m) {
  const firm = c.preset.firm, ns = new Set(c.not_stated), r = c.rules;
  const val = (field, text) => (ns.has(field) ? SF_LINES.not_stated_one(firm) : text);
  const kind = r.drawdown === 'static' ? 'fixed' : r.drawdown === 'trailing_eod' ? 'trailing, end of day' : 'trailing, each trade';
  const rows = [
    [SF_TEXT.r_target, unsigned(m, r.target)],
    [SF_TEXT.r_daily, val('daily_loss', r.daily_loss === null ? SF_TEXT.none : unsigned(m, r.daily_loss))],
    [SF_TEXT.r_max, ns.has('drawdown') ? unsigned(m, r.max_loss) : SF_LINES.max_kind(unsigned(m, r.max_loss), kind)],
    [SF_TEXT.r_best, val('consistency', r.consistency === null ? SF_TEXT.none : share(r.consistency))],
    [SF_TEXT.r_days, val('min_days', r.min_days ? count(r.min_days) : SF_TEXT.none)],
  ];
  const dl = el('dl', { class: 'happened sf-rules' });
  for (const [k, v] of rows) dl.append(el('div', {}, el('dt', { text: k }), el('dd', { text: v })));
  return dl;
}

// Where a day starts, in words: the firm's stated reset in its own zone, and the zone the file is read in. An unstated
// reset is named in the not-stated line instead ("midnight on your file's clock"), which is what the check uses.
const zoneName = (z) => (z === 'broker' ? 'broker server time (GMT+2, GMT+3 in summer)' : z === 'file' ? 'on your file’s clock'
  : z && typeof z === 'object' ? `UTC${z.offset_min >= 0 ? '+' : ''}${z.offset_min / 60}` : /^Etc\/GMT[+-]\d+$/.test(z) ? `UTC${z[7] === '-' ? '+' : '−'}${z.slice(8)}` : `${z} time`);
function dayStartLine(c) {
  if (!c.day_start_stated) return null;
  return el('p', { class: 'small', id: 'sf-day-start', text: SF_LINES.day_start(c.preset.firm, c.day_start.hour, zoneName(c.day_start.tz), zoneName(c.file_tz)) });
}

function notStatedLine(c) {
  const shown = new Set(['daily_loss', 'consistency', 'min_days']);   // those three say it in the list above
  const parts = c.not_stated.filter((f) => !shown.has(f) && NS_NAMES[f]).map((f) => SF_LINES.ns_part(...NS_NAMES[f]));
  return parts.length ? el('p', { class: 'small', id: 'sf-not-stated', text: SF_LINES.not_stated(c.preset.firm, parts.join('; ')) }) : null;
}

function breachBlock(c, m, years) {
  const box = el('div', { class: 'sf-block', id: 'sf-breaches' }, el('h3', { text: SF_TEXT.breach_h }));
  if (c.rules.daily_loss === null) { box.append(el('p', { text: SF_TEXT.no_daily })); return box; }
  if (!c.breaches.length) { box.append(el('p', { text: SF_LINES.no_breach(unsigned(m, c.rules.daily_loss)) })); return box; }
  box.append(el('p', { class: 'sf-count', text: SF_LINES.breach_count(c.breaches.length, c.days.length) }));
  const ol = el('ol', { class: 'sf-list' });
  const SHOW = 10;
  for (const b of c.breaches.slice(0, SHOW)) {
    ol.append(el('li', {}, SF_LINES.breach_row(b.day, b.trade.n, dateText(b.trade.close_ts, years)) + ' ', el('span', { class: 'sf-nw', text: m(b.running) })));
  }
  box.append(ol);
  if (c.breaches.length > SHOW) box.append(el('p', { class: 'small muted', text: SF_LINES.breach_more(c.breaches.length - SHOW) }));
  return box;
}

function consistencyBlock(c, m) {
  const k = c.consistency, firm = c.preset.firm;
  const box = el('div', { class: 'sf-block', id: 'sf-consistency' }, el('h3', { text: SF_TEXT.cons_h }));
  if (k.kind === 'no_win_day') { box.append(el('p', { text: SF_TEXT.cons_no_win })); return box; }
  if (k.kind === 'no_profit') { box.append(el('p', { text: SF_LINES.cons_no_profit(m(k.net), m(k.best)) })); return box; }
  const numeric = typeof k.limit === 'number';
  box.append(el('p', { class: 'sf-v' + (k.over ? ' loss' : ''), text: share(k.share) }),
    shareBar(k.share, k.over ? 'is-loss' : 'is-plan', numeric ? k.limit : null),
    el('p', { class: 'sf-s', text: SF_LINES.cons_line(m(k.best), m(k.net)) }),
    el('p', { class: 'sf-s', text: numeric ? (k.over ? SF_LINES.cons_over(firm, share(k.limit)) : SF_LINES.cons_within(firm, share(k.limit)))
      : k.limit === NOT_STATED ? SF_LINES.not_stated_one(firm) + '.' : SF_TEXT.cons_none }));
  return box;
}

// Habit trades on breach days and on the other losing days, under the free Readiness Check's own rule (Tester S4 B1):
// fewer than MIN_BREACH_DAYS breach days → its "Too few breach days" line and nothing else; a habit that needs times on
// a dates-only file → its own line. Otherwise both groups, in the same words and weight: days with the habit, its
// trades and their total. Counts and totals only; no bars, no colour, no ranking.
function habitsBlock(c, m) {
  if (!c.breaches.length) return null;
  const box = el('div', { class: 'sf-block', id: 'sf-habits' }, el('h3', { text: SF_TEXT.habits_h }));
  if (c.breaches.length < MIN_BREACH_DAYS) {
    box.append(el('p', { id: 'sf-habits-few', text: SF_LINES.few_count(c.breaches.length, MIN_BREACH_DAYS) }));
    return box;
  }
  const list = el('ul', { class: 'sf-habits' });
  for (const h of c.habits) {
    const li = el('li', { class: 'sf-habit', 'data-habit': h.id }, el('p', { class: 'sf-hn', text: HABIT_NAMES[h.id] }));
    if (h.status === 'not_described') li.append(sub(SF_TEXT.not_described, 'muted'));
    else {
      const group = (label, on, of, n, total) => el('p', { class: 'sf-s' }, el('span', { class: 'sf-hg', text: label + ': ' }),
        of ? SF_LINES.habit_group(on, of, n, m(total)) : SF_LINES.habit_group_none);
      li.append(group(SF_TEXT.habits_breach, h.on_breach, h.n_breach, h.n_trades, h.total),
        group(SF_TEXT.habits_other, h.on_other_losing, h.n_other_losing, h.n_trades_other, h.total_other));
    }
    list.append(li);
  }
  box.append(list, el('p', { class: 'small', text: SF_TEXT.habits_not_cause }),
    el('p', { class: 'small muted', text: `${SF_TEXT.habits_up_to} ${SF_TEXT.by_design}` }));
  return box;
}

function checkOut(trades, preset, size, tz, m, unit) {
  const c = challengeCheck(trades, preset, { accountSize: size, fileTz: resolveTz(tz) });
  const years = new Set(trades.map((t) => new Date(t.close_ts).getUTCFullYear())).size > 1;
  const [lead, subline] = firstLine(c, m, years);
  const out = [el('p', { class: 'sf-first ' + (c.first.outcome === 'bust' ? 'is-bust' : ''), id: 'sf-first', text: lead })];
  if (subline) out.push(el('p', { class: 'sf-s', text: subline }));
  // a size the firm does not sell as such reads as the firm's rules scaled to it (Tester S4 M8)
  const sizeText = unsigned(m, c.preset.account_size);
  const own = c.preset.scale !== 'percent' || Math.abs(c.preset.account_size - c.preset.own_size) < 0.005;
  out.push(el('p', { class: 'small sf-rules-for', text: own ? SF_LINES.rules_for(c.preset.firm, c.preset.program, sizeText)
    : SF_LINES.rules_scaled(c.preset.firm, c.preset.program, sizeText) }),
    unit !== c.preset.currency ? el('p', { class: 'small', text: SF_LINES.percent_unit(c.preset.firm) }) : null,
    rulesList(c, m), dayStartLine(c), notStatedLine(c), dayStrip(c, m), breachBlock(c, m, years), consistencyBlock(c, m), habitsBlock(c, m));
  const src = el('p', { class: 'small muted sf-source' }, c.preset.read_text ? SF_LINES.read_on(c.preset.firm, c.preset.read_text) + ' ' : '');
  // every source page in the library for this preset, not only the first (Tester S4 M9)
  if (c.preset.urls.length) {
    src.append(SF_TEXT.sources + ' ');
    c.preset.urls.forEach((u, i) => {
      let host = u;
      try { host = new URL(u).hostname; } catch (e) { /* the library only holds https URLs */ }
      src.append(...(i ? [', '] : []), el('a', { href: u, rel: 'noopener', text: c.preset.urls.length > 1 ? `${host} (${i + 1})` : host }));
    });
  }
  out.push(src, el('details', { class: 'how-more' }, el('summary', { text: SF_TEXT.leaves_out }),
    el('ul', {}, ...c.not_modelled.map((x) => el('li', { text: x })), el('li', { text: SF_TEXT.closed_only }))));
  return { nodes: out.filter(Boolean), check: c };
}

export function challengeSection(trades, opts) {
  const m = keepSign(opts.money);
  const presets = usablePresets(opts.presets);
  const sec = el('section', { class: 'section sf-rules-sec', id: 'rule-check', 'aria-labelledby': 'rule-check-h' },
    el('h2', { id: 'rule-check-h', text: SF_TEXT.rules_h }), el('p', { text: SF_TEXT.rules_lead }));
  const sel = el('select', { id: 'sf-preset' }, el('option', { value: '', text: SF_TEXT.pick_none }));
  const firms = [];
  for (const p of presets) if (!firms.includes(p.firm)) firms.push(p.firm);   // the library's own order
  for (const f of firms) {
    const g = el('optgroup', { label: f });
    for (const p of presets.filter((x) => x.firm === f)) g.append(el('option', { value: p.id, text: `${p.firm}, ${p.program}` }));
    sel.append(g);
  }
  const size = el('input', { id: 'sf-account', type: 'text', inputmode: 'decimal', autocomplete: 'off', 'aria-describedby': 'sf-account-hint' });
  const sizeHint = el('p', { class: 'hint', id: 'sf-account-hint', text: '' });
  const tz = el('select', { id: 'sf-tz' }, el('option', { value: 'local', text: SF_TEXT.tz_local }),
    el('option', { value: 'UTC', text: SF_TEXT.tz_utc }), el('option', { value: 'broker', text: SF_TEXT.tz_broker }));
  tz.value = defaultFileTz(opts.format, opts.sample);
  const form = el('div', { class: 'field-grid sf-form no-print' },
    el('div', { class: 'field' }, el('label', { for: 'sf-preset', text: SF_TEXT.pick }), sel),
    el('div', { class: 'field' }, el('label', { for: 'sf-account', text: SF_TEXT.account }), sizeHint, size),
    el('div', { class: 'field' }, el('label', { for: 'sf-tz', text: SF_TEXT.tz }), tz));
  // Only the result's first line is announced, not the whole region on every change (Tester S4 M11).
  const live = el('p', { class: 'visually-hidden', id: 'sf-live', 'aria-live': 'polite' });
  const out = el('div', { class: 'sf-out', id: 'sf-out' }, el('p', { class: 'muted', text: SF_TEXT.waiting }));
  sec.append(form, live, out);
  sec.lastCheck = null;
  const unit = opts.unit || (trades[0] && trades[0].pnl_unit);
  const draw = () => {
    const p = presets.find((x) => x.id === sel.value);
    if (!p) { out.replaceChildren(el('p', { class: 'muted', text: SF_TEXT.waiting })); live.textContent = ''; sec.lastCheck = null; return; }
    // rules are money: points never, and a fixed-amount preset only in its own currency (Tester S4 B2)
    const bad = unitMismatch(unit, p);
    if (bad) {
      const line = bad.why === 'points' ? SF_TEXT.points_refused : SF_LINES.currency_refused(unitName(unit), p.firm, unitName(p.currency));
      out.replaceChildren(el('p', { class: 'notice', id: 'sf-refused', text: line }));
      live.textContent = line; sec.lastCheck = null; return;
    }
    sizeHint.textContent = p.scale === 'percent' ? SF_TEXT.account_pct : SF_TEXT.account_fixed;
    size.readOnly = p.scale !== 'percent';
    const raw = size.value.replace(/[\s,$]/g, '');
    const v = Number(raw);
    if (p.scale === 'percent' && !(raw !== '' && Number.isFinite(v) && v > 0)) {
      out.replaceChildren(el('p', { class: 'error', text: SF_TEXT.account_bad })); sec.lastCheck = null; return;
    }
    try {
      const r = checkOut(trades, p, p.scale === 'percent' ? v : p.account_size, tz.value, m, unit);
      out.replaceChildren(...r.nodes);
      live.textContent = r.nodes[0].textContent;
      sec.lastCheck = r.check;
    } catch (e) {
      out.replaceChildren(el('p', { class: 'error', text: SF_TEXT.no_rules }));
      sec.lastCheck = null;
    }
  };
  // A new firm starts from its own account size, unless the trader typed one (kept for any percent preset).
  let typed = null;
  size.addEventListener('input', () => { if (!size.readOnly) typed = size.value; });
  sel.addEventListener('change', () => {
    const p = presets.find((x) => x.id === sel.value);
    if (p) size.value = p.scale === 'percent' && typed !== null && typed.trim() !== '' ? typed : String(p.account_size);
    draw();
  });
  size.addEventListener('change', draw);
  tz.addEventListener('change', draw);
  return sec;
}

// The firm-rules library the build embedded in the page (<script type="application/json" id="sf-presets">).
export function presetsFromPage(doc = document) {
  const n = doc.getElementById('sf-presets');
  if (!n) return { presets: [] };
  try { return JSON.parse(n.textContent); } catch (e) { return { presets: [] }; }
}
