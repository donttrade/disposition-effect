// readiness-card.js — the Challenge Readiness Check's share card (ARCHITECT-CHALLENGE-READINESS §2.5), drawn in
// this tab on a <canvas>. Nothing is uploaded. Always the light palette, so it reads the same everywhere.
//
// On the card: the three shares as a bar, the rule that broke most, the most common habit on breach days (only
// when its pill is "hit"), the rules as percentages of the account (never a firm's name), an optional what-if
// line the trader ticked, and "Past trades only. Not investment advice." with "donttrade.ca". Never on it: an
// amount, a currency, P&L, a balance, an account size, a date, a symbol, a file name, a firm's name or logo,
// a price or anything about buying. A card from the example data carries a strip saying so.
// Every string the card can show is built from CARD_STRINGS (scanned by the wording tests).

export const SIZES = Object.freeze({ portrait: [1080, 1350], wide: [1200, 630] });
export const CARD_STRINGS = Object.freeze({
  headline: 'Passed in {p}% of {n} replays',
  pass: 'Passed {p}%', bust: 'Broke a rule {p}%', time: 'Out of time {p}%',
  rule_daily: 'Rule that broke most: daily loss',
  rule_max: 'Rule that broke most: maximum loss',
  habit: 'Most common on breach days: {habit}',
  rules: '{t}% target · {d} daily · {m}% max ({kind})',
  whatif: 'With {rule}: passed {a}% → {b}%',
  whatif_short: 'With your rules: passed {a}% → {b}%',
  footer: 'Past trades only. Not investment advice.',
  site: 'donttrade.ca',
  example: 'Example data, not a real trader',
  static: 'fixed floor', moving: 'moving floor', none: 'no',
});
// Short names of the what-if rules, so the card's line stays within 12 words.
export const SHORT_RULES = Object.freeze({
  stop_after_losses: (v) => `stop after ${v} ${v === 1 ? 'loss' : 'losses'}`,
  stop_at_day_loss: (v) => `stop at ${Math.round(v * 100)}% of the daily limit`,
  stop_at_day_loss_amount: () => 'a daily stop',
  max_trades: (v) => `at most ${v} ${v === 1 ? 'trade' : 'trades'} a day`,
  cooldown_s: (v) => `a ${v / 60}-minute pause after a loss`,
  after_loss_factor: (v) => `${{ 0.25: 'a quarter', 0.5: 'half', 0.75: 'three quarters' }[v]} size after a loss`,
});
const C = { bg: '#FFFFFF', text: '#16181C', muted: '#5B606A', gain: '#1F7A52', loss: '#A3264F', time: '#C7C9CE', rust: '#9A3B1C', border: '#DADCE0' };
const fill = (tpl, v) => tpl.replace(/\{(\w+)\}/g, (_, k) => String(v[k]));
const whole = (x) => Math.round(x * 100);
const grouped = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

export function shortRule(personal) {
  return Object.entries(personal || {}).filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => SHORT_RULES[k](v)).join(' and ');
}

// data: {pass, bust, timeout (shares 0-1), runs, rule: 'daily'|'max'|null, habit: label|null,
//        rulesPct: {t, d (number or null), m, kind: 'static'|'moving'}|null, whatif: {personal, a, b}|null, example}
// → the card's lines, in drawing order (also its alt text).
export function cardLines(data) {
  const S = CARD_STRINGS;
  const lines = { headline: fill(S.headline, { p: whole(data.pass), n: grouped(data.runs) }),
    shares: [fill(S.pass, { p: whole(data.pass) }), fill(S.bust, { p: whole(data.bust) }), fill(S.time, { p: whole(data.timeout) })],
    facts: [] };
  if (data.rule) lines.facts.push(data.rule === 'daily' ? S.rule_daily : S.rule_max);
  if (data.habit) lines.facts.push(fill(S.habit, { habit: data.habit.charAt(0).toLowerCase() + data.habit.slice(1) }));
  if (data.rulesPct) {
    const r = data.rulesPct;
    lines.facts.push(fill(S.rules, { t: r.t, d: r.d === null ? S.none : `${r.d}%`, m: r.m, kind: r.kind === 'static' ? S.static : S.moving }));
  }
  if (data.whatif) {
    const v = { rule: shortRule(data.whatif.personal), a: whole(data.whatif.a), b: whole(data.whatif.b) };
    const line = fill(S.whatif, v);
    lines.facts.push(line.split(' ').length <= 12 ? line : fill(S.whatif_short, v));   // a card line stays within 12 words
  }
  lines.footer = [S.footer, S.site];
  if (data.example) lines.example = S.example;
  return lines;
}

export function altText(data) {
  const l = cardLines(data);
  return [l.headline + '.', l.shares.join(', ') + '.', ...l.facts.map((f) => f + '.'), l.example ? l.example + '.' : null, ...l.footer]
    .filter(Boolean).join(' ');
}

