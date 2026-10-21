/* numbers.js — how the two old calculators read a typed number (21 Oct 2026).
 *
 * The SAME decimal rule as the trade-file engine (static/js/engine/csv.js: parseNumber,
 * numberShape, resolveNumberStyle; plan DATA MODEL "Number and date parsing"), with the form
 * playing the part of the file. tests/test_calc_numbers.py runs both on the same inputs.
 *   - "12,5" is a decimal comma (12.5); "1,234.5" and "1.234,5" are read by their shape.
 *   - "1,234" (one comma, exactly 3 digits after it, no dot) could be 1.234 or 1234: refused,
 *     always, never merged (plan rule).
 *   - "1.500" (one dot, 3 digits after it) is decided once per form from the other inputs:
 *     a decimal comma elsewhere → 1500; a decimal point elsewhere → 1.5; neither → refused.
 *   - a decimal comma in one input and a decimal point in another → refused.
 * One addition for typed input only: a space inside a number must group thousands ("1 780");
 * "4 2" is refused instead of read as 42. The engine strips such spaces in exported files.
 * Whole-number boxes (readForm(raws, {whole: true}), launch NIT N3): "1,780" or a lone "1.780"
 * can only mean 1780 there, since 1.78 is not a count, so it is read as 1780 instead of refused.
 * The page's own example is written "1,780". The engine has no whole-number-only columns.
 * Nothing here guesses from the browser's language: the engine does not either (its golden
 * tests run under de-DE), and a person's browser language says little about how they type.
 * Pure functions; nothing is stored or sent.
 */
