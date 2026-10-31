/* "Original / V2 Redesign" switch, on every page of both versions (Oct 31, 2026; site/redesign/build_preview.py).
   Opens the equivalent page in the other version and carries the context both understand: procedure, area, payment,
   network, ZIP, filters and selected providers. When the other version has no equivalent page yet, it says so and offers
   to stay on this page; it never drops the visitor on a homepage. Needs /shared/hcf-data.js (window.HCF.state). */
(function () {
  'use strict';
  var SLUGS = /*SLUGS*/{}/*/SLUGS*/;          // procedure page slug -> billing code (site/procedure_slugs.csv)
  var AREAS = /*AREAS*/[]/*/AREAS*/;          // [{slug, name, path, costs}] from /cities.json
  var V2_READY = ['/v2/', '/v2/price-finder/', '/v2/provider/', '/v2/plan-calculator/', '/v2/not-ready/'];
  var St = (window.HCF && window.HCF.state) || { read: function () { return {}; }, query: function () { return ''; }, save: function () {}, load: function () { return {}; } };
  var path = location.pathname.replace(/index\.html$/, '');
  var isV2 = path === '/v2/' || path.indexOf('/v2/') === 0;
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var byPath = function (p) { for (var i = 0; i < AREAS.length; i++) if (AREAS[i].path === p) return AREAS[i]; return null; };
  var bySlug = function (s) { for (var i = 0; i < AREAS.length; i++) if (AREAS[i].slug === s || AREAS[i].costs === s) return AREAS[i]; return null; };
  var notReady = function (from) { return '/v2/not-ready/?from=' + encodeURIComponent(from); };

  // ---------- read this Original page's live state (its own variables and controls) ----------
  function originalState() {
    var s = {};
    try {
      if (typeof S !== 'undefined' && S && typeof D !== 'undefined' && D && D.nets) {       // a Price Finder page
        s.code = S.code;
        if (S.pay === 'cash') s.pay = 'cash';
        else if (S.pay === 'all') s.pay = 'all';
        else if (/^\d+$/.test(String(S.pay))) {
          var pe = document.getElementById('pay');
          var asked = pe && pe.classList.contains('ux-ask');     // still the example network, not the visitor's pick
          if (!asked) { s.pay = 'net'; s.net = D.nets[+S.pay]; }
        }
        if (S.view === 'map') s.view = 'map';
        var sel = [].slice.call(document.querySelectorAll('[data-pt]:checked')).map(function (c) { return 'f' + c.getAttribute('data-pt'); });
        if (sel.length) s.sel = sel.slice(0, 4);
        var z = document.querySelector('#mapv input[inputmode="numeric"], #mapv input[name="zip"], #mapv .zip input');
        if (z && /^\d{5}$/.test(z.value)) s.zip = z.value;
      } else if (typeof S !== 'undefined' && S && S.proc && document.getElementById('plan')) {   // the Plan Calculator
        s.code = S.proc; if (S.plan) s.plan = S.plan; if (+S.paid) s.paid = String(S.paid);
        try { if (typeof YEAR !== 'undefined') s.year = String(YEAR); } catch (e) {}
        if (location.hash === '#own') s.tab = 'own';
      }
    } catch (e) {}
    return s;
  }

  // ---------- Original -> V2 ----------
  function toV2() {
    var s = originalState(), q;
    if (path === '/') return '/v2/';
    if (path === '/folders/') return '/v2/#files';
    var a = byPath(path);
    if (a) { s.area = a.slug; q = St.query(s, ['area', 'code', 'pay', 'net', 'zip', 'kind', 'sel', 'view']); return '/v2/price-finder/' + q; }
    var m = path.match(/^\/costs\/([^/]+)\/([^/]+)\/$/);
    if (m && bySlug(m[1]) && SLUGS[m[2]]) {
      var c = St.load(); var x = { area: bySlug(m[1]).slug, code: SLUGS[m[2]] };
      if (c.pay) { x.pay = c.pay; if (c.net) x.net = c.net; }
      return '/v2/price-finder/' + St.query(x);
    }
    if (path === '/plan-calculator/') {
      if (s.tab === 'own') return notReady(path + '#own');
      return '/v2/plan-calculator/' + St.query(s, ['code', 'year', 'plan', 'paid']);
    }
    return notReady(path + location.search + location.hash);
  }

  // ---------- V2 -> Original ----------
  function toOriginal() {
    var s = St.read(), extra = [];
    if (path === '/v2/') return '/';
    if (path === '/v2/not-ready/') { var f = new URLSearchParams(location.search).get('from') || '/'; return /^\/(?!\/)/.test(f) ? f : '/'; }
    var a = bySlug(s.area || 'dfw') || bySlug('dfw') || { path: '/price-finder/' };
    if (path === '/v2/price-finder/' || path === '/v2/provider/') {
      var u = new URLSearchParams();
      if (s.code) u.set('code', s.code);
      if (s.pay === 'net' && s.net) u.set('net', s.net);
      if (s.pay === 'cash' || s.pay === 'all') u.set('hcf_pay', s.pay);
      if (s.view === 'map') u.set('hcf_view', 'map');
      if (s.zip) u.set('hcf_zip', s.zip);
      var V = window.HCF_V2, sel = V ? V.origSel() : (s.sel || []).filter(function (x) { return /^f\d+$/.test(x); });
      if (sel.length) u.set('hcf_sel', sel.join(','));
      var pp = V && path === '/v2/provider/' ? V.origP() : null;
      if (pp) u.set('hcf_p', pp);
      var qs = u.toString();
      return a.path + (qs ? '?' + qs : '');
    }
    if (path === '/v2/plan-calculator/') {
      var c = new URLSearchParams();
      if (s.year) c.set('year', s.year);
      if (s.code) c.set('hcf_code', s.code);
      if (s.plan) c.set('hcf_plan', s.plan);
      if (s.paid) c.set('hcf_paid', s.paid);
      var cq = c.toString();
      return '/plan-calculator/' + (cq ? '?' + cq : '');
    }
    return '/';
  }

  // ---------- arriving on an Original page with context from V2 ----------
  function applyOnOriginal() {
    var u = new URLSearchParams(window.__hcfArrive != null ? window.__hcfArrive : location.search), any = false;
    ['hcf_pay', 'hcf_view', 'hcf_zip', 'hcf_sel', 'hcf_p', 'hcf_code', 'hcf_plan', 'hcf_paid'].forEach(function (k) { if (u.has(k)) any = true; });
    if (!any) return;
    var get = function (k) { return u.get(k) || ''; };
    var clean = function () { var x = new URL(location.href); ['hcf_pay', 'hcf_view', 'hcf_zip', 'hcf_sel', 'hcf_p', 'hcf_code', 'hcf_plan', 'hcf_paid'].forEach(function (k) { x.searchParams.delete(k); }); try { history.replaceState(history.state, '', x.href); } catch (e) {} };
    var tries = 0;
    (function go() {
      var pf = typeof S !== 'undefined' && S && typeof D !== 'undefined' && D && D.nets && document.getElementById('pay');
      var calc = typeof S !== 'undefined' && S && S.proc && document.getElementById('plan');
      if (!pf && !calc) { if (++tries < 60) return setTimeout(go, 150); return; }
      try {
        if (pf) {
          var pay = document.getElementById('pay');
          var setPay = function (v) { if ([].some.call(pay.options, function (o) { return o.value === v; }) && pay.value !== v) { pay.value = v; pay.dispatchEvent(new Event('change', { bubbles: true })); } };
          if (get('hcf_pay') === 'cash') setPay('cash');
          if (get('hcf_pay') === 'all') setPay('all');
          if (get('hcf_view') === 'map') { var vm = document.getElementById('vMap'); if (vm) vm.click(); }
          var sel = get('hcf_sel').split(',').filter(function (x) { return /^f\d+$/.test(x); });
          var p = get('hcf_p');
          setTimeout(function () {
            sel.forEach(function (id) { var cb = document.querySelector('[data-pt="' + id.slice(1) + '"]'); if (cb && !cb.checked) cb.click(); });
            if (/^f\d+$/.test(p)) {
              var cb = document.querySelector('[data-pt="' + p.slice(1) + '"]'), row = cb && cb.closest('tr');
              if (row) { row.style.outline = '3px solid #F7C925'; row.scrollIntoView({ block: 'center' }); }
            }
            var z = get('hcf_zip');
            if (z) { var zi = document.querySelector('#mapv input[inputmode="numeric"], #mapv input[name="zip"]'); if (zi) { zi.value = z; zi.dispatchEvent(new Event('input', { bubbles: true })); zi.dispatchEvent(new Event('change', { bubbles: true })); } }
            clean();
          }, 600);
        } else {
          var set = function (id, v) { var el = document.getElementById(id); if (!el || !v) return; if (el.tagName === 'SELECT' && ![].some.call(el.options, function (o) { return o.value === v; })) return; el.value = v; el.dispatchEvent(new Event(el.tagName === 'INPUT' ? 'input' : 'change', { bubbles: true })); };
          if (get('hcf_plan')) {
            var plan = null; try { plan = D.plans.find(function (x) { return x.id === get('hcf_plan'); }); } catch (e) {}
            if (plan) { var ins = D.net[plan.k][0]; set('ins', ins); set('plan', plan.id); }
          }
          set('proc', get('hcf_code'));
          set('paid', get('hcf_paid'));
          clean();
        }
      } catch (e) {}
    })();
  }

  // ---------- the bar ----------
  function bar() {
    var cur = isV2 ? 'v2' : 'orig';
    var other = isV2 ? toOriginal : toV2;
    var el = document.createElement('div');
    el.className = 'hcf-vs'; el.setAttribute('role', 'region'); el.setAttribute('aria-label', 'Site version');
    el.innerHTML = '<div class="hcf-vs-in"><span class="hcf-vs-l" id="hcfVsL">Site version</span>' +
      '<div class="hcf-vs-seg" role="group" aria-labelledby="hcfVsL">' +
      '<a href="' + (isV2 ? '#' : '#') + '" data-v="orig"' + (cur === 'orig' ? ' aria-current="page"' : '') + '>Original</a>' +
      '<a href="#" data-v="v2"' + (cur === 'v2' ? ' aria-current="page"' : '') + '>V2 Redesign</a></div>' +
      '<span class="hcf-vs-n">' + (isV2 ? 'Preview of the redesign. Same data as the Original.' : 'You are on the Original design.') + '</span></div>';
    var link = el.querySelector('[data-v="' + (isV2 ? 'orig' : 'v2') + '"]');
    var here = el.querySelector('[data-v="' + cur + '"]');
    here.href = location.pathname + location.search + location.hash;
    here.addEventListener('click', function (e) { e.preventDefault(); });
    // compute the target when it is used, so it reflects what the visitor has picked by then
    var refresh = function () { try { link.href = other(); } catch (e) { link.href = isV2 ? '/' : notReady(path); } };
    refresh();
    ['pointerenter', 'focus', 'touchstart'].forEach(function (ev) { link.addEventListener(ev, refresh, { passive: true }); });
    link.addEventListener('click', function () { refresh(); try { St.save(isV2 ? St.read() : originalState()); } catch (e) {} });
    document.body.insertBefore(el, document.body.firstChild);
  }

  function start() { bar(); if (!isV2) applyOnOriginal(); }
  if (document.body) start(); else document.addEventListener('DOMContentLoaded', start);
  window.HCF_SWITCH = { toV2: toV2, toOriginal: toOriginal, ready: V2_READY };
})();
