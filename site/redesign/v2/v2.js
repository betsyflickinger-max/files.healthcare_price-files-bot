/* The Healthcare Files, V2 Redesign: page logic (Oct 31, 2026).
   Every figure comes from the same files the Original pages read, through /shared/hcf-data.js (window.HCF):
   the area Price Finder's data block, its per-code pf/t (insurer files) and pf/h (hospital files), its map file, and the
   Plan Calculator's own data and cost-sharing function (/shared/calc-core.js). Nothing here estimates or averages a price. */
(function () {
  'use strict';
  var H = window.HCF, R = H.rules, St = H.state;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); };
  var money = R.money;
  var tidy = function (t) { return H.tidy ? H.tidy(String(t || '')) : String(t || ''); };
  var fmtDate = function (s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); if (!m) return s || 'no date in file'; return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); };
  var ageDays = function (s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? (Date.now() - new Date(+m[1], +m[2] - 1, +m[3]).getTime()) / 864e5 : null; };
  var stale = function (s) { var a = ageDays(s); return a != null && a > 183; };   // the site's six-month old-price rule (methodology)
  var page = document.body.getAttribute('data-page');
  var S = St.read();
  var AREAS = [], PROCS = [];

  function setURL(keys) { var q = St.query(S, keys); try { history.replaceState(null, '', location.pathname + q + location.hash); } catch (e) {} St.save(S); }
  async function getJSON(u) { var r = await H.nativeFetch(u, { credentials: 'same-origin' }); if (!r.ok) throw new Error(u + ' ' + r.status); return r.json(); }
  function areaOf(slug) { return AREAS.find(function (a) { return a.slug === slug; }) || AREAS.find(function (a) { return a.slug === 'dfw'; }); }
  function areaOptions(sel, cur) {
    var byState = {};
    AREAS.forEach(function (a) { (byState[a.state] = byState[a.state] || []).push(a); });
    sel.innerHTML = Object.keys(byState).sort().map(function (st) {
      var L = byState[st].sort(function (a, b) { return a.slug === 'dfw' ? -1 : b.slug === 'dfw' ? 1 : a.name.localeCompare(b.name); });
      if (L.length === 1 && L[0].name === st) return '<option value="' + esc(L[0].slug) + '">' + esc(st) + '</option>';
      return '<optgroup label="' + esc(st) + '">' + L.map(function (a) { return '<option value="' + esc(a.slug) + '">' + esc(a.name) + '</option>'; }).join('') + '</optgroup>';
    }).join('');
    sel.value = cur || 'dfw';
  }

  // ---------- procedure search: an accessible combobox (type, arrows, Enter, Escape) ----------
  function combo(input, list, items, onPick) {
    var open = false, act = -1, shown = [];
    var norm = function (s) { return String(s).toLowerCase().replace(/[^a-z0-9 ]/g, ' '); };
    var close = function () { open = false; act = -1; list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); };
    var draw = function () {
      var q = norm(input.value).trim(), words = q.split(/\s+/).filter(Boolean);
      shown = !q ? [] : items.filter(function (it) { var h = it.h || (it.h = norm(it.name + ' ' + it.code + ' ' + (it.alt || ''))); return words.every(function (w) { return h.indexOf(w) >= 0; }); }).slice(0, 12);
      list.innerHTML = shown.map(function (it, i) { return '<li role="option" id="' + list.id + '-' + i + '" aria-selected="' + (i === act) + '" data-i="' + i + '">' + esc(it.name) + ' <span class="mono muted">' + esc(it.code) + '</span></li>'; }).join('') ||
        (q ? '<li class="none" role="option" aria-disabled="true">No match. Try another word, like “MRI” or “colonoscopy”.</li>' : '');
      open = !!q; list.hidden = !open; input.setAttribute('aria-expanded', String(open));
      if (act >= 0) input.setAttribute('aria-activedescendant', list.id + '-' + act); else input.removeAttribute('aria-activedescendant');
    };
    input.setAttribute('role', 'combobox'); input.setAttribute('aria-autocomplete', 'list'); input.setAttribute('aria-expanded', 'false'); input.setAttribute('aria-controls', list.id);
    list.setAttribute('role', 'listbox');
    input.addEventListener('input', function () { act = -1; input.dataset.code = ''; draw(); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) draw(); act = Math.min(act + 1, shown.length - 1); draw(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); act = Math.max(act - 1, 0); draw(); }
      else if (e.key === 'Enter' && open && act >= 0) { e.preventDefault(); pick(shown[act]); }
      else if (e.key === 'Escape' && open) { e.preventDefault(); close(); }
    });
    list.addEventListener('mousedown', function (e) { var li = e.target.closest('[data-i]'); if (li) { e.preventDefault(); pick(shown[+li.dataset.i]); } });
    input.addEventListener('blur', function () { setTimeout(close, 120); });
    function pick(it) { if (!it) return; input.value = it.name; input.dataset.code = it.code; close(); if (onPick) onPick(it); }
    return { pick: pick, first: function () { if (!shown.length) draw(); return shown[0] || null; } };
  }
  var comboCSS = '.cb{position:relative}.cb ul{position:absolute;z-index:30;left:0;right:0;top:100%;margin:4px 0 0;padding:4px 0;list-style:none;background:#fff;border:1.5px solid #151515;border-radius:6px;max-height:320px;overflow:auto;box-shadow:0 10px 24px rgba(0,0,0,.18)}' +
    '.cb li{padding:9px 12px;cursor:pointer;color:#151515}.cb li[aria-selected="true"],.cb li:hover{background:#DCE5FC}.cb li.none{color:#4A4A4A;cursor:default}';
  document.head.insertAdjacentHTML('beforeend', '<style>' + comboCSS + '</style>');

  // ==========================================================================================
  // HOME
  // ==========================================================================================
  async function home() {
    try { AREAS = await getJSON('/shared/areas.json'); } catch (e) { AREAS = [{ slug: 'dfw', name: 'Dallas–Fort Worth', path: '/price-finder/', state: 'Texas' }]; }
    try { PROCS = await getJSON('/shared/procedures.json'); } catch (e) { PROCS = []; }
    var sel = $('#hArea'); areaOptions(sel, S.area || 'dfw');
    var cb = combo($('#hProc'), $('#hProcList'), PROCS);
    $('#hForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var inp = $('#hProc'), code = inp.dataset.code, err = $('#hErr');
      if (!code && inp.value.trim()) { var f = cb.first(); if (f) code = f.code; }
      if (!code && /^\s*[0-9A-Z]{3,5}\s*$/i.test(inp.value)) code = inp.value.trim().toUpperCase();
      if (!code) { err.hidden = false; err.textContent = 'Type a procedure, like “knee MRI”, then pick it from the list.'; inp.focus(); return; }
      err.hidden = true;
      location.href = '/v2/price-finder/' + St.query({ area: sel.value, code: code });
    });
    // popular searches follow the chosen place
    var pop = function () { $$('#hPop a').forEach(function (a) { a.href = '/v2/price-finder/' + St.query({ area: sel.value, code: a.dataset.code }); }); };
    sel.addEventListener('change', pop); pop();
  }

  // ==========================================================================================
  // RESULTS
  // ==========================================================================================
  var A = null, C = null, CODE = null, ROWS = [];
  function kindOf(k) { return R.KIND[k] || 'Provider'; }
  function locFor(row) {
    var G = A.G; if (!G) return null;
    if (row.fi != null) { var li = G.p && G.p[row.fi]; return li != null && li >= 0 ? G.locs[li] : null; }
    if (row.place != null) { var lp = G.p && G.p[row.place]; if (lp != null && lp >= 0) return G.locs[lp]; }
    if (row.src != null) { var x = A.D.hosp.src[row.src], k = (x[0] + '|' + x[1]).toLowerCase(); return G.hn && G.hn[k] != null ? G.locs[G.hn[k]] : null; }
    if (row.cash != null) { var c = A.D.cash[row.cash], kk = (c.name + '|' + c.city).toLowerCase(); return G.cash && G.cash[kk] != null ? G.locs[G.cash[kk]] : null; }
    return null;
  }
  function quarantined() { var q = (H.Q.areas || {})[A.path]; return q ? q.src || [] : []; }
  function netLabel(n) { var s = A.D.nets[n] || ''; var p = s.split('|'); return p[0] + ' · ' + p.slice(1).join('|'); }
  function netIndex(label) { if (!label) return -1; var i = A.D.nets.indexOf(label); if (i >= 0) return i; var l = String(label).toLowerCase(); return A.D.nets.findIndex(function (n) { return n.toLowerCase() === l; }); }
  function defaultFee(T) {
    var nf = 0, nd = 0; Object.keys(T).forEach(function (fi) { var rs = T[fi]; if (rs.some(function (r) { return r[1] === 0; })) nf++; if (rs.some(function (r) { return r[1] === 1; })) nd++; });
    return nf ? 'fac' : nd ? 'doc' : 'fac';   // the facility fee when anyone lists one (what a patient usually asks first); the doctor's fee when it is the only bill
  }

  // one list of rows for the current state; every surface (cards, count, compare, CSV, receipt) reads this
  function buildRows() {
    var T = C.T, Hc = C.H, D = A.D, out = [], doc = S.fee === 'doc' ? 1 : 0, bad = new Set(quarantined());
    if (S.pay === 'cash') {
      var best = {};
      (Hc.c || []).forEach(function (r) {
        if (bad.has(r[0]) || !(r[2] > 0) || (r[5] ? 1 : 0) !== doc) return;
        if (!best[r[0]] || r[2] < best[r[0]].r[2]) best[r[0]] = { r: r };
      });
      Object.keys(best).forEach(function (s) {
        var x = D.hosp.src[+s], r = best[s].r, tie = A.ML && A.ML.h && A.ML.h[s] ? A.ML.h[s][1] : null, pl = tie && tie.length ? +tie[0] : null, pf = pl != null ? D.fac[pl] : null;
        out.push({ id: 'h' + s, src: +s, place: pl, name: tidy(R.nice(x[0])), city: x[1] || (pf ? pf[1] : ''), legal: pf ? tidy(pf[0]) : '', kind: pf ? pf[2] : 'H', fileName: R.nice(x[0]), v: r[2], what: doc ? "Cash price, doctor's part · the hospital's own price file" : "Cash price, facility fee · the hospital's own price file",
          date: x[3], url: x[4], row: r[4], unit: x[6], setting: r[1], list: r[3], flags: [] });
      });
      if (!doc) (D.cash || []).forEach(function (c, i) {
        if (c.code !== CODE || !(c.v > 0)) return;
        out.push({ id: 'c' + i, cash: i, name: tidy(c.name), city: c.city || '', kind: '', v: c.v, hi: c.hi, what: 'Posted cash price' + (c.label ? ' (' + c.label + ')' : '') + " · the provider's own website",
          date: c.chk, url: c.src, flags: [], note: c.note });
      });
    } else if (S.pay === 'net') {
      var n = netIndex(S.net); if (n < 0) return [];
      Object.keys(T).forEach(function (fi) {
        if (fi === '__err') return;
        var r = R.pick(T[fi], n, doc); if (!r) return;
        var f = D.fac[+fi]; if (!f) return;
        out.push({ id: 'f' + fi, fi: +fi, name: tidy(f[0]), city: f[1], kind: f[2], v: r[3], r: r, net: n,
          what: (doc ? "Doctor's fee" : 'Facility fee') + ' · negotiated rate · ' + netLabel(n), date: D.dates[r[5]], url: D.urls[r[6]], flags: R.flags(r) });
      });
    } else if (S.pay === 'all') {
      Object.keys(T).forEach(function (fi) {
        if (fi === '__err') return;
        var f = D.fac[+fi]; if (!f) return;
        var per = {}; T[fi].forEach(function (r) { if (r[1] !== doc || r[2] !== 0 || (r[4] & 4)) return; if (!per[r[0]] || r[3] < per[r[0]][3]) per[r[0]] = r; });
        var L = Object.keys(per).map(function (k) { return per[k]; }).sort(function (a, b) { return a[3] - b[3]; });
        if (!L.length) return;
        out.push({ id: 'f' + fi, fi: +fi, name: tidy(f[0]), city: f[1], kind: f[2], v: L[0][3], hi: L[L.length - 1][3], nets: L.length, r: L[0], net: L[0][0],
          what: (doc ? "Doctor's fee" : 'Facility fee') + ' · negotiated rates in ' + L.length + ' network' + (L.length > 1 ? 's' : '') + ' (lowest to highest)', date: D.dates[L[0][5]], url: D.urls[L[0][6]], flags: [] });
      });
    }
    var z = S.zip && A.G && A.G.zips && A.G.zips[S.zip];
    out.forEach(function (o) { var p = locFor(o); o.loc = p; o.mi = z && p ? R.miles(z, p) : null; });
    return out;
  }
  function filtered() {
    var rad = +(S.rad || 25);
    var L = ROWS.filter(function (o) {
      if (S.kind && o.kind !== S.kind && !(S.kind === 'H' && o.src != null)) return false;
      if (S.zip && A.G && A.G.zips && A.G.zips[S.zip] && !(o.mi != null && o.mi <= rad)) return false;
      return true;
    });
    if (S.sort === 'near' && S.zip) L.sort(function (a, b) { return (a.mi == null) - (b.mi == null) || a.mi - b.mi || a.v - b.v; });
    else L.sort(function (a, b) { return a.v - b.v || a.name.localeCompare(b.name); });
    return L;
  }
  var SHOWN = 25;
  function card(o) {
    var sel = S.sel.indexOf(o.id) >= 0;
    var amt = S.pay === 'all' && o.hi != null && o.hi !== o.v ? money(o.v) + '<span class="muted" style="font-size:.6em;font-weight:600"> to ' + money(o.hi) + '</span>' : money(o.v);
    var where = [kindOf(o.kind || (o.src != null ? 'H' : '')), o.city, o.mi != null ? o.mi.toFixed(1) + ' mi from ' + S.zip : (S.zip ? 'distance unknown (not on the map)' : '')].filter(Boolean).join(' · ');
    var rq = St.query({ area: S.area, code: CODE, pay: S.pay, net: S.net, fee: S.fee, p: o.id, zip: S.zip });
    return '<li class="pc' + (sel ? ' sel' : '') + '"><input type="checkbox" data-id="' + esc(o.id) + '"' + (sel ? ' checked' : '') + ' aria-label="Select ' + esc(o.name) + ' to compare">' +
      '<div><h3><a href="/v2/provider/' + rq + '">' + esc(o.name) + '</a></h3><p class="kind">' + esc(where) + '</p></div>' +
      '<div class="amt"><span class="price sm">' + amt + '</span><span class="what">' + esc(o.what) + '</span></div>' +
      (o.flags.length || stale(o.date) ? '<div class="flags">' + o.flags.map(function (f) { return '<span class="tag flag">' + esc(f) + '</span>'; }).join('') + (stale(o.date) ? '<span class="tag flag">file over 6 months old</span>' : '') + '</div>' : '') +
      '<div class="links"><a href="/v2/provider/' + rq + '#included">What’s included</a><a href="' + esc(o.url) + '" target="_blank" rel="noopener">Source file, ' + esc(fmtDate(o.date)) + ' ↗</a><a href="/v2/provider/' + rq + '#background">Background</a></div></li>';
  }
  function excludedBlock() {
    var q = quarantined(); if (!q.length) return '';
    var files = (H.Q.files || []);
    return '<details class="excl card"><summary>Left out of ' + esc(areaOf(S.area).name) + ': ' + q.length + ' price file' + (q.length > 1 ? 's' : '') + ' from another place</summary>' +
      q.map(function (s) {
        var x = A.D.hosp.src[s] || [], f = files.find(function (f) { return (x[4] || '').toLowerCase().indexOf(f.url_contains.toLowerCase()) >= 0; }) || {};
        return '<p><b>' + esc(R.nice(x[0] || 'Unknown file')) + '</b>: ' + esc(f.reason || 'belongs to another place') + '. ' + esc(f.evidence || '') +
          ' <a href="' + esc(x[4]) + '" target="_blank" rel="noopener">The file ↗</a></p>';
      }).join('') + '<p class="small muted">It stays out of this area’s lists, map, counts and comparisons in both versions of the site until its location is confirmed. Nothing in the file was changed.</p></details>';
  }
  function benchBlock() {
    var m = A.D.med && A.D.med.codes && A.D.med.codes[CODE], src = A.D.med && A.D.med.src; if (!m || !src) return '';
    var lk = function (k) { return src[k] ? '<a href="' + esc(src[k][1]) + '" target="_blank" rel="noopener">CMS, ' + esc(src[k][2]) + ' ↗</a>' : ''; };
    var L = [];
    if (m.opps) L.push(['Hospital outpatient facility fee', 'national rate before local wage adjustment', m.opps[0], 'opps']);
    if (m.asc) L.push(['Surgery center facility fee', 'national rate before local wage adjustment', m.asc[0], 'asc']);
    if (m.pfs && m.pfs.dal) { var d = m.pfs.dal; if (d[1] != null) L.push(['Doctor, when done in a hospital or surgery center', 'Dallas locality', d[1], 'pfs']); if (d[0] != null && d[0] !== d[1]) L.push(['Doctor or clinic, when done in an office', 'Dallas locality, includes office costs', d[0], 'pfs']); }
    if (m.lab) L.push(['Lab test', 'national payment limit', m.lab, 'lab']);
    if (!L.length) return '';
    return '<section class="bench" aria-labelledby="bH"><h2 id="bH" style="font-size:22px;margin:0 0 4px">Medicare benchmark, for comparison</h2><p class="muted" style="margin:0 0 10px">What traditional Medicare pays in 2026, from CMS’s fee schedules. A reference point only, not a price you can get.' + (S.area !== 'dfw' ? ' Doctor amounts shown are for the Dallas locality.' : '') + '</p>' +
      '<table><thead><tr><th scope="col">Medicare pays</th><th scope="col" class="n">Amount</th><th scope="col">Source</th></tr></thead><tbody>' +
      L.map(function (x) { return '<tr><td><b>' + esc(x[0]) + '</b><div class="small muted">' + esc(x[1]) + '</div></td><td class="n">' + money(x[2]) + '</td><td>' + lk(x[3]) + '</td></tr>'; }).join('') + '</tbody></table></section>';
  }
  function billsBlock() {
    var c = A.D.codes[CODE] || {}, cat = c.cat || '', L;
    if (CODE.indexOf('00') === 0) L = [['The anesthesia team', 'priced on this page'], ['The place', 'facility fee, a separate bill'], ['The doctor', 'who does the procedure']];
    else if (/DRG/.test(c.type || '')) L = [['The hospital stay', 'priced on this page'], ['The doctors', 'who see you in the hospital'], ['Surgery and anesthesia', 'if you have an operation']];
    else if (cat === 'Imaging') L = [['The place', 'the scan itself'], ['The radiologist', 'who reads the scan']];
    else if (/Lab/.test(cat)) L = [['The lab', 'priced on this page'], ['Drawing the blood, maybe', 'sometimes a small separate charge']];
    else if (/Office|Behavioral|therapy|Heart/i.test(cat)) L = [['The clinician', 'priced on this page'], ['A facility fee, maybe', 'only at clinics a hospital owns']];
    else L = [['The place', 'facility fee: room, staff, equipment'], ['The doctor', 'who does the procedure'], ['Anesthesia', 'often a separate company'], ['Lab work, maybe', 'only if tissue is sent to a pathologist']];
    return '<section class="sec" style="padding:20px 0 0" aria-labelledby="blH"><h2 id="blH" style="font-size:22px">Expect more than one bill</h2><p class="lede">Each is usually a separate bill, often from a different company. This page shows one kind at a time (switch between facility and doctor’s fees above). We don’t add them up: they come from different files and providers, so a total would be a guess.</p>' +
      '<ol class="steps" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">' + L.map(function (x) { return '<li><b>' + esc(x[0]) + '</b><span class="muted small">' + esc(x[1]) + '</span></li>'; }).join('') + '</ol></section>';
  }
  function renderResults() {
    var L = filtered(), box = $('#rList'), D = A.D;
    var nProv = L.length;
    var unit = S.pay === 'cash' ? 'place' : 'provider';
    var head = S.pay === 'net' && netIndex(S.net) < 0 ? '' : nProv.toLocaleString() + ' ' + unit + (nProv === 1 ? '' : 's') + (S.zip ? ' within ' + (S.rad || 25) + ' miles of ' + S.zip : '') + ' · lowest price first';
    $('#rCount').textContent = head;
    $('#rMeaning').innerHTML = S.pay === 'cash' ? 'Cash prices are what a hospital file or a provider’s website lists for paying without insurance. Ask whether the price is a package and what it leaves out.'
      : S.pay === 'net' ? 'A negotiated rate is what this network agreed to pay the provider in total. <b>It is not your bill.</b> Your share depends on your plan’s deductible, copay and coinsurance. <a href="/v2/plan-calculator/' + St.query({ code: CODE, area: S.area, pay: S.pay, net: S.net }) + '">Estimate my share</a>.'
      : 'Not sure of your network? This shows each provider’s rates across every network we read. Your price depends on your plan’s network, so pick it under Insurance when you know it.';
    if (S.pay === 'net' && netIndex(S.net) < 0) { box.innerHTML = '<li class="empty">Choose your plan’s network above to see its rates. Your insurance card or plan documents name it (for example “Aetna Choice POS II”).</li>'; $('#rMore').hidden = true; cmpBar(); return; }
    if (C.T.__err) { box.innerHTML = '<li class="empty">This procedure’s rates didn’t load. Reload the page to try again.</li>'; return; }
    if (!L.length) {
      box.innerHTML = '<li class="empty">' + (S.zip ? 'Nothing within ' + (S.rad || 25) + ' miles of ' + esc(S.zip) + '. Try a bigger distance, or clear the ZIP code.' :
        S.pay === 'cash' ? 'No cash prices are published for this procedure in this area in the files we read. That means no published price, not that no one offers it.' :
        'This network’s files list no dollar rate of this type here. Try the other fee type, or another network.') + '</li>';
      $('#rMore').hidden = true; cmpBar(); return;
    }
    box.innerHTML = L.slice(0, SHOWN).map(card).join('');
    $('#rMore').hidden = L.length <= SHOWN; $('#rMore').textContent = 'Show ' + Math.min(25, L.length - SHOWN) + ' more (of ' + L.length.toLocaleString() + ')';
    cmpBar();
  }
  function cmpBar() {
    var n = S.sel.length, b = $('#cmpBar');
    b.hidden = !n;
    $('#cmpN').textContent = n + ' selected';
    var go = $('#cmpGo'); go.disabled = n < 2; go.setAttribute('aria-disabled', String(n < 2));
    $('#cmpHint').textContent = n < 2 ? 'Select one more to compare' : n >= 4 ? 'Up to 4 at a time' : '';
  }
  function openCompare(btn) {
    var byId = {}; ROWS.forEach(function (o) { byId[o.id] = o; });
    var P = S.sel.map(function (id) { return byId[id]; }).filter(Boolean);
    var d = $('#cmpDlg');
    $('#cmpBody').innerHTML = P.map(function (o) {
      return '<section class="card"><h3 style="margin:0;font-size:17px">' + esc(o.name) + '</h3><p class="muted small" style="margin:2px 0 8px">' + esc([kindOf(o.kind || (o.src != null ? 'H' : '')), o.city].filter(Boolean).join(' · ')) + '</p>' +
        '<span class="price">' + money(o.v) + '</span>' + (S.pay === 'all' && o.hi != null && o.hi !== o.v ? '<span class="muted"> to ' + money(o.hi) + '</span>' : '') +
        '<dl><dt>What this is</dt><dd>' + esc(o.what) + '</dd><dt>File date</dt><dd>' + esc(fmtDate(o.date)) + (stale(o.date) ? ' (over 6 months old)' : '') + '</dd><dt>Distance</dt><dd>' + (o.mi != null ? o.mi.toFixed(1) + ' mi from ' + esc(S.zip) : S.zip ? 'not on the map' : 'add a ZIP code above') + '</dd>' +
        '<dt>Other bills</dt><dd>' + (S.fee === 'doc' ? 'Facility fee, if any, is separate' : 'Doctor’s fee and others are separate') + '</dd><dt>Flags</dt><dd>' + (o.flags.length ? esc(o.flags.join(', ')) : 'none') + '</dd></dl>' +
        '<p class="small" style="margin:10px 0 0"><a href="/v2/provider/' + St.query({ area: S.area, code: CODE, pay: S.pay, net: S.net, fee: S.fee, p: o.id, zip: S.zip }) + '">Read the receipt</a> · <a href="' + esc(o.url) + '" target="_blank" rel="noopener">Source ↗</a></p></section>';
    }).join('');
    d.__ret = btn; d.showModal();
    $('#cmpX').focus();
  }
  function csv() {
    var L = filtered(), q = function (v) { v = String(v == null ? '' : v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var rows = [['procedure_code', 'procedure', 'area', 'payment', 'network', 'fee_type', 'provider', 'city', 'kind', 'amount_usd', 'amount_high_usd', 'what_it_is', 'file_date', 'source_url', 'miles_from_zip']];
    L.forEach(function (o) { rows.push([CODE, A.D.codes[CODE].name, areaOf(S.area).name, S.pay, S.pay === 'net' ? S.net : '', S.fee === 'doc' ? 'doctor' : 'facility', o.name, o.city, kindOf(o.kind || (o.src != null ? 'H' : '')), o.v, o.hi || '', o.what, o.date, o.url, o.mi != null ? o.mi.toFixed(1) : '']); });
    var b = new Blob([rows.map(function (r) { return r.map(q).join(','); }).join('\n')], { type: 'text/csv' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'healthcare-files-' + CODE + '-' + S.area + '-' + S.pay + '.csv'; document.body.append(a); a.click(); a.remove();
  }
  function payUI() {
    $$('#paySeg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.pay === S.pay)); });
    $('#netWrap').hidden = S.pay !== 'net';
    $$('#feeSeg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.fee === S.fee)); });
    $('#feeSeg').hidden = false;
  }
  async function results() {
    try { AREAS = await getJSON('/shared/areas.json'); } catch (e) { AREAS = [{ slug: 'dfw', name: 'Dallas–Fort Worth', path: '/price-finder/', state: 'Texas' }]; }
    S.area = (areaOf(S.area) || {}).slug || 'dfw';
    S.pay = ['net', 'cash', 'all'].indexOf(S.pay) >= 0 ? S.pay : 'net';
    var a = areaOf(S.area);
    areaOptions($('#qArea'), S.area);
    $('#rWhere').textContent = a.name;
    $('#rStatus').textContent = 'Loading prices for ' + a.name + '…';
    try { A = await H.loadArea(a.path); } catch (e) { $('#rStatus').textContent = 'The prices for ' + a.name + ' didn’t load. Reload the page to try again.'; return; }
    var D = A.D;
    var items = Object.keys(D.codes).map(function (c) { return { code: c, name: D.codes[c].name }; });
    var cb = combo($('#qProc'), $('#qProcList'), items);
    $('#qForm').addEventListener('submit', function (e) {
      e.preventDefault();
      var inp = $('#qProc'), code = inp.dataset.code || (inp.value.trim() && (cb.first() || {}).code) || (D.codes[inp.value.trim().toUpperCase()] ? inp.value.trim().toUpperCase() : '');
      if (!code) { $('#qErr').hidden = false; inp.focus(); return; }
      location.href = '/v2/price-finder/' + St.query({ area: $('#qArea').value, code: code, pay: S.pay, net: S.net, fee: S.fee, zip: S.zip });
    });
    // network picker: grouped by insurer, no default (an example network is not your network)
    var ins = {}; D.nets.forEach(function (n, i) { var p = n.split('|'); (ins[p[0]] = ins[p[0]] || []).push([i, p.slice(1).join('|')]); });
    $('#net').innerHTML = '<option value="">Choose your network</option>' + Object.keys(ins).sort().map(function (k) { return '<optgroup label="' + esc(k) + '">' + ins[k].map(function (x) { return '<option value="' + esc(D.nets[x[0]]) + '">' + esc(k + ' · ' + x[1]) + '</option>'; }).join('') + '</optgroup>'; }).join('');
    if (S.net && netIndex(S.net) >= 0) $('#net').value = D.nets[netIndex(S.net)];
    CODE = S.code && D.codes[S.code] ? S.code : null;
    if (!CODE) {
      $('#rStatus').textContent = S.code ? 'We don’t have billing code ' + S.code + ' in ' + a.name + '. Search for a procedure above.' : 'Search for a procedure above.';
      $('#rTitle').textContent = 'Find a price'; $('#rCode').textContent = ''; $('#qProc').focus(); return;
    }
    var c = D.codes[CODE];
    document.title = c.name + ' · ' + a.name + ' · The Healthcare Files (V2)';
    $('#rTitle').textContent = c.name; $('#rCode').textContent = (c.type || 'Code') + ' ' + CODE; $('#crProc').textContent = c.name;
    $('#qProc').value = c.name; $('#qProc').dataset.code = CODE;
    C = await H.loadCode(a.path, CODE);
    if (!S.fee) S.fee = defaultFee(C.T);
    $('#rStatus').textContent = ''; $('#rStatus').hidden = true; $('#rBody').hidden = false;
    var rebuild = function () { ROWS = buildRows(); S.sel = S.sel.map(function (id) { if (ROWS.some(function (o) { return o.id === id; })) return id; var t = ROWS.find(function (o) { return o.place != null && 'f' + o.place === id; }); return t ? t.id : null; }).filter(function (id, i, a) { return id && a.indexOf(id) === i; }); SHOWN = 25; renderResults(); setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']); };
    payUI();
    $('#paySeg').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; S.pay = b.dataset.pay; payUI(); rebuild(); });
    $('#feeSeg').addEventListener('click', function (e) { var b = e.target.closest('button'); if (!b) return; S.fee = b.dataset.fee; payUI(); rebuild(); });
    $('#net').addEventListener('change', function () { S.net = $('#net').value; rebuild(); });
    $('#fKind').value = S.kind || ''; $('#fKind').addEventListener('change', function () { S.kind = $('#fKind').value; SHOWN = 25; renderResults(); setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']); });
    $('#fZip').value = S.zip || '';
    var zipMsg = $('#fZipMsg');
    var applyZip = function () {
      var z = $('#fZip').value.trim();
      if (z && !/^\d{5}$/.test(z)) { zipMsg.textContent = 'Enter a 5-digit ZIP code.'; return; }
      if (z && !(A.G && A.G.zips && A.G.zips[z])) { zipMsg.textContent = 'That ZIP code isn’t in this area’s map.'; return; }
      zipMsg.textContent = z ? 'Showing places within ' + (S.rad || 25) + ' miles. Your ZIP code stays in your browser.' : '';
      S.zip = z; ROWS = buildRows(); SHOWN = 25; renderResults(); setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']);
    };
    $('#fZipGo').addEventListener('click', applyZip);
    $('#fZip').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); applyZip(); } });
    $('#fRad').addEventListener('change', function () { S.rad = $('#fRad').value; renderResults(); });
    $('#fSort').addEventListener('change', function () { S.sort = $('#fSort').value; renderResults(); });
    $('#rList').addEventListener('change', function (e) {
      var cbx = e.target.closest('input[type=checkbox][data-id]'); if (!cbx) return;
      var id = cbx.dataset.id, i = S.sel.indexOf(id);
      if (cbx.checked && i < 0) { if (S.sel.length >= 4) { cbx.checked = false; $('#cmpHint').textContent = 'Up to 4 at a time. Clear one first.'; return; } S.sel.push(id); }
      if (!cbx.checked && i >= 0) S.sel.splice(i, 1);
      cbx.closest('.pc').classList.toggle('sel', cbx.checked); cmpBar(); setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']);
    });
    $('#rMore').addEventListener('click', function () { SHOWN += 25; renderResults(); });
    $('#cmpGo').addEventListener('click', function (e) { if (S.sel.length >= 2) openCompare(e.currentTarget); });
    $('#cmpClr').addEventListener('click', function () { S.sel = []; renderResults(); setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']); });
    var dlg = $('#cmpDlg');
    $('#cmpX').addEventListener('click', function () { dlg.close(); });
    dlg.addEventListener('close', function () { if (dlg.__ret) dlg.__ret.focus(); });
    $('#csvGo').addEventListener('click', csv);
    $('#mapGo').addEventListener('click', function () { $('#mapNote').hidden = false; $('#mapOrig').href = window.HCF_SWITCH ? (function () { var s0 = S.view; S.view = 'map'; setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel', 'view']); var h = window.HCF_SWITCH.toOriginal(); S.view = s0; setURL(['area', 'code', 'pay', 'net', 'fee', 'zip', 'kind', 'sel']); return h; })() : a.path; $('#mapNote').focus(); });
    $('#rExtra').innerHTML = excludedBlock() + benchBlock() + billsBlock();
    $('#rCalc').href = '/v2/plan-calculator/' + St.query({ code: CODE, area: S.area, pay: S.pay, net: S.net });
    rebuild();
  }

  // ==========================================================================================
  // RECEIPT (one provider, one procedure)
  // ==========================================================================================
  async function receipt() {
    try { AREAS = await getJSON('/shared/areas.json'); } catch (e) { AREAS = [{ slug: 'dfw', name: 'Dallas–Fort Worth', path: '/price-finder/', state: 'Texas' }]; }
    S.area = (areaOf(S.area) || {}).slug || 'dfw';
    var a = areaOf(S.area), box = $('#rcBody');
    try { A = await H.loadArea(a.path); } catch (e) { box.innerHTML = '<p class="empty">This area’s prices didn’t load. Reload the page to try again.</p>'; return; }
    var D = A.D; CODE = S.code;
    if (!CODE || !D.codes[CODE] || !S.p) { box.innerHTML = '<p class="empty">This receipt link is missing its procedure or provider. <a href="/v2/price-finder/' + St.query({ area: S.area, code: CODE }) + '">Back to the results</a>.</p>'; return; }
    C = await H.loadCode(a.path, CODE);
    S.pay = ['net', 'cash', 'all'].indexOf(S.pay) >= 0 ? S.pay : 'net';
    if (!S.fee) S.fee = defaultFee(C.T);
    ROWS = buildRows();
    var o = ROWS.find(function (x) { return x.id === S.p; });
    var back = '/v2/price-finder/' + St.query({ area: S.area, code: CODE, pay: S.pay, net: S.net, fee: S.fee, zip: S.zip });
    $('#crBack').href = back; $('#crProc').textContent = D.codes[CODE].name; $('#crProc').href = back;
    var qid = S.p.charAt(0), idx = +S.p.slice(1), bad = quarantined();
    if (qid === 'h' && bad.indexOf(idx) >= 0) {
      var x = D.hosp.src[idx] || [];
      box.innerHTML = '<div class="note bad"><b>This price file is left out of ' + esc(a.name) + '.</b> ' + esc(R.nice(x[0])) + '’s file gives an address in another state, so it is not offered as a nearby choice. <a href="' + esc(x[4]) + '" target="_blank" rel="noopener">The file ↗</a></div>';
      return;
    }
    var name = o ? o.name : qid === 'f' && D.fac[idx] ? tidy(D.fac[idx][0]) : qid === 'h' && D.hosp.src[idx] ? R.nice(D.hosp.src[idx][0]) : qid === 'c' && D.cash[idx] ? D.cash[idx].name : 'This provider';
    var city = o ? o.city : qid === 'f' && D.fac[idx] ? D.fac[idx][1] : '';
    var kind = qid === 'f' && D.fac[idx] ? D.fac[idx][2] : qid === 'h' ? 'H' : '';
    document.title = name + ' · ' + D.codes[CODE].name + ' · The Healthcare Files (V2)';
    $('#crName').textContent = name;
    var npi = null, prof = null;
    var place = qid === 'f' ? idx : o && o.place != null ? o.place : null;
    if (place != null && D.fac[place]) { kind = D.fac[place][2]; }
    try { if (place != null) { var N = await getJSON('/shared/npi/' + S.area + '.json'); npi = N[place] || null; } } catch (e) {}
    try { var P = await getJSON('/shared/profiles.json'); prof = (npi && P.npi[npi]) || (qid === 'h' && P.file[(D.hosp.src[idx] || [])[4]]) || null; } catch (e) {}
    var fee = S.fee === 'doc' ? 'doctor' : 'facility';
    var payLabel = S.pay === 'cash' ? 'Paying cash' : S.pay === 'all' ? 'Every network' : netIndex(S.net) >= 0 ? netLabel(netIndex(S.net)) : 'No network chosen';
    var h = '';
    h += '<section class="receipt" aria-labelledby="crName"><div class="id"><p class="tag blue">' + esc(kindOf(kind)) + '</p><h2 style="margin-top:8px">' + esc(name) + '</h2><p>' + esc([city, a.name].filter(Boolean).join(' · ')) + (o && o.legal && o.legal.toLowerCase() !== name.toLowerCase() ? ' · listed by insurers as ' + esc(o.legal) : '') + (o && o.mi != null ? ' · ' + o.mi.toFixed(1) + ' mi from ' + esc(S.zip) : '') + '</p></div>';
    if (!o) {
      h += '<div class="note warn" style="margin-top:14px"><b>No ' + fee + ' price for this choice.</b> ' + esc(payLabel) + ' lists no dollar ' + fee + ' rate for this procedure at this provider in the files we read. Try another payment choice or fee type on the <a href="' + back + '">results</a>.</div>';
    } else {
      h += '<div class="big"><span class="price">' + money(o.v) + '</span>' + (S.pay === 'all' && o.hi != null && o.hi !== o.v ? '<span class="price sm muted">to ' + money(o.hi) + '</span>' : '') + '<span class="tag">' + esc(S.pay === 'cash' ? 'cash price' : 'negotiated rate') + '</span></div>';
      h += '<p style="margin:4px 0 0">' + esc(o.what) + '</p>';
      h += '<p class="note" style="margin-top:12px">' + (S.pay === 'cash' ? 'A published cash price. Ask whether it is a package and what it leaves out before you pay.' : '<b>This is not your bill.</b> It is the total the network agreed to pay. Your share depends on your plan.') + '</p>';
      if (o.flags.length || stale(o.date)) h += '<p style="margin:10px 0 0">' + o.flags.map(function (f) { return '<span class="tag flag">' + esc(f) + '</span> '; }).join('') + (stale(o.date) ? '<span class="tag flag">file over 6 months old</span>' : '') + '</p>';
      // what's included: only what the source says, unknowns stated
      var lab = o.r && o.r[10] >= 0 ? D.labs[o.r[10]] : '';
      h += '<h3 id="included">What this price covers</h3><ul class="inc">';
      if (S.pay === 'cash') h += '<li class="y">' + (o.src != null ? 'The hospital’s own price-file line' + (o.setting ? ' (' + ({ o: 'outpatient', i: 'inpatient', b: 'inpatient or outpatient' }[o.setting] || o.setting) + ')' : '') + (o.list ? ', list price ' + money(o.list) : '') : 'The price as posted on the provider’s website' + (o.note ? ': ' + esc(o.note) : '')) + '</li>';
      else h += '<li class="y">' + (S.fee === 'doc' ? 'The doctor’s (professional) fee, as the insurer file lists it' : 'The facility’s fee (room, staff, equipment), as the insurer file lists it') + (lab ? '. The file says: “' + esc(lab) + '”' : '') + '</li>';
      h += '</ul><h3>May be billed separately</h3><ul class="inc">' + (S.fee === 'doc' ? '<li class="q">The facility fee, if done at a hospital or surgery center: unknown here</li>' : '<li class="q">The doctor’s fee: unknown here. See doctor’s fees on the <a href="' + esc('/v2/price-finder/' + St.query({ area: S.area, code: CODE, pay: S.pay, net: S.net, fee: 'doc' })) + '">results</a></li>') +
        '<li class="q">Anesthesia, pathology or other services, if needed: unknown here</li></ul>';
      if (o.r && (o.r[7] || o.r[9])) {
        var ex = (o.r[8] || []).map(function (v) { return '<li>' + esc(D.labs[v[1]] || 'same service, another contract line') + ': ' + (o.r[2] ? v[0] + '%' : money(v[0])) + '</li>'; }).join('');
        h += '<h3>Other lines in this file</h3><ul class="qs">' + ex + (o.r[7] - (o.r[8] || []).length > 0 ? '<li>and ' + (o.r[7] - (o.r[8] || []).length) + ' more</li>' : '') + (o.r[9] ? '<li>' + o.r[9] + ' line' + (o.r[9] > 1 ? 's' : '') + ' at $0 (paid inside another charge)</li>' : '') + '</ul>';
      }
      if (S.pay !== 'cash') h += '<p style="margin:18px 0 0"><a class="btn y" href="/v2/plan-calculator/' + St.query({ code: CODE, area: S.area, pay: S.pay, net: S.net, p: S.p, fee: S.fee }) + '">Estimate my share →</a></p>';
      // source details
      h += '<details open><summary>Source details</summary><dl class="kv">' +
        '<dt>Publisher</dt><dd>' + esc(S.pay === 'cash' ? (o.src != null ? name + ' (its own price file)' : name + ' (its website)') : (A.D.nets[o.net] || '').split('|')[0] + ' (insurer price file)') + '</dd>' +
        (S.pay !== 'cash' ? '<dt>Network</dt><dd>' + esc(netLabel(o.net)) + '</dd>' : '') +
        '<dt>Rate type</dt><dd>' + esc(S.pay === 'cash' ? 'cash price' : 'negotiated rate, ' + fee + ' fee') + '</dd>' +
        '<dt>File date</dt><dd>' + esc(fmtDate(o.date)) + (stale(o.date) ? ' (over 6 months old)' : '') + '</dd>' +
        (o.row ? '<dt>Where in the file</dt><dd>' + esc((o.unit || 'row') + ' ' + o.row) + '</dd>' : '') +
        '<dt>File</dt><dd><a href="' + esc(o.url) + '" target="_blank" rel="noopener">' + esc(String(o.url).replace(/^https?:\/\//, '').slice(0, 70)) + '… ↗</a></dd></dl>' +
        '<p class="small muted" style="margin:10px 0 0">Large files can open in data software, not a browser. How we read them: <a href="/methodology/">Methodology</a> (Original page).</p></details>';
    }
    // every rate this provider has for this code
    if (qid === 'f' && C.T[idx]) {
      var rs = C.T[idx].filter(function (r) { return r[1] === (S.fee === 'doc' ? 1 : 0); }).sort(function (a, b) { return a[2] - b[2] || a[3] - b[3]; });
      if (rs.length) {
        var per = {}; rs.forEach(function (r) { if (!per[r[0]]) per[r[0]] = r; });
        h += '<details><summary>Every network’s rate here (' + Object.keys(per).length + ')</summary><table class="rates"><thead><tr><th scope="col">Network</th><th scope="col" class="n">Lowest listed</th><th scope="col">File</th></tr></thead><tbody>' +
          Object.keys(per).map(function (k) { var r = per[k]; return '<tr' + (S.pay === 'net' && +k === netIndex(S.net) ? ' class="mine"' : '') + '><td>' + esc(netLabel(+k)) + (R.flags(r).length ? '<div class="small muted">' + esc(R.flags(r).join(', ')) + '</div>' : '') + '</td><td class="n">' + (r[2] ? r[3] + '% of billed charges' : (r[4] & 4) ? '$0 listed' : money(r[3])) + '</td><td><a href="' + esc(D.urls[r[6]]) + '" target="_blank" rel="noopener">' + esc(fmtDate(D.dates[r[5]])) + ' ↗</a></td></tr>'; }).join('') +
          '</tbody></table></details>';
      }
    }
    h += '<details id="questions"><summary>Before booking: questions to ask</summary><ol class="qs" id="qsList"><li>Is ' + esc(name) + ' in my plan’s network for this?</li><li>What billing code will you use? (We looked up ' + esc(CODE) + '.)</li><li>Which other providers will bill me (doctor, anesthesia, pathology)? Are they in my network?</li><li>What will I owe after my deductible and coinsurance? Can I get a written good-faith estimate?</li></ol><button type="button" class="btn" id="qsCopy">Copy these questions</button> <span id="qsMsg" role="status" class="small muted"></span></details>';
    h += '<details><summary>Think there’s an error?</summary><p>Tell us what looks wrong and we’ll check it against the file. <a href="/corrections/">Corrections and right of reply</a> (Original page).</p></details>';
    h += '</section>';
    // side: background (separate from price data), benchmark
    var side = '<aside class="side" aria-label="About this provider"><section class="card" id="background"><h2 style="font-size:18px;margin:0 0 6px">Background</h2>' +
      '<p class="small muted" style="margin:0 0 8px">Who this is, from public records. This is not a quality rating or an endorsement.</p><dl class="kv">' +
      '<dt>Kind of place</dt><dd>' + esc(kindOf(kind)) + '</dd>' + (city ? '<dt>City</dt><dd>' + esc(city) + '</dd>' : '') +
      (npi ? '<dt>NPI</dt><dd>' + esc(npi) + ' · <a href="https://npiregistry.cms.hhs.gov/provider-view/' + esc(npi) + '" target="_blank" rel="noopener">address in the NPI Registry ↗</a></dd>' : '') + '</dl>' +
      (prof ? '<p style="margin:10px 0 0"><a href="/hospitals/' + esc(prof) + '/">Hospital profile: ownership, Medicare rating, price files</a> (Original page)</p>' : '<p class="small muted" style="margin:10px 0 0">No hospital profile for this provider.</p>') + '</section>' +
      '<section class="card">' + (benchBlock() || '<p class="muted">No Medicare benchmark for this code.</p>') + '</section></aside>';
    box.innerHTML = '<div class="rc-grid">' + h + side + '</div>';
    var qc = $('#qsCopy'); if (qc) qc.addEventListener('click', function () {
      var t = $$('#qsList li').map(function (li, i) { return (i + 1) + '. ' + li.textContent; }).join('\n');
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { $('#qsMsg').textContent = 'Copied.'; }, function () { $('#qsMsg').textContent = 'Couldn’t copy. Select the text instead.'; });
    });
    if (location.hash) { var t = document.getElementById(location.hash.slice(1)); if (t) { if (t.tagName === 'DETAILS') t.open = true; t.scrollIntoView(); } }
    St.save(S);
  }

  // ==========================================================================================
  // CALCULATOR
  // ==========================================================================================
  async function calculator() {
    var K = window.HCF_CALC;
    var tabs = $$('.ctabs [role=tab]'), panes = $$('[role=tabpanel]');
    var show = function (id) { tabs.forEach(function (t) { var on = t.id === id; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; }); panes.forEach(function (p) { p.hidden = p.getAttribute('aria-labelledby') !== id; }); };
    $('.ctabs').addEventListener('click', function (e) { var t = e.target.closest('[role=tab]'); if (t) show(t.id); });
    $('.ctabs').addEventListener('keydown', function (e) { var i = tabs.indexOf(document.activeElement); if (i < 0) return; if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { e.preventDefault(); var n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); show(n.id); } });
    show(S.tab === 'own' ? 'tOwn' : S.tab === 'mine' ? 'tMine' : 'tMkt');
    // ---- marketplace: the Original calculator's own data and functions ----
    var html = '';
    try { var r = await H.nativeFetch('/plan-calculator/', { credentials: 'same-origin' }); html = await r.text(); } catch (e) {}
    var block = function (id) { var i = html.indexOf('id="' + id + '"'); if (i < 0) return null; return JSON.parse(html.slice(html.indexOf('>', i) + 1, html.indexOf('</script>', i))); };
    var YEARS = { 2027: 'data2027', 2026: 'data' }, YEAR = YEARS[+S.year] ? +S.year : 2027, D = null;
    try { D = block(YEARS[YEAR]); } catch (e) {}
    if (!D || !K) { $('#mStatus').textContent = 'The marketplace plans didn’t load. Reload the page to try again.'; }
    else {
      var isPro = K.isProFor(D), INS = K.INS || {};
      $('#mYear').innerHTML = Object.keys(YEARS).sort().reverse().map(function (y) { return '<option value="' + y + '"' + (+y === YEAR ? ' selected' : '') + '>' + y + ' plans</option>'; }).join('');
      $('#mYear').addEventListener('change', function () { S.year = $('#mYear').value; location.search = St.query(S, ['code', 'area', 'pay', 'net', 'p', 'fee', 'year']); });
      var insurers = []; D.net.forEach(function (n) { if (insurers.indexOf(n[0]) < 0) insurers.push(n[0]); });
      var byIns = {}; D.plans.forEach(function (p) { var i = D.net[p.k][0]; (byIns[i] = byIns[i] || []).push(p); });
      var M = { ins: null, plan: S.plan || null, proc: null, paid: +S.paid || 0, kind: S.fee === 'doc' ? 'pro' : 'fac', all: false };
      var start = S.plan && D.plans.find(function (p) { return p.id === S.plan; });
      M.ins = start ? D.net[start.k][0] : insurers.indexOf('Blue Cross and Blue Shield of Texas') >= 0 ? 'Blue Cross and Blue Shield of Texas' : insurers[0];
      var codeIn = S.code && D.proc.some(function (p) { return p[0] === S.code; });
      M.proc = codeIn ? S.code : (D.proc.find(function (p) { return p[0] === '73721'; }) || D.proc[0])[0];
      if (S.code && !codeIn) $('#mCodeNote').innerHTML = '<div class="note warn">The marketplace calculator covers ' + D.proc.length + ' common procedures, and billing code ' + esc(S.code) + ' isn’t one of them yet. Use <b>Enter my plan</b> for it, or pick a covered procedure below.</div>';
      var opt = function (v, t, s) { return '<option value="' + esc(v) + '"' + (s ? ' selected' : '') + '>' + esc(t) + '</option>'; };
      $('#mIns').innerHTML = insurers.map(function (i) { return opt(i, INS[i] || i, i === M.ins); }).join('');
      var fillPlans = function () {
        var seen = {}, ps = (byIns[M.ins] || []).filter(function (p) { var k = JSON.stringify([p.n, p.m, p.d, p.x, p.k, p.cs]); if (seen[k]) return false; seen[k] = 1; return true; })
          .sort(function (a, b) { return a.k - b.k || a.d - b.d || a.n.localeCompare(b.n); });
        var g = {}; ps.forEach(function (p) { var n = D.net[p.k][1]; (g[n] = g[n] || []).push(p); });
        $('#mPlan').innerHTML = Object.keys(g).map(function (n) { return '<optgroup label="' + esc(n) + ' network">' + g[n].map(function (p) { return opt(p.id, p.n + ' · ' + p.m + ' · $' + Math.round(p.d).toLocaleString() + ' deductible', false); }).join('') + '</optgroup>'; }).join('');
        if (!ps.some(function (p) { return p.id === M.plan; })) M.plan = (ps.find(function (p) { return p.m === 'Silver' && p.d >= 1500; }) || ps.find(function (p) { return p.d > 0; }) || ps[0]).id;
        $('#mPlan').value = M.plan;
      };
      fillPlans();
      $('#mProc').innerHTML = D.proc.map(function (p) { return opt(p[0], p[1], p[0] === M.proc); }).join('');
      $('#mPaid').value = M.paid || '';
      $('#mCount').textContent = D.plans.length.toLocaleString() + ' Dallas–Fort Worth marketplace plans for ' + YEAR + ' have rates we could match to their insurer’s network files. A plan that isn’t listed isn’t supported yet; we don’t guess its network.';
      var render = function () {
        var p = D.plans.find(function (x) { return x.id === M.plan; }), pi = D.proc.findIndex(function (x) { return x[0] === M.proc; });
        var paid = Math.min(Math.max(+M.paid || 0, 0), p.d), dedRem = p.d - paid, oopRem = Math.max(p.x - paid, 0);
        var all = D.rates.filter(function (r) { return r[0] === p.k && r[1] === pi; });
        var skip = function (r) { return window.__calcSkip && window.__calcSkip(D.prov[r[2]][0], D.proc[pi] && D.proc[pi][1]); };
        var usable = function (r) { return !skip(r) && p.cs[r[5]]; };
        // review F03: tab counts and the result count use the same unit (distinct providers) and the same exclusions
        var nU = function (f) { var s = new Set(); all.forEach(function (r) { if (f(r) && usable(r)) s.add(r[2]); }); return s.size; };
        $('#mkFac').textContent = 'Facility fees (' + nU(function (r) { return !isPro(r); }) + ')';
        $('#mkPro').textContent = 'Doctor fees (' + nU(isPro) + ')';
        $('#mkFac').setAttribute('aria-pressed', String(M.kind === 'fac')); $('#mkPro').setAttribute('aria-pressed', String(M.kind === 'pro'));
        var list = all.filter(function (r) { return (M.kind === 'pro' ? isPro(r) : !isPro(r)) && usable(r); })
          .map(function (r) { return { r: r, o: K.oop(r[3], p.cs[r[5]], dedRem, oopRem) }; })
          .sort(function (a, b) { return a.o.pay - b.o.pay || a.r[3] - b.r[3]; });
        var nProv = new Set(list.map(function (x) { return x.r[2]; })).size;
        $('#mTicket').innerHTML = '<div class="row"><span>Deductible</span><b>$' + Math.round(p.d).toLocaleString() + '</b></div><div class="row"><span>Left to meet</span><b>$' + Math.round(dedRem).toLocaleString() + '</b></div><div class="row"><span>Out-of-pocket max</span><b>$' + Math.round(p.x).toLocaleString() + '</b></div>' +
          (p.sbc ? '<p class="small" style="margin:8px 0 0"><a href="' + esc(p.sbc) + '" target="_blank" rel="noopener">This plan’s Summary of Benefits ↗</a></p>' : '');
        var head = D.proc[pi][1] + ' (' + (/^\d{3}$/.test(D.proc[pi][0]) ? 'DRG ' : 'CPT ') + D.proc[pi][0] + ')';
        $('#mHead').textContent = head;
        $('#mN').textContent = list.length ? nProv + ' ' + (M.kind === 'pro' ? 'providers' : 'facilities') + ' in network' + (list.length !== nProv ? ' (' + list.length + ' rates)' : '') + ' · lowest share first' : '';
        if (!list.length) { $('#mList').innerHTML = '<li class="empty" style="display:block">' + esc(INS[D.net[p.k][0]] || D.net[p.k][0]) + '’s rate file has no dollar rate of this type for this procedure on this network in Dallas–Fort Worth. Try the other fee type or another plan.</li>'; $('#mMore').hidden = true; est(null); return; }
        var low = list[0].o.pay, shown = M.all ? list : list.slice(0, 25);
        $('#mList').innerHTML = shown.map(function (x) { var pv = D.prov[x.r[2]], pro = isPro(x.r);
          return '<li class="' + (x.o.pay === low ? 'low' : '') + '"' + (npiWant && pv[3] === npiWant ? ' style="outline:3px solid var(--yellow)"' : '') + '><div><b>' + esc(pv[0]) + '</b><div class="small muted">' + esc(pv[1] + ' · ' + pv[2]) + ' · <a href="' + esc(D.src[x.r[8]]) + '" target="_blank" rel="noopener">insurer file, ' + esc(fmtDate(x.r[9])) + ' ↗</a></div></div>' +
            '<div class="pay">' + money(x.o.pay) + '<span class="of">your share of ' + money(x.r[3]) + ' ' + (pro ? "doctor's fee" : 'facility fee') + '</span></div><div class="how">You pay: ' + x.o.how.replace(/<[^>]+>/g, '') + '</div></li>'; }).join('');
        $('#mMore').hidden = M.all || list.length <= 25; $('#mMore').textContent = 'Show all ' + list.length + ' rates';
        var mine = npiWant ? list.find(function (x) { return D.prov[x.r[2]][3] === npiWant; }) : null;
        est(mine || list[0], !!mine, p);
        S.plan = M.plan; S.paid = String(M.paid || ''); S.code = M.proc; S.year = String(YEAR);
        setURL(['code', 'area', 'pay', 'net', 'p', 'fee', 'year', 'plan', 'paid']);
      };
      var est = function (x, isMine, p) {
        var e = $('#mEst');
        if (!x) { e.innerHTML = '<h2>Your estimate</h2><p>Not calculated: no rate of this type on this plan’s network.</p>'; return; }
        var pv = D.prov[x.r[2]];
        e.innerHTML = '<h2>' + (isMine ? 'Your estimate at ' + esc(pv[0]) : 'Lowest estimate on this plan') + '</h2>' +
          (npiWant && !isMine ? '<p class="small">The provider you picked has no rate of this type on this plan’s network in the calculator’s data, so this shows the lowest instead.</p>' : '') +
          '<div class="row"><span>' + (isPro(x.r) ? 'Doctor’s fee' : 'Facility fee') + ' (negotiated)</span><b>' + money(x.r[3]) + '</b></div>' +
          '<div class="row you"><span>Your share</span><b>' + money(x.o.pay) + '</b></div><p class="small" style="margin:6px 0 0">' + esc(x.o.how.replace(/<[^>]+>/g, '')) + '</p>' +
          '<p class="small" style="margin:8px 0 0">Other bills (doctor, anesthesia, pathology) are not included. Each has its own share.</p>';
      };
      var npiWant = null;
      if (S.p && /^f\d+$/.test(S.p) && S.area) { try { var NN = await getJSON('/shared/npi/' + S.area + '.json'); npiWant = NN[+S.p.slice(1)] || null; } catch (e) {} }
      $('#mIns').addEventListener('change', function () { M.ins = $('#mIns').value; M.all = false; fillPlans(); render(); });
      $('#mPlan').addEventListener('change', function () { M.plan = $('#mPlan').value; M.all = false; render(); });
      $('#mProc').addEventListener('change', function () { M.proc = $('#mProc').value; M.all = false; render(); });
      $('#mPaid').addEventListener('input', function () { M.paid = $('#mPaid').value; render(); });
      $('#m0').addEventListener('click', function () { M.paid = 0; $('#mPaid').value = ''; render(); });
      $('#mAll').addEventListener('click', function () { var p = D.plans.find(function (x) { return x.id === M.plan; }); M.paid = p.d; $('#mPaid').value = p.d; render(); });
      $('#mkFac').addEventListener('click', function () { M.kind = 'fac'; M.all = false; render(); });
      $('#mkPro').addEventListener('click', function () { M.kind = 'pro'; M.all = false; render(); });
      $('#mMore').addEventListener('click', function () { M.all = true; render(); });
      $('#mStatus').textContent = ''; $('#mStatus').hidden = true; $('#mBody').hidden = false;
      render();
    }
    // ---- enter my plan: the same cost-sharing function on a rate from the files, or one the visitor types ----
    var rateBox = $('#oRate'), rateSrc = $('#oRateSrc');
    if (S.p && S.code && S.area) {
      try {
        AREAS = await getJSON('/shared/areas.json'); var a = areaOf(S.area); A = await H.loadArea(a.path); CODE = S.code; C = await H.loadCode(a.path, CODE);
        S.fee = S.fee || defaultFee(C.T); S.pay = S.pay || 'net'; ROWS = buildRows(); var o = ROWS.find(function (x) { return x.id === S.p; });
        if (o && S.pay !== 'cash') { rateBox.value = o.v; rateSrc.innerHTML = 'From the receipt: ' + esc(o.name) + ', ' + esc(o.what) + ', file dated ' + esc(fmtDate(o.date)) + '. <a href="' + esc(o.url) + '" target="_blank" rel="noopener">Source ↗</a>'; }
      } catch (e) {}
    }
    var oCalc = function () {
      var rate = +rateBox.value, ded = $('#oDed').value, co = $('#oCo').value, cp = $('#oCp').value, oop = $('#oOop').value, out = $('#oEst');
      if (!(rate > 0) || ded === '' || co === '') { out.innerHTML = '<h2>Your estimate</h2><div class="row"><span>Rate</span><b>' + (rate > 0 ? money(rate) : 'Not set') + '</b></div><div class="row you"><span>Your share</span><b>Not calculated</b></div><p class="small">Enter the rate, how much of your deductible is left, and your coinsurance. Your plan’s Summary of Benefits lists them.</p>'; return; }
      var r = K.oop(rate, [+cp || 0, +co || 0, 1], +ded || 0, oop === '' ? 1e12 : +oop);
      out.innerHTML = '<h2>Your estimate</h2><div class="row"><span>Rate (negotiated)</span><b>' + money(rate) + '</b></div><div class="row you"><span>Your share</span><b>' + money(r.pay) + '</b></div><p class="small" style="margin:6px 0 0">' + esc(r.how.replace(/<[^>]+>/g, '')) + '</p>' +
        '<p class="small" style="margin:8px 0 0">Assumes the deductible applies before coinsurance and that this is in-network. Family deductibles, tiers and per-day copays are not handled here. Other bills are not included.</p>';
    };
    ['oRate', 'oDed', 'oCo', 'oCp', 'oOop'].forEach(function (id) { $('#' + id).addEventListener('input', oCalc); });
    oCalc();
    $('#ownOrig').href = '/plan-calculator/#own';
  }

  // the version switch asks V2 which Original rows the selection means (a hospital file's row -> the provider it belongs to)
  window.HCF_V2 = { origSel: function () { return (S.sel || []).map(function (id) { var o = ROWS.find(function (x) { return x.id === id; }); return o && o.fi != null ? 'f' + o.fi : o && o.place != null ? 'f' + o.place : null; }).filter(Boolean); },
                    origP: function () { var o = ROWS.find(function (x) { return x.id === S.p; }); return o && o.fi != null ? 'f' + o.fi : o && o.place != null ? 'f' + o.place : null; } };
  var run = { home: home, results: results, receipt: receipt, calculator: calculator }[page];
  if (run) run().catch(function (e) { var s = $('#rStatus') || $('#mStatus') || $('main'); if (s) s.insertAdjacentHTML('beforeend', '<p class="note bad">Something went wrong loading this page. Reload to try again.</p>'); console.error(e); });
})();
