/* Source-file links (Oct 19, 2026, first-visitor test): every price links to the hospital's or insurer's own file, and those
   files can be gigabytes. Before one starts downloading, say what it is and how big it may be; the visitor can still open it.
   Added to every page by site/sitewide.py as /hcf-src.js. */
(function () {
  if (window.hcfSrc) return; window.hcfSrc = 1;
  var BIG = /\.(json|gz|zip|csv|xlsx?|txt|xml|zst)(\?|#|$)|in-network|standardcharges|standard-charges|machine-readable|pricetransparency|price-transparency|chargemaster|cdm|download\.aspx|blob\.core\.windows\.net|amazonaws\.com|mrf/i;
  var K = 'hcf-src-ok';
  var ok = function () { try { return sessionStorage.getItem(K) === '1'; } catch (e) { return false; } };
  var esc = function (s) { return String(s || '').replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); };
  var dlg = null;
  function ask(a) {
    if (!dlg) {
      dlg = document.createElement('dialog'); dlg.className = 'hcf-src'; dlg.setAttribute('aria-labelledby', 'hcfSrcH');
      var st = document.createElement('style');
      st.textContent = 'dialog.hcf-src{max-width:460px;width:calc(100% - 32px);border:2px solid #151515;padding:20px 22px;background:#fff;color:#151515;font:16px/1.5 "Look Hanken",system-ui,sans-serif;box-shadow:8px 8px 0 #151515}' +
        'dialog.hcf-src::backdrop{background:rgba(21,21,21,.45)}dialog.hcf-src h3{margin:0 0 8px;font:800 20px/1.2 "Look Hanken",system-ui,sans-serif}dialog.hcf-src p{margin:0 0 10px}' +
        'dialog.hcf-src .w{font:13px/1.45 "Look DM Mono",ui-monospace,monospace;background:#F4F1EA;padding:8px 10px;overflow-wrap:anywhere}' +
        'dialog.hcf-src .b{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}dialog.hcf-src .b a,dialog.hcf-src .b button{min-height:44px;padding:0 16px;border:2px solid #151515;font:700 15px "Look Hanken",system-ui,sans-serif;cursor:pointer;display:inline-flex;align-items:center;text-decoration:none}' +
        'dialog.hcf-src .b a{background:#151515;color:#fff}dialog.hcf-src .b button{background:#fff;color:#151515}dialog.hcf-src label{display:flex;gap:8px;align-items:center;font-size:14px;margin-top:10px}';
      document.head.appendChild(st);
      document.body.appendChild(dlg);
      dlg.addEventListener('click', function (e) {
        if (e.target === dlg || e.target.closest('[data-x]')) { dlg.close(); return; }
        if (e.target.closest('a[data-go]')) { var c = dlg.querySelector('input[type=checkbox]'); if (c && c.checked) try { sessionStorage.setItem(K, '1'); } catch (er) {} dlg.close(); }
      });
    }
    var tip = a.getAttribute('title') || '';
    var host = ''; try { host = new URL(a.href).hostname; } catch (e) {}
    dlg.innerHTML = '<h3 id="hcfSrcH">This opens the original price file</h3>' +
      '<p>It\'s the file the price came from, posted by the hospital or insurer as federal rules require. Files like this are often hundreds of megabytes, and insurer files can be several gigabytes. They open in data software, not a web browser, and on a phone they can use a lot of data.</p>' +
      (tip ? '<p class="w">What to look for: ' + esc(tip) + '</p>' : '') +
      '<p style="font-size:14px;color:#4A4A4A">Source: ' + esc(host) + '</p>' +
      '<label><input type="checkbox"> Don\'t ask again this visit</label>' +
      '<div class="b"><a data-go href="' + esc(a.href) + '" target="_blank" rel="noopener">Download the file</a><button type="button" data-x>Cancel</button></div>';
    dlg.showModal();
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.closest('dialog.hcf-src') || ok() || e.defaultPrevented || e.button) return;
    var u; try { u = new URL(a.href, location.href); } catch (er) { return; }
    if (u.origin === location.origin || !/^https?:$/.test(u.protocol) || !BIG.test(u.pathname + u.search + ' ' + u.hostname)) return;
    if (/\.(html?|aspx)(\?|$)/i.test(u.pathname) && !/download\.aspx/i.test(u.pathname)) return;   // ordinary web pages open as usual
    e.preventDefault(); ask(a);
  }, true);
})();
