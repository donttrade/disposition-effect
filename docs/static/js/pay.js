// pay.js — the site-wide pay dialog (29 Oct, owner: "the whole website always one click away from paying").
// Paid builds only (partials/pay_dialog.html). A click on any buy link (a[data-pay], or a link to
// /pricing/#last-step) opens the <dialog> on the current page instead of leaving it; without JavaScript, or in a
// browser without <dialog>, the link works as before. Esc and the close button close it; focus goes back to the
// link that opened it. "Full details before you pay" copies the #before-you-pay block on demand (from this page when
// it has one, as /pricing/ does, else from a hidden same-origin frame of /before-you-pay/, removed once read), so only
// build.ADDRESS_LINE_PATHS carry the seller's address in their HTML and no page needs connect-src. /before-you-pay/
// loads no analytics, so opening the details is not counted as a pageview of /pricing/ or any page. Stores nothing;
// with Umami on, opening the dialog sends Umami the fixed event name pay-open, nothing else.
(function () {
  'use strict';
  // /pricing/'s #last-step and #byp-more <details> are open in the HTML (for visitors without JavaScript). Close each
  // unless the URL targets it or an element inside it; .ls-ready hands it back to site.css's normal rules.
  var id = '';
  try { id = decodeURIComponent(location.hash.slice(1)); } catch (e) { /* a malformed hash targets nothing */ }
  var t = id && document.getElementById(id);
  ['last-step', 'byp-more'].forEach(function (name) {
    var d = document.getElementById(name);
    if (!d || d.tagName !== 'DETAILS') return;
    if (!(t && d.contains(t))) d.open = false;
    d.classList.add('ls-ready');
  });
  // Umami Cloud (2 Nov): the fixed event name pay-continue when a Stripe link (data-pay-continue) is clicked. Not a
  // data-umami-event attribute: on a link, Umami's own handler cancels the click and follows it only once its request
  // to gateway.umami.is settles, so a slow or hanging gateway would hold up the payment. This listener never calls
  // preventDefault: the browser follows the link at once, and the request (keepalive) goes on by itself.
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[data-pay-continue]') : null;
    if (!a) return;
    try { if (window.umami && typeof window.umami.track === 'function') window.umami.track('pay-continue'); } catch (err) { /* counting never blocks paying */ }
  }, true);
  // 6 Nov (Round A6): partner links. A link like /pricing/?via=<slug> carries the partner's slug only; the code and the
  // name come from the allow-list the build puts in <meta name="dt-partners"> (active partners only), never from the
  // URL, so an unknown, inactive, upper-case-trick or overlong ?via= changes nothing and shows nothing. For a known
  // slug, in memory only (nothing is stored, no cookie, no localStorage): every Stripe link on the page gets the
  // promotion code (prefilled_promo_code) and a client_reference_id ending _p-<slug> (letters, digits, - and _ only,
  // as Stripe allows), and the pay panel says, before the buyer pays, that the code is applied and that the partner
  // earns a commission. The text is set with textContent; no HTML comes from the URL or the meta.
  (function () {
    var meta = document.querySelector('meta[name="dt-partners"]');
    if (!meta || typeof URL !== 'function') return;
    var cfg, via = '';
    try {
      cfg = JSON.parse(meta.getAttribute('content'));
      via = (new URLSearchParams(location.search).get('via') || '').toLowerCase();
    } catch (e) { return; }
    if (!cfg || !cfg.p || !/^[a-z0-9-]{2,30}$/.test(via) || !Object.prototype.hasOwnProperty.call(cfg.p, via)) return;
    var code = cfg.p[via][0], name = cfg.p[via][1], applied = 0;
    var links = document.querySelectorAll('a[data-pay-continue]');
    for (var i = 0; i < links.length; i++) {
      try {
        var u = new URL(links[i].getAttribute('href'), location.href);
        if (u.hostname !== 'buy.stripe.com') continue;
        u.searchParams.set('prefilled_promo_code', code);
        u.searchParams.set('client_reference_id', ((u.searchParams.get('client_reference_id') || 'site') + '_p-' + via).slice(0, 200));
        links[i].setAttribute('href', u.toString());
        applied++;
      } catch (e) { /* a link we cannot read is left as it was */ }
    }
    if (!applied) return;
    var notes = document.querySelectorAll('[data-partner-note]');
    for (var j = 0; j < notes.length; j++) {
      notes[j].textContent = (document.documentElement.lang === 'fr'
        ? 'Le code de partenaire ' + code + ' sera appliqué sur la page de paiement : ' + cfg.d + ' % de rabais. ' + name + ' gagne une commission si vous achetez.'
        : 'Partner code ' + code + ' will be applied on the payment page: ' + cfg.d + '% off. ' + name + ' earns a commission if you buy.');
      notes[j].hidden = false;
    }
  })();
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
    // /before-you-pay/ gives the heading as an h2 (under its h1); in the dialog it sits under the dialog's h2
    var hd = copy.querySelector('#pd-byp-h');
    if (hd && hd.tagName !== 'H3') {
      var h3 = document.createElement('h3');
      [].slice.call(hd.attributes).forEach(function (a) { h3.setAttribute(a.name, a.value); });
      while (hd.firstChild) h3.appendChild(hd.firstChild);
      hd.replaceWith(h3);
    }
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
    // Umami Cloud (2 Nov): the fixed event name pay-open. Not a data-umami-event attribute on the buy links: Umami's
    // own click handler would cancel this one and follow the link to /pricing/#last-step instead of the dialog.
    try { if (window.umami && typeof window.umami.track === 'function') window.umami.track('pay-open'); } catch (err) { /* counting never blocks paying */ }
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
