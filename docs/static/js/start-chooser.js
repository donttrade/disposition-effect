// start-chooser.js: the /start/ chooser with JS (ARCHITECT-V3 §c.6, A4). Without it, each choice is a
// link to #<id> and CSS :target shows that section. This only adds: the hash change inside a view
// transition (when the browser has one and motion is allowed), focus on the shown section's heading,
// focus back on the chosen link after Back, and ?product=<id> with no hash opening that section.
// Stores and sends nothing.
(function () {
  'use strict';
  var flow = document.querySelector('[data-start-flow]');
  if (!flow) return;
  var ids = [].map.call(flow.querySelectorAll('.choice'), function (s) { return s.id; });
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
  var last = null;
  function go(hash) {
    var set = function () { location.hash = hash; };
    if (document.startViewTransition && !(reduce && reduce.matches)) document.startViewTransition(set);
    else set();
  }
  flow.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[data-choice], a.choice-back');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    e.preventDefault();
    go(a.getAttribute('href').slice(1));
  });
  // 29 Oct (one product): the retired products' links land on the monthly plan.
  var OLD = { snapshot: 'plan', memo: 'plan', outcomes: 'plan' };
  window.addEventListener('hashchange', function () {
    var id = location.hash.slice(1);
    if (OLD[id]) id = OLD[id];
    if (ids.indexOf(id) !== -1) {
      last = id;
      document.getElementById(id + '-h').focus();
    } else if (last && (id === '' || id === 'firm' || id === 'choose')) {
      flow.querySelector('a[data-choice="' + last + '"]').focus();
    }
  });
  if (!location.hash) {
    var m = /[?&]product=([a-z]+)/.exec(location.search);
    var want = m && (OLD[m[1]] || m[1]);
    if (want && (ids.indexOf(want) !== -1 || want === 'platform' || want === 'trader')) location.replace('#' + want);
  }
})();
