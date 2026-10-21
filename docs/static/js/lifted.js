// lifted.js — the small behaviours of the pages lifted from the pre-v2 site (plan steps 28–29),
// which their old inline <head> script and inline attributes provided. The v2 CSP allows no
// inline script, so they live here:
//   * "Scroll sideways" hints disappear when their table fits (class "fits");
//   * "Copy address" buttons copy, or select the address when the clipboard is refused;
//   * the old calculators' forms never submit (they had onsubmit="return false").
// Nothing is stored and nothing is sent.
(function () {
  'use strict';

  function wire() {
    var hints = document.querySelectorAll('.scroll-hint');
    function fit() {
      for (var j = 0; j < hints.length; j++) {
        var t = hints[j].nextElementSibling;
        if (t) hints[j].classList.toggle('fits', t.scrollWidth <= t.clientWidth + 1);
      }
    }
    fit();
    window.addEventListener('resize', fit);
    window.addEventListener('load', fit);

    var copies = document.querySelectorAll('button.copy[data-copy]');
    for (var i = 0; i < copies.length; i++) {
      (function (c) {
        c.hidden = false;
        function fail() {
          var blk = c.parentNode, a = blk.querySelector('.addr'), m = blk.querySelector('.copy-msg');
          if (a && window.getSelection) {
            var r = document.createRange();
            r.selectNodeContents(a);
            var sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(r);
          }
          if (!m) {
            m = document.createElement('p');
            m.className = 'copy-msg';
            m.setAttribute('role', 'status');
            blk.appendChild(m);
          }
          m.textContent = 'Copy failed — select the address above and copy it.';
        }
        c.addEventListener('click', function () {
          if (!navigator.clipboard || !navigator.clipboard.writeText) { fail(); return; }
          navigator.clipboard.writeText(c.getAttribute('data-copy')).then(function () {
            var o = c.textContent;
            c.textContent = 'Copied';
            setTimeout(function () { c.textContent = o; }, 2000);
          }, fail);
        });
      })(copies[i]);
    }

    var calcs = document.querySelectorAll('form.calc');
    for (var k = 0; k < calcs.length; k++) {
      calcs[k].addEventListener('submit', function (e) { e.preventDefault(); });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
