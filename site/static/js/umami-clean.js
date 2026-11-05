// umami-clean.js: Umami Cloud's data-before-send hook (partials/analytics.html loads it, deferred, just before the
// tracker). Of the address's query it keeps only the four campaign tags our own post links carry, with short lowercase
// values; everything else after "?" (a checkout session id, a typed question, click ids) and all of "#" is dropped, and
// the referrer keeps no query or hash. Anything unexpected: nothing is sent.
(function () {
  'use strict';
  var KEEP = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'];
  var VALUE = /^[a-z0-9][a-z0-9._-]{0,63}$/;
  function address(u) {
    var x = new URL(u, location.href), q = [];
    KEEP.forEach(function (k) {
      var v = x.searchParams.get(k);
      if (v !== null) { v = v.toLowerCase(); if (VALUE.test(v)) q.push(k + '=' + v); }
    });
    return x.origin + x.pathname + (q.length ? '?' + q.join('&') : '');
  }
  function from(r) {
    if (!r) return r;
    var x = new URL(r, location.href);
    return x.origin === location.origin ? x.pathname : x.origin + x.pathname;
  }
  window.dtUmamiClean = function (type, payload) {
    try {
      if (type !== 'event' || !payload || typeof payload !== 'object' || typeof payload.url !== 'string') return false;
      var p = {};
      for (var k in payload) if (Object.prototype.hasOwnProperty.call(payload, k)) p[k] = payload[k];
      p.url = address(p.url);
      if (typeof p.referrer === 'string') p.referrer = from(p.referrer);
      return p;
    } catch (e) { return false; }
  };
})();
