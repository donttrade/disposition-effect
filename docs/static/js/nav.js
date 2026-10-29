// nav.js: the phone menu (a <details>, so it works without JS). 29 Oct (owner): the header has no drop-downs.
// Adds: Escape closes the menu and refocuses its button; a click or focus leaving it closes it; it closes when
// the window grows past the phone layout. Stores and sends nothing.
(function () {
  'use strict';
  function wire() {
    var nav = document.querySelector('.site-nav');
    var menu = nav && nav.querySelector('[data-nav-menu]');
    if (!menu) return;
    var sum = menu.querySelector('summary');
    document.addEventListener('keydown', function (e) {
      if ((e.key === 'Escape' || e.key === 'Esc') && menu.open) { menu.open = false; sum.focus(); }
    });
    document.addEventListener('click', function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    menu.addEventListener('focusout', function (e) {
      if (e.relatedTarget && !menu.contains(e.relatedTarget)) menu.open = false;
    });
    var wide = window.matchMedia && window.matchMedia('(min-width: 900px)');
    var fit = function () { if (wide.matches) menu.open = false; };
    if (wide && wide.addEventListener) wide.addEventListener('change', fit);
    else if (wide && wide.addListener) wide.addListener(fit);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
