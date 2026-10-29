// theme.js — light/dark. Follows prefers-color-scheme unless the visitor picks one
// with the toggle. The choice is the only thing the free site stores, under the
// same key as the v1 site, and every storage call is wrapped: private windows and
// blocked storage must not break the page.
(function () {
  'use strict';
  var KEY = 'donttrade-theme';
  var root = document.documentElement;
  var COLORS = { dark: '#16181C', light: '#FFFFFF' };
  try { // motion: decided before first paint (this file blocks in <head>); motion.js and site.css read it
    if (window.matchMedia('(prefers-reduced-motion: no-preference)').matches && 'IntersectionObserver' in window) {
      root.classList.add('dt-motion');
      // failsafe for the hero numbers (site.css hides them under .dt-motion:not(.dt-fs)): shown 800 ms after
      // navigation start unless motion.js has claimed them for the count by then. A class, not a CSS
      // animation, so nothing runs off the compositor (Lighthouse "non-composited animations").
      setTimeout(function () { root.classList.add('dt-fs'); }, 800 - performance.now());
    }
  } catch (e) { /* no motion */ }

  function setMeta(t) {
    var m = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < m.length; i++) m[i].setAttribute('content', COLORS[t]);
  }
  try {
    var saved = window.localStorage.getItem(KEY);
    if (saved === 'dark' || saved === 'light') { root.setAttribute('data-theme', saved); setMeta(saved); }
  } catch (e) { /* storage blocked: follow the system setting */ }

  function current() {
    var a = root.getAttribute('data-theme');
    if (a) return a;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function wire() {
    var buttons = document.querySelectorAll('[data-theme-toggle]');
    // QA 25 Oct: the button is named by what it does ("Light mode" while dark is on). A label that
    // changes carries the state itself, so the button has no aria-pressed (APG button pattern).
    function sync() {
      var dark = current() === 'dark';
      for (var j = 0; j < buttons.length; j++) {
        var label = buttons[j].querySelector('.tt-label');
        if (label) label.textContent = dark ? 'Light mode' : 'Dark mode';
      }
    }
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].addEventListener('click', function () {
        var next = current() === 'dark' ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        try { window.localStorage.setItem(KEY, next); } catch (e) { /* not saved; still switches */ }
        setMeta(next);
        sync();
      });
      buttons[i].hidden = false; // the toggle needs JS, so it stays hidden without it
    }
    sync();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
// 25 Oct: a link to an id inside a collapsed <details> (the /pricing/ last step and price history, the
// long terms sections) opens it, on load and on hashchange. Here because every page loads theme.js.
(function () {
  'use strict';
  function openHash() {
    var id = decodeURIComponent((location.hash || '').slice(1));
    var el = id && document.getElementById(id);
    if (!el || !el.closest) return;
    var any = false;
    for (var d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) {
      if (d.closest('.site-nav')) break;
      if (!d.open) { d.open = true; any = true; }
    }
    if (any) el.scrollIntoView();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', openHash);
  else openHash();
  window.addEventListener('hashchange', openHash);
  // sweep 3 (29 Oct): the folded sections of /terms/ and /privacy/ all print open
  window.addEventListener('beforeprint', function () {
    [].forEach.call(document.querySelectorAll('details.legal-sec'), function (d) { d.open = true; });
  });
})();
