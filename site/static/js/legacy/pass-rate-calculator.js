/* Prop-firm pass-rate calculator. Runs entirely in the browser; nothing is sent anywhere.
 *
 * Code fixes of 21 Oct 2026 (the page text is unchanged; the v1 script is kept in
 * checks/lifted-baseline/legacy-v1/pass-rate-calculator.js):
 *   - numbers are read with the trade-file engine's rule (numbers.js): "1,5" is 1.5, so it is
 *     refused as a count instead of being read as 15; "1,780" and "4 2" get a clear message;
 *   - a box is checked only once it has been typed in or left, or the form is submitted:
 *     nothing is marked wrong on first load;
 *   - each refused box gets its own message next to it, and the summary below the buttons;
 *   - the boxes take whole numbers only, so "1,780" (the page's own example) is 1780 (launch NIT N3).
 * compute() and the results are unchanged, so the worked example gives the same figures.
 * 24 Oct 2026: pct() never rounds a rate below 1 to "100.0%" or a rate above 0 to "0.0%".
 */
(function (root) {
  'use strict';

  var N = root.dtNumbers || (typeof require !== 'undefined' ? require('./numbers.js') : null);
  var LIMIT = 1e12;

  /* One count from a form read by N.readForm: {ok, value} | {ok: false, msg} (value null = empty). */
  function countFrom(label, p) {
    if (!p.ok) return { ok: false, msg: N.message(label, p.why) };
    if (p.value === null) return { ok: true, value: null };
    if (Math.floor(p.value) !== p.value) {
      return { ok: false, msg: label + (p.decimalComma ? ' reads as a decimal (the comma is a decimal comma). ' : ' has decimals. ') +
        'Counts are whole numbers: type it without a comma or dot, for example 1780.' };
    }
    if (p.value < 0) return { ok: false, msg: label + ' cannot be negative. Enter a whole number of zero or more.' };
    if (p.value > LIMIT) return { ok: false, msg: label + ' is too large: this calculator takes counts up to 1,000,000,000,000.' };
    return { ok: true, value: p.value };
  }

  /* Kept for the v1 API: one count on its own. */
  function parseCount(raw, allowEmpty) {
    var c = countFrom('The count', N.readForm([raw], { whole: true })[0]);
    if (c.ok && c.value === null) return allowEmpty ? c : { ok: false };
    return c.ok ? c : { ok: false, error: c.msg };
  }

  /* traders is optional: pass null/undefined to leave it out. */
  function compute(started, open, passed, paid, traders) {
    var errors = [], hasTraders = !(traders === null || traders === undefined);
    var req = { started: started, open: open, passed: passed, paid: paid };
    var k;
    for (k in req) {
      if (typeof req[k] !== 'number' || !isFinite(req[k]) || req[k] < 0 || Math.floor(req[k]) !== req[k]) {
        errors.push('Every count must be a whole number of zero or more.');
        break;
      }
    }
    if (hasTraders && (typeof traders !== 'number' || !isFinite(traders) || traders < 0 || Math.floor(traders) !== traders)) {
      errors.push('Unique traders must be a whole number of zero or more, or left empty.');
    }
    if (errors.length) return { ok: false, errors: errors };

    if (started === 0) errors.push('Evaluations started must be at least 1.');
    if (open > started) errors.push('Still open cannot be more than evaluations started.');
    if (passed > started) errors.push('Passed cannot be more than evaluations started.');
    if (passed + open > started) errors.push('Passed plus still open cannot be more than evaluations started: an account cannot be both.');
    if (paid > passed) errors.push('Funded accounts with a payout cannot be more than accounts that passed.');
    if (hasTraders && traders < 1) errors.push('Unique traders must be at least 1, or leave it empty.');
    if (hasTraders && traders > started) errors.push('Unique traders cannot be more than evaluations started.');
    if (errors.length) return { ok: false, errors: errors };

    var finished = started - open, notes = [];
    var passRateFinished = finished > 0 ? passed / finished : null;
    if (finished === 0) notes.push('Every evaluation in this cohort is still open, so a pass rate among finished evaluations cannot be worked out yet.');
    var perFunded = passed > 0 ? paid / passed : null;
    if (passed === 0) notes.push('No accounts passed, so the payout rate per funded account is not defined.');
    var r = {
      ok: true, finished: finished,
      passRateFinished: passRateFinished,
      rangeLow: passed / started, rangeHigh: (passed + open) / started,
      payoutPerEvaluation: paid / started,
      payoutPerFunded: perFunded,
      accountsPerTrader: null, notes: notes
    };
    if (hasTraders) {
      r.accountsPerTrader = started / traders;
      notes.push('Per-person rates (for example, the share of people who ever passed) need person-level data: one row per trader, not per account. This page does not compute one from account counts.');
    }
    return r;
  }

  /* Tester §12 (v1 test_pass_rate_never_rounds_to_100_when_some_failed): one decimal rounded 19,999
   * passed of 20,000 to "100.0%" and 1 of 20,000 to "0.0%". A rate that is not exactly 1 or 0 never
   * shows as 100.0% or 0.0%: it reads "over 99.9%" or "under 0.1%". */
  function pct(x) {
    if (x === null) return 'not defined';
    var s = (x * 100).toFixed(1);
    if (s === '100.0' && x < 1) return 'over 99.9%';
    if (s === '0.0' && x > 0) return 'under 0.1%';
    return s + '%';
  }
  function num(x, d) { return x === null ? 'not defined' : x.toFixed(d); }

  var api = { parseCount: parseCount, countFrom: countFrom, compute: compute, pct: pct, num: num };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  if (typeof document !== 'undefined') {
    var $ = function (id) { return document.getElementById(id); };
    var fields = ['pr-started', 'pr-open', 'pr-passed', 'pr-paid', 'pr-traders'];
    var labels = ['Evaluations started', 'Still open', 'Passed', 'Funded with a payout', 'Unique traders'];
    var touched = {};

    /* The inline message under a box: made here, so the page's frozen text is unchanged. */
    var errOf = function (id) {
      var e = $(id + '-err');
      if (!e) {
        e = document.createElement('p');
        e.id = id + '-err';
        e.className = 'error';
        e.hidden = true;
        var input = $(id);
        input.parentNode.insertBefore(e, input.nextSibling);
      }
      return e;
    };
    var mark = function (id, msg) {
      var el = $(id), e = errOf(id);
      e.textContent = msg || '';
      e.hidden = !msg;
      if (msg) {
        el.setAttribute('aria-invalid', 'true');
        el.setAttribute('aria-describedby', id + '-err pr-msg');
      } else {
        el.removeAttribute('aria-invalid');
        el.setAttribute('aria-describedby', 'pr-msg');
      }
    };

    var update = function () {
      var raws = fields.map(function (id) { return $(id).value; });
      var read = N.readForm(raws, { whole: true }), vals = [], errs = [], complete = true, i;
      for (i = 0; i < fields.length; i++) {
        var c = countFrom(labels[i], read[i]), msg = '';
        if (!c.ok) msg = c.msg;
        else if (c.value === null && i !== 4) msg = labels[i] + ' is empty. Enter a whole number, or 0.';
        if (msg) complete = false;
        vals.push(c.ok ? c.value : null);
        if (msg && touched[fields[i]]) { mark(fields[i], msg); errs.push(msg); } else mark(fields[i], '');
      }
      var msgEl = $('pr-msg'), outBox = $('pr-results');
      var setOut = function (k, v) { var e = $('pr-' + k); e.textContent = v; e.className = v === 'not defined' || v === '–' ? 'na' : ''; };
      var hide = function () { outBox.hidden = true; ['rate', 'range', 'perEval', 'perFunded', 'perTrader'].forEach(function (k) { setOut(k, '–'); }); };
      if (!complete) { msgEl.textContent = errs.join(' '); hide(); return; }
      var r = compute(vals[0], vals[1], vals[2], vals[3], vals[4]);
      if (!r.ok) { msgEl.textContent = r.errors.join(' '); hide(); return; }
      msgEl.textContent = '';
      outBox.hidden = false;
      setOut('rate', pct(r.passRateFinished));
      setOut('range', pct(r.rangeLow) + ' to ' + pct(r.rangeHigh));
      setOut('perEval', pct(r.payoutPerEvaluation));
      setOut('perFunded', pct(r.payoutPerFunded));
      $('pr-trader-wrap').hidden = r.accountsPerTrader === null;
      setOut('perTrader', r.accountsPerTrader === null ? '–' : num(r.accountsPerTrader, 2));
      var ul = $('pr-notes'); ul.textContent = '';
      r.notes.forEach(function (n) { var li = document.createElement('li'); li.textContent = n; ul.appendChild(li); });
    };
    var touchAll = function () { fields.forEach(function (id) { touched[id] = true; }); };
    var init = function () {
      if (!$('pr-started') || !N) return;
      fields.forEach(function (id) {
        $(id).addEventListener('input', function () { touched[id] = true; update(); });
        $(id).addEventListener('blur', function () { touched[id] = true; update(); });
      });
      // Enter in a box: the form has several boxes and no submit button, so the browser does not
      // submit it (and lifted.js stops a submit anyway); Enter checks every box instead.
      $('pr-form').addEventListener('submit', function () { touchAll(); update(); });
      $('pr-form').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') { e.preventDefault(); touchAll(); update(); }
      });
      $('pr-example').addEventListener('click', function () {
        $('pr-started').value = '1000'; $('pr-open').value = '150'; $('pr-passed').value = '170'; $('pr-paid').value = '40'; $('pr-traders').value = '800';
        touchAll(); update();
      });
      $('pr-clear').addEventListener('click', function () { fields.forEach(function (id) { $(id).value = ''; }); touched = {}; update(); });
      update();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(this);