(function (root) {
  'use strict';

  var WS = '[\\t\\n\\v\\f\\r \\u00a0\\u2000-\\u200a\\u202f\\u205f\\u3000]';
  var RE_STRIP = new RegExp(WS, 'g');
  var RE_EDGE = new RegExp('^' + WS + '+|' + WS + '+$', 'g');
  var RE_INNER = new RegExp(WS);
  var RE_SPACE_GROUPS = new RegExp('^[+\\-−]?\\d{1,3}(' + WS + '\\d{3})+([.,]\\d+)?$');

  // engine/csv.js parseNumber
  var RE_PLAIN = /^[+-]?(\d+\.?\d*|\.\d+)$/;
  var RE_THOUSANDS_COMMA = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
  var RE_EURO = /^[+-]?\d{1,3}(\.\d{3})+,\d+$/;
  var RE_SINGLE_COMMA = /^[+-]?\d+,\d+$/;
  // engine/csv.js numberShape
  var SH_INT = /^[+-]?\d+$/;
  var SH_ONE_COMMA = /^[+-]?\d+,(\d+)$/;
  var SH_US = /^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$/;
  var SH_DOT3 = /^[+-]?[1-9]\d{0,2}\.\d{3}$/;
  var SH_ONE_DOT = /^[+-]?(\d+\.?\d*|\.\d+)$/;
  var SH_DOTS_THOUSANDS = /^[+-]?[1-9]\d{0,2}(\.\d{3}){2,}$/;

  function bare(raw) { return String(raw == null ? '' : raw).replace(RE_STRIP, '').replace(/−/g, '-'); }

  /* 'neutral' | 'comma' | 'dot' | 'dot3' | 'other' — exactly engine numberShape. */
  function shape(raw) {
    var s = bare(raw);
    if (s === '' || SH_INT.test(s)) return 'neutral';
    var c = SH_ONE_COMMA.exec(s);
    if (c) return c[1].length === 3 ? 'neutral' : 'comma';
    if (RE_EURO.test(s) || SH_DOTS_THOUSANDS.test(s)) return 'comma';
    if (SH_US.test(s)) return 'dot';
    if (SH_DOT3.test(s)) return 'dot3';
    if (SH_ONE_DOT.test(s)) return 'dot';
    return 'other';
  }

  /* One value, as engine parseNumber reads it: {ok, value} (value null when empty) or
     {ok: false, why: 'ambiguous_comma' | 'not_number'}. */
  function parseOne(raw) {
    var s = bare(raw);
    if (s === '') return { ok: true, value: null };
    var commas = (s.match(/,/g) || []).length, dots = (s.match(/\./g) || []).length;
    if (commas > 0) {
      if (dots === 0 && commas === 1 && RE_SINGLE_COMMA.test(s)) {
        if (/,\d{3}$/.test(s)) return { ok: false, why: 'ambiguous_comma' };
        s = s.replace(',', '.');
      } else if (RE_THOUSANDS_COMMA.test(s)) {
        s = s.replace(/,/g, '');
      } else if (RE_EURO.test(s)) {
        s = s.replace(/\./g, '').replace(',', '.');
      } else {
        return { ok: false, why: 'not_number' };
      }
    }
    if (!RE_PLAIN.test(s)) return { ok: false, why: 'not_number' };
    var v = Number(s);
    if (!isFinite(v)) return { ok: false, why: 'not_number' };
    return { ok: true, value: v };
  }

  /* Every input of one form at once (engine resolveNumberStyle with no fallback, then
     parseNumber). raws: array of strings. Returns an array of
     {ok, value, decimalComma} | {ok: false, why}, why one of
     'space', 'ambiguous_comma', 'ambiguous_dot', 'mixed', 'not_number'. */
  function readForm(raws, opts) {
    var whole = !!(opts && opts.whole);
    var shapes = [], i, firstComma = -1, firstDot = -1, out = [];
    for (i = 0; i < raws.length; i++) {
      shapes.push(shape(raws[i]));
      if (shapes[i] === 'comma' && firstComma < 0) firstComma = i;
      if (shapes[i] === 'dot' && firstDot < 0) firstDot = i;
    }
    var mixed = firstComma >= 0 && firstDot >= 0;
    var later = mixed ? (firstComma > firstDot ? 'comma' : 'dot') : null;
    var style = firstComma >= 0 ? 'comma' : firstDot >= 0 ? 'dot' : null;
    for (i = 0; i < raws.length; i++) {
      var t = String(raws[i] == null ? '' : raws[i]).replace(RE_EDGE, '');
      if (RE_INNER.test(t) && !RE_SPACE_GROUPS.test(t)) { out.push({ ok: false, why: 'space' }); continue; }
      if (mixed && shapes[i] === later) { out.push({ ok: false, why: 'mixed' }); continue; }
      var s = bare(raws[i]);
      if (shapes[i] === 'dot3' || SH_DOTS_THOUSANDS.test(s)) {
        if (style === null && shapes[i] === 'dot3') {
          out.push(whole ? { ok: true, value: Number(s.replace('.', '')), grouped: true } : { ok: false, why: 'ambiguous_dot' });
          continue;
        }
        if (style === 'comma') s = s.replace(/\./g, '');
      }
      var p = parseOne(s);
      if (!p.ok && p.why === 'ambiguous_comma' && whole) p = { ok: true, value: Number(s.replace(',', '')), grouped: true };
      if (p.ok) p.decimalComma = shapes[i] === 'comma';   // only read when the value has decimals
      out.push(p);
    }
    return out;
  }

  /* The sentence for a refused value, naming the field; it never repeats what was typed. */
  function message(label, why) {
    switch (why) {
      case 'space': return label + ': a space inside a number is only read as a thousands separator, as in 1 780. Remove the space or type the number again.';
      case 'ambiguous_comma': return label + ': a number like 1,780 could mean 1.78 (a decimal comma) or 1780 (a thousands comma). Type it without the comma, for example 1780.';
      case 'ambiguous_dot': return label + ': a number like 1.780 could mean 1.78 or 1780, and no other box shows which. Type it without the dot, for example 1780.';
      case 'mixed': return label + ': the boxes mix decimal commas and decimal points. Use one style, or type whole numbers without separators.';
      default: return label + ' is not a number. Type digits only, for example 1780.';
    }
  }

  var api = { shape: shape, parseOne: parseOne, readForm: readForm, message: message };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.dtNumbers = api;
})(this);
