/* Price Finder "Compare" view (Oct 19, 2026, Betsy): every place x every insurer for the code on screen.
   Served as /pf-table.js and loaded by every Price Finder after its own scripts (site/pf_table.py adds the tag).
   Rows: the kinds of places that do this service (same rules as the price pages, site/procedure_pages.py). Columns: Medicare
   for that place, Medicare Advantage and cash from the hospital's own file, then one column per insurer with a network
   picker. The first row is the doctor's fee in each network. Pick a network under "How are you paying?" and the table
   narrows to that network: the place's fee + the doctor's fee, against Medicare. Tick places to compare them side by side.
   Nothing is estimated or averaged: every figure is a published price; the doctor's "typical" fee is the middle listed one.
   ml.json next to the page (site/ux_polish.py write_ml): f = {provider index: wage index} for places matched to their
   Medicare record, h = {hospital file index: [provider index, ...]} from CMS IDs (data/hospitals.csv + NPI matches). */
(function () {
  if (typeof D === 'undefined' || typeof render !== 'function' || !document.getElementById('board')) return;
  var E = function (s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  var M$ = function (v) { return '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}); };
  var X = function (x) { return (x < 10 ? x.toFixed(1) : Math.round(x).toLocaleString()) + '×'; };
  var BAND = function (x) { return x <= 1.5 ? 1 : x <= 3 ? 2 : x <= 5 ? 3 : 4; };
  // same rules as site/procedure_pages.py (NOT_HERE, SPECIALTY, FERTILITY, IMAGING, LAB)
  var NOT_HERE = /rehab|behavioral|psychiatr|hospice|nursing|long[- ]?term|\bltac\b|kindred|select specialty|\bopco\b|real estate|skilled|senior living|assisted living|home health|dialysis|\bdental|\bdds\b|pharmacy|lifecare|\bvibra\b|\bltach?\b|nexus specialty|acuity hospital|post[- ]?acute|cornerstone (?:hospital|specialty)|texas health specialty hospital|transitional hospitals/i;
  var SPEC = [[/\beye\b|eyecare|surgeye|vision|retina|ophthalm|lasik|cataract/i, ['Eye']], [/cardiac|cardio|\bheart\b|\bcath\b|vascular/i, ['Heart', 'Imaging', 'Inpatient stays']],
    [/nephrolog|kidney/i, ['Lab tests']], [/dermatolog|plastic surg|cosmetic|aesthetic/i, []], [/\bpain\b/i, ['Pain management', 'Spine']],
    [/endoscop|gastro|\bgi\b|digestive|colon/i, ['GI', 'Anesthesia']], [/orthop|\bspine\b|sports med/i, ['Orthopedics', 'Spine', 'Pain management', 'Imaging', 'Physical therapy']]];
  var FERT = /reproduct|fertility|\bivf\b|\bccrm\b/i, IMG = /imag|radiolog|\bmri\b|diagnostic|\bscan|x-?ray|ultrasound|mammo|breast/i;
  var LABRX = /\blab\b|labs\b|laborator|diagnostic|patholog|quest|labcorp|bioreference|sonic|clinical ref/i;
  var LEG = {'Digestive system': 'GI', 'Heart and blood vessels': 'Heart', 'Brain, spine and nerves': 'Spine', 'Anesthesia': 'Anesthesia', 'Visits': 'Office visits',
    'Imaging and radiation therapy': 'Imaging', 'Ultrasound': 'Imaging', 'Nuclear medicine': 'Imaging'};
  var PAR = /par\s*plan/i;
  var T = {all: false, n: 25, q: '', k: '', sel: {}, col: {}};
  var ML = null, LEGAL = {};
  var CHILD = /child|pediatric|scottish rite/i, VA = /\bVA\b|\bVAMC\b|veterans/i, WRONG = /dallascohospital\.org/i;
  var PERSON = /(^|[ ,])(M\.?D\.?|D\.?O\.?|DPM|DDS|DMD|PA-C|NP|FNP|APRN|CRNA|LCSW|LPC|PhD)($|[ ,])/;
  var MDDO = /(^|[ ,])(M\.?D\.?|D\.?O\.?)($|[ ,])/;
  // the files' spelling slips (the page's own tidy() fixes them on screen; these keep one row per place)
  D.fac.forEach(function (x) {
    x[0] = String(x[0]).replace(/\bMuesnter\b/g, 'Muenster').replace(/\bSouhtlake\b/g, 'Southlake');
    if ((x[2] === 'H' || x[2] === 'A') && PERSON.test(x[0]) && !/hospital|center|surgery|clinic/i.test(x[0])) x[2] = 'P';   // a person filed as a facility
  });
  function applyNames() {     // the name people know (CMS's hospital name), with the legal name kept for the fine print
    if (!ML || ML.nf !== D.fac.length || !ML.nm) return;
    Object.keys(ML.nm).forEach(function (i) { if (LEGAL[i] == null) { LEGAL[i] = D.fac[i][0]; D.fac[i][0] = ML.nm[i]; } });
  }
  try { fetch('ml.json').then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { ML = j || {}; if (j && !window.UXML) window.UXML = j; applyNames(); cache = {}; FITC = {}; render(); }).catch(function () { ML = {}; }); } catch (e) { ML = {}; }

  function placeholder(v, med) {
    if (!med || v <= 5 * med) return false;
    var t = v.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    return t.indexOf('9999') >= 0 || /^\d*999(\.99?)?$/.test(t) || (v >= 100000 && v % 10000 === 0 && v > 20 * med) || v > 100 * med;
  }
  function median(xs) { xs = xs.slice().sort(function (a, b) { return a - b; }); return xs.length >= 5 ? xs[xs.length >> 1] : null; }
  function kindOf(i) { var x = D.fac[i]; return x[2] === 'A' && /\bhospital\b/i.test(x[0]) ? 'H' : x[2]; }
  function pfsOf(code) { var m = D.med && D.med.codes[code]; if (!m || !m.pfs) return null; var k = Object.keys(m.pfs)[0]; return k ? m.pfs[k] : null; }

  // the kinds of places that do a service (same rules as the price pages); also used by the Price list tab
  var FITC = {};
  function fitsFor(code, i) {
    var C = D.codes[code] || {}, cat = LEG[C.cat] || C.cat || '', drg = /DRG/.test(C.type || '');
    var key = code + '|' + i; if (key in FITC) return FITC[key];
    var SURG = /^(GI|Orthopedics|Spine|Pain management|Eye|Ear|Urology|Gynecology|Skin and breast|Lungs and nose|Endocrine|Blood and lymph|Surgery|ENT)$/;
    var kinds = drg ? 'H' : /^(Imaging|Lab tests)$/.test(cat) ? 'HG' : SURG.test(cat) ? 'HA' : 'HAG';
    var nm = D.fac[i][0], k = kindOf(i), ok = true;
    if (kinds.indexOf(k) < 0 || NOT_HERE.test(nm) || (FERT.test(nm) && !/^(Imaging|Lab tests|Maternity)$/.test(cat))) ok = false;
    for (var j = 0; ok && j < SPEC.length; j++) if (SPEC[j][0].test(nm) && SPEC[j][1].indexOf(cat) < 0) ok = false;
    if (ok && k === 'G' && cat === 'Imaging') ok = IMG.test(nm);
    if (ok && k === 'G' && cat === 'Lab tests') ok = LABRX.test(nm) && !/cath/i.test(nm);
    return (FITC[key] = ok);
  }
  window.__ptFits = fitsFor;
  // ---------- the numbers for one code ----------
  var cache = cache || {};
  function build(code) {
    var C = D.codes[code];
    if (cache[code] && cache[code].f === C.f && cache[code].ml === ML) return cache[code];
    var cat = C.cat || '', drg = /DRG/.test(C.type || ''), anes = code.slice(0, 2) === '00', f = C.f || {};
    // the price pages' categories, plus the Price Finder's wider ones for every other code
    cat = LEG[cat] || cat;
    var SURG = /^(GI|Orthopedics|Spine|Pain management|Eye|Ear|Urology|Gynecology|Skin and breast|Lungs and nose|Endocrine|Blood and lymph|Surgery|ENT)$/;
    var kinds = drg ? 'H' : /^(Imaging|Lab tests)$/.test(cat) ? 'HG' : SURG.test(cat) ? 'HA' : 'HAG';
    var docLead = anes || /^(Office visits|Behavioral health|Physical therapy|Maternity|Anesthesia)$/.test(cat);
    var fits = function (i) { return fitsFor(code, i); };
    var ok = function (r) { return !r[2] && !(r[4] & 6) && r[3] > 0; };
    var facV = [], docV = [];
    Object.keys(f).forEach(function (fi) { f[fi].forEach(function (r) { if (!ok(r)) return; if (r[1] || anes) docV.push(r[3]); else if (fits(+fi)) facV.push(r[3]); }); });
    var mF = median(facV), mD = median(docV);
    var keep = function (r, m) { return ok(r) && !(m && r[3] < 0.2 * m) && !(r[4] & 8) && !placeholder(r[3], m); };
    var places = {}, docs = {};
    Object.keys(f).forEach(function (fi) {
      f[fi].forEach(function (r) {
        var isDoc = r[1] || anes;
        if (isDoc) { if (keep(r, mD) && !/derived/.test(r[10] >= 0 ? String(D.labs[r[10]] || '') : '')) { var k = fi + '|' + r[0]; if (!(k in docs) || r[3] < docs[k][0]) docs[k] = [r[3], r]; } return; }
        if (!fits(+fi) || !keep(r, mF)) return;
        var p = places[fi] || (places[fi] = {}); if (!p[r[0]] || r[3] < p[r[0]][3]) p[r[0]] = r;
      });
    });
    var useDoc = docLead || !Object.keys(places).length;
    if (useDoc) {                 // office visits, therapy, anesthesia...: the clinician's fee is the price; rows are practices and clinicians
      places = {};
      Object.keys(docs).forEach(function (k) { var fi = k.split('|')[0], r = docs[k][1], p = places[fi] || (places[fi] = {}); if (!p[r[0]] || r[3] < p[r[0]][3]) p[r[0]] = r; });
    }
    var byNet = {};
    var isDoctor = function (i) { var nm = D.fac[i][0], k = kindOf(i); return k === 'P' ? MDDO.test(nm) : k === 'G' && !LABRX.test(nm) && !IMG.test(nm) && !NOT_HERE.test(nm); };
    if (!useDoc) Object.keys(docs).forEach(function (k) { var n = k.split('|')[1]; if (isDoctor(+k.split('|')[0])) (byNet[n] = byNet[n] || []).push(docs[k][0]); });
    var doc = {};
    Object.keys(byNet).forEach(function (n) { var v = byNet[n].sort(function (a, b) { return a - b; }); doc[n] = {lo: v[0], mid: v[v.length >> 1], hi: v[v.length - 1], n: v.length}; });
    // Medicare for each place
    var fresh = ML && ML.nf === D.fac.length;    // ml.json written for this page's provider list (a rebuild can reorder it)
    var m = D.med && D.med.codes[code], pfs = pfsOf(code), wi = (fresh && ML.f) || {};
    var medFor = function (i) {
      var k = kindOf(i);
      if (useDoc) return pfs ? (k === 'P' || k === 'G' ? [pfs[0] != null ? pfs[0] : pfs[1], 'office rate, ' + (window.MED_AREA || 'this area')] : null) : null;
      if (k === 'H' && m && m.opps) return wi[i] ? [Math.round(m.opps[0] * (0.6 * wi[i] + 0.4) * 100) / 100, 'this hospital'] : [m.opps[0], 'national rate'];
      if (k === 'A' && m && m.asc) return wi[i] ? [Math.round(m.asc[0] * (0.5 * wi[i] + 0.5) * 100) / 100, 'this surgery center'] : [m.asc[0], 'national rate'];
      if (k === 'G' && pfs && pfs[0] != null) return [pfs[0], 'office rate, ' + (window.MED_AREA || 'this area')];
      return null;
    };
    // Medicare Advantage and cash from the hospital's own file, tied to places by CMS ID (ml.json h)
    var HC = (H.codes && H.codes[code]) || {c: [], r: []}, plans = HC.p || H.plans || [], hmap = {};
    if (fresh && ML.h) Object.keys(ML.h).forEach(function (si) { var e = ML.h[si]; if (H.src[si] && H.src[si][5] === e[0]) hmap[si] = e[1]; });
    var ma = {}, cash = {};
    (HC.r || []).forEach(function (r) {
      if (r[2] !== 2 || r[4] || r[5] || !(r[6] > 0)) return;
      (hmap[r[0]] || []).forEach(function (i) { if (!ma[i] || r[6] < ma[i].v) ma[i] = {v: r[6], s: r[0], row: r[7], who: H.ins[r[1]] + (plans[r[3]] ? ' · ' + plans[r[3]] : '')}; });
    });
    (HC.c || []).forEach(function (r) {
      if (r[5] !== 0 || !(r[2] > 0)) return;
      (hmap[r[0]] || []).forEach(function (i) { if (!cash[i] || r[2] < cash[i].v) cash[i] = {v: r[2], s: r[0], row: r[4], what: "hospital's price file, hospital fee only"}; });
    });
    var norm = function (s) { return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); };
    var posted = (D.cash || []).filter(function (c) { return c.code === code; });
    var rows = Object.keys(places).map(function (fi) {
      var i = +fi, x = D.fac[i], md = medFor(i), pc = posted.filter(function (c) { return norm(c.name) === norm(x[0]); })[0];
      var cs = cash[i] || null;
      if (pc && (!cs || pc.v < cs.v)) cs = {v: pc.v, url: pc.src, what: 'posted cash price' + (pc.chk ? ', checked ' + pc.chk : '')};
      return {i: i, name: x[0], city: x[1], kind: kindOf(i), fees: places[fi], med: md, ma: ma[i] || null, cash: cs, legal: LEGAL[i],
              tag: VA.test(x[0]) ? 'veterans only' : CHILD.test(x[0]) ? "children's" : ''};
    });
    // one row per place: the same name and city under two IDs keeps the lowest fee in each network
    var seen = {};
    rows = rows.filter(function (o) {
      var k = norm(o.name) + '|' + norm(o.city), m0 = seen[k];
      if (!m0) { seen[k] = o; return true; }
      Object.keys(o.fees).forEach(function (n) { if (!m0.fees[n] || o.fees[n][3] < m0.fees[n][3]) m0.fees[n] = o.fees[n]; });
      ['ma', 'cash'].forEach(function (q) { if (o[q] && (!m0[q] || o[q].v < m0[q].v)) m0[q] = o[q]; });
      if (o.med && (!m0.med || /this/.test(o.med[1]))) m0.med = o.med;
      return false;
    });
    // every cash price for this code: each hospital file's own cash line, and prices posted on providers' sites (same as the price pages)
    var placeOf = {}; rows.forEach(function (o) { placeOf[o.i] = o; });
    var byName = {}; rows.forEach(function (o) { byName[norm(o.name)] = o; if (o.legal) byName[norm(o.legal)] = o; });
    var cashAll = [], hc = {};
    (HC.c || []).forEach(function (r) {
      if (r[5] !== 0 || !(r[2] > 0) || !H.src[r[0]] || WRONG.test(String(H.src[r[0]][4]))) return;
      if (!hc[r[0]] || r[2] < hc[r[0]].v) hc[r[0]] = {v: r[2], s: r[0], row: r[4], what: "hospital's price file, hospital fee only"};
    });
    Object.keys(hc).forEach(function (si) {
      var e = hc[si], x = H.src[si], pl = (hmap[si] || []).map(function (i) { return placeOf[i]; }).filter(Boolean)[0] || byName[norm(x[0])] || null;
      e.name = pl ? pl.name : x[0]; e.city = pl ? pl.city : x[1]; e.date = x[3]; e.place = pl; e.kind = 'H';
      e.med = pl && pl.med ? pl.med : m && m.opps ? [m.opps[0], 'national hospital rate'] : null;
      cashAll.push(e);
    });
    posted.forEach(function (c) {
      var pl = byName[norm(c.name)] || null, office = pfs && pfs[0] != null && /^(Imaging|Lab tests|Office visits)$/.test(cat);
      cashAll.push({v: c.v, url: c.src, what: 'posted cash price' + (c.label ? ' (' + c.label + ')' : ''), date: c.chk || '', name: pl ? pl.name : c.name, city: pl ? pl.city : (c.city || ''), place: pl,
                    med: pl && pl.med ? pl.med : office ? [pfs[0], 'office or imaging-center rate'] : m && m.asc ? [m.asc[0], 'national surgery-center rate'] : null});
    });
    cashAll.sort(function (a, b) { return a.v - b.v; });
    // networks: insurer columns, the default network per insurer, and networks paying one amount at most places
    var cnt = {}, vals = {};
    rows.forEach(function (o) { Object.keys(o.fees).forEach(function (n) { cnt[n] = (cnt[n] || 0) + 1; var v = o.fees[n][3]; (vals[n] = vals[n] || {})[v] = (vals[n][v] || 0) + 1; }); });
    var flat = {};
    Object.keys(cnt).forEach(function (n) { var top = 0, tv = 0; Object.keys(vals[n]).forEach(function (v) { if (vals[n][v] > top) { top = vals[n][v]; tv = +v; } }); if (cnt[n] >= 5 && top >= cnt[n] / 2) flat[n] = [tv, top]; });
    var ins = {};
    Object.keys(cnt).forEach(function (n) { (ins[NET[n].i] = ins[NET[n].i] || []).push(+n); });
    var order = Object.keys(ins).sort(function (a, b) { var ca = Math.max.apply(null, ins[a].map(function (n) { return cnt[n]; })), cb = Math.max.apply(null, ins[b].map(function (n) { return cnt[n]; })); return cb - ca || a.localeCompare(b); });
    var def = {};
    order.forEach(function (k) { var c = ins[k].filter(function (n) { return !PAR.test(NET[n].n); }).sort(function (a, b) { return cnt[b] - cnt[a]; }); def[k] = c.length ? c[0] : ins[k][0]; });
    return (cache[code] = {f: C.f, ml: ML, rows: rows, cashAll: cashAll, doc: doc, useDoc: useDoc, cnt: cnt, flat: flat, ins: ins, order: order, def: def, m: m, pfs: pfs});
  }

  // ---------- drawing ----------
  var fileLink = function (r, txt, x) {
    return '<a class="pt-v" href="' + E(D.urls[r[6]]) + '" target="_blank" rel="noopener" title="' + E((x ? X(x) + ' Medicare · ' : '') + 'insurer file dated ' + D.dates[r[5]]) + '">' + txt + '</a>';
  };
  var hLink = function (o, txt) {
    var s = o.s != null && H.src[o.s];
    var url = s ? s[4] : o.url, tip = s ? (o.who ? o.who + ' · ' : '') + "hospital's price file dated " + (s[3] || 'with no date') + (o.row ? ', ' + (s[6] || 'row') + ' ' + o.row.toLocaleString() : '') : o.what;
    return url ? '<a class="pt-v" href="' + E(url) + '" target="_blank" rel="noopener" title="' + E(tip) + '">' + txt + '</a>' : '<span class="pt-v" title="' + E(tip) + '">' + txt + '</span>';
  };
  var shade = function (v, o) { var x = o.med ? v / o.med[0] : null; return [x ? ' class="pt-b' + BAND(x) + '"' : '', x ? '<span class="pt-x">' + X(x) + ' Medicare</span>' : '']; };
  // a rate's own label from the file: "derived" amounts are insurers' bookkeeping figures (often for HMO doctors paid a set
  // amount per patient), not prices; a doctor's fee filed for a hospital or clinic setting compares with Medicare's facility-setting rate
  var labOf = function (r) { return r[10] >= 0 ? String(D.labs[r[10]] || '') : ''; };
  var DER = '<span class="pt-der" title="The insurer calls this a derived amount: a figure it uses for its own bookkeeping, often for doctors paid a set amount per patient each month. It is not a price anyone pays for this visit or procedure.">derived, not a price</span>';
  function feeCell(o, n) {
    var r = o.fees[n]; if (!r) return '<td><span class="pt-none" title="No published rate in this network">—</span></td>';
    var lb = labOf(r), der = /derived/.test(lb), ref = o.med, pfs = pfsOf(S.code), fac = /outpatient|inpatient/.test(lb);
    if ((o.kind === 'P' || o.kind === 'G') && pfs && fac && pfs[1] != null) ref = [pfs[1], 'Medicare in a hospital or clinic setting'];
    var x = ref ? r[3] / ref[0] : null;
    return '<td' + (x && !der ? ' class="pt-b' + BAND(x) + '"' : '') + '>' + fileLink(r, M$(r[3]), x) + (x ? '<span class="pt-x">' + X(x) + ' Medicare' + (fac && ref !== o.med ? ' (clinic setting)' : '') + '</span>' : '') + (der ? DER : '') + '</td>';
  }
  function placeCell(o) {
    var KN = {H: 'hospital', A: 'surgery center', G: 'practice or clinic', P: 'clinician'};
    return '<td class="pt-pl"><label><input type="checkbox" data-pt="' + o.i + '"' + (T.sel[o.i] ? ' checked' : '') + ' aria-label="Compare ' + E(o.name) + '"><span><b class="who">' + E(o.name) + '</b>' +
      '<span class="pt-m">' + E(o.city) + ' <span class="pt-kind">' + KN[o.kind] + '</span>' + (o.tag ? ' <span class="pt-tagp">' + E(o.tag) + '</span>' : '') + '</span>' +
      (o.legal && o.legal.toLowerCase() !== o.name.toLowerCase() ? '<span class="pt-legal">files as ' + E(o.legal) + '</span>' : '') + '</span></label></td>';
  }
  var medCell = function (o) { return '<td class="pt-med">' + (o.med ? '<span class="pt-v pt-ink">' + M$(o.med[0]) + '</span><span class="pt-x">' + E(o.med[1]) + '</span>' : '<span class="pt-none" title="No Medicare figure for this place">—</span>') + '</td>'; };
  var maCell = function (o) { return '<td class="pt-med">' + (o.ma ? hLink(o.ma, M$(o.ma.v)).replace('class="pt-v"', 'class="pt-v pt-ink"') + '<span class="pt-x">' + E(o.ma.who.split(' · ')[0]) + '</span>' : '<span class="pt-none" title="' + (o.kind === 'H' ? "Not in this hospital's price file, or we couldn't tie the file to this hospital" : "Only hospitals have to post Medicare Advantage rates") + '">—</span>') + '</td>'; };
  var cashCell = function (o) { if (!o.cash) return '<td><span class="pt-none" title="No cash price posted; ask for a written Good Faith Estimate">—</span></td>'; var s = shade(o.cash.v, o); return '<td' + s[0] + '>' + hLink(o.cash, M$(o.cash.v)) + s[1] + '</td>'; };
  var bar = function (v, m) { if (!m) return '<td class="pt-bar"></td>'; var mx = Math.max(v, m) * 1.05; return '<td class="pt-bar"><span class="pt-x">' + X(v / m) + ' Medicare</span><div class="pt-track" aria-hidden="true"><div class="pt-fill" style="width:' + (v / mx * 100) + '%"></div><div class="pt-mline" style="left:' + (m / mx * 100) + '%"></div></div></td>'; };
  var netLab = function (n) { var a = NET[n].i, b = NET[n].n; return b.toLowerCase().indexOf(a.toLowerCase()) === 0 ? b : a + ' ' + b; };

  function renderTable() {
    var code = S.code, C = D.codes[code], B = build(code);
    var chosen = !document.getElementById('pay').classList.contains('ux-ask');
    var mode = S.pay === 'cash' ? 'cash' : (!T.all && chosen && /^\d+$/.test(S.pay) && B.cnt[S.pay]) ? 'net' : 'all';
    var q = T.q.toLowerCase();
    var list = B.rows.filter(function (o) { return (!T.k || o.kind === T.k || (T.k === 'G' && o.kind === 'P')) && (!q || (o.name + ' ' + o.city).toLowerCase().indexOf(q) >= 0); });
    var kinds = {}; B.rows.forEach(function (o) { kinds[o.kind === 'P' ? 'G' : o.kind] = 1; });
    var KB = [['', 'All']].concat([['A', 'Surgery centers'], ['H', 'Hospitals'], ['G', B.useDoc ? 'Practices and clinicians' : 'Clinics, labs, imaging']].filter(function (k) { return kinds[k[0]]; }));
    var col = function (k) { return T.col[code + k] != null ? T.col[code + k] : B.def[k]; };
    var head = '', body = '', total = 0, lede = '';
    var thing = B.useDoc ? "fee" : "own fee (the facility fee)";
    if (mode === 'all') {
      var lo = function (o) { var v = Infinity; B.order.forEach(function (k) { var n = col(k), r = o.fees[n]; if (r && !B.flat[n] && r[3] < v) v = r[3]; }); return v; };
      list.sort(function (a, b) { return (!!a.tag - !!b.tag) || lo(a) - lo(b) || a.name.localeCompare(b.name); });
      total = list.length;
      lede = "Each row is one " + (B.useDoc ? 'practice or clinician' : 'place') + ", with its " + thing + " in each insurer's network." + (B.useDoc || !Object.keys(B.doc).length ? '' : " The first row is the doctor's fee, a separate bill from whoever does it.") + " Switch a column's network at the top of it, or pick yours under <b>How are you paying?</b> to see " + (B.useDoc ? 'only your network' : 'both bills together') + '.';
      var mine = chosen && /^\d+$/.test(S.pay) ? NET[S.pay].i : null;
      head = '<tr><th class="pt-pl">' + (B.useDoc ? 'Practice or clinician' : 'Place') + '<span class="pt-x">tick 2 or more to compare</span></th><th>Medicare<span class="pt-x">traditional, 2026</span></th>' +
        (B.useDoc ? '' : '<th>Medicare Advantage<span class="pt-x">hospital files</span></th><th>Cash<span class="pt-x">no insurance</span></th>') +
        B.order.map(function (k) {
          var n = col(k), fl = B.flat[n];
          return '<th' + (k === mine ? ' class="pt-mine"' : '') + '><span class="pt-ins">' + E(k) + '</span>' + (B.ins[k].length > 1 ? '<select data-ptcol="' + E(k) + '" aria-label="' + E(k) + ' network">' + B.ins[k].map(function (m) { return '<option value="' + m + '"' + (m === n ? ' selected' : '') + '>' + E(NET[m].n) + '</option>'; }).join('') + '</select>' : '<span class="pt-x">' + E(NET[n].n) + '</span>') +
            (fl ? '<span class="pt-flat">same ' + M$(fl[0]) + ' at ' + fl[1] + ' of ' + B.cnt[n] + '</span>' : '') + (PAR.test(NET[n].n) ? '<span class="pt-flat">not a network you pick</span>' : '') + '</th>';
        }).join('') + '</tr>';
      if (!B.useDoc && Object.keys(B.doc).length) {
        var dm = B.pfs && B.pfs[1] != null ? '<span class="pt-v pt-ink">' + M$(B.pfs[1]) + '</span><span class="pt-x">' + E(window.MED_AREA || '') + '</span>' : '<span class="pt-none">—</span>';
        body += '<tr class="pt-doc"><td class="pt-pl"><b>Doctor\'s fee</b><span class="pt-m">a separate bill · typical listed fee (lowest–highest listed below)</span></td><td class="pt-med">' + dm + '</td><td class="pt-med"><span class="pt-none">—</span></td><td><span class="pt-none">ask</span></td>' +
          B.order.map(function (k) { var g = B.doc[col(k)]; return '<td>' + (g ? '<span class="pt-v" title="' + E('Lowest ' + M$(g.lo) + ' · middle ' + M$(g.mid) + ' · highest ' + M$(g.hi) + ' across ' + g.n.toLocaleString() + ' listed doctors (MD/DO) and practices') + '">' + M$(g.mid) + '</span><span class="pt-x">' + M$(g.lo) + '–' + M$(g.hi) + '</span>' : '<span class="pt-none">—</span>') + '</td>'; }).join('') + '</tr>';
      }
      list.slice(0, T.n).forEach(function (o) { body += '<tr' + (T.sel[o.i] ? ' class="pt-sel"' : '') + '>' + placeCell(o) + medCell(o) + (B.useDoc ? '' : maCell(o) + cashCell(o)) + B.order.map(function (k) { return feeCell(o, col(k)); }).join('') + '</tr>'; });
    } else if (mode === 'cash') {
      var cl = B.cashAll.filter(function (c) { return (!q || (c.name + ' ' + c.city).toLowerCase().indexOf(q) >= 0) && (!T.k || (c.place ? c.place.kind === T.k : T.k === (c.s != null ? 'H' : 'G'))); });
      total = cl.length;
      lede = "Cash prices a place posts on its website or lists in its hospital price file, next to Medicare's rate for the same place. Many places don't publish one: call and ask, and ask for a written Good Faith Estimate.";
      head = '<tr><th class="pt-pl">Place</th><th>Cash price</th><th>Medicare</th><th class="pt-bar">Against Medicare</th></tr>';
      cl.slice(0, T.n).forEach(function (c) {
        var old = c.date && (Date.now() - Date.parse(c.date)) / 864e5 > 183, x = c.med ? c.v / c.med[0] : null;
        var who = c.place ? placeCell(c.place) : '<td class="pt-pl"><b class="who">' + E(c.name) + '</b><span class="pt-m">' + E(c.city) + '</span></td>';
        body += '<tr>' + who + '<td' + (x ? ' class="pt-b' + BAND(x) + '"' : '') + '>' + hLink(c, M$(c.v)) + '<span class="pt-x">' + E(c.what) + (c.date ? ' · ' + E(c.date) : ' · no date') + '</span>' +
          (old ? '<span class="pt-flat">over 6 months old</span>' : '') + '</td><td class="pt-med">' + (c.med ? '<span class="pt-v pt-ink">' + M$(c.med[0]) + '</span><span class="pt-x">' + E(c.med[1]) + '</span>' : '<span class="pt-none">—</span>') + '</td>' + bar(c.v, c.med && c.med[0]) + '</tr>';
      });
    } else {
      var n = +S.pay, g = B.doc[n], dmed = B.pfs && B.pfs[1];
      list = list.filter(function (o) { return o.fees[n]; }).sort(function (a, b) { return (!!a.tag - !!b.tag) || a.fees[n][3] - b.fees[n][3]; });
      total = list.length;
      lede = B.useDoc ? "Your network's published fee at each practice and clinician, against Medicare. Lowest first." :
        "Both bills in your network: the place's fee plus the doctor's. The doctor's figure is the middle fee this network lists across this area's doctors and groups (each one a real listed price); yours depends on who does it. Lowest total first. <button type=\"button\" class=\"pt-link\" data-ptall>Show every insurer instead</button>";
      head = B.useDoc ? '<tr><th class="pt-pl">Practice or clinician</th><th>Fee</th><th>Medicare</th><th class="pt-bar">Against Medicare</th></tr>' :
        '<tr><th class="pt-pl">Place</th><th>Place\'s fee</th><th>+ Doctor\'s fee<span class="pt-x">typical</span></th><th>= Both bills</th><th>Medicare, both<span class="pt-x">this place + doctor</span></th><th class="pt-bar">Against Medicare</th></tr>';
      list.slice(0, T.n).forEach(function (o) {
        var r = o.fees[n];
        if (B.useDoc) { body += '<tr>' + placeCell(o) + feeCell(o, n) + medCell(o) + bar(r[3], o.med && o.med[0]) + '</tr>'; return; }
        var tot = r[3] + (g ? g.mid : 0), mt = o.med && dmed != null ? o.med[0] + dmed : null;
        body += '<tr>' + placeCell(o) + feeCell(o, n) + '<td>' + (g ? '<span class="pt-v" title="' + E('Lowest ' + M$(g.lo) + ' · highest ' + M$(g.hi)) + '">' + M$(g.mid) + '</span><span class="pt-x">' + M$(g.lo) + '–' + M$(g.hi) + '</span>' : '<span class="pt-none">—</span>') + '</td>' +
          '<td><span class="pt-v pt-big">' + M$(tot) + '</span></td><td class="pt-med">' + (mt ? '<span class="pt-v pt-ink">' + M$(mt) + '</span>' : '<span class="pt-none">—</span>') + '</td>' + bar(tot, mt) + '</tr>';
      });
    }
    var title = mode === 'all' ? 'Every place, every insurer' : mode === 'cash' ? 'Paying cash' : netLab(+S.pay);
    var html = '<section class="pt"><p class="pt-k">What it costs at each place</p><h2>' + E(title) + '</h2><p class="pt-lede">' + lede + '</p>' +
      '<div class="pt-tools"><input type="search" data-ptq value="' + E(T.q) + '" placeholder="Find a place or city" aria-label="Find a place or city">' +
      (KB.length > 2 ? '<div class="pt-seg" role="group" aria-label="Kind of place">' + KB.map(function (k) { return '<button type="button" data-ptk="' + k[0] + '" aria-pressed="' + (T.k === k[0]) + '">' + k[1] + '</button>'; }).join('') + '</div>' : '') + '</div>' +
      '<p class="pt-legend"><span>Each price is shaded by how many times Medicare\'s rate for that same place it is:</span><span><i class="pt-sw pt-b1"></i>up to 1.5×</span><span><i class="pt-sw pt-b2"></i>1.5–3×</span><span><i class="pt-sw pt-b3"></i>3–5×</span><span><i class="pt-sw pt-b4"></i>over 5×</span></p>' +
      (mode === 'all' ? '<div class="pt-pick">' + B.order.filter(function (k) { return B.ins[k].length > 1; }).map(function (k) { return '<label>' + E(k) + '<select data-ptcol="' + E(k) + '">' + B.ins[k].map(function (m) { return '<option value="' + m + '"' + (m === col(k) ? ' selected' : '') + '>' + E(NET[m].n) + '</option>'; }).join('') + '</select></label>'; }).join('') + '</div>' : '') +
      (total ? '<div class="pt-wrap"><table class="pt-t"><thead>' + head + '</thead><tbody>' + body + '</tbody></table></div>' : '<p class="empty">' + (mode === 'cash' ? 'No cash prices published for this code here yet.' : 'No published dollar rates for this code here yet. The other tabs list every line, including percent-of-charges rates.') + '</p>') +
      '<div class="pt-more">' + (total > T.n ? '<button type="button" class="more" data-ptmore>Show more</button>' : '') + '<span>Showing ' + Math.min(T.n, total) + ' of ' + total + '</span></div>' +
      '<p class="pt-fine">Medicare is CMS\'s 2026 rate for that kind of place, adjusted for the place\'s local wages where we matched it to its Medicare record (<a href="/methodology/#medicare-each-place">how</a>); it\'s a yardstick, not a price you can get unless you\'re on Medicare. Medicare Advantage is the lowest Medicare Advantage line in the hospital\'s own price file. Rates marked <i>derived, not a price</i> are insurers\' bookkeeping figures, often for doctors paid a set amount per patient; they\'re listed but not shaded, and left out of the doctor\'s fee. Left out, as on the price pages: percent-of-charges rates, $0 lines, rates flagged unusually low, filler-looking rates, and places that don\'t do this kind of service (they\'re all on the <b>Every rate</b> tab). Every price links to the file it came from.</p></section>';
    var bd = document.getElementById('board');
    bd.innerHTML = html + scenarios(code) + '<div class="pt-tray"' + (Object.keys(T.sel).length ? '' : ' hidden') + '><span data-ptn></span><button type="button" class="more" data-ptcmp>Compare side by side</button><button type="button" class="pt-link" data-ptclr>Clear</button></div>';
    // each cell carries its column's name, so on a phone every row reads as a card
    var th = bd.querySelectorAll('.pt .pt-t thead th');
    var labs = [].map.call(th, function (h) { var a = h.querySelector('.pt-ins'), sel = h.querySelector('select'), x = h.querySelector('.pt-x');
      return a ? a.textContent + ' · ' + (sel ? sel.selectedOptions[0].textContent : x ? x.textContent : '') : (h.childNodes[0] && h.childNodes[0].textContent || h.textContent).trim(); });
    bd.querySelectorAll('.pt .pt-t tbody tr').forEach(function (tr) { [].forEach.call(tr.children, function (td, j) { if (j) td.setAttribute('data-l', labs[j] || ''); }); });
    tray();
  }

  // what makes this bill bigger, for the procedure on screen
  function scenarios(code) {
    var C = D.codes[code], cat = LEG[C.cat] || C.cat || '';
    var col = ['45378', '45380', '45384', '45385', 'G0105', 'G0121', '45391', '45388'];
    var L = [];
    if (col.indexOf(code) >= 0) L = [
      ['It started as a screening', 'Screening or diagnostic changes who pays', 'Most plans cover a routine screening colonoscopy at no cost to you under the Affordable Care Act. If it\'s done to check symptoms, or as a follow-up, it\'s billed as diagnostic and you pay toward your deductible. Ask how it will be billed before you schedule.'],
      ['They find a polyp', 'A different code, plus a lab bill', 'Removing a polyp is billed under a different code (<a href="?q=45385">45385</a> by snare, <a href="?q=45380">45380</a> by biopsy), and the tissue goes to a lab, which bills separately. On a screening, federal rules say removing a polyp shouldn\'t add cost-sharing on most private plans (<a href="https://www.dol.gov/sites/dolgov/files/EBSA/about-ebsa/our-activities/resource-center/faqs/aca-part-xii.pdf" target="_blank" rel="noopener">ACA FAQs Part XII</a>).'],
      ['You\'re sedated', 'Anesthesia is its own company', 'Sedation is usually billed by a separate anesthesia group, by the minute. At an in-network hospital or surgery center, the No Surprises Act stops an out-of-network anesthesiologist from billing you more than your in-network share.']];
    else if (cat === 'Imaging') L = [
      ['With or without contrast', 'Contrast is a different code', 'A scan "with contrast" (dye) is billed under its own code and usually costs more. Check which one your order says.'],
      ['Someone reads it', 'The radiologist bills separately', 'The doctor who reads the scan sends their own bill. At an in-network place, the No Surprises Act limits what an out-of-network radiologist can charge you.'],
      ['Where you go', 'Hospital or imaging center', 'The same scan often costs several times more at a hospital than at a stand-alone imaging center in the same network. Compare both in the table.']];
    else if (/DRG/.test(C.type || '')) L = [
      ['Complications', 'The group can change', 'Hospital stays are paid by group. If there\'s a complication (CC) or a major one (MCC), the stay moves to a higher-paid group.'],
      ['Doctors in the hospital', 'Their bills are separate', 'Surgeons, anesthesiologists and hospitalists usually bill on their own. At an in-network hospital, the No Surprises Act protects you from out-of-network bills from them.']];
    else if (cat !== 'Lab tests' && !/Office|Behavioral|therapy/i.test(cat) && code.slice(0, 2) !== '00') L = [
      ['You\'re sedated', 'Anesthesia is its own company', 'Anesthesia is usually billed by a separate group, by the minute. At an in-network hospital or surgery center, the No Surprises Act stops an out-of-network anesthesiologist from billing you more than your in-network share.'],
      ['Something more is done', 'Another code, another price', 'If the doctor does more than planned, it can be billed under an added or different code. Ask what codes they expect to bill before you schedule.']];
    if (!L.length) return '';
    return '<section class="pt-when"><p class="pt-k">When this costs more</p><div>' + L.map(function (x) { return '<div><span class="pt-tag">' + E(x[0]) + '</span><h3>' + E(x[1]) + '</h3><p>' + x[2] + '</p></div>'; }).join('') + '</div></section>';
  }

  function tray() {
    var t = document.querySelector('.pt-tray'); if (!t) return;
    var n = Object.keys(T.sel).length;
    t.hidden = !n;
    t.querySelector('[data-ptn]').textContent = n + (n === 1 ? ' place ticked · tick one more to compare' : ' places ticked');
    t.querySelector('[data-ptcmp]').disabled = n < 2;
  }
  function compare() {
    var B = build(S.code), ps = B.rows.filter(function (o) { return T.sel[o.i]; });
    var nets = {}; ps.forEach(function (o) { Object.keys(o.fees).forEach(function (n) { nets[n] = 1; }); });
    nets = Object.keys(nets).sort(function (a, b) { return netLab(a).localeCompare(netLab(b)); });
    var row = function (lab, vals, ref) {
      var nums = vals.filter(function (v) { return v != null; }), mn = Math.min.apply(null, nums);
      return '<tr><td>' + lab + '</td>' + vals.map(function (v) { return '<td' + (!ref && v != null && v === mn && nums.length > 1 ? ' class="pt-win"' : '') + '>' + (v == null ? '<span class="pt-none">—</span>' : '<span class="pt-v' + (ref ? ' pt-ink' : '') + '">' + M$(v) + '</span>') + '</td>'; }).join('') + '</tr>';
    };
    var h = '<table class="pt-t"><thead><tr><th class="pt-pl">Network</th>' + ps.map(function (o) { return '<th>' + E(o.name) + '<span class="pt-x">' + E(o.city) + '</span></th>'; }).join('') + '</tr></thead><tbody>' +
      row('<b>Medicare</b>', ps.map(function (o) { return o.med ? o.med[0] : null; }), true) +
      (B.useDoc ? '' : row('<b>Medicare Advantage</b>', ps.map(function (o) { return o.ma ? o.ma.v : null; }), true) + row('<b>Cash</b>', ps.map(function (o) { return o.cash ? o.cash.v : null; }))) +
      nets.map(function (n) { return row(E(netLab(n)), ps.map(function (o) { return o.fees[n] ? o.fees[n][3] : null; })); }).join('') + '</tbody></table>';
    var d = document.getElementById('ptDlg');
    if (!d) { d = document.createElement('dialog'); d.id = 'ptDlg'; d.className = 'pt-dlg'; d.setAttribute('aria-labelledby', 'ptDlgH'); document.body.appendChild(d); }
    d.innerHTML = '<div class="pt-dh"><h3 id="ptDlgH">Side by side</h3><button type="button" data-ptx>Close</button></div><div class="pt-cmp">' + h +
      '<p class="pt-fine">' + (B.useDoc ? "The clinician's fee in each network." : "The place's fee only; the doctor, anesthesia and any lab bill separately.") + ' Green: the lowest of the places you picked in that network.</p></div>';
    d.showModal();
  }

  // ---------- events ----------
  var board = document.getElementById('board');
  board.addEventListener('input', function (e) { if (e.target.matches('[data-ptq]')) { T.q = e.target.value; T.n = 25; var p = e.target.selectionStart; renderTable(); var q = board.querySelector('[data-ptq]'); q.focus(); try { q.setSelectionRange(p, p); } catch (err) {} } });
  board.addEventListener('change', function (e) {
    var s = e.target.closest('[data-ptcol]'); if (s) { T.col[S.code + s.dataset.ptcol] = +s.value; renderTable(); return; }
    var c = e.target.closest('[data-pt]'); if (c) { var i = +c.dataset.pt; if (c.checked) T.sel[i] = 1; else delete T.sel[i]; c.closest('tr').classList.toggle('pt-sel', c.checked); tray(); }
  });
  board.addEventListener('click', function (e) {
    var b = e.target.closest('[data-ptk]'); if (b) { T.k = b.dataset.ptk; T.n = 25; renderTable(); return; }
    if (e.target.closest('[data-ptmore]')) { T.n += 50; renderTable(); return; }
    if (e.target.closest('[data-ptall]')) { T.all = true; renderTable(); return; }
    if (e.target.closest('[data-ptcmp]')) { compare(); return; }
    if (e.target.closest('[data-ptclr]')) { T.sel = {}; renderTable(); }
  });
  document.addEventListener('click', function (e) { if (e.target.closest('[data-ptx]') || (e.target.matches && e.target.matches('dialog.pt-dlg'))) document.getElementById('ptDlg').close(); });
  document.getElementById('pay').addEventListener('change', function () { T.all = false; T.n = 25; this.classList.remove('ux-ask'); }, true);   // before the page's own re-render
  var lastCode = S.code;

  // ---------- the new view: "Compare" tab, drawn in the board area ----------
  var rb = renderBoard;
  renderBoard = function () {
    if (lastCode !== S.code) { lastCode = S.code; T.sel = {}; T.q = ''; T.k = ''; T.n = 25; }
    return S.view === 'table' ? renderTable() : rb.apply(this, arguments);
  };
  // "What it costs" over the procedure name (Betsy liked the old name's wording)
  var ttl = document.getElementById('title'), ar = document.getElementById('area');
  if (ttl && !document.querySelector('.pt-kick')) {
    var kk = document.createElement('p'); kk.className = 'pt-kick';
    var an = ar && ar.selectedOptions && ar.selectedOptions[0] ? ar.selectedOptions[0].textContent.trim() : '';
    kk.textContent = 'What it costs' + (an ? ' · ' + an : '');
    var host = /flex|grid/.test(getComputedStyle(ttl.parentElement).display) ? ttl.parentElement : ttl;   // above the title's row, not inside it
    host.insertAdjacentElement('beforebegin', kk);
  }
  var tabs = document.getElementById('vPatient');
  var vt = document.createElement('button'); vt.type = 'button'; vt.id = 'vTable'; vt.textContent = 'Compare'; vt.setAttribute('aria-pressed', 'false');
  tabs.insertAdjacentElement('beforebegin', vt);
  setView = function (v) {
    S.view = v; try { localStorage.setItem('view', v); } catch (e) {}
    [['vTable', 'table'], ['vPatient', 'patient'], ['vBoard', 'board'], ['vMap', 'map']].forEach(function (x) { var el = document.getElementById(x[0]); if (el) el.setAttribute('aria-pressed', v === x[1]); });
    document.getElementById('patient').hidden = v !== 'patient'; document.getElementById('board').hidden = v !== 'board' && v !== 'table';
    document.getElementById('mapv').hidden = v !== 'map'; document.getElementById('payWrap').hidden = v === 'board';
    var ux = document.querySelector('.ux-pay span');       // the "showing X as an example" note says what this view shows
    if (ux) { if (!ux.dataset.orig) ux.dataset.orig = ux.innerHTML;
      ux.innerHTML = v === 'table' ? 'Showing <b>every insurer</b>. Prices depend on your insurance, so pick your plan\'s network in <b>paying with</b> to see just yours, or choose <b>Paying cash</b>.' : ux.dataset.orig; }
    var bills = document.querySelector('.ux-bills');      // "Expect more than one bill" follows the view it belongs to
    if (bills) document.getElementById(v === 'table' ? 'board' : 'patient').insertAdjacentElement('afterend', bills);
    render();
  };
  vt.addEventListener('click', function () { setView('table'); });
  var first = false;
  try { first = !localStorage.getItem('pfv2'); localStorage.setItem('pfv2', '1'); } catch (e) {}
  setView(first || S.view === 'table' ? 'table' : S.view);

  // the bill slips (site/ux_polish.py) get this page's own published ranges when the Compare view knows them
  var rw = render;
  render = function () {
    var out = rw.apply(this, arguments);
    try {
      var qb = document.querySelector('.ux-hits'), q0 = window.__uxQ || new URLSearchParams(location.search).get('q');
      if (qb && q0) document.getElementById('title').textContent = 'Results for “' + q0 + '”';
      var u = new URL(location.href); u.searchParams.set('code', S.code);
      if (/^\d+$/.test(S.pay) && !payEl.classList.contains('ux-ask')) u.searchParams.set('net', D.nets[S.pay]); else u.searchParams.delete('net');
      if (!qb) u.searchParams.delete('q');
      if (u.href !== location.href) history.replaceState(history.state, '', u.href);
    } catch (e) {}
    try {
      var kq = document.querySelector('.pt-kick'), aq = document.getElementById('area');
      if (kq && aq && aq.selectedOptions && aq.selectedOptions[0] && aq.value) kq.textContent = 'What it costs · ' + aq.selectedOptions[0].textContent.trim();
    } catch (e) {}
    try {
      var C = D.codes[S.code], sl = document.querySelectorAll('.ux-bills .ux-slip');
      if (S.view === 'table' && C && C.f && sl.length >= 2) {
        var B = build(S.code), n = /^\d+$/.test(S.pay) && !document.getElementById('pay').classList.contains('ux-ask') && B.cnt[S.pay] ? +S.pay : null;
        var vs = []; B.rows.forEach(function (o) { Object.keys(o.fees).forEach(function (k) { if ((n == null ? !B.flat[k] && !PAR.test(NET[k].n) : +k === n)) vs.push(o.fees[k][3]); }); });
        vs.sort(function (a, b) { return a - b; });
        var put = function (el, v, note) { var b = el.querySelector('.v b'), t = el.querySelector('.v span'); if (b) b.textContent = v; if (t) t.textContent = 'RANGE'; var s2 = el.querySelector('.s'); if (s2) s2.textContent = note; };
        if (vs.length && !B.useDoc) put(sl[0], M$(vs[0]) + '–' + M$(vs[vs.length - 1]), n == null ? 'lowest to highest, any network, in the table above' : 'lowest to highest in ' + netLab(n));
        var g = n != null && B.doc[n];
        if (g && !B.useDoc) put(sl[1], M$(g.lo) + '–' + M$(g.hi), 'typical (middle listed fee) ' + M$(g.mid) + ' in ' + netLab(n));
      }
    } catch (e) {}
    return out;
  };

  // ---------- "Every insurer" in How are you paying? (first-visitor test, Oct 19) ----------
  var payEl = document.getElementById('pay');
  if (!payEl.querySelector('option[value="all"]')) {
    var oa = document.createElement('option'); oa.value = 'all'; oa.textContent = 'Every insurer (compare them)';
    payEl.insertBefore(oa, payEl.firstChild);
  }
  if (payEl.classList.contains('ux-ask')) { payEl.value = 'all'; S.pay = 'all'; }
  var pickFirst = '<p class="note">This list shows one network at a time. Pick your network under <b>How are you paying?</b>, or open <button type="button" class="pt-link" data-ptgo>Compare</button> to see every insurer side by side.</p>';
  // Price list tab: hospitals and surgery centers list their facility fee; a place with only a doctor's fee listed goes with the practices
  var rp = renderPatient;
  try {
    var src = rp.toString(), from = ": f.kind === kind) && primary(f).length)";
    if (src.indexOf(from) > 0) {
      src = src.replace(from, ": f.kind === kind || (kind === 'G' && (f.kind === 'A' || f.kind === 'H') && !f.facD.length)) && ((kind === 'A' || kind === 'H') && !drg ? f.facD.length && window.__ptFits(S.code, f.fi) : primary(f).length))");
      var sc = document.createElement('script'); sc.textContent = 'window.__ptRP = ' + src + ';'; document.head.appendChild(sc);
      if (typeof window.__ptRP === 'function') rp = window.__ptRP;
    }
  } catch (e) {}
  renderPatient = function () { if (S.pay === 'all') { document.getElementById('patient').innerHTML = pickFirst; return; } return rp.apply(this, arguments); };
  if (window.renderMap) { var rm = window.renderMap; window.renderMap = function () { if (S.pay === 'all') { document.getElementById('mapv').innerHTML = pickFirst; return; } return rm.apply(this, arguments); }; }
  document.addEventListener('click', function (e) { if (e.target.closest('[data-ptgo]')) setView('table'); });

  // ---------- search: any word order, everyday words (the homepage says "knee MRI"; the files say "MRI ... knee") ----------
  var SYN = {mri: 'magnetic resonance', ct: 'computed tomography', cat: 'computed tomography', 'x-ray': 'xray', xray: 'x-ray', ultrasound: 'sonogram', echo: 'echocardiogram',
    egd: 'upper endoscopy', mammogram: 'mammography', mammo: 'mammography', 'c-section': 'cesarean', csection: 'cesarean', physical: 'preventive', checkup: 'preventive',
    bloodwork: 'blood', scope: 'endoscopy', replacement: 'arthroplasty', shot: 'injection', stitches: 'repair'};
  var toks = function (t) { return String(t).toLowerCase().replace(/[^a-z0-9 -]+/g, ' ').split(/ +/).filter(Boolean); };
  var hasW = function (n, w) { var w2 = w.replace(/s$/, ''); return n.indexOf(w) >= 0 || n.indexOf(w2) >= 0 || (SYN[w] && n.indexOf(SYN[w]) >= 0); };
  var qBox = document.querySelector('.ux-hits'), qq = window.__uxQ || new URLSearchParams(location.search).get('q');
  if (qBox && qq) {
    var tw = toks(qq), codes = Object.keys(D.codes);
    var exact = codes.filter(function (c) { return c.toLowerCase() === qq.trim().toLowerCase(); });
    var all = codes.filter(function (c) { var n = (D.codes[c].name || '').toLowerCase(); return tw.length && tw.every(function (w) { return hasW(n, w); }); });
    var near = all.length ? [] : codes.map(function (c) { var n = (D.codes[c].name || '').toLowerCase(); return [c, tw.filter(function (w) { return w.length > 2 && hasW(n, w); }).length]; })
      .filter(function (x) { return x[1]; }).sort(function (a, b) { return b[1] - a[1]; }).map(function (x) { return x[0]; });
    var shown = exact.concat(all.filter(function (c) { return exact.indexOf(c) < 0; }), near).slice(0, 60);
    qBox.innerHTML = '<p><b>' + (all.length + exact.length ? (shown.length >= 60 ? '60+' : shown.length) + ' billing code' + (shown.length === 1 ? ' matches' : 's match') + ' “' + E(qq) + '”.</b> Pick one:'
      : (shown.length ? 'No exact match for “' + E(qq) + '”. Close matches:' : 'Nothing matches “' + E(qq) + '”. Try one word, like “knee” or “MRI”, or a billing code.')) + '</p>' +
      (shown.length ? '<ul>' + shown.map(function (c) { return '<li><button type="button" data-c="' + E(c) + '">' + E(D.codes[c].name) + ' <span>' + E(D.codes[c].type || 'CPT') + ' ' + E(c) + '</span></button></li>'; }).join('') + '</ul>' : '');
  }

  // ---------- one Medicare block: each kind of place once, national rate and the local range together ----------
  if (typeof medBlock === 'function' && typeof mlHTML === 'function') {
    mlHTML = function () { return ''; };
    var mb = medBlock;
    medBlock = function (code) {
      var s = mb(code), m = D.med && D.med.codes[code], R = (window.UXML && UXML.r) || {};
      [['opps', 'H', 0.6, 'hospitals'], ['asc', 'A', 0.5, 'surgery centers']].forEach(function (x) {
        var r = R[x[1]]; if (!m || !m[x[0]] || !r) return;
        var nat = m[x[0]][0], lo = Math.round(nat * (x[2] * r[0] + 1 - x[2]) * 100) / 100, hi = Math.round(nat * (x[2] * r[1] + 1 - x[2]) * 100) / 100;
        s = s.replace('national rate before local wage adjustment', 'national rate; ' + (lo === hi ? M$(lo) : M$(lo) + '–' + M$(hi)) + ' after the local wage adjustment at the ' + r[2] + ' ' + x[3] + ' here we matched to Medicare (<a href="/methodology/#medicare-each-place">how</a>)');
      });
      return s;
    };
  }
  render();   // once more, with everything above in place
})();
