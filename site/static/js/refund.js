// refund.js — the refund request form (6 Nov 2026, Round A8; ARCHITECT-ADDENDUM-REFUNDS §3.4). ES5, no dependencies.
// 1. "Something else" makes the note required (the form works without this: then the note stays optional).
// 2. On a valid submit, with Umami on, it sends the fixed event name refund-reason-<slug> for the radio picked, and
//    nothing else: no email, no order reference, no note, no event data. The slug must be in REASONS, the same nine
//    as site/config/refund_reasons.json (tests/test_refund.py holds the two equal); anything else sends nothing.
// It never calls preventDefault, so a failed count cannot stop the request, and it stores nothing in the browser.
// Register after form-ref.js (script order): form-ref.js stops an invalid submit, and this file then sees
// defaultPrevented and counts nothing.
(function () {
  'use strict';
  var REASONS = ['unreadable', 'wont-run', 'nothing-tested', 'not-run', 'mistake', 'unrecognised', 'disagree', 'expected-other', 'other'];
  var form = document.getElementById('refund-form');
  if (!form) return;
  var detail = form.querySelector('textarea[name="detail"]');

  function picked() {
    var el = form.querySelector('input[name="reason"]:checked');
    return el ? el.value : '';
  }

  function sync() {
    if (!detail) return;
    if (picked() === 'other') detail.setAttribute('required', ''); else detail.removeAttribute('required');
  }

  form.addEventListener('change', sync);
  sync();

  form.addEventListener('submit', function (e) {
    if (e.defaultPrevented) return;
    var v = picked();
    if (REASONS.indexOf(v) === -1) return;
    try {
      if (window.umami && typeof window.umami.track === 'function') window.umami.track('refund-reason-' + v);
    } catch (err) { /* counting never blocks the request */ }
  });
})();
