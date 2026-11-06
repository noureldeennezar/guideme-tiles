// legal.js - the ONE place to fill in before you publish the privacy / terms / delete-account pages.
// Upload it to the same place as the three .html files (the guideme-tiles repo root).
window.GUIDEME_LEGAL = {
  developer: 'Noureldeen-Nezar',      // exactly as it appears as the developer name on your Google Play listing
  email: 'Noureldeennezar@gmail.com',          // a real inbox you read; people will write here about privacy and deleting accounts
  country: 'Egypt',                              // where you are based (used in the Terms)
  updated: '2026-11-06'                          // change this date whenever you change the text of a page
};
(function () {
  var L = window.GUIDEME_LEGAL;
  function fill() {
    var set = function (sel, fn) { var n = document.querySelectorAll(sel); for (var i = 0; i < n.length; i++) fn(n[i]); };
    set('[data-fill="developer"]', function (e) { e.textContent = L.developer; });
    set('[data-fill="country"]', function (e) { e.textContent = L.country; });
    set('[data-fill="updated"]', function (e) { e.textContent = L.updated; });
    set('[data-fill="email"]', function (e) {
      e.textContent = L.email;
      if (e.tagName === 'A') e.href = 'mailto:' + L.email + (e.getAttribute('data-subject') ? '?subject=' + encodeURIComponent(e.getAttribute('data-subject')) : '');
    });
    if (/SET-YOUR/.test(L.developer + L.email)) {
      var b = document.createElement('div');
      b.style.cssText = 'background:#b94040;color:#fff;padding:10px 14px;font:14px system-ui;text-align:center';
      b.textContent = 'Not ready: open legal.js and fill in your name and email before you publish this page.';
      document.body.insertBefore(b, document.body.firstChild);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fill); else fill();
})();