// Draws the card on `canvas` at SIZES[size]. Fonts are the site's own, loaded first.
export async function drawCard(canvas, data, size = 'portrait') {
  const [W, H] = SIZES[size];
  canvas.width = W; canvas.height = H;
  try {
    await Promise.all(['400 32px "Plex Sans"', '600 32px "Plex Sans"'].map((f) => document.fonts.load(f)));
  } catch (e) { /* the fallback font draws the same words */ }
  const g = canvas.getContext('2d');
  const l = cardLines(data);
  const wide = size === 'wide';
  // sizes in px: [headline, line height, bar, legend, facts, facts line height, footer]
  const z = wide ? { h: 56, hl: 66, bar: 52, leg: 28, f: 32, fl: 42, foot: 26, pad: 64 }
    : { h: 84, hl: 100, bar: 88, leg: 38, f: 46, fl: 60, foot: 34, pad: 84 };
  const pad = z.pad;
  const font = (wt, px) => `${wt} ${px}px "Plex Sans", "Segoe UI", Roboto, sans-serif`;
  g.fillStyle = C.bg; g.fillRect(0, 0, W, H);
  g.fillStyle = C.rust; g.fillRect(0, 0, W, 14);
  g.textBaseline = 'alphabetic'; g.textAlign = 'left';
  let y = pad + z.h;
  if (l.example) {   // a strip across the top, under the rust line: on every card made from the example data
    const sh = wide ? 54 : 76;
    g.fillStyle = 'rgba(154, 59, 28, 0.12)'; g.fillRect(0, 14, W, sh);
    g.fillStyle = C.rust; g.font = font(600, wide ? 26 : 34); g.textAlign = 'center';
    g.fillText(l.example, W / 2, 14 + sh / 2 + (wide ? 9 : 12));
    g.textAlign = 'left';
    y += sh - (wide ? 20 : 10);
  }
  g.fillStyle = C.text; g.font = font(600, z.h);
  y = wrap(g, l.headline, pad, y, W - 2 * pad, z.hl);
  y += wide ? 10 : 30;
  const bw = W - 2 * pad;
  let x = pad;
  for (const [share, col] of [[data.pass, C.gain], [data.bust, C.loss], [data.timeout, C.time]]) {
    const w = Math.round(share * bw);
    g.fillStyle = col; g.fillRect(x, y, w, z.bar); x += w;
  }
  y += z.bar + z.leg + (wide ? 24 : 36);
  let leg = z.leg;
  const gap = wide ? 44 : 52;
  for (; leg > 18; leg -= 2) {   // the three labels fit on one line
    g.font = font(400, leg);
    const sqw = Math.round(leg * 0.62) + 10;
    if (l.shares.reduce((t, s) => t + sqw + g.measureText(s).width, 0) + 2 * gap <= bw) break;
  }
  const cols = [C.gain, C.loss, C.muted];
  let lx = pad;
  const sq = Math.round(leg * 0.62);
  l.shares.forEach((s, i) => {
    g.fillStyle = cols[i]; g.fillRect(lx, y - sq, sq, sq);
    g.fillStyle = C.text; g.fillText(s, lx + sq + 10, y);
    lx += sq + 10 + g.measureText(s).width + gap;
  });
  y += wide ? 30 : 60;
  const footY = H - pad - (wide ? 44 : 64);
  g.fillStyle = C.border; g.fillRect(pad, y, W - 2 * pad, 2);
  // the facts: the largest size at which they all end above the footer line
  let fs = z.f, fl = z.fl;
  const sep = wide ? 6 : 18;
  for (; fs > 20; fs -= 2, fl = Math.round(fs * 1.3)) {
    g.font = font(400, fs);
    const h = l.facts.reduce((t, f) => t + lines(g, f, W - 2 * pad) * fl + sep, 0);
    if (y + fl + (wide ? 8 : 20) + h - fl <= footY - fs) break;
  }
  y += fl + (wide ? 8 : 20);
  g.font = font(400, fs);
  for (const f of l.facts) {
    g.fillStyle = C.text;
    y = wrap(g, f, pad, y, W - 2 * pad, fl) + sep;
  }
  g.fillStyle = C.border; g.fillRect(pad, footY, W - 2 * pad, 2);
  g.font = font(400, z.foot); g.fillStyle = C.muted;
  g.fillText(l.footer[0], pad, H - pad);
  g.font = font(600, z.foot); g.fillStyle = C.rust; g.textAlign = 'right';
  g.fillText(l.footer[1], W - pad, H - pad);
  g.textAlign = 'left';
  canvas.setAttribute('aria-label', altText(data));
  return canvas;
}

function lines(g, text, max) {
  let n = 1, line = '';
  for (const w of text.split(' ')) {
    const t = line ? `${line} ${w}` : w;
    if (g.measureText(t).width > max && line) { n++; line = w; } else line = t;
  }
  return n;
}

function wrap(g, text, x, y, max, lh) {
  const words = text.split(' ');
  let line = '';
  for (const w of words) {
    const t = line ? `${line} ${w}` : w;
    if (g.measureText(t).width > max && line) { g.fillText(line, x, y); line = w; y += lh; } else line = t;
  }
  if (line) g.fillText(line, x, y);
  return y + lh;
}

export function cardBlob(canvas) {
  return new Promise((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'));
}
