// answers.js: the answer box (ARCHITECT-V3 §c.5). Matches a question to an EXISTING answer in
// window.DT_ANSWERS (answers-index.js, the pages' own text) and shows it word for word with its link.
// No AI, no network, no storage. DTAnswer.ask(q) → Promise<{status, text, citations, engine}>,
// status answered|ambiguous|no_match|out_of_scope; the out-of-scope guard runs first. BM25 over
// question (×3) + answer, × (0.5 + share of the query's words in the question), × 2 for the exact question;
// answered needs score ≥ T, ≥ 1.25 × the next, and under a third of the query's words unknown to every page
// (T and the rest calibrated on tests/fixtures/answers_queries.json).
(function () {
  'use strict';
  var T = 4, LEAD = 1.25, UNK = 0.34, K1 = 1.2, B = 0.75, E = 'index-v1', idx = null, D = null, ld = null;
  var STOP = ('a an the is are was were be been to of in on for and or i my me we us our you your it its this that ' +
    'do does did can could how what when where which who why with at by from as if will would there their about ' +
    'into than then so just get got any some here am have has had also only please tell work works know').split(' ');
  var OUT = [/\bshould (i|we) (buy|sell|short|go long|hold|enter|exit|close|trade|take|join|use)\b/,
    /\bwhich (stock|share|pair|coin|crypto|currency|firm|prop firm|broker|etf|asset)s? (is|are) (the )?(best|good)\b/,
    /\bwhich (stock|share|pair|coin|crypto|currency|firm|prop firm|broker|etf|asset)s? (should|to)\b/,
    /\b(what|how much|how many|which) (lot|lots|size|position size|leverage|risk)\b.*\bshould\b/,
    /\bsignals?\b/, /\bis .* a good (trade|firm|buy|investment|broker|stock|entry)\b/, /\b(buy|sell) or (sell|hold|buy)\b/,
    /\bwill .* (go up|go down|rise|fall|crash|pump)\b/, /\bbest (strategy|setup|entry|stock|pair|coin|broker|prop firm)\b/,
    /\b(price target|where should i put)\b/];
  function stem(w) {
    if (w.length > 4 && /ies$/.test(w)) w = w.slice(0, -3) + 'y';
    else if (/sses$/.test(w)) w = w.slice(0, -2);
    else if (w.length > 5 && /ing$/.test(w)) w = w.slice(0, -3);
    else if (w.length > 4 && /ed$/.test(w)) w = w.slice(0, -2);
    else if (w.length > 4 && /(s|x|z|ch|sh)es$/.test(w)) w = w.slice(0, -2);
    else if (w.length > 3 && /[^s]s$/.test(w)) w = w.slice(0, -1);
    return w.length > 3 && /e$/.test(w) ? w.slice(0, -1) : w;
  }
  function norm(s) {
    return (s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[’']/g, '')
      .replace(/[^a-z0-9$%]+/g, ' ').trim();
  }
  function toks(s) { return norm(s).split(' ').filter(function (w) { return w && STOP.indexOf(w) < 0; }).map(stem); }
  function syn(q) {   // [answers.synonyms]: a phrase in the question is replaced by the site's word for it
    var s = ' ' + norm(q) + ' ', m = D.synonyms || {};
    Object.keys(m).forEach(function (k) { s = s.split(' ' + norm(k) + ' ').join(' ' + m[k] + ' '); });
    return s;
  }
  function tf(l) { var m = {}; l.forEach(function (t) { m[t] = (m[t] || 0) + 1; }); return m; }
  function build() {
    var lq = 0, la = 0, df = {};
    var docs = D.units.map(function (u) {
      var q = toks(u.q), a = toks(u.a);
      lq += q.length; la += a.length;
      Object.keys(tf(q.concat(a))).forEach(function (t) { df[t] = (df[t] || 0) + 1; });
      return {u: u, q: tf(q), a: tf(a), lq: q.length, la: a.length};
    });
    idx = {docs: docs, n: docs.length, aq: lq / docs.length, aa: la / docs.length, df: df};
  }
  function bm(f, l, avg) { return f ? f * (K1 + 1) / (f + K1 * (1 - B + B * l / avg)) : 0; }
  function rank(q) {
    var ts = Object.keys(tf(toks(syn(q))));
    return idx.docs.map(function (d) {
      var s = 0, inQ = 0, unk = 0;
      ts.forEach(function (t) {
        if (d.q[t]) inQ++;
        if (!idx.df[t]) { unk++; return; }
        s += Math.log(1 + (idx.n - idx.df[t] + 0.5) / (idx.df[t] + 0.5)) * (3 * bm(d.q[t], d.lq, idx.aq) + bm(d.a[t], d.la, idx.aa));
      });
      return {u: d.u, s: ts.length ? s * (0.5 + inQ / ts.length) * (norm(q) === norm(d.u.q) ? 2 : 1) : 0, c: ts.length ? unk / ts.length : 1};
    }).sort(function (x, y) { return y.s - x.s; });
  }
  function cite(u) { return {id: u.id, q: u.q, url: u.url, section: u.section}; }
  function byId(id) { return D.units.filter(function (u) { return u.id === id; })[0]; }
  function result(q) {
    var n = norm(q), r, top, adv;
    if (OUT.some(function (x) { return x.test(n); })) {
      adv = byId(D.advice);
      return {status: 'out_of_scope', text: adv.a, citations: [cite(adv)], engine: E, disclaimer: D.disclaimer};
    }
    r = n ? rank(q) : [];
    top = r[0];
    if (!top || top.s < T || top.c >= UNK) return {status: 'no_match', text: null, citations: [], engine: E};
    if (top.s >= LEAD * (r[1] || {s: 0}).s) return {status: 'answered', text: top.u.a, citations: [cite(top.u)], engine: E};
    return {status: 'ambiguous', text: null, engine: E, citations: r.slice(0, 3).filter(function (x) {
      return x.s >= T && x.c < UNK; }).map(function (x) { return cite(x.u); })};
  }
  function load() {
    if (window.DT_ANSWERS) return Promise.resolve();
    return ld || (ld = new Promise(function (ok, no) {
      var f = document.querySelector('[data-index-src]'), s = document.createElement('script');
      if (!f) return no();
      s.src = f.getAttribute('data-index-src'); s.onload = ok; s.onerror = no;
      document.head.appendChild(s);
    }));
  }
  function ask(q) {
    return load().then(function () {
      if (D !== window.DT_ANSWERS) { D = window.DT_ANSWERS; build(); }
      return result(String(q).slice(0, 200));
    });
  }
  function byIdPub(id) { return D && byId(id); }
  window.DTAnswer = {ask: ask, unit: byIdPub, disclaimer: function () { return D && D.disclaimer; },
    _rank: function (q) { return rank(q).slice(0, 3).map(function (x) { return [x.u.id, +x.s.toFixed(2), +x.c.toFixed(2)]; }); }};
})();
