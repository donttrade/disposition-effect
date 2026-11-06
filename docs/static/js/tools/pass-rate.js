/* Prop-firm pass-rate calculator (native page, 6 Nov 2026). Runs entirely in the browser; nothing is sent anywhere.
 *
 * The maths is the lifted page's, unchanged: countFrom(), parseCount(), compute(), pct() and num() are copied
 * word for word from static/js/legacy/pass-rate-calculator.js, which stays as the test oracle
 * (tests/test_tools_b2.py runs both on the same inputs and needs identical results). Numbers are read with the
 * trade-file engine's rule (legacy/numbers.js, loaded before this file), whole numbers only.
 * New (owner, 6 Nov; ARCHITECT-PLAN-TOOLS-REDESIGN A.9-5):
 *   - wilson(): the Wilson 95% interval of passed ÷ finished, shown only once at least BAND_MIN (30) evaluations
 *     have finished, the site's small-sample rule (the Readiness Check's 30 days, the test's 30 trades per group);
 *   - the funnel (started, finished, passed, paid out) drawn to scale on the dark display, with the band on the
 *     passed bar. It only sets SVG attributes and text: no style attribute (the CSP has no 'unsafe-inline').
 * No example counts: no firm publishes cohort counts we can show.
 */
(function (root) {
  'use strict';

  var N = root.dtNumbers || (typeof require !== 'undefined' ? require('../legacy/numbers.js') : null);
  var LIMIT = 1e12;
  var BAND_MIN = 30;
  var Z = 1.96;

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

  /* The Wilson score interval of k successes in n at 95% (z = 1.96): {lo, hi}, or null below BAND_MIN finished. */
  function wilson(k, n) {
    if (!(n >= BAND_MIN) || k < 0 || k > n) return null;
    var p = k / n, z2 = Z * Z, den = 1 + z2 / n;
    var mid = (p + z2 / (2 * n)) / den;
    var half = Z * Math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / den;
    return { lo: Math.max(0, mid - half), hi: Math.min(1, mid + half) };
  }

  var api = { parseCount: parseCount, countFrom: countFrom, compute: compute, pct: pct, num: num, wilson: wilson,
              BAND_MIN: BAND_MIN };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  if (typeof document !== 'undefined') {
    var $ = function (id) { return document.getElementById(id); };
    var fields = ['pr-started', 'pr-open', 'pr-passed', 'pr-paid', 'pr-traders'];
    var labels = ['Evaluations started', 'Still open', 'Passed', 'Funded with a payout', 'Unique traders'];
    var touched = {};
    var W = 240;

    var mark = function (id, msg) {
      var el = $(id), e = $(id + '-err');
      e.textContent = msg || '';
      e.hidden = !msg;
      if (msg) {
        el.setAttribute('aria-invalid', 'true');
        el.setAttribute('aria-describedby', id + '-hint ' + id + '-err pr-msg');
      } else {
        el.removeAttribute('aria-invalid');
        el.setAttribute('aria-describedby', id + '-hint pr-msg');
      }
    };
    var bar = function (k, share, label) {
      var w = Math.max(share > 0 ? 2 : 0, Math.round(share * W * 10) / 10);
      $('pf-' + k).setAttribute('width', String(w));
      var t = $('pf-' + k + '-t');
      t.textContent = label;
      t.setAttribute('x', String(w > 120 ? 4 : w + 4));
      t.setAttribute('class', 'dg-t pf-lab' + (w > 120 ? ' pf-on' : ''));
    };
    var LABELS = { started: 'started', finished: 'finished', passed: 'passed', paid: 'paid out' };
    /* Back to the empty funnel (no cohort, or counts that do not add up): every bar and the band at width 0, the
     * plain labels. Tester F1: Clear and invalid counts left the last cohort drawn. */
    var emptyFunnel = function () {
      Object.keys(LABELS).forEach(function (k) {
        $('pf-' + k).setAttribute('width', '0');
        var t = $('pf-' + k + '-t');
        t.textContent = LABELS[k];
        t.setAttribute('x', '4');
        t.setAttribute('class', 'dg-t pf-lab');
      });
      $('pf-band').setAttribute('x', '0');
      $('pf-band').setAttribute('width', '0');
    };
    var funnel = function (v, r, band) {
      var s = v[0];
      bar('started', 1, v[0].toLocaleString('en-US') + ' started');
      bar('finished', r.finished / s, r.finished.toLocaleString('en-US') + ' finished');
      bar('passed', v[2] / s, v[2].toLocaleString('en-US') + ' passed');
      bar('paid', v[3] / s, v[3].toLocaleString('en-US') + ' paid out');
      var b = $('pf-band'), fw = r.finished / s * W;
      if (band) {
        var bx = Math.round(band.lo * fw * 10) / 10, bw = Math.max(1.2, Math.round((band.hi - band.lo) * fw * 10) / 10);
        b.setAttribute('x', String(bx));
        b.setAttribute('width', String(bw));
        var t = $('pf-passed-t');   // a label beside the bar starts after the band, so the two never overlap
        if (t.getAttribute('class').indexOf('pf-on') < 0) t.setAttribute('x', String(Math.round((Math.max(v[2] / s * W, bx + bw) + 4) * 10) / 10));
      } else b.setAttribute('width', '0');
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
      var hide = function () { outBox.hidden = true; ['rate', 'band', 'range', 'perEval', 'perFunded', 'perTrader'].forEach(function (k) { setOut(k, '–'); }); emptyFunnel(); };
      if (!complete) { msgEl.textContent = errs.join(' '); hide(); return; }
      var r = compute(vals[0], vals[1], vals[2], vals[3], vals[4]);
      if (!r.ok) { msgEl.textContent = r.errors.join(' '); hide(); return; }
      msgEl.textContent = '';
      outBox.hidden = false;
      setOut('rate', pct(r.passRateFinished));
      var band = wilson(vals[2], r.finished);
      $('pr-band-wrap').hidden = !band;
      setOut('band', band ? pct(band.lo) + ' to ' + pct(band.hi) : '–');
      setOut('range', pct(r.rangeLow) + ' to ' + pct(r.rangeHigh));
      setOut('perEval', pct(r.payoutPerEvaluation));
      setOut('perFunded', pct(r.payoutPerFunded));
      $('pr-trader-wrap').hidden = r.accountsPerTrader === null;
      setOut('perTrader', r.accountsPerTrader === null ? '–' : num(r.accountsPerTrader, 2));
      var ul = $('pr-notes'); ul.textContent = '';
      var notes = r.notes.slice();
      if (r.finished > 0 && r.finished < BAND_MIN) {
        notes.push('Fewer than ' + BAND_MIN + ' evaluations have finished, so no 95% band is shown: with so few, the rate can swing a long way.');
      }
      notes.forEach(function (n) { var li = document.createElement('li'); li.textContent = n; ul.appendChild(li); });
      funnel(vals, r, band);
    };
    var touchAll = function () { fields.forEach(function (id) { touched[id] = true; }); };
    var reveal = function () {
      var box = $('pr-results');
      if (!box || box.hidden || !box.scrollIntoView) return;
      var still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      box.scrollIntoView({ block: 'nearest', behavior: still ? 'auto' : 'smooth' });
    };
    var shownOnce = false;
    var init = function () {
      if (!$('pr-started') || !N) return;
      fields.forEach(function (id) {
        $(id).addEventListener('input', function () { touched[id] = true; update(); });
        $(id).addEventListener('blur', function () { touched[id] = true; update(); });
        $(id).addEventListener('change', function () {
          var box = $('pr-results');
          if (shownOnce || !box || box.hidden) return;
          shownOnce = true;
          if (box.getBoundingClientRect().top > window.innerHeight - 80) setTimeout(reveal, 60);
        });
      });
      $('pr-form').addEventListener('submit', function (e) { e.preventDefault(); touchAll(); update(); reveal(); });
      $('pr-form').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') { e.preventDefault(); touchAll(); update(); reveal(); }
      });
      $('pr-clear').addEventListener('click', function () { fields.forEach(function (id) { $(id).value = ''; }); touched = {}; shownOnce = false; update(); });
      update();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(this);
