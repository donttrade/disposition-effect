// nav.js: header drop-downs + phone menu (ARCHITECT-V3 B2). All are <details>, so they work without JS.
// Adds: Escape closes and refocuses the summary; focus or a click leaving closes; ArrowDown on an open
// summary focuses its first link; hover intent on a fine pointer only (open 100 ms, close 300 ms after
// leaving; a click within 400 ms of a hover-open keeps it open). Stores and sends nothing.
(function () {
  'use strict';
  function wire() {
    var nav = document.querySelector('.site-nav');
    if (!nav) return;
    var menu = nav.querySelector('[data-nav-menu]');
    var dds = [].slice.call(nav.querySelectorAll('[data-nav-dd]'));
    var mq = function (q) { return window.matchMedia && window.matchMedia(q); };
    var fine = mq('(hover: hover) and (pointer: fine)');
    var mouse = function (e) { return e.pointerType === 'mouse' && fine && fine.matches; };
    var sum = function (d) { return d.querySelector('summary'); };
    var all = function (f) { dds.forEach(f); };
    document.addEventListener('keydown', function (e) {
      var cur = dds.filter(function (d) { return d.open; })[0];
      if (e.key === 'Escape' || e.key === 'Esc') {
        var d = cur || (menu && menu.open && menu);
        if (d) { d.open = false; sum(d).focus(); }
      } else if (e.key === 'ArrowDown' && cur && document.activeElement === sum(cur)) {
        e.preventDefault();
        cur.querySelector('a').focus();
      }
    });
    document.addEventListener('click', function (e) {
      all(function (d) { if (!d.contains(e.target)) d.open = false; });
      if (menu && !menu.contains(e.target)) menu.open = false;
    });
    nav.addEventListener('focusout', function (e) {
      if (e.relatedTarget && !nav.contains(e.relatedTarget)) all(function (d) { d.open = false; });
    });
    all(function (d) {
      var tOpen, tShut, at = 0;
      sum(d).addEventListener('click', function (e) { if (d.open && Date.now() - at < 400) e.preventDefault(); });
      d.parentNode.addEventListener('pointerenter', function (e) {
        if (!mouse(e)) return;
        clearTimeout(tShut);
        if (!d.open) tOpen = setTimeout(function () {
          all(function (o) { o.open = o === d; });   // name="nav" does this too; older browsers do not
          at = Date.now();
        }, 100);
      });
      d.parentNode.addEventListener('pointerleave', function (e) {
        if (!mouse(e)) return;
        clearTimeout(tOpen);
        var a = document.activeElement;
        if (!d.contains(a) || a === sum(d)) tShut = setTimeout(function () { d.open = false; }, 300);
      });
    });
    var wide = mq('(min-width: 900px)');
    var fit = function () {
      if (wide.matches && menu) menu.open = false;
      if (!wide.matches) all(function (d) { d.open = false; });
    };
    if (wide && wide.addEventListener) wide.addEventListener('change', fit);
    else if (wide && wide.addListener) wide.addListener(fit);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
