/* Prop-firm pass-rate calculator. Runs entirely in the browser; nothing is sent anywhere. */
(function (root) {
  'use strict';

  function parseCount(raw, allowEmpty) {
    var s = String(raw == null ? '' : raw).replace(/[,\s]/g, '');
    if (s === '') return allowEmpty ? { ok: true, value: null } : { ok: false };
    if (!/^\d+$/.test(s)) return { ok: false };
    var n = parseInt(s, 10);
    if (n > 1e12) return { ok: false };
    return { ok: true, value: n };
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

  function pct(x) { return x === null ? 'not defined' : (x * 100).toFixed(1) + '%'; }
  function num(x, d) { return x === null ? 'not defined' : x.toFixed(d); }

  var api = { parseCount: parseCount, compute: compute, pct: pct, num: num };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  if (typeof document !== 'undefined') {
    var $ = function (id) { return document.getElementById(id); };
    var fields = ['pr-started', 'pr-open', 'pr-passed', 'pr-paid', 'pr-traders'];
    var labels = ['Evaluations started', 'Still open', 'Passed', 'Funded with a payout', 'Unique traders'];
    var update = function () {
      var vals = [], errs = [], anyFilled = false, i, p;
      for (i = 0; i < fields.length; i++) {
        var el = $(fields[i]);
        el.removeAttribute('aria-invalid');
        var empty = String(el.value).replace(/\s/g, '') === '';
        if (!empty) anyFilled = true;
        p = parseCount(el.value, i === 4);
        if (!p.ok) {
          errs.push(empty ? labels[i] + ' is empty. Enter a whole number, or 0.' : labels[i] + ' must be a whole number of zero or more (no decimals, no minus sign).');
          el.setAttribute('aria-invalid', 'true');
        }
        vals.push(p.ok ? p.value : null);
      }
      var msg = $('pr-msg'), outBox = $('pr-results');
      var setOut = function (k, v) { var e = $('pr-' + k); e.textContent = v; e.className = v === 'not defined' || v === '–' ? 'na' : ''; };
      var hide = function () { outBox.hidden = true; ['rate', 'range', 'perEval', 'perFunded', 'perTrader'].forEach(function (k) { setOut(k, '–'); }); };
      if (!anyFilled) { msg.textContent = ''; hide(); return; }
      if (errs.length) { msg.textContent = errs.join(' '); hide(); return; }
      var r = compute(vals[0], vals[1], vals[2], vals[3], vals[4]);
      if (!r.ok) { msg.textContent = r.errors.join(' '); hide(); return; }
      msg.textContent = '';
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
    var init = function () {
      if (!$('pr-started')) return;
      fields.forEach(function (id) { $(id).addEventListener('input', update); });
      $('pr-example').addEventListener('click', function () {
        $('pr-started').value = '1000'; $('pr-open').value = '150'; $('pr-passed').value = '170'; $('pr-paid').value = '40'; $('pr-traders').value = '800';
        update();
      });
      $('pr-clear').addEventListener('click', function () { fields.forEach(function (id) { $(id).value = ''; }); update(); });
      update();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(this);
