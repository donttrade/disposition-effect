// print.js — [data-print] buttons print the page (no inline handlers: the CSP forbids them).
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('[data-print]') : null;
  if (b) window.print();
});
// 25 Oct: the "Before you pay" block sits in a <details> on /pricing/: open it for any print, so it prints.
window.addEventListener('beforeprint', function () {
  [].forEach.call(document.querySelectorAll('[data-print]'), function (b) {
    for (var d = b.closest ? b.closest('details') : null; d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
  });
});
