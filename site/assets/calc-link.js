/* Plan Calculator helpers (Oct 19, 2026, first-visitor tests). Added to /plan-calculator/ by site/pf_table.py.
   1. ?code=45378 (and &net=BCBSTX|Blue Choice PPO from the Price Finder) opens the calculator on that procedure, and with a
      network it switches to "Work or somewhere else" and picks that network, so a visitor doesn't start over.
   2. __calcSkip(name, procedureName): leave out places whose names say they don't do the procedure (same rules as the
      price pages: rehab, psychiatric, nursing, real estate..., fertility labs, single-specialty places named for another
      specialty). */
(function () {
  var NOT_HERE = /rehab|behavioral|psychiatr|hospice|nursing|long[- ]?term|\bltac\b|kindred|select specialty|\bopco\b|real estate|skilled|senior living|assisted living|home health|dialysis|\bdental|\bdds\b|pharmacy|lifecare|\bvibra\b|\bltach?\b|nexus specialty|acuity hospital|post[- ]?acute|cornerstone (?:hospital|specialty)|texas health specialty hospital|transitional hospitals/i;
  var FERT = /reproduct|fertility|\bivf\b|\bccrm\b/i;
  var SPEC = [[/\beye\b|eyecare|surgeye|vision|retina|ophthalm|lasik|cataract/i, /cataract|eye|lens/i],
    [/cardiac|cardio|\bheart\b|\bcath\b|vascular/i, /heart|cardiac|calcium|echo|stress/i],
    [/endoscop|gastro|\bgi\b|digestive|colon/i, /colonoscopy|endoscopy|egd|esophag|colon/i],
    [/orthop|\bspine\b|sports med/i, /knee|hip|shoulder|acl|menisc|arthroscop|carpal|spine|back|joint|mri|x-ray|ct /i],
    [/\bpain\b/i, /pain|injection|spine|back/i], [/dermatolog|plastic surg|cosmetic|aesthetic/i, /^$/]];
  window.__calcSkip = function (name, proc) {
    var nm = String(name || ''), pr = String(proc || '');
    if (NOT_HERE.test(nm) || (FERT.test(nm) && !/birth|delivery|c-section|ultrasound/i.test(pr))) return true;
    for (var i = 0; i < SPEC.length; i++) if (SPEC[i][0].test(nm) && !SPEC[i][1].test(pr)) return true;
    return false;
  };
  var P = new URLSearchParams(location.search), code = P.get('code'), net = P.get('net');
  if (!code && !net) return;
  function go() {
    var mp = document.getElementById('proc');
    if (code && mp && [].some.call(mp.options, function (o) { return o.value === code; }) && mp.value !== code) { mp.value = code; mp.dispatchEvent(new Event('change')); }
    if (!net) return;
    var b = document.getElementById('mOwn'); if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
    var parts = net.split('|'), ins = (parts[0] || '').toLowerCase(), nn = (parts[1] || '').toLowerCase(), tries = 0;
    var t = setInterval(function () {
      var s = document.getElementById('onet'), p = document.getElementById('oproc');
      if (++tries > 60) { clearInterval(t); return; }
      if (!s || s.options.length < 2) return;
      clearInterval(t);
      var o = [].filter.call(s.options, function (x) {
        var g = x.parentElement && x.parentElement.label ? x.parentElement.label.toLowerCase() : '';
        return x.value !== '' && x.textContent.trim().toLowerCase() === nn && (!g || g.indexOf(ins) >= 0 || ins.indexOf(g) >= 0);
      })[0] || [].filter.call(s.options, function (x) { return x.value !== '' && x.textContent.trim().toLowerCase() === nn; })[0];
      if (o) { s.value = o.value; s.dispatchEvent(new Event('change')); }
      if (code && p && [].some.call(p.options, function (x) { return x.value === code; })) { p.value = code; p.dispatchEvent(new Event('change')); }
    }, 200);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go();
})();
