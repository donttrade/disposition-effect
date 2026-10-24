// ask.js: loads the answer box only when someone uses it (ARCHITECT-V3 §c.5, A3): answers.js and its
// index are fetched as scripts on the first focus of a box, never before. Also the header "Ask" popover:
// Escape closes it and refocuses "Ask"; focus or a click leaving it closes it. Stores and sends nothing.
(function () {
  'use strict';
  var p = null;
  function js(src) {
    return new Promise(function (ok, no) {
      var s = document.createElement('script');
      s.src = src; s.onload = ok; s.onerror = no;
      document.head.appendChild(s);
    });
  }
  function load(box) {   // the engine (answers.js), then its UI (answer-ui.js); the index loads on the first question
    if (window.DTAnswer && window.DTAnswer._wire) return Promise.resolve();
    var f = box.querySelector('form');
    return p || (p = js(f.getAttribute('data-js-src')).then(function () { return js(f.getAttribute('data-ui-src')); }));
  }
  [].forEach.call(document.querySelectorAll('[data-answer-box]'), function (box) {
    var form = box.querySelector('form');
    box.addEventListener('focusin', function () { load(box); });
    form.addEventListener('submit', function (e) {
      if (window.DTAnswer && window.DTAnswer._wire) return;
      e.preventDefault();
      load(box).then(function () { window.DTAnswer._wire(box); form.requestSubmit ? form.requestSubmit() : form.submit(); },
        function () { form.submit(); });
    });
  });
  var d = document.querySelector('[data-ask]');
  if (!d) return;
  var sum = d.querySelector('summary');
  d.addEventListener('toggle', function () { if (d.open) d.querySelector('input').focus(); });
  document.addEventListener('keydown', function (e) {
    if (d.open && (e.key === 'Escape' || e.key === 'Esc')) { d.open = false; sum.focus(); }
  });
  document.addEventListener('click', function (e) { if (d.open && !d.contains(e.target)) d.open = false; });
  d.addEventListener('focusout', function (e) { if (e.relatedTarget && !d.contains(e.relatedTarget)) d.open = false; });
})();
