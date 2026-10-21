// tabs.js — WAI-ARIA tablist: click or arrow keys switch panels, Home/End jump.
// The URL hash picks the starting tab (#firms opens Firms). Without JS every panel
// is shown stacked, because the build renders them unhidden and this script hides them.
(function () {
  'use strict';
  function init(list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function panelOf(t) { return document.getElementById(t.getAttribute('aria-controls')); }
    function select(t, focus) {
      tabs.forEach(function (x) {
        var on = x === t;
        x.setAttribute('aria-selected', on ? 'true' : 'false');
        x.tabIndex = on ? 0 : -1;
        var p = panelOf(x);
        if (p) p.hidden = !on;
      });
      if (focus) t.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(t, false); });
      t.addEventListener('keydown', function (e) {
        var k = e.key, n = null;
        if (k === 'ArrowRight') n = tabs[(i + 1) % tabs.length];
        else if (k === 'ArrowLeft') n = tabs[(i - 1 + tabs.length) % tabs.length];
        else if (k === 'Home') n = tabs[0];
        else if (k === 'End') n = tabs[tabs.length - 1];
        if (n) { e.preventDefault(); select(n, true); }
      });
    });
    var start = tabs[0];
    var hash = window.location.hash.slice(1);
    tabs.forEach(function (t) { if (hash && t.getAttribute('data-hash') === hash) start = t; });
    select(start, false);
  }
  function run() { Array.prototype.forEach.call(document.querySelectorAll('[role="tablist"]'), init); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
