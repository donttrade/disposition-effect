// wording.js — the paid report's sentences, exactly as ARCHITECT-STATS-AMENDMENT-2026-10-21 §7.1
// gives them, filled from Report / Habit fields. No DOM, no I/O: report.js (pages Coder) renders
// them. Every sentence describes the file's past trades only and passes checks/lint.py
// (tests/test_paid_wording.py).
//
// fmt: { money(x), duration(seconds), ratio(x) } — the page passes its own formatters (money as
// report.js formats it now); the defaults are plain, for tests.

const DEFAULT_FMT = {
  money: (x) => String(x),
  duration: (s) => `${s} s`,
  ratio: (x) => x.toFixed(2),
};

const TESTED = ['hold_gap', 'revenge', 'size_up', 'tilt'];

function fmtOf(fmt) {
  return { ...DEFAULT_FMT, ...(fmt || {}) };
}

// The first sentence of a tested habit (the measures). Not used when the habit is too_few.
export function measureSentence(h, fmt) {
  const f = fmtOf(fmt);
  switch (h.id) {
    case 'revenge': return `Trades opened within 15 minutes of a losing trade's close averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`;
    case 'tilt': return `Trades taken after 2 or more losses in a row averaged ${f.money(h.measure_a)} per trade; your other trades averaged ${f.money(h.measure_b)}.`;
    case 'hold_gap': return `Your losing trades were held a median of ${f.duration(h.measure_a)}; your winning trades a median of ${f.duration(h.measure_b)}.`;
    case 'size_up': return `Your median size after a loss was ${f.ratio(h.effect)}× your median size after a win.`;
    default: throw new Error(`measureSentence: ${h.id} is not a tested habit`);
  }
}

// The second sentence, by verdict and direction. For too_few it is the sentence that replaces both.
export function verdictSentence(h, report) {
  if (!TESTED.includes(h.id)) throw new Error(`verdictSentence: ${h.id} is not a tested habit`);
  switch (h.verdict) {
    case 'distinguishable': {
      const s = `This gap is distinguishable from noise, after adjusting for the ${report.n_tested} patterns tested.`;
      return h.direction === 'opposite' ? `${s} It runs the opposite way to this pattern's name.` : s;
    }
    case 'not_distinguishable':
      return 'A gap this size is within what chance alone produces in files with no pattern, so this file cannot tell it apart from noise.';
    case 'too_few':
      if (h.id === 'revenge' || h.id === 'tilt') {
        return `Not enough trades to tell: this pattern compares two groups of at least 30 trades each, and this file has ${h.n_a} and ${h.n_b}.`;
      }
      if (h.n_a_compared === null || h.n_b_compared === null) throw new Error(`verdictSentence: ${h.id} too_few without compared counts`);
      return `Not enough trades to tell: this pattern compares two groups of at least 30 trades each, counted on days that have both, and this file has ${h.n_a_compared} and ${h.n_b_compared}.`;
    default:
      throw new Error(`verdictSentence: unknown verdict ${h.verdict}`);
  }
}

// Both sentences of a tested habit as shown under its heading.
export function habitSentences(h, report, fmt) {
  if (h.verdict === 'too_few') return [verdictSentence(h, report)];
  return [measureSentence(h, fmt), verdictSentence(h, report)];
}

// The method line (small text under each tested habit that has a p).
export function methodLine(h) {
  if (h.n_perm === null) return null;
  if (h.id === 'revenge') return `Compared with your other trades from the same days, matched on whether another trade had just closed: the results were reshuffled within each day ${h.n_perm} times to see how large a gap chance alone produces.`;
  if (h.id === 'tilt') return `Compared with your other trades from the same days: the results were reshuffled within each day ${h.n_perm} times to see how large a gap chance alone produces.`;
  if (h.id === 'hold_gap' || h.id === 'size_up') return `Compared within the same days: the labels were reshuffled within each day ${h.n_perm} times to see how large a gap chance alone produces.`;
  throw new Error(`methodLine: ${h.id} is not a tested habit`);
}

// Page 1: the headline lines. Returns a list of sentences.
// PLAN CONFLICT (CODER-STATS-REPORT): §7.1 has no sentence for a report whose distinguishable
// gaps include one in the habit's own direction whose dollar figure is not negative (focus null,
// but not because every gap runs the opposite way). For that case no "no pattern is shown first"
// line is returned (the opposite-way sentence would be false) until the Architect supplies one.
export function page1Lines(report, fmt) {
  const f = fmtOf(fmt);
  const k = report.n_distinguishable, n = report.n_tested;
  if (k === 0) {
    return ['No pattern in this file is distinguishable from noise.',
      'That does not show the patterns are absent; it means this file cannot tell them apart from chance.'];
  }
  const lines = [`${k} of the ${n} patterns tested in this file ${k === 1 ? 'is' : 'are'} distinguishable from noise. Each verdict is adjusted for testing ${n} patterns at once, so in files with no real pattern, at least one shows as distinguishable in about 1 report in 20 or fewer.`];
  if (report.focus !== null) {
    const h = report.habits.find((x) => x.id === report.focus);
    if (!h) throw new Error(`page1Lines: focus ${report.focus} not in habits`);
    lines.push(`Shown first: ${h.name}. ${h.dollars.label} totalled ${f.money(h.dollars.amount)} (historical).`);
    return lines;
  }
  const dist = report.habits.filter((h) => h.verdict === 'distinguishable');
  if (dist.every((h) => h.direction === 'opposite')) {
    lines.push(dist.length === 1
      ? 'The distinguishable gap runs the opposite way to its pattern name, so no pattern is shown first.'
      : 'The distinguishable gaps run the opposite way to their pattern names, so no pattern is shown first.');
  }
  return lines;
}

// Coverage line (page 1, always).
export function coverageLines(report) {
  const lines = [`${report.n_tested} of the 4 patterns could be tested. Each one compares two groups of at least 30 trades.`];
  if (report.n_tested < 4) {
    const names = report.habits.filter((h) => TESTED.includes(h.id) && h.p_raw === null).map((h) => h.name);
    lines.push(`Not tested: ${names.join(', ')}.`);
  }
  return lines;
}
