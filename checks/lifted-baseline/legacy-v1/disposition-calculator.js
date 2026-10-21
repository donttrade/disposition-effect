/* Disposition-effect calculator. Runs entirely in the browser; nothing is sent anywhere. */
(function (root) {
  'use strict';

  function parseCount(raw) {
    var s = String(raw == null ? '' : raw).replace(/[,\s]/g, '');
    if (s === '') return { ok: false, error: 'empty' };
    if (!/^\d+$/.test(s)) return { ok: false, error: 'not a whole number of zero or more' };
    var n = parseInt(s, 10);
    if (n > 1e12) return { ok: false, error: 'too large' };
    return { ok: true, value: n };
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

  var api = { parseCount: parseCount, compute: compute, fmt: fmt };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

  if (typeof document !== 'undefined') {
    var ids = ['dc-rg', 'dc-pg', 'dc-rl', 'dc-pl'];
    var $ = function (id) { return document.getElementById(id); };
    var update = function () {
      var vals = [], errs = [], anyFilled = false, i, p;
      var names = ['Realised gains', 'Paper gains', 'Realised losses', 'Paper losses'];
      for (i = 0; i < 4; i++) {
        var el = $(ids[i]);
        el.removeAttribute('aria-invalid');
        if (String(el.value).replace(/\s/g, '') === '') { errs.push(names[i] + ' is empty. Enter a whole number, or 0.'); el.setAttribute('aria-invalid', 'true'); continue; }
        anyFilled = true;
        p = parseCount(el.value);
        if (!p.ok) { errs.push(names[i] + ' must be a whole number of zero or more (no decimals, no minus sign).'); el.setAttribute('aria-invalid', 'true'); } else vals.push(p.value);
      }
      var msg = $('dc-msg'), outBox = $('dc-results');
      var setOut = function (k, v) { var e = $('dc-' + k); e.textContent = v; e.className = v === 'not defined' || v === '–' ? 'na' : ''; };
      var clear = function () { ['pgr', 'plr', 'ratio', 'diff', 'se', 't'].forEach(function (k) { setOut(k, '–'); }); $('dc-reading').textContent = ''; };
      if (!anyFilled) { msg.textContent = ''; clear(); outBox.hidden = true; return; }
      if (errs.length) { msg.textContent = errs.join(' '); clear(); outBox.hidden = true; return; }
      var r = compute(vals[0], vals[1], vals[2], vals[3]);
      if (!r.ok) { msg.textContent = r.errors.join(' '); clear(); outBox.hidden = true; return; }
      msg.textContent = r.notes.join(' ');
      outBox.hidden = false;
      setOut('pgr', fmt(r.pgr, 4)); setOut('plr', fmt(r.plr, 4)); setOut('ratio', fmt(r.ratio, 2));
      setOut('diff', fmt(r.diff, 4)); setOut('se', fmt(r.se, 4)); setOut('t', fmt(r.t, 2));
      $('dc-reading').textContent = r.reading;
    };
    var init = function () {
      if (!$('dc-rg')) return;
      ids.forEach(function (id) { $(id).addEventListener('input', update); });
      $('dc-example').addEventListener('click', function () {
        $('dc-rg').value = '420'; $('dc-pg').value = '1780'; $('dc-rl').value = '260'; $('dc-pl').value = '2240';
        update();
      });
      $('dc-clear').addEventListener('click', function () { ids.forEach(function (id) { $(id).value = ''; }); update(); });
      update();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  }
})(this);
