// form-ref.js — copies ?ref= and ?product= from the page URL into the matching hidden form
// fields (inputs with data-from-query). The forms work without it: the fields keep their
// default values. Only short lowercase tags are copied; anything else is ignored.
(function () {
  'use strict';
  var params;
  try { params = new URLSearchParams(window.location.search); } catch (e) { return; }
  // Firm products only: the partner form's product is fixed in the HTML (Tester D1).
  var PRODUCTS = ['pilot', 'plan', 'copy-leader', 'claims-test'];
  // 29 Oct (one product): links to the retired products ask about the monthly plan.
  var OLD = { snapshot: 'plan', memo: 'plan', outcomes: 'plan' };
  function apply() {
    var inputs = document.querySelectorAll('input[data-from-query]');
    for (var i = 0; i < inputs.length; i++) {
      var key = inputs[i].getAttribute('data-from-query');
      var v = (params.get(key) || '').toLowerCase();
      if (!/^[a-z0-9-]{1,40}$/.test(v)) continue;
      if (key === 'product' && OLD[v]) v = OLD[v];
      if (key === 'product' && PRODUCTS.indexOf(v) === -1) continue;
      // NIT 9: a field may refuse some products (the enquiry form never becomes a Pilot request)
      var refuse = (inputs[i].getAttribute('data-refuse') || '').split(' ');
      if (refuse.indexOf(v) !== -1) continue;
      inputs[i].value = v;
    }
  }
  // QA 25 Oct: an empty or wrong field gets the site's own message under it (not only the browser's
  // tooltip). Without JavaScript the browser's own required checks still stop the POST.
  function labelOf(el) {
    var fs = el.type === 'radio' && el.closest('fieldset');
    var l = fs ? fs.querySelector('legend') : document.querySelector('label[for="' + el.id + '"]');
    var t = l ? l.textContent.replace(/\(required[^)]*\)/, '').trim() : '';
    return t.replace(/[?.:]$/, '');
  }
  function message(el) {
    if (el.type === 'checkbox') return 'Tick this box to continue.';
    if (el.type === 'radio') return 'Choose one answer.';
    if (el.validity.valueMissing) return labelOf(el) + ' is required.';
    if (el.type === 'email') return 'Enter a full email address, like name@example.com.';
    return 'Check this field.';
  }
  function errBox(el) {
    var key = el.type === 'radio' ? el.name : el.id;
    var id = (el.form.id || 'f') + '-' + key + '-err';
    var box = document.getElementById(id);
    if (!box) {
      box = document.createElement('p');
      box.id = id; box.className = 'field-err small'; box.hidden = true;
      var at = (el.type === 'radio' && el.closest('fieldset')) || el.closest('.field') || el.parentNode;
      at.appendChild(box);
      var d = el.getAttribute('aria-describedby');
      var group = el.type === 'radio' ? el.form.querySelectorAll('input[name="' + el.name + '"]') : [el];
      for (var i = 0; i < group.length; i++) group[i].setAttribute('aria-describedby', (d ? d + ' ' : '') + id);
    }
    return box;
  }
  function check(form) {
    var first = null, seen = {};
    var els = form.querySelectorAll('input[required], textarea[required], select[required]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.type === 'radio') { if (seen[el.name]) continue; seen[el.name] = true; }
      var box = errBox(el), bad = !el.checkValidity();
      box.textContent = bad ? message(el) : ''; box.hidden = !bad;
      if (bad) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
      if (bad && !first) first = el;
    }
    return first;
  }
  function wire() {
    var forms = document.querySelectorAll('form[method="POST"][action*="web3forms"]');
    for (var i = 0; i < forms.length; i++) {
      var f = forms[i];
      f.noValidate = true;
      f.addEventListener('submit', function (e) {
        var first = check(e.currentTarget);
        if (first) { e.preventDefault(); first.focus(); }
      });
      f.addEventListener('change', function (e) {
        if (e.target.getAttribute && e.target.getAttribute('aria-invalid')) check(e.currentTarget);
      });
    }
  }
  function start() { apply(); wire(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
