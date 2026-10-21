// motion.js: fade-up, hero wipe, count-up; any error drops .dt-motion
(function () {
  'use strict';
  var root = document.documentElement;
  if (!root.classList.contains('dt-motion')) return;
  var raf = 0, nums = [], io = null, RV = ['rv', 'rv-in', 'rv-d1', 'rv-d2', 'rv-d3'];

  function done(el) { el.removeAttribute('data-cu'); el.classList.remove('cu-on'); el.classList.add('cu-done'); }
  function stop() {
    root.classList.remove('dt-motion');
    cancelAnimationFrame(raf);
    if (io) io.disconnect();
    nums.forEach(function (n) { done(n.el); });
    [].forEach.call(document.querySelectorAll('.rv'), un);
  }
  function txt(n, v) { return n.pre + v.toFixed(n.dec) + n.post; }
  function count() {
    var t0 = 0;
    raf = requestAnimationFrame(function frame(now) {
      t0 = t0 || now;
      var p = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - p, 3);
      nums.forEach(function (n) { if (p < 1) n.el.setAttribute('data-cu', txt(n, n.to * e)); else done(n.el); });
      raf = p < 1 ? requestAnimationFrame(frame) : 0;
    });
  }
  function un(k) { k.classList.remove.apply(k.classList, RV); }
  function below(el) { return el.getBoundingClientRect().top > innerHeight * 0.9; }
  function parts(el) { return el.hasAttribute('data-reveal-stagger') ? [].slice.call(el.children) : [el]; }
  function show(el) {
    if (el === dash) { el.classList.remove('is-waiting'); if (nums.length) count(); return; }
    var p = parts(el);
    p.forEach(function (k) { k.classList.add('rv-in'); });
    setTimeout(function () { p.forEach(un); }, 800);
  }

  try {
    var nav = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || {};
    var fresh = (nav.type || 'navigate') === 'navigate' && !location.hash, early = fresh && performance.now() < 1000;
    var dash = document.querySelector('.hero-dash');
    io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { io.unobserve(e.target); show(e.target); } });
    }, { rootMargin: '0px 0px -10% 0px' });
    [].forEach.call(document.querySelectorAll('.hero-dash [data-count]'), function (el) {
      var m = early && /^(\D*?)(\d+(?:\.\d+)?)(\D*)$/.exec(el.textContent);
      if (!m) return done(el);
      var n = { el: el, pre: m[1], post: m[3], to: +m[2], dec: (m[2].split('.')[1] || '').length };
      nums.push(n); el.setAttribute('data-cu', txt(n, 0)); el.classList.add('cu-on');
    });
    if (dash && below(dash)) { dash.classList.add('is-waiting'); io.observe(dash); } else if (nums.length) count();
    if (fresh) {
      [].filter.call(document.querySelectorAll('[data-reveal]'), below).forEach(function (el) {
        parts(el).forEach(function (k, i) { k.classList.add('rv'); if (i && i < 4) k.classList.add('rv-d' + i); });
        io.observe(el);
      });
    }
    var mq = matchMedia('(prefers-reduced-motion: reduce)');
    if (mq.addEventListener) mq.addEventListener('change', function (e) { if (e.matches) stop(); });
    addEventListener('beforeprint', stop);
  } catch (err) { stop(); }
})();
