// tools-index.js (6 Nov, tools redesign B2): the only motion script on /tools/ and the tool pages. No dependency.
// 1. Each /tools/ module (.tl) and each tool-page display (.tool-display) plays its drawing once when it is half in
//    view (class .play; the keyframes are in tools.css). A tool page's glyph (.tool-mark) plays once on load.
// 2. [data-scope] (the /tools/ hero): a cursor sweeps the real equity curve once to its deepest point (2.4 s, eased
//    in and out, from 0.5 s after load), then the pointer scrubs any trade. Only SVG transform attributes and
//    textContent are written (the CSP has no 'unsafe-inline'), the readout only when the trade changes.
// Reduced motion: nothing plays, and the scope rests on the deepest point, as the HTML shows; turned on mid-sweep,
// the sweep stops there.
(function () {
  'use strict';
  var mq = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var reduce = !!(mq && mq.matches);

  function start() {
    if (!reduce) {
      document.querySelectorAll('.tool-mark').forEach(function (m) { m.classList.add('play'); });
      if ('IntersectionObserver' in window) {
        var io = new IntersectionObserver(function (es) {
          es.forEach(function (e) {
            if (e.isIntersecting) { e.target.classList.add('play'); io.unobserve(e.target); }
          });
        }, { threshold: 0.5 });
        document.querySelectorAll('.tl, .tool-display').forEach(function (el) { io.observe(el); });
      }
    }
    document.querySelectorAll('[data-scope]').forEach(scope);
  }

  function money(v) {
    var s = Math.abs(v).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (v < -0.004 ? '−$' : v > 0.004 ? '+$' : '$') + s;
  }

  function scope(el) {
    var curve = el.getAttribute('data-curve').split(',').map(Number);
    var months = (el.getAttribute('data-months') || '').split(',');
    var n = curve.length, peaks = [], p = 0;
    curve.forEach(function (v) { p = Math.max(p, v); peaks.push(p); });
    var a = function (k) { return +el.getAttribute('data-' + k); };
    var x0 = a('x0'), x1 = a('x1'), y0 = a('y0'), y1 = a('y1'), lo = a('lo'), hi = a('hi');
    var q = function (s) { return el.querySelector(s); };
    var cur = q('.sc-cursor'), dot = q('.sc-dot'), fut = q('.sc-future'), svg = q('svg');
    var out = { n: q('[data-out="n"]'), m: q('[data-out="m"]'), eq: q('[data-out="eq"]'), dd: q('[data-out="dd"]') };
    var deepest = 0, dmin = 0, shown = -1;
    curve.forEach(function (v, i) { if (v - peaks[i] < dmin) { dmin = v - peaks[i]; deepest = i; } });
    function show(i) {
      i = Math.max(0, Math.min(n - 1, Math.round(i)));
      if (i === shown) return;
      shown = i;
      var x = (x0 + (x1 - x0) * i / (n - 1)).toFixed(1);
      var y = (y1 - (curve[i] - lo) / (hi - lo) * (y1 - y0)).toFixed(1);
      cur.setAttribute('transform', 'translate(' + x + ' 0)');
      // the future mask spans the plot, scaled from its right edge; the dot sits at 0,0
      fut.setAttribute('transform', 'translate(' + x1 + ' 0) scale(' + ((x1 - x) / (x1 - x0)).toFixed(4) + ' 1) translate(' + (-x1) + ' 0)');
      dot.setAttribute('transform', 'translate(' + x + ' ' + y + ')');
      out.n.textContent = String(i + 1);
      if (months[i]) out.m.textContent = months[i];
      out.eq.textContent = money(curve[i]);
      var d = curve[i] - peaks[i];
      out.dd.textContent = d < -0.005 ? money(d) : 'at a high';
    }
    if (reduce || !svg || !cur) return;   // the HTML already rests on the deepest point
    fut.setAttribute('x', x0); fut.setAttribute('width', x1 - x0);
    dot.setAttribute('cx', 0); dot.setAttribute('cy', 0);
    var t0 = null, user = false;
    function step(t) {
      if (user) return;
      if (t0 === null) t0 = t;
      var k = Math.min(1, (t - t0) / 2400);
      show((k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2) * deepest);   // ease in and out (cubic)
      if (k < 1) requestAnimationFrame(step);
    }
    if (mq && mq.addEventListener) {
      mq.addEventListener('change', function (e) { if (e.matches && !user) { user = true; show(deepest); } });
    }
    show(0);
    setTimeout(function () { if (!user) requestAnimationFrame(step); }, 500);
    svg.addEventListener('pointermove', function (ev) {
      user = true;
      var r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal;
      show(((ev.clientX - r.left) / r.width * vb.width - x0) / (x1 - x0) * (n - 1));
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
