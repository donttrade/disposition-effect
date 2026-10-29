// pay.js — the site-wide pay dialog (29 Oct, owner: "the whole website always one click away from paying").
// Paid builds only (partials/pay_dialog.html). A click on any buy link (a[data-pay], or a link to
// /pricing/#last-step) opens the <dialog> on the current page instead of leaving it; without JavaScript, or in a
// browser without <dialog>, the link works as before. Esc and the close button close it; focus goes back to the
// link that opened it. "Full details before you pay" copies the #before-you-pay block on demand (from this page when
// it has one, as /pricing/ does, else from a hidden same-origin frame of /before-you-pay/, removed once read), so only
// build.ADDRESS_LINE_PATHS carry the seller's address in their HTML and no page needs connect-src. /before-you-pay/
// loads no analytics, so opening the details is not counted as a pageview of /pricing/ or any page. Stores and sends nothing.
(function () {
  'use strict';
  var dlg = document.getElementById('pay-dialog');
  if (!dlg || typeof dlg.showModal !== 'function') return;
  var opener = null, loaded = false;
  var full = dlg.querySelector('[data-pay-full]');
  var more = dlg.querySelector('[data-pay-more]');

  function isBuy(a) {
    if (a.hasAttribute('data-pay')) return true;
    var h = a.getAttribute('href') || '';
    return h === '/pricing/#last-step' || (location.pathname === '/pricing/' && h === '#last-step' && a.tagName === 'A');
  }

  // the block, ids renamed so the copy never duplicates /pricing/'s own ids
  function place(node) {
    var copy = document.importNode(node, true);
    var nodes = [copy].concat([].slice.call(copy.querySelectorAll('[id]')));
    nodes.forEach(function (n) { if (n.id) n.id = 'pd-' + n.id; });
    [copy].concat([].slice.call(copy.querySelectorAll('[aria-labelledby]'))).forEach(function (n) {
      var v = n.getAttribute('aria-labelledby');
      if (v) n.setAttribute('aria-labelledby', v.split(/\s+/).map(function (x) { return 'pd-' + x; }).join(' '));
    });
    copy.removeAttribute('data-requires-flag');
    full.replaceChildren(copy);
    loaded = true;
  }

  function load() {
    if (loaded) return;
    var here = document.getElementById('before-you-pay');   // never the copy: its ids start with pd-
    if (here) { place(here); return; }
    var f = document.createElement('iframe');
    f.setAttribute('aria-hidden', 'true');
    f.setAttribute('tabindex', '-1');
    f.title = 'Before you pay';
    f.className = 'pd-frame';
    var done = false;
    var stop = setTimeout(function () { done = true; f.remove(); }, 10000);   // the link to /pricing/ stays
    f.addEventListener('load', function () {
      if (done) return;
      done = true; clearTimeout(stop);
      try {
        var n = f.contentDocument && f.contentDocument.getElementById('before-you-pay');
        if (n) place(n);
      } catch (e) { /* the link to /pricing/#before-you-pay stays */ }
      f.remove();
    });
    f.src = '/before-you-pay/';
    document.body.append(f);
  }

  document.addEventListener('click', function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || dlg.contains(a) || !isBuy(a)) return;
    e.preventDefault();
    var menu = a.closest('details.nav-menu');
    if (menu) { menu.open = false; opener = menu.querySelector('summary'); } else opener = a;
    dlg.showModal();
    document.documentElement.classList.add('pd-open');
  });
  dlg.addEventListener('close', function () {
    document.documentElement.classList.remove('pd-open');
    if (opener && opener.focus) opener.focus();
    opener = null;
  });
  dlg.addEventListener('click', function (e) {
    if (e.target === dlg) { dlg.close(); return; }   // the backdrop
    if (e.target.closest('[data-pay-close]')) { dlg.close(); return; }
    var p = e.target.closest('[data-print]');
    if (p) { e.stopPropagation(); window.print(); }   // print.js would print too on /pricing/
  });
  if (more) more.addEventListener('toggle', function () { if (more.open) load(); });
  window.addEventListener('beforeprint', function () { if (dlg.open && more) more.open = true; });
})();
