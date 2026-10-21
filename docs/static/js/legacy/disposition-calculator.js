/* Disposition-effect calculator. Runs entirely in the browser; nothing is sent anywhere.
 *
 * Code fixes of 21 Oct 2026 (the page text is unchanged; the v1 script is kept in
 * checks/lifted-baseline/legacy-v1/disposition-calculator.js):
 *   - numbers are read with the trade-file engine's rule (numbers.js): "1,5" is 1.5, so it is
 *     refused as a count instead of being read as 15; "1,780" and "4 2" get a clear message;
 *   - a box is checked only once it has been typed in or left, or the form is submitted:
 *     nothing is marked wrong on first load;
 *   - each refused box gets its own message next to it, and the summary below the buttons;
 *   - the boxes take whole numbers only, so "1,780" (the page's own example) is 1780 (launch NIT N3).
 * compute() and the results are unchanged, so the worked example gives the same figures.
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
  function parseCount(raw) {
    var c = countFrom('The count', N.readForm([raw], { whole: true })[0]);
    if (c.ok && c.value === null) return { ok: false, error: 'empty' };
    return c.ok ? c : { ok: false, error: c.msg };
  }

  function compute(rg, pg, rl, pl) {
    var vals = [rg, pg, rl, pl], i;
    for (i = 0; i < 4; i++) {
      if (typeof vals[i] !== 'number' || !isFinite(vals[i]) || vals[i] < 0 || Math.floor(vals[i]) !== vals[i]) {
        return { ok: false, errors: ['All four counts must be whole numbers of zero or more.'] };
      }
    }
    var gainsDen = rg + pg, lossesDen = rl + pl, errors = [];
    if (gainsDen === 0) errors.push('Realised gains + paper gains is zero, so the proportion of gains realised (PGR) cannot be worked out. Enter at least one gain.');
    if (lossesDen === 0) errors.push('Realised losses + paper losses is zero, so the proportion of losses realised (PLR) cannot be worked out. Enter at least one loss.');
    if (errors.length) return { ok: false, errors: errors };

    var pgr = rg / gainsDen, plr = rl / lossesDen;
    var diff = pgr - plr;
    var ratio = plr === 0 ? null : pgr / plr;
    var se = Math.sqrt(pgr * (1 - pgr) / gainsDen + plr * (1 - plr) / lossesDen);
    var t = se === 0 ? null : diff / se;
    var notes = [];
    if (plr === 0) notes.push('The ratio is not defined because PLR is zero (no losses were sold).');
    if (se === 0) notes.push('The standard error is zero (both proportions are 0 or 1), so t is not defined.');

    var reading;
    if (ratio === null) {
      reading = pgr > 0 ? 'No losses were sold, while some gains were, so the ratio is not defined.' : 'Neither gains nor losses were sold, so there is nothing to compare.';
    } else if (ratio > 1) {
      reading = 'Gains were sold about ' + ratio.toFixed(2) + ' times as readily as losses.';
    } else if (ratio < 1) {
      if (ratio === 0) reading = 'No gains were sold, while some losses were.';
      else reading = 'Losses were sold about ' + (1 / ratio).toFixed(2) + ' times as readily as gains.';
    } else {
      reading = 'Gains and losses were sold equally readily.';
    }
    if (t !== null && Math.abs(t) < 1.96) reading += ' Caution: this difference is within the range noise could produce.';

    return { ok: true, pgr: pgr, plr: plr, ratio: ratio, diff: diff, se: se, t: t, gainsDen: gainsDen, lossesDen: lossesDen, reading: reading, notes: notes };
  }

  function fmt(x, d) { return x === null ? 'not defined' : x.toFixed(d); }

  var api = { parseCount: parseCount, countFrom: countFrom, compute: compute, fmt: fmt };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  if (typeof document !== 'undefined') {
    var ids = ['dc-rg', 'dc-pg', 'dc-rl', 'dc-pl'];
    var names = ['Realised gains', 'Paper gains', 'Realised losses', 'Paper losses'];
    var $ = function (id) { return document.getElementById(id); };
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
        el.setAttribute('aria-describedby', id + '-err dc-msg');
      } else {
        el.removeAttribute('aria-invalid');
        el.setAttribute('aria-describedby', 'dc-msg');
      }
    };

    var update = function () {
      var raws = ids.map(function (id) { return $(id).value; });
      var read = N.readForm(raws, { whole: true }), vals = [], errs = [], complete = true, i;
      for (i = 0; i < 4; i++) {
        var c = countFrom(names[i], read[i]), msg = '';
        if (!c.ok) msg = c.msg;
        else if (c.value === null) msg = names[i] + ' is empty. Enter a whole number, or 0.';
        if (msg) complete = false; else vals.push(c.value);
        if (msg && touched[ids[i]]) { mark(ids[i], msg); errs.push(msg); } else mark(ids[i], '');
      }
      var msgEl = $('dc-msg'), outBox = $('dc-results');
      var setOut = function (k, v) { var e = $('dc-' + k); e.textContent = v; e.className = v === 'not defined' || v === '–' ? 'na' : ''; };
      var clear = function () { ['pgr', 'plr', 'ratio', 'diff', 'se', 't'].forEach(function (k) { setOut(k, '–'); }); $('dc-reading').textContent = ''; };
      if (!complete) { msgEl.textContent = errs.join(' '); clear(); outBox.hidden = true; return; }
      var r = compute(vals[0], vals[1], vals[2], vals[3]);
      if (!r.ok) { msgEl.textContent = r.errors.join(' '); clear(); outBox.hidden = true; return; }
      msgEl.textContent = r.notes.join(' ');
      outBox.hidden = false;
      setOut('pgr', fmt(r.pgr, 4)); setOut('plr', fmt(r.plr, 4)); setOut('ratio', fmt(r.ratio, 2));
      setOut('diff', fmt(r.diff, 4)); setOut('se', fmt(r.se, 4)); setOut('t', fmt(r.t, 2));
      $('dc-reading').textContent = r.reading;
    };
    var touchAll = function () { ids.forEach(function (id) { touched[id] = true; }); };
    var init = function () {
      if (!$('dc-rg') || !N) return;
      ids.forEach(function (id) {
        $(id).addEventListener('input', function () { touched[id] = true; update(); });
        $(id).addEventListener('blur', function () { touched[id] = true; update(); });
      });
      // Enter in a box: the form has several boxes and no submit button, so the browser does not
      // submit it (and lifted.js stops a submit anyway); Enter checks every box instead.
      $('dc-form').addEventListener('submit', function () { touchAll(); update(); });
      $('dc-form').addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') { e.preventDefault(); touchAll(); update(); }
      });
      $('dc-example').addEventListener('click', function () {
        $('dc-rg').value = '420'; $('dc-pg').value = '1780'; $('dc-rl').value = '260'; $('dc-pl').value = '2240';
        touchAll(); update();
      });
      $('dc-clear').addEventListener('click', function () { ids.forEach(function (id) { $(id).value = ''; }); touched = {}; update(); });
      update();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(this);
