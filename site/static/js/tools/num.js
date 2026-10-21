// num.js — strict number input for the calculators.
//
// Why strict: "1,500" is fifteen hundred in Toronto and one-and-a-half in Berlin. A
// calculator that guesses gives a confident wrong answer, so anything that can be read
// two ways is refused with a message saying how to write it. Same rule as the trade-file
// engine (a lone comma followed by exactly three digits is ambiguous).
//
// Accepted:  1500   1500.25   .5   1,500.25   1,500,000   1 500 is NOT accepted (spaces)
// Refused:   1,5 (comma decimal)   1,500 (ambiguous)   4 2   1,0,0   1.2.3   12abc   (blank)

export class InputError extends Error {
  constructor(message) { super(message); this.name = 'InputError'; }
}

const PLAIN = /^[+-]?(\d+\.?\d*|\.\d+)$/;
const GROUPED = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;

// Returns a finite number, or throws InputError with a sentence the page shows verbatim.
export function parseStrict(raw, label) {
  const s = String(raw === null || raw === undefined ? '' : raw).trim();
  if (s === '') throw new InputError(`Enter ${label}.`);
  if (/\s/.test(s)) throw new InputError(`${cap(label)}: remove the spaces (write 1500 or 1,500.00).`);
  if (PLAIN.test(s)) return finiteOr(Number(s), label);
  if (GROUPED.test(s)) {
    // "1,500" alone could be 1.5 (decimal comma). Two or more groups, or a dot decimal
    // after the groups, can only be thousands separators.
    const groups = s.split('.')[0].split(',').length - 1;
    if (groups === 1 && !s.includes('.')) {
      throw new InputError(`${cap(label)}: "${s}" could mean ${s.replace(',', '')} or ${s.replace(',', '.')}. Write it without the comma (for example ${s.replace(',', '')}), or with a decimal point (${s}.00).`);
    }
    return finiteOr(Number(s.replace(/,/g, '')), label);
  }
  if (/^[+-]?\d+,\d+$/.test(s)) {
    throw new InputError(`${cap(label)}: use a decimal point, not a comma (write ${s.replace(',', '.')}).`);
  }
  throw new InputError(`${cap(label)}: "${s}" is not a number this page can read. Use digits and at most one decimal point.`);
}

export function parsePositive(raw, label) {
  const n = parseStrict(raw, label);
  if (!(n > 0)) throw new InputError(`${cap(label)} has to be more than zero.`);
  return n;
}

export function parseNonNegative(raw, label) {
  const n = parseStrict(raw, label);
  if (n < 0) throw new InputError(`${cap(label)} cannot be negative.`);
  return n;
}

export function parseWhole(raw, label, min = 0, max = Infinity) {
  const n = parseStrict(raw, label);
  if (!Number.isInteger(n)) throw new InputError(`${cap(label)} has to be a whole number.`);
  if (n < min || n > max) throw new InputError(`${cap(label)} has to be between ${min} and ${max === Infinity ? 'any size' : max}.`);
  return n;
}

function finiteOr(n, label) {
  if (!Number.isFinite(n)) throw new InputError(`${cap(label)} is too large.`);
  if (Math.abs(n) > 1e15) throw new InputError(`${cap(label)} is too large.`);
  return n;
}

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
