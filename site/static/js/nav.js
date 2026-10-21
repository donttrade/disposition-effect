// nav.js — the phone menu in the shared header (Manager V3). The menu is a <details>, so it opens
// and closes without JavaScript; this only adds what a menu button is expected to do:
//   * Escape closes it and puts focus back on "Menu";
//   * a click or tap outside the header closes it;
//   * it closes when the window grows to the desktop layout (the nav row is shown there).
// Nothing is stored and nothing is sent.
(function () {
  'use strict';
  function wire() {
    var menu = document.querySelector('[data-nav-menu]');
    if (!menu) return;
    var summary = menu.querySelector('summary');
    document.addEventListener('keydown', function (e) {
      if (menu.open && (e.key === 'Escape' || e.key === 'Esc')) {
        menu.open = false;
        summary.focus();
      }
    });
    document.addEventListener('click', function (e) {
      if (menu.open && !menu.contains(e.target)) menu.open = false;
    });
    if (window.matchMedia) {
      var wide = window.matchMedia('(min-width: 900px)');
      var shut = function () { if (wide.matches) menu.open = false; };
      if (wide.addEventListener) wide.addEventListener('change', shut);
      else if (wide.addListener) wide.addListener(shut);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
