// answer-ui.js: shows an answer box result (ARCHITECT-V3 §c.5), loaded with answers.js on first use.
// The answer is the unit's own text, inside a <blockquote cite> with its source link, in a polite live
// region; only textContent is written, never HTML. An "answered" result whose citations are empty or not
// units of the index is shown as no_match. On /help/?q=… (the no-JS form's landing page) it answers at once.
(function () {
  'use strict';
  var A = window.DTAnswer;
  function el(tag, text, attrs) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function ok(r) {   // an answer must cite units that exist, at their own URL
    return r.citations && r.citations.length && r.citations.every(function (c) { var u = A.unit(c.id); return u && u.url === c.url; });
  }
  function show(out, r, q, mail) {
    var c, p, ul, m;
    out.textContent = '';
    if (/^(answered|out_of_scope)$/.test(r.status) && !ok(r)) r = {status: 'no_match', citations: []};
    if (r.status === 'answered' || r.status === 'out_of_scope') {
      c = r.citations[0];
      out.appendChild(el('p', 'Answer from ' + c.section, {'class': 'ans-from'}));
      p = el('blockquote', null, {cite: c.url}); p.appendChild(el('p', A.unit(c.id).a)); out.appendChild(p);
      if (r.status === 'out_of_scope') out.appendChild(el('p', A.disclaimer(), {'class': 'small'}));
      p = el('p'); p.appendChild(el('a', 'Read it on its page', {href: c.url})); out.appendChild(p);
    } else if (r.status === 'ambiguous' && r.citations.length) {
      out.appendChild(el('p', 'More than one page may answer that:', {'class': 'ans-from'}));
      ul = el('ul');
      r.citations.forEach(function (x) { var li = el('li'); li.appendChild(el('a', x.q, {href: x.url})); ul.appendChild(li); });
      out.appendChild(ul);
    } else {
      out.appendChild(el('p', 'We have no page that answers that yet.', {'class': 'ans-from'}));
      m = el('p'); m.appendChild(document.createTextNode('Ask us: '));
      m.appendChild(el('a', mail, {href: 'mailto:' + mail + '?subject=' + encodeURIComponent(q)}));
      m.appendChild(document.createTextNode(' · ')); m.appendChild(el('a', 'All questions', {href: '/help/'}));
      out.appendChild(m);
    }
  }
  function wire(box) {
    var f = box.querySelector('form'), out = box.querySelector('[data-answer-out]');
    if (!f || !out || box.dtWired) return;
    box.dtWired = true;
    f.addEventListener('submit', function (e) {
      var q = f.querySelector('input').value;
      e.preventDefault();
      A.ask(q).then(function (r) { show(out, r, q, f.getAttribute('data-mail')); }, function () { f.submit(); });
    });
  }
  A._show = show;
  A._wire = wire;
  [].forEach.call(document.querySelectorAll('[data-answer-box]'), wire);
  var m = /[?&]q=([^&#]*)/.exec(location.search), box = document.querySelector('#ask [data-answer-box]');
  if (m && box) {
    box.querySelector('input').value = decodeURIComponent(m[1].replace(/\+/g, ' ')).slice(0, 200);
    box.querySelector('form').dispatchEvent(new Event('submit', {cancelable: true}));
  }
})();
