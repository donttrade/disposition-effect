// theme.js — light/dark. Follows prefers-color-scheme unless the visitor picks one
// with the toggle. The choice is the only thing the free site stores, under the
// same key as the v1 site, and every storage call is wrapped: private windows and
// blocked storage must not break the page.
(function () {
  'use strict';
  var KEY = 'donttrade-theme';
  var root = document.documentElement;
  var COLORS = { dark: '#16181C', light: '#FFFFFF' };

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
    function sync() {
      for (var j = 0; j < buttons.length; j++) {
        var dark = current() === 'dark';
        buttons[j].setAttribute('aria-pressed', dark ? 'true' : 'false');
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
