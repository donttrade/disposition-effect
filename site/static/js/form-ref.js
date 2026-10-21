// form-ref.js — copies ?ref= and ?product= from the page URL into the matching hidden form
// fields (inputs with data-from-query). The forms work without it: the fields keep their
// default values. Only short lowercase tags are copied; anything else is ignored.
(function () {
  'use strict';
  var params;
  try { params = new URLSearchParams(window.location.search); } catch (e) { return; }
  var PRODUCTS = ['pilot', 'snapshot', 'memo', 'outcomes', 'copy-leader', 'claims-test', 'platform'];
  function apply() {
    var inputs = document.querySelectorAll('input[data-from-query]');
    for (var i = 0; i < inputs.length; i++) {
      var key = inputs[i].getAttribute('data-from-query');
      var v = (params.get(key) || '').toLowerCase();
      if (!/^[a-z0-9-]{1,40}$/.test(v)) continue;
      if (key === 'product' && PRODUCTS.indexOf(v) === -1) continue;
      inputs[i].value = v;
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply);
  else apply();
})();
