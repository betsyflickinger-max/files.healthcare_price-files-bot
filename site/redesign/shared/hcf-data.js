/* The Healthcare Files: shared data layer for BOTH site versions (Original and V2 Redesign). Oct 31, 2026.
   - One quarantine list (site/source_quarantine.csv): price files that belong to another place are left out of an
     area's lists, map and figures before any page code reads them. Same rule in both versions.
   - One loader for the Price Finder's own data (the area page's embedded data block and its per-code pf/t, pf/h files).
   - One page-state model (procedure, area, payment, network, ZIP, filters, selected providers) that the version switch
     carries between equivalent pages.
   Loaded synchronously in <head> so it is in place before a page's own scripts run. Built by site/redesign/build_preview.py. */
(function () {
  'use strict';
  window.__hcfArrive = location.search;   // read before any page script rewrites the address (the version switch uses it)
  var Q = /*Q*/{"rx": "", "files": [], "areas": {}}/*/Q*/;
  var RX = Q.rx ? new RegExp(Q.rx, 'i') : null;
  window.HCF_Q = { rx: RX, files: Q.files, areas: Q.areas };

  // ---------- quarantine at the data boundary ----------
  function b64utf8(s) { return btoa(unescape(encodeURIComponent(s))); }
  async function decodeB64(text) {
    var b64 = String(text).trim();
    if (!/^[A-Za-z0-9+/=]+$/.test(b64.slice(0, 200))) return null;
    var buf = Uint8Array.from(atob(b64), function (ch) { return ch.charCodeAt(0); });
    try { return JSON.parse(await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).text()); }
    catch (e) { return JSON.parse(new TextDecoder().decode(buf)); }
  }
  function areaFor(pathname) {
    var m = pathname.match(/^(.*\/price-finder\/)pf\/(h\/[^/]+\.txt|g\/geo\.json)$/);
    return m && Q.areas[m[1]] ? { base: m[1], kind: m[2].charAt(0), A: Q.areas[m[1]] } : null;
  }
  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var hit = null;
    try { hit = areaFor(new URL(url, location.href).pathname); } catch (e) {}
    if (!hit) return nativeFetch(input, init);
    return nativeFetch(input, init).then(async function (res) {
      if (!res.ok) return res;
      try {
        var bad = new Set(hit.A.src || []);
        if (hit.kind === 'h') {
          var H = await decodeB64(await res.clone().text());
          if (!H) return res;
          var drop = function (rows) { return (rows || []).filter(function (r) { return !bad.has(r[0]); }); };
          H.c = drop(H.c); H.r = drop(H.r);
          return new Response(b64utf8(JSON.stringify(H)), { status: 200, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
        }
        var G = await res.clone().json();
        (hit.A.hn || []).forEach(function (k) {
          if (G.hn && k in G.hn) delete G.hn[k];
          (G.unplaced = G.unplaced || []).push({ key: k, why: 'quarantined: this price file belongs to another state (it is not shown on this area’s map)' });
        });
        return new Response(JSON.stringify(G), { status: 200, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
      } catch (e) { return res; }
    });
  };

  // ---------- loader (used by V2; Original pages keep their own copies of the same reads) ----------
  var areaCache = {}, codeCache = {};
  async function loadArea(path) {
    if (areaCache[path]) return areaCache[path];
    areaCache[path] = (async function () {
      var r = await nativeFetch(path, { credentials: 'same-origin' });
      if (!r.ok) throw new Error('area page ' + r.status);
      var html = await r.text(), i = html.indexOf('id="data"');
      if (i < 0) throw new Error('no data block');
      var D = JSON.parse(html.slice(html.indexOf('>', i) + 1, html.indexOf('</script>', i)));
      var G = null, ML = null;
      try { var g = await window.fetch(path + 'pf/g/geo.json', { credentials: 'same-origin' }); if (g.ok) G = await g.json(); } catch (e) {}
      // which provider each hospital price file belongs to (ml.json "h": file index -> [file fingerprint, provider indexes]),
      // the same tie the Original Compare view uses; used only when the fingerprint still matches this page's file
      try { var m = await nativeFetch(path + 'ml.json', { credentials: 'same-origin' }); if (m.ok) ML = await m.json(); } catch (e) {}
      var bad = new Set(((Q.areas || {})[path] || {}).src || []);
      if (ML && ML.h) Object.keys(ML.h).forEach(function (k) { var x = D.hosp && D.hosp.src[+k]; if (bad.has(+k) || !x || x[5] !== ML.h[k][0]) delete ML.h[k]; });
      return { path: path, D: D, G: G, ML: ML };
    })();
    return areaCache[path];
  }
  async function getB64(url) {
    var r = await window.fetch(url, { credentials: 'same-origin' });
    if (!r.ok) return null;
    return decodeB64(await r.text());
  }
  async function loadCode(path, code) {
    var k = path + '|' + code;
    if (!codeCache[k]) codeCache[k] = Promise.all([
      getB64(path + 'pf/t/' + code + '.txt').then(function (j) { return (j && j.f) || {}; }).catch(function () { return { __err: 1 }; }),
      getB64(path + 'pf/h/' + code + '.txt').then(function (j) { return j || { c: [], r: [] }; }).catch(function () { return { c: [], r: [], err: 1 }; })
    ]).then(function (x) { return { T: x[0], H: x[1] }; });
    return codeCache[k];
  }

  // ---------- rules shared with the Original Price Finder (same pick, same flags) ----------
  var R = {
    KIND: { A: 'Surgery center', H: 'Hospital', G: 'Practice, clinic, lab or imaging center', P: 'Individual clinician' },
    isZero: function (r) { return !!(r[4] & 4); },
    // a provider's lowest DOLLAR rate on one network for one bill type: percent-of-charges and $0 lines skipped (as the Price Finder and calculator do)
    pick: function (rs, net, doc) {
      var m = (rs || []).filter(function (r) { return r[0] === net && r[1] === doc && r[2] === 0 && !(r[4] & 4); })
        .sort(function (a, b) { return a[3] - b[3]; });
      return m[0] || null;
    },
    flags: function (r) { var f = []; if (r[4] & 1) f.push('same price for many procedures'); if (r[4] & 2) f.push('unusually low'); if (r[4] & 8) f.push('unusually high'); return f; },
    miles: function (a, b) {
      var t = Math.PI / 180, dl = (b[0] - a[0]) * t, dn = (b[1] - a[1]) * t;
      var x = Math.sin(dl / 2) * Math.sin(dl / 2) + Math.cos(a[0] * t) * Math.cos(b[0] * t) * Math.sin(dn / 2) * Math.sin(dn / 2);
      return 3958.8 * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
    },
    money: function (v) { return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
    nice: function (t) { return t && t === t.toUpperCase() ? t.toLowerCase().replace(/\b([a-z])/g, function (c) { return c.toUpperCase(); }).replace(/\bEr\b/g, 'ER') : t; }
  };

  // ---------- one page state for both versions ----------
  var KEYS = ['area', 'code', 'pay', 'net', 'zip', 'kind', 'fee', 'sel', 'view', 'p', 'plan', 'year', 'paid'];
  var State = {
    KEYS: KEYS,
    read: function (search) {
      var u = new URLSearchParams(search == null ? location.search : search), s = {};
      KEYS.forEach(function (k) { var v = u.get(k); if (v != null && v !== '') s[k] = v; });
      if (s.sel) s.sel = s.sel.split(',').filter(Boolean).slice(0, 4); else s.sel = [];
      return s;
    },
    query: function (s, keys) {
      var u = new URLSearchParams();
      (keys || KEYS).forEach(function (k) { var v = s[k]; if (Array.isArray(v)) v = v.join(','); if (v != null && v !== '') u.set(k, v); });
      var q = u.toString(); return q ? '?' + q : '';
    },
    // the context the version switch carries: kept per tab so a round trip Original -> V2 -> Original keeps it
    save: function (s) { try { sessionStorage.setItem('hcf-ctx', JSON.stringify(s)); } catch (e) {} },
    load: function () { try { return JSON.parse(sessionStorage.getItem('hcf-ctx') || '{}') || {}; } catch (e) { return {}; } }
  };

  window.HCF = { Q: window.HCF_Q, loadArea: loadArea, loadCode: loadCode, getB64: getB64, rules: R, state: State, nativeFetch: nativeFetch };
})();
