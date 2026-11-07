// band-expiry.js: hides a dated band in the browser on and after its data-expires date (YYYY-MM-DD, UTC).
// The build already leaves the band out on and after that date; this covers a page that was built earlier and is still cached.
(function () {
  var bands = document.querySelectorAll("[data-dated-band][data-expires]");
  var today = new Date().toISOString().slice(0, 10);
  for (var i = 0; i < bands.length; i++) {
    if (today >= bands[i].getAttribute("data-expires")) bands[i].hidden = true;
  }
})();
