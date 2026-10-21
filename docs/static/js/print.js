// print.js — [data-print] buttons print the page (no inline handlers: the CSP forbids them).
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('[data-print]') : null;
  if (b) window.print();
});
