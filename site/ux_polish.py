"""Guidance and polish pass on the hand-written parts of the site (Oct 17, 2026).

  python site/ux_polish.py DIR      # DIR from `site_files.py pull DIR`; edits DIR/site in place (safe to run again)
  python site/ux_polish.py --r2     # also patch the Price Finder layouts the monthly builds start from (R2 site/deploy/...)

What it does (every step checks a marker first, so running it twice changes nothing):
  - Homepage header: a "Start here" button that is always visible (the full menu stays behind "Menu"), nav in a
    newcomer-friendly order, footer no longer says "Dallas–Fort Worth" or "working title".
  - Homepage front section: the same layout procedure_pages.py now writes (how-it-works steps, proof first), applied to
    the live page so it shows before the next daily build.
  - Start here: "find a price in three steps" and "which one are you?" paths above the explainer.
  - Every Price Finder page (and its R2 layout): asks how you're paying instead of silently showing one insurer, remembers
    the choice, puts the price list ahead of the Medicare and arbitration context, and tidies provider-name capitalization.
  - Pages with the shared top link bar: "Start here" styled as a button.
  - Plan Calculator: two-column pickers (no cut-off insurer names), readable CMS quality line.
The Price Finder additions are one added block between <!-- UX:START --> and <!-- UX:END --> and change no existing
wording, so city_page.py's wording checks still pass.
"""
import html
import json
import os
import re
import sys

MARK_PF = '<!-- UX:START'

# ------------------------------------------------------------------ Price Finder block (added before </body>)
PF_BLOCK = r'''<!-- UX:START (site/ux_polish.py: pay prompt, list first, tidy names) -->
<style id="uxCss">
.ux-pay{margin:14px 0 0;padding:12px 16px;border:2px solid var(--brick);display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:15px;line-height:1.45}
.ux-pay[hidden]{display:none}
.ux-pay button{min-height:42px;padding:0 16px;border:0;background:var(--brick);color:var(--paper);font:700 14px var(--body);cursor:pointer}
#pay.ux-ask{outline:3px solid var(--brick);outline-offset:3px}
.ux-ctx{margin:26px 0 0}
details.ux-ctx{border-top:1px solid var(--rule);padding-top:6px}
.ux-hits{margin:18px 0;padding:16px 18px;border:2px solid var(--ink)}.ux-hits ul{list-style:none;margin:10px 0 0;padding:0;columns:2 320px;column-gap:24px}.ux-hits li{break-inside:avoid}.ux-hits button{display:block;width:100%;text-align:left;min-height:44px;padding:8px 0;border:0;border-bottom:1px solid var(--rule);background:none;color:var(--ink);font:inherit;cursor:pointer}.ux-hits button span{font:12px var(--type);opacity:.75}
.ux-words{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:18px 0 6px;font-size:15px}.ux-words>span{font-weight:700;margin-right:4px}.ux-chip{min-height:40px;padding:0 12px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);font:inherit;cursor:pointer;text-decoration:underline dotted;text-underline-offset:4px}dialog.ux-wc{max-width:420px;width:calc(100% - 32px);border:2px solid var(--ink);padding:20px 22px;background:var(--paper);color:var(--ink);box-shadow:8px 8px 0 var(--ink)}dialog.ux-wc::backdrop{background:rgba(0,0,0,.35)}.ux-wcn{margin:0 0 8px;font:700 12px var(--type);letter-spacing:.1em;text-transform:uppercase;opacity:.75}.ux-wch{display:flex;align-items:center;gap:14px;color:var(--brick)}.ux-wch h3{margin:0;color:var(--ink);font:700 28px/1.05 var(--display)}.ux-wcm{font-size:17px;line-height:1.5;margin:12px 0 0}.ux-wcb{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 0}.ux-wcb button{min-height:44px;padding:0 14px;border:2px solid var(--ink);background:var(--paper);color:var(--ink);font:700 15px var(--body);cursor:pointer}.ux-wcb button[data-uxwc]{background:var(--ink);color:var(--paper)}.ux-bills{margin:34px 0 10px}.ux-bills .ux-k{margin:0;font:700 13px var(--type);letter-spacing:.12em;text-transform:uppercase;color:var(--brick)}.ux-bills h2{margin:6px 0 6px}.ux-lede{margin:0 0 12px;max-width:62ch}.ux-slips{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));padding:6px 4px 10px}.ux-slip{background:var(--paper);color:var(--ink);font-family:var(--type);padding:14px 16px 16px;box-shadow:0 4px 0 -1px var(--rule);border:1px solid var(--rule);display:flex;flex-direction:column;gap:6px}.ux-slip:nth-child(odd){transform:rotate(-.8deg)}.ux-slip:nth-child(even){transform:rotate(.7deg);margin-top:8px}.ux-slip.maybe{background:transparent;border:2px dashed var(--ink);box-shadow:none}.ux-slip p{margin:0}.ux-slip .n{font-size:11px;letter-spacing:.12em;text-transform:uppercase;text-align:center;border-bottom:1px dashed var(--ink);padding-bottom:6px}.ux-slip .t{font-weight:700;font-size:16px;text-transform:uppercase}.ux-slip .w{font-size:13px}.ux-slip .v{display:flex;justify-content:space-between;gap:8px;border-top:1px dashed var(--ink);padding-top:6px;font-weight:700}.ux-slip .s{font-size:12px;opacity:.8}.ux-slip .l a{font:700 13px var(--body);color:var(--brick)}@media(prefers-reduced-motion:reduce){.ux-slip{transform:none!important}}
details.ux-ctx>summary{cursor:pointer;font:700 15px var(--body);min-height:44px;display:flex;align-items:center}
</style>
<script id="uxJs">
(() => {
  const pay = document.getElementById('pay');
  if (!pay || typeof render !== 'function') return;
  const K = 'wic-pay';                       // the network the visitor picked, by its label, across pages and visits
  const h = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const label = () => ((pay.selectedOptions || [])[0] || {}).textContent || '';
  let chosen = !!new URLSearchParams(location.search).get('net');
  const box = document.createElement('div');
  box.className = 'ux-pay'; box.setAttribute('role', 'note');
  const sent = document.querySelector('.sent');
  if (sent) sent.insertAdjacentElement('afterend', box);
  const show = () => {
    pay.classList.toggle('ux-ask', !chosen);
    box.hidden = chosen;
    if (!chosen) box.innerHTML = `<span>Showing <b>${h(label())}</b> as an example. Prices depend on your insurance, so pick your plan's network in <b>paying with</b>, or choose <b>Paying cash</b>.</span><button type="button">Choose my insurance</button>`;
  };
  box.addEventListener('click', e => {
    if (!e.target.closest('button')) return;
    pay.scrollIntoView({block: 'center', behavior: 'smooth'}); pay.focus();
    try { pay.showPicker(); } catch (err) {}
  });
  pay.addEventListener('change', () => { chosen = true; try { localStorage.setItem(K, label()); } catch (err) {} show(); });
  try {
    const saved = localStorage.getItem(K);
    const o = !chosen && saved && [...pay.options].find(x => x.textContent === saved);
    if (o && o.value !== pay.value) { pay.value = o.value; pay.dispatchEvent(new Event('change')); }
    else if (o) chosen = true;
  } catch (err) {}
  show();

  // provider names as the files spell them: "Children'S", "West PArk", "Mckinney", "Medical Center At Dallas", "Llc"
  const tidy = t => t.replace(/([A-Za-z])'S\b/g, "$1's")
    .replace(/\b([A-Z])([A-Z])([a-z]{2,})\b/g, (m, a, b, c) => a + b.toLowerCase() + c)
    .replace(/\bMc([a-z])/g, (m, a) => 'Mc' + a.toUpperCase())
    .replace(/(\S )(Of|And|At|For|The)(?= \S)/g, (m, a, b) => a + b.toLowerCase())
    .replace(/\b(Llc|Llp|Lp|Pllc|Pa|Pc|Vamc|Va|Uhs|Ii|Iii|Iv|Usmd|Jps|Hma|Fw|Mca|Chi|Utsw|Ut|Bsw|Hca|Ltac|Asc|Er)\b/g, m => m.toUpperCase())
    .replace(/\bSouhtlake\b/g, 'Southlake').replace(/\bMuesnter\b/g, 'Muenster');
  const tidyIn = root => root && root.querySelectorAll('.who').forEach(w => {
    const it = document.createTreeWalker(w, NodeFilter.SHOW_TEXT); let n;
    while ((n = it.nextNode())) { const t = tidy(n.nodeValue); if (t !== n.nodeValue) n.nodeValue = t; }
  });

  // the price list first; Medicare benchmark and surprise-bill arbitration follow it
  const listFirst = () => {
    const P = document.getElementById('patient');
    if (!P || P.querySelector('.ux-ctx')) return;
    const med = [], arb = []; let cur = null;
    for (const el of [...P.children]) {
      if (el.tagName === 'H4') { const t = el.textContent.toLowerCase(); cur = /medicare benchmark/.test(t) ? med : /arbitration/.test(t) ? arb : null; }
      else if (el.tagName === 'H2' || el.matches('.strip,.legend,.cols')) cur = null;
      if (cur) cur.push(el);
    }
    if (!med.length && !arb.length) return;
    const cols = P.querySelectorAll(':scope > .cols');
    let at = cols.length ? cols[cols.length - 1] : null;
    if (!at) return;                           // nothing to put first; leave the page as it is
    if (med.length) { const d = document.createElement('div'); d.className = 'ux-ctx'; med.forEach(e => d.appendChild(e)); at.insertAdjacentElement('afterend', d); at = d; }
    if (arb.length) { const d = document.createElement('details'); d.className = 'ux-ctx';
      d.innerHTML = '<summary>When a surprise bill for this goes to federal arbitration</summary>'; arb.slice(1).forEach(e => d.appendChild(e)); arb[0].remove();
      at.insertAdjacentElement('afterend', d); }
  };
  // word cards (one at a time) and the separate bills to expect, for the procedure on screen (Oct 18)
  const ICON = {neg:'<path d="M6 12h52v34H6z"/><path d="M6 22h52M14 32h18M14 39h10"/><path d="M38 52l6 6 12-12"/>',
    fac:'<path d="M8 56V24l24-14 24 14v32z"/><path d="M26 56V40h12v16"/>', cash:'<path d="M6 18h52v30H6z"/><circle cx="32" cy="33" r="8"/>',
    med:'<path d="M6 46h52"/><path d="M14 46V30M24 46V22M34 46V34M44 46V18"/>', ded:'<path d="M18 12h28v6l4 6v30H14V24l4-6z"/><path d="M14 40h36"/>',
    pct:'<path d="M14 50L50 14"/><circle cx="18" cy="18" r="6"/><circle cx="46" cy="46" r="6"/>'};
  const CARDS = [['neg','Negotiated rate','The total an insurer agreed to pay a place. Until you meet your deductible, you pay all of it.'],
    ['fac','Facility fee',"What the hospital or surgery center charges for the room, staff, equipment and supplies. The doctor's fee is a separate bill."],
    ['cash','Cash price','What a provider says it charges if you pay yourself, without insurance. Ask for a written Good Faith Estimate.'],
    ['med','Medicare rate','What Medicare pays for the same service. A yardstick for judging a price, not a price you can get.'],
    ['ded','Deductible','What you pay each year before your plan starts sharing the cost. Until then, you usually pay the negotiated rate (some care, like preventive screenings, is covered before the deductible).'],
    ['pct','Percent of billed charges',"Some contracts pay a share of the hospital's list price instead of a dollar amount, so the bill depends on that list price."]];
  const words = document.createElement('div'); words.className = 'ux-words';
  words.innerHTML = '<span>Words on this page:</span>' + CARDS.map(c => `<button type="button" class="ux-chip" data-uxwc="${c[0]}">${h(c[1])}</button>`).join('')
    + CARDS.map((c, i) => `<dialog class="ux-wc" id="uxwc-${c[0]}" aria-labelledby="uxwct-${c[0]}"><p class="ux-wcn">Word card · ${i + 1} of ${CARDS.length}</p>`
      + `<div class="ux-wch"><svg viewBox="0 0 64 64" width="60" height="60" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">${ICON[c[0]]}</svg><h3 id="uxwct-${c[0]}">${h(c[1])}</h3></div>`
      + `<p class="ux-wcm">${h(c[2])}</p><p class="ux-wcb">${i + 1 < CARDS.length ? `<button type="button" data-uxwc="${CARDS[i + 1][0]}">Next card: ${h(CARDS[i + 1][1].toLowerCase())} →</button>` : ''}<button type="button" data-uxclose>Close</button></p></dialog>`).join('');
  const tabs = document.querySelector('nav.vtabs'); if (tabs) tabs.insertAdjacentElement('beforebegin', words);
  document.addEventListener('click', e => { const o = e.target.closest('[data-uxwc]'); if (o) { const d = document.getElementById('uxwc-' + o.dataset.uxwc);
      if (d) { const op = document.querySelector('dialog.ux-wc[open]'); if (op) op.close(); d.showModal(); } }
    if (e.target.closest('[data-uxclose]')) e.target.closest('dialog').close(); if (e.target.matches && e.target.matches('dialog.ux-wc')) e.target.close(); });
  const bills = document.createElement('section'); bills.className = 'ux-bills';
  const pat = document.getElementById('patient'); if (pat) pat.insertAdjacentElement('afterend', bills);
  const slipsFor = () => {
    const C = (typeof D !== 'undefined' && D.codes && D.codes[S.code]) || {}; const cat = C.cat || '', code = S.code || '', drg = /DRG/.test(C.type || '');
    const look = (w, t) => `<a href="?q=${encodeURIComponent(w)}">${h(t)} →</a>`;
    const here = ['Shown above', 'pick your network'], ask = ['Ask for this one', ''];
    let L;
    if (code.startsWith('00')) L = [['The anesthesia team', 'this page', here], ['The place', 'facility fee, a separate bill', ask], ['The doctor', 'who does the procedure', ask]];
    else if (drg) L = [['The hospital stay', 'this page', here], ['The doctors', 'who see you in the hospital', ask], ['Surgery and anesthesia', 'if you have an operation', ask]];
    else if (cat === 'Imaging') L = [['The place', 'the scan itself', here], ['The radiologist', 'who reads the scan', ask]];
    else if (/Lab/.test(cat)) L = [['The lab', 'this page', here], ['Drawing the blood, maybe', 'sometimes a small separate charge', ask]];
    else if (/Office|Behavioral|therapy|Heart/i.test(cat)) L = [['The clinician', 'this page', here], ['A facility fee, maybe', 'only at clinics a hospital owns', ask]];
    else L = [['The place', 'facility fee: room, staff, equipment', here], ['The doctor', 'who does the procedure', ask],
      ['Anesthesia', 'often a separate company', ask.concat(look('anesthesia', 'Look up anesthesia prices'))],
      ['Lab work, maybe', 'only if tissue is sent to a pathologist', ask.concat(look('pathologist', 'Look up pathology prices'))]];
    bills.innerHTML = `<p class="ux-k">You'll likely get these bills</p><h2>Expect more than one bill</h2><p class="ux-lede">Each slip is a separate bill, often from a different company. This page prices one slip at a time.</p><div class="ux-slips">`
      + L.map((x, i) => `<div class="ux-slip${/maybe/i.test(x[0]) ? ' maybe' : ''}"><p class="n">Bill ${i + 1} of ${L.length}</p><p class="t">${h(x[0])}</p><p class="w">${h(x[1])}</p>`
        + `<p class="v"><span>${x[2][0].startsWith('$') ? 'TOTAL' : 'PRICE'}</span><b>${h(x[2][0])}</b></p>${x[2][1] ? `<p class="s">${h(x[2][1])}</p>` : ''}${x[2][2] ? `<p class="l">${x[2][2]}</p>` : ''}</div>`).join('') + '</div>';
  };
  const after = () => { try { slipsFor(); } catch (err) {} try { listFirst(); } catch (err) {} try { tidyIn(document.getElementById('patient')); tidyIn(document.getElementById('board')); tidyIn(document.getElementById('mapv')); } catch (err) {} };
  // ?q=colon (from the homepage search): list every billing code whose name matches, pick one to load it
  try {
    const qq = window.__uxQ || new URLSearchParams(location.search).get('q');
    if (qq && typeof D !== 'undefined' && D.codes) {
      const t = qq.trim().toLowerCase();
      const hits = Object.keys(D.codes).filter(c => c.toLowerCase() === t || String(D.codes[c].name || '').toLowerCase().includes(t)).slice(0, 60);
      const box = document.createElement('div'); box.className = 'ux-hits';
      box.innerHTML = `<p><b>${hits.length >= 60 ? '60+' : hits.length} billing code${hits.length === 1 ? '' : 's'} match “${h(qq)}”.</b> ${hits.length ? 'Pick one:' : 'Try a shorter word or a billing code.'}</p>`
        + (hits.length ? '<ul>' + hits.map(c => `<li><button type="button" data-c="${h(c)}">${h(D.codes[c].name)} <span>${h(D.codes[c].type || 'CPT')} ${h(c)}</span></button></li>`).join('') + '</ul>' : '');
      const q = document.querySelector('section.q'); (q || document.body).insertAdjacentElement(q ? 'afterend' : 'afterbegin', box);
      box.addEventListener('click', e => { const b = e.target.closest('button[data-c]'); if (!b) return;
        S.code = b.dataset.c; S.showAll = {}; const pr = document.getElementById('proc'); if (pr) pr.value = `${D.codes[S.code].name} · ${S.code}`;
        box.remove(); render(); window.scrollTo(0, 0); });
    }
  } catch (err) {}
  const base = render;
  render = function () { const r = base.apply(this, arguments); after(); return r; };
  after();
})();
</script>
<!-- UX:END -->
'''
TRUST = ('<p class="ux-trust" style="max-width:68ch;margin:36px auto 24px;padding:14px 16px 0;border-top:1px solid var(--rule,#d6cbb8);font-size:13.5px">'
         'Who runs this site and how it works: <a href="/about/">About</a> · <a href="/methodology/">How we read the files</a> · '
         '<a href="/disclaimers/">Disclaimers</a> · <a href="/corrections/">Report a wrong price</a></p>')
PF_BLOCK = PF_BLOCK.replace('<!-- UX:END -->', TRUST + '\n<!-- UX:END -->')

NAV_CSS = ('<style id="uxNav">.sn-links a[href="/start-here/"],.toplinks a[href="/start-here/"]{background:var(--brick);color:var(--paper)!important;'
           'padding:1px 10px;text-decoration:none;font-weight:700}</style>')


def sub1(s, old, new, what):
    if s.count(old) != 1:
        raise SystemExit(f'STOP: expected text not found once ({what}); nothing written')
    return s.replace(old, new)


Q_EARLY = '<script id="uxQ">try{window.__uxQ=new URLSearchParams(location.search).get("q")}catch(e){}</script>'


def patch_pf(s):
    if 'id="uxQ"' not in s:
        s = s.replace('<head>', '<head>' + Q_EARLY, 1)
    if MARK_PF in s:
        return re.sub(r'<!-- UX:START.*?<!-- UX:END -->\n', lambda m: PF_BLOCK, s, count=1, flags=re.S)
    i = s.rfind('</body>')
    if i < 0:
        raise SystemExit('STOP: Price Finder page has no </body>')
    s = s[:i] + PF_BLOCK + s[i:]
    return patch_nav(s)


def patch_nav(s):
    if 'id="uxNav"' in s or ('class="sn-links"' not in s and 'class="toplinks"' not in s):
        return s
    return s.replace('</head>', NAV_CSS + '</head>', 1)


# ------------------------------------------------------------------ homepage
HOME_CSS = ('.start-pill{margin-left:auto;display:inline-flex;align-items:center;min-height:44px;padding:0 14px;background:var(--hi);'
            'color:var(--ink)!important;font-weight:800;font-size:15px;text-decoration:none;white-space:nowrap}.start-pill:hover{filter:brightness(.93)}\n'
            '@media(max-width:420px){.logo{font-size:24px!important}.start-pill{padding:0 10px;font-size:14px}.bar .wrap{gap:10px}}\n')
NAV_NEW = '''<nav class="nav" id="nav" aria-label="Main">
      <a href="/start-here/">Start here</a> <a href="/costs/">Prices</a><a href="/price-finder/">Price Finder</a><a href="/plan-calculator/">Plan Calculator</a>
      <a href="/price-file-watch/">Price File Watch</a><a href="/surprise-bills/">Surprise Bills</a><a href="/employer-plans/">Employer Plans</a><a href="/insurers/">Insurers</a>
      <a href="#/r/45378" data-route="receipt">Receipts</a>
      <a href="#/chargemaster" data-route="chargemaster">The Chargemaster</a>
      <a href="#/rules" data-route="rules">House rules</a>
      <button class="ask" data-open="ask">Ask the Chargemaster</button>
    </nav>'''

NAT_CSS = ('.nat-new{margin:4px 0 0;font:700 17px var(--body)}.nat-new a{color:var(--hi);text-underline-offset:4px}\n'
           '.nat-trust{margin:0;font:14px/1.5 var(--mono);color:var(--board-sub);letter-spacing:.02em}.nat-trust i{font-style:normal;padding:0 6px}\n'
           '.steps{list-style:none;counter-reset:st;margin:18px 0 0;padding:0;display:grid;gap:0;border:2px solid var(--rule)}@media(min-width:800px){.steps{grid-template-columns:repeat(3,1fr)}}\n'
           '.steps li{counter-increment:st;display:flex;flex-direction:column;gap:6px;padding:22px;background:var(--paper);border-bottom:2px solid var(--rule)}.steps li:last-child{border-bottom:0}\n'
           '@media(min-width:800px){.steps li{border-bottom:0;border-right:2px solid var(--rule)}.steps li:last-child{border-right:0}}\n'
           '.steps li::before{content:counter(st);font:900 44px/1 var(--display);color:var(--stamp)}.steps b{font-size:19px}.steps span{color:var(--muted)}.steps a{color:var(--stamp)}.steps-more{margin:18px 0 0}\n')
NAT_AFTER_FORM = ('<p class="nat-new"><a href="/start-here/">New here? See how it works <span aria-hidden="true">→</span></a></p>\n'
                  '<p class="nat-trust">Free <i aria-hidden="true">·</i> No ads <i aria-hidden="true">·</i> Every price dated and linked to the file it came from</p>\n')
NAT_STEPS = '''<div class="sec"><p class="kicker">How it works</p><h2>Three steps to a real price</h2>
<ol class="steps">
<li><b>Pick a procedure and a place.</b><span>Start with a common one, like a colonoscopy or a knee MRI, or look up any billing code in the <a href="/price-finder/">Price Finder</a>.</span></li>
<li><b>See the real range.</b><span>The lowest and highest prices published in your area, from hospitals' and insurers' own files, plus cash prices where they're posted.</span></li>
<li><b>Check your plan.</b><span>Pick your insurer's network to see what it pays each place. On a HealthCare.gov plan in DFW? The <a href="/plan-calculator/">Plan Calculator</a> shows what you'd owe.</span></li>
</ol>
<p class="steps-more"><a class="btn" href="/start-here/">Read the 2-minute guide</a></p></div>
'''


def patch_home(s):
    s = s.replace('What insurers actually pay hospitals, doctors and labs in Dallas–Fort Worth, from the price files',
                  'What insurers actually pay hospitals, doctors and labs, place by place, from the price files')
    if 'class="start-pill"' not in s:
        s = sub1(s, '</style>\n\n<header class="bar">', HOME_CSS + '@media(min-width:1601px){.start-pill{display:none}}\n</style>\n\n<header class="bar">', 'home css')
        s = sub1(s, '<button class="menu-btn" id="menuBtn"', '<a class="start-pill" href="/start-here/">Start here</a>\n    <button class="menu-btn" id="menuBtn"', 'home menu')
        s = re.sub(r'<nav class="nav" id="nav" aria-label="Main">.*?</nav>', lambda m: NAV_NEW, s, count=1, flags=re.S)
        s = sub1(s, 'The receipt for the U.S. healthcare system · working title, private preview', 'The receipt for the U.S. healthcare system · private preview', 'footer 1')
        s = sub1(s, 'Prices from federally required hospital and insurer files · Dallas–Fort Worth<br>', 'Prices from the files hospitals and insurers are required to publish<br>', 'footer 2')
    if 'class="steps"' not in s and '<!-- NATIONAL:START' in s:
        a, b = s.index('<!-- NATIONAL:START'), s.index('<!-- NATIONAL:END -->')
        n = s[a:b]
        n = sub1(n, '\n@media(max-width:1600px)', '\n' + NAT_CSS + '@media(max-width:1600px)', 'national css')
        n = sub1(n, '</form>\n<p class="msg"', '</form>\n' + NAT_AFTER_FORM + '<p class="msg"', 'national form')
        ex = re.search(r'<div class="sec"><div class=\'receiptish\'>.*?</div></div>\n', n, re.S)
        doors = re.search(r'<div class="sec"><p class="kicker">Three ways in</p>.*?</div></div>\n', n, re.S)
        if not doors:
            raise SystemExit('STOP: homepage "Three ways in" block not found')
        dtxt = doors.group(0).replace('<p class="kicker">Three ways in</p><h2>Who this is for</h2>', '<p class="kicker">Who it\'s for</p><h2>Start where you are</h2>')
        n = n.replace(doors.group(0), '')
        etxt = ''
        if ex:
            etxt = ex.group(0)
            n = n.replace(etxt, '')
        n = sub1(n, '<div class="wrap">\n<div class="sec split">', '<div class="wrap">\n' + NAT_STEPS + etxt + dtxt + '<div class="sec split">', 'national order')
        s = s[:a] + n + s[b:]
    return s


# ------------------------------------------------------------------ Start here
GUIDE = '''<section class="ux-guide" aria-labelledby="g3">
  <h2 id="g3" class="ux-h">Find a price in three steps</h2>
  <ol class="ux-steps">
    <li><b>Pick a procedure and a place.</b> Start with a common one on the <a href="/costs/">price pages</a>, or look up any billing code in the <a href="/price-finder/">Price Finder</a>.</li>
    <li><b>See the real range.</b> The lowest and highest prices published where you live, each linked to the hospital or insurer file it came from.</li>
    <li><b>Check your plan.</b> Pick your insurer's network to see what it pays each place, or choose "Paying cash." Until you meet your deductible, the negotiated rate is what you pay.</li>
  </ol>
  <h2 class="ux-h">Which one are you?</h2>
  <div class="ux-paths">
    <a href="/costs/"><b>I have insurance through work or on my own</b><span>Look up the procedure, then pick your insurer's network in the Price Finder. Your plan's network decides which price applies to you.</span></a>
    <a href="/plan-calculator/"><b>I have a HealthCare.gov plan in Dallas–Fort Worth</b><span>The Plan Calculator applies your deductible, copay and coinsurance to each place's rate.</span></a>
    <a href="/costs/"><b>I'm paying cash or I'm uninsured</b><span>Compare posted cash prices. Before scheduled care, you can ask for a written good faith estimate (see section 04 below).</span></a>
    <a href="/surprise-bills/"><b>I got a surprise bill</b><span>See how out-of-network bills for your procedure fared in federal arbitration, and what the law limits you to.</span></a>
    <a href="/employer-plans/"><b>I run benefits for an employer</b><span>See which networks your plan uses and what those networks actually pay.</span></a>
    <a href="/price-file-watch/"><b>I'm a reporter or policymaker</b><span>Who isn't publishing usable price files, with the rule they're under. <em>How we read the files</em> is on the <a href="/methodology/">methodology page</a>.</span></a>
  </div>
  <p class="ux-bg">Want the background first? The seven short sections below explain the rules, the files and every kind of price on this site.</p>
</section>
'''
GUIDE_CSS = '''<style id="uxGuide">
.ux-guide{margin:26px 0 0}
.ux-h{font:600 26px/1.2 var(--display);margin:30px 0 10px;padding:0;border:0}
.ux-steps{margin:0;padding-left:22px;display:grid;gap:8px}
.ux-paths{display:grid;gap:10px;margin-top:6px}@media(min-width:640px){.ux-paths{grid-template-columns:1fr 1fr}}
.ux-paths>a{display:flex;flex-direction:column;gap:4px;padding:14px 16px;border:1.5px solid var(--ink);background:var(--paper-2);text-decoration:none;color:var(--ink)}
.ux-paths>a:hover{border-color:var(--brick)}.ux-paths b{color:var(--brick);font-size:16px}.ux-paths span{font-size:14.5px;color:var(--ink-2)}
.ux-paths span a{color:inherit}
.ux-bg{margin:26px 0 0;color:var(--ink-2)}
</style>'''


def patch_start(s):
    if 'class="ux-guide"' in s:
        return s
    # a link inside a link is invalid HTML; the last card keeps one link
    guide = GUIDE.replace(' <em>How we read the files</em> is on the <a href="/methodology/">methodology page</a>.', '')
    s = sub1(s, '  <ol class="toc">', guide + '  <ol class="toc">', 'start toc')
    s = sub1(s, '<h1>What healthcare actually costs, and how to read the prices</h1>', '<h1>How to find a real price, and how to read it</h1>', 'start h1')
    s = s.replace('</head>', GUIDE_CSS + '</head>', 1)
    return patch_nav(s)


# ------------------------------------------------------------------ Plan Calculator
CALC_CSS = ('<style id="uxCalc">@media(min-width:760px){form#f.form{grid-template-columns:repeat(2,minmax(0,1fr))}}'
            '.qrow{display:flex;flex-wrap:wrap;gap:2px 18px;margin-top:4px}</style>')


def patch_calc(s):
    if 'id="uxCalc"' in s:
        return s
    s = sub1(s, '<span class="t qrow"><span class="st">${qv(p.q[0])}</span>', '<span class="t qrow"><span class="st">overall: ${qv(p.q[0])}</span>', 'calc quality')
    s = s.replace('</head>', CALC_CSS + '</head>', 1)
    return add_trust(patch_nav(s))


def add_trust(s):
    if 'class="ux-trust"' in s or 'href="/about/"' in s:
        return s
    i = s.rfind('</body>')
    return s[:i] + TRUST + '\n' + s[i:] if i > 0 else s


def patch_watch(s):
    old = 'We read the files for Dallas–Fort Worth.'
    if old in s and 'Other areas are next.' not in s:
        s = s.replace(old, 'We read the files for Dallas–Fort Worth first. Other areas are next.', 1)
    return add_trust(patch_nav(s))


def patch_mw(s):
    """Testers see the site in its default look without the Look switcher (it's Betsy's preview tool)."""
    if 'look-pick{display:none' in s:
        return s
    old = "el.append('<link rel=\"stylesheet\" href=\"/looks/looks.css\"><script src=\"/looks/looks.js\"></script>', { html: true });"
    new = ("el.append('<link rel=\"stylesheet\" href=\"/looks/looks.css\"><script src=\"/looks/looks.js\"></script>' + "
           "(tester ? '<style>.look-pick{display:none!important}</style>' : ''), { html: true });")
    return sub1(s, old, new, 'middleware looks')


HOTLINE_V2 = """
/* ux: hotline v2 (Oct 17): match the original Hotline mockup: solid black, no scan lines or ruled stripes through text */
html[data-look="hotline"]:not(#_) body{background:#050807!important}
html[data-look="hotline"]:not(#_) .board{background-image:none!important;border-bottom:2px solid #45F0AE}
html[data-look="hotline"]:not(#_) .board h1+p{font-family:"Look Archivo",sans-serif!important;font-weight:800;color:#C9CFCB!important;border-bottom:3px solid #E0301E;padding-bottom:12px;max-width:900px}
html[data-look="hotline"]:not(#_) :is(.doors,.door,.steps,.steps li,.tile,.receiptish){border-color:#45F0AE!important}
html[data-look="hotline"]:not(#_) :is(.nat-search button,.btn,.btn.hi){background:#45F0AE!important;color:#050807!important;border:0}
html[data-look="hotline"]:not(#_) .nat-search select{background:#07120D;color:#D5F7EA;border:2px solid #45F0AE}
html[data-look="hotline"]:not(#_) .nat-trust{color:#8FCFB4}
html[data-look="hotline"]:not(#_) .nat-pop a{border-color:#1E5C45}html[data-look="hotline"]:not(#_) .nat-pop a:hover{border-color:#45F0AE}
"""


def patch_looks_css(s):
    if '/* ux: hotline v2' not in s:
        s += HOTLINE_V2
    elif '.nat-pop a{border-color:#1E5C45}' not in s:
        s += HOTLINE_V2.split('\n')[-2] + '\n'
    if '/* ux: start pill */' not in s:
        s += ('\n/* ux: start pill */html[data-look="hotline"]:not(#_) .start-pill{background:#45F0AE!important;color:#050807!important}\n')
    if '/* ux: phone */' in s:
        return s
    return s + ('\n/* ux: phone */@media(max-width:700px){.look-pick{left:auto;right:8px;bottom:8px;padding:4px 6px;gap:4px;font-size:12px;opacity:.9}'
                '.look-pick select{max-width:118px;min-height:28px;font-size:12px}}\n')


def patch_disclaimers(s):
    old = re.search(r'\[Choose one:\]\s*- \[(The Healthcare Files does not currently accept payment[^\]]*)\]\s*- \[Some providers pay[^\]]*\]', s)
    return s.replace(old.group(0), old.group(1)) if old else s


def patch_method(s):
    old = ('Each price shows two dates: when the source says it was last updated, and when we last checked it. Prices more than 12 months old, '
           'or with no date in the source, carry an "Older price" flag.')
    new = ('Each hospital and insurer price shows the date its source file gives. Prices from files more than six months old, or from files '
           'with no date, are flagged. Posted cash prices show the date we last checked the provider\'s page.')
    return s.replace(old, new) if old in s else s


NOT_FOUND = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Page not found · The Healthcare Files</title>
<style>body{margin:0;background:#f6f1e7;color:#231f1a;font:17px/1.6 "Public Sans",system-ui,sans-serif;padding:0 16px}main{max-width:640px;margin:12vh auto}
h1{font:600 40px/1.1 Georgia,serif;margin:0 0 12px}a{color:#9b3a2a}ul{padding-left:20px}</style></head><body><main>
<p style="font:700 13px monospace;letter-spacing:.12em;text-transform:uppercase;color:#9b3a2a">404</p><h1>We couldn't find that page</h1>
<p>The link may be old or mistyped. Try one of these:</p>
<ul><li><a href="/">Home</a></li><li><a href="/start-here/">Start here: how the site works</a></li><li><a href="/costs/">Look up a price</a></li><li><a href="/price-finder/">Price Finder (every billing code)</a></li><li><a href="/hospitals/">Hospitals</a></li><li><a href="/insurers/">Insurers</a></li><li><a href="/surprise-bills/">Surprise Bills</a></li></ul>
</main></body></html>
'''


# ------------------------------------------------------------------ Oct 18: Units as the site look, same opening on every page
import home_bits
import page_meta

UNITS_V1 = """
/* ux: units v2 (Oct 18): every page opens on the same blue band; Start here stands out; labels readable on cream */
html[data-look="units"]:not(#_) :is(.sn,.top){border-bottom:0!important;padding-block:16px!important;color:#fff;
  border-image:linear-gradient(#2E5BE6 0 0) fill 0 / 0 / 0 100vmax}
html[data-look="units"]:not(#_) :is(.sn-brand,.brand){color:#fff!important;font:800 26px/1 "Look Hanken",sans-serif!important;text-transform:uppercase;letter-spacing:-.01em}
html[data-look="units"]:not(#_) :is(.sn-links,.toplinks){color:#fff}html[data-look="units"]:not(#_) :is(.sn-links,.toplinks) a{color:#fff!important}
html[data-look="units"]:not(#_) :is(.sn-links,.toplinks) a[href="/start-here/"]{background:#F7C925!important;color:#151515!important;padding:4px 12px!important;font-weight:700}
html[data-look="units"]:not(#_) .wrap>header,html[data-look="units"]:not(#_) main>header.ux-band,html[data-look="units"]:not(#_) section.q{color:#fff;padding-block:30px 36px!important;margin-top:0!important;border-bottom:0!important;
  border-image:repeating-linear-gradient(#2E5BE6 0 26px,#3D69EC 26px 28px) fill 0 / 0 / 0 100vmax}
html[data-look="units"]:not(#_) :is(.wrap>header,header.ux-band,section.q) h1{color:#fff!important;font-weight:800!important;text-transform:uppercase;letter-spacing:-.025em}
html[data-look="units"]:not(#_) :is(.wrap>header,header.ux-band) .eyebrow{color:#F7C925!important}
html[data-look="units"]:not(#_) :is(.wrap>header,header.ux-band) .lede{color:#DCE5FC!important;border-bottom:0!important}
html[data-look="units"]:not(#_) :is(.wrap>header,header.ux-band) :is(a,.lede a){color:#fff!important}
html[data-look="units"]:not(#_) .eyebrow{color:#2E5BE6}
html[data-look="units"]:not(#_) .wrap>header .tally,html[data-look="units"]:not(#_) .wrap>header .tally *{color:#fff!important}
html[data-look="units"]:not(#_) .wrap>header .tally span span,html[data-look="units"]:not(#_) .wrap>header .tally :is(small,i,em){color:#DCE5FC!important}
html[data-look="units"]:not(#_) .wrap>:is(.asof,.topbar){color:#DCE5FC!important;margin:0!important;padding-block:6px 0!important;border-bottom:0!important;border-image:linear-gradient(#2E5BE6 0 0) fill 0 / 0 / 0 100vmax}
html[data-look="units"]:not(#_) .wrap>:is(.asof,.topbar) *{color:#DCE5FC!important}
html[data-look="units"]:not(#_) section.q :is(.sent,.sent label,.meta2,.code,#codeLine){color:#DCE5FC!important}
html[data-look="units"]:not(#_) section.q select{color:#fff!important;background-color:transparent!important;border-color:#fff!important}
html[data-look="units"]:not(#_) section.q select option{color:#151515;background:#fff}
html[data-look="units"]:not(#_) section.q .hv{color:#F7C925!important}
html[data-look="units"]:not(#_) section.q .sbtn{background:#fff!important;color:#151515!important}
html[data-look="units"]:not(#_) section.q #spanel{background:#fff;color:#151515;padding:16px;margin-top:12px}
html[data-look="units"]:not(#_) section.q .ux-pay{border-color:#F7C925;background:rgba(0,0,0,.14);color:#fff}
html[data-look="units"]:not(#_) section.q .ux-pay button{background:#F7C925;color:#151515}
html[data-look="units"]:not(#_) #pay.ux-ask{outline-color:#F7C925}
html[data-look="units"]:not(#_) .nat-pop a{border:0!important;padding:0!important;min-height:0!important;color:#fff!important;text-decoration:underline;text-underline-offset:3px}
html[data-look="units"]:not(#_) .nat-pop{gap:4px 14px;font-size:16px}
"""


CONTRAST_OCT18 = """
/* ux: contrast oct18 (pre-launch check): footer text on the blue band, source links on white tiles */
html[data-look="units"]:not(#_) footer .wrap>span,html[data-look="units"]:not(#_) footer .wrap>span *{color:#fff!important}
html[data-look="units"]:not(#_) .tile .src,html[data-look="units"]:not(#_) .tile a.src{color:#1F45C4!important}
"""



# Insurer and hospital profiles (and the Hospitals list) put their header inside <main class="prof">; give it the same blue band.
UNITS_PROF = r"""
/* ux: units profiles oct18 */
html[data-look="units"]:not(#_) main.prof>header{color:#fff;padding-block:30px 36px!important;margin-top:0!important;border-bottom:0!important;border-image:repeating-linear-gradient(#2E5BE6 0 26px,#3D69EC 26px 28px) fill 0 / 0 / 0 100vmax}
html[data-look="units"]:not(#_) main.prof>header h1{color:#fff!important;font-weight:800!important;text-transform:uppercase;letter-spacing:-.025em}
html[data-look="units"]:not(#_) main.prof>header .eyebrow{color:#F7C925!important}
html[data-look="units"]:not(#_) main.prof>header .lede{color:#DCE5FC!important;border-bottom:0!important}
html[data-look="units"]:not(#_) main.prof>header a{color:#fff!important}
html[data-look="units"]:not(#_) main.prof>header .tag{color:#fff!important;border-color:#DCE5FC!important;background:transparent!important}
"""


# The longer name (The Healthcare Files) pushed the phone Menu button off screen; long links and wide tables on profiles.
UNITS_PHONE = r"""
/* ux: units phone oct18b */
@media (max-width:480px){html[data-look="units"]:not(#_) .logo{font-size:19px!important;letter-spacing:-.01em!important;white-space:nowrap}html[data-look="units"]:not(#_) .start-pill{padding:6px 9px!important;font-size:14px!important}html[data-look="units"]:not(#_) .menu-btn{padding:6px 10px!important}html[data-look="units"]:not(#_) .bar .wrap{gap:8px!important}}
@media (max-width:700px){html[data-look="units"]:not(#_) main.prof a{overflow-wrap:anywhere}html[data-look="units"]:not(#_) main.prof table{display:block;overflow-x:auto;max-width:100%}}
"""

def patch_units_css(s):
    s = s if '/* ux: units v2' in s else s.split('\n/* ux: units v1')[0] + UNITS_V1
    s = s if '/* ux: contrast oct18' in s else s + CONTRAST_OCT18
    s = s if '/* ux: units profiles oct18' in s else s + UNITS_PROF
    return s if '/* ux: units phone oct18b' in s else s + UNITS_PHONE


def patch_looks_js(s):
    s = s.replace("var KEY = 'hcf-look-v2';", "var KEY = 'hcf-look-v3'; // v3 (Oct 18): default changed to Units")
    s = s.replace("if (!ok(v)) v = 'hotline';", "if (!ok(v)) v = 'units';")
    # Each look also pins the page's own light/dark colors, so a dark-mode computer can't put
    # dark-mode box colors under a light look's dark text (Oct 18: unreadable boxes on /insurers/).
    old = "if (look === 'original') root.removeAttribute('data-look'); else root.setAttribute('data-look', look);"
    new = ("if (look === 'original') { root.removeAttribute('data-look'); if (root.getAttribute('data-theme-by') === 'look') { root.removeAttribute('data-theme'); root.removeAttribute('data-theme-by'); } }\n"
           "    else { root.setAttribute('data-look', look); root.setAttribute('data-theme', DARK.indexOf(look) >= 0 ? 'dark' : 'light'); root.setAttribute('data-theme-by', 'look'); }")
    if 'data-theme-by' not in s:
        s = s.replace(old, new).replace("  var root = document.documentElement;", "  var DARK = ['hotline', 'amber', 'pedal', 'phos'];\n  var root = document.documentElement;", 1)
    return s


def patch_start_band(s):
    if 'class="ux-band"' in s:
        return s
    m = re.search(r'(<main>\s*)(<p class="eyebrow">.*?</p>\s*<h1>.*?</h1>\s*<p class="lede">.*?</p>)', s, re.S)
    return s[:m.start(2)] + '<header class="ux-band">' + m.group(2) + '</header>' + s[m.end(2):] if m else s


def patch_home_hero(s):
    if 'id="natQ"' in s or '<!-- NATIONAL:START' not in s:
        return s
    every = '21,000+'
    s = s.replace('<p style="font-size:21px;color:var(--board-ink)">Hospitals and insurers are required to publish their prices. They buried them in files too big to open. We opened them, and every price here links back to the file it came from.</p>', home_bits.LEDE)
    m = re.search(r'<label for="natProc">What do you need\?</label>\n<div class="row"><select id="natProc" aria-label="Procedure">(.*?)</select>', s, re.S)
    s = s[:m.start()] + '<label for="natQ">What do you need?</label>\n<div class="row">' + home_bits.qbox(m.group(1), every) + s[m.end():]
    s = re.sub(r'<p class="nat-new">.*?</p>\n<p class="nat-trust">.*?</p>\n', lambda _: home_bits.foot(every) + '\n', s, count=1, flags=re.S)
    s = re.sub(r"<script>\(function\(\)\{var f=document.getElementById\('natForm'\).*?</script>", lambda _: home_bits.HOME_JS.replace('__EVERY__', every), s, count=1, flags=re.S)
    i = s.index('.nat-trust{margin:0;font:14px/1.5 var(--mono)'); j = s.index('\n', i)
    return s[:j + 1] + home_bits.HOME_CSS2 + s[j + 1:]


INS_OLD = ("'</b> companies</span><span><b style=\"color:var(--ink)\">'+p.st+'</b> states with members</span></div>'")
INS_NEW = ("'</b> compan'+(p.c.length===1?'y':'ies')+'</span><span><b style=\"color:var(--ink)\">'+p.st+'</b> state'+(p.st===1?'':'s')+' with members</span></div>'+(AKA[p.n]?'<p class=\"aka\" style=\"margin:0;font-size:15px\">'+AKA[p.n]+'</p>':'')")
INS_AKA = ("var AKA={'Health Care Service Corp (HCSC)':'Runs <b>Blue Cross and Blue Shield</b> of Texas, Illinois, Oklahoma, New Mexico and Montana, as an independent licensee of the Blue Cross Blue Shield Association. It is owned by its members, not stockholders.'};\n  function drawPanel(){")


def patch_insurers(s):
    if 'var AKA=' in s:
        return s
    return s.replace(INS_OLD, INS_NEW).replace('  function drawPanel(){', INS_AKA, 1)


# ---------------------------------------------------------------- Oct 18 fact-check fixes (independent review, scratch report factcheck-report.md)
DOL_XII = 'https://www.dol.gov/sites/dolgov/files/EBSA/about-ebsa/our-activities/resource-center/faqs/aca-part-xii.pdf'
ECFR_180_50 = 'https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-E/part-180/subpart-B/section-180.50'
FACT = {
    'index.html': [
        ("Every hospital keeps a secret menu. It's called the <b>chargemaster</b>:", "Every hospital keeps a master price list. It's called the <b>chargemaster</b>:"),
        ("Every hospital keeps a secret menu called the <b>chargemaster</b>:", "Every hospital keeps a master price list called the <b>chargemaster</b>:"),
        ("Picture a diner where the prices are made up, the specials are whispered, and the check shows up six weeks later.",
         "Picture a diner where almost nobody pays the menu price, every table has its own deal, and the check shows up six weeks later."),
        ("A diner where the prices are made up, the specials are whispered, and the check shows up six weeks later.",
         "A diner where almost nobody pays the menu price, every table has its own deal, and the check shows up six weeks later."),
        ("They buried them in files too big to open.", "They're in files too big to open."),
        ("401 of 886 hospital colonoscopy facility rates are more than double Medicare's, and 264 are more than triple.",
         "401 of 886 hospital colonoscopy facility rates are more than double Medicare's national hospital outpatient rate (before local wage adjustment), and 264 are more than triple."),
        ("The columns every hospital's file must now include, under federal rules.</figcaption>",
         f'The columns every hospital\'s file must now include, under federal rules (<a href="{ECFR_180_50}" target="_blank" rel="noopener">45 CFR 180.50</a>).</figcaption>'),
        ("We show when each file was checked and flag anything that's gone stale.", "We show the date on each file and flag anything over six months old."),
    ],
    'start-here/index.html': [
        ("A screening that turns into a diagnostic procedure, such as a polyp removed during a colonoscopy, can also change both the billing code and what your plan covers.",
         f'A screening that turns into a diagnostic procedure can change the billing code. Under federal rules, removing a polyp during a screening colonoscopy shouldn\'t add cost-sharing on most private plans (<a href="{DOL_XII}" target="_blank" rel="noopener">U.S. Department of Labor, ACA FAQs Part XII</a>); billing mistakes still happen, and Medicare\'s rules differ.'),
        ("Until you meet your deductible, the negotiated rate is what you pay.", "Until you meet your deductible, you usually pay the negotiated rate."),
        ("These are the only public source for what insurers pay", "These are the main public source for what insurers pay"),
        ("A single insurer's files can run to hundreds of gigabytes.", "A single insurer's files are far too big to open on a normal computer."),
        ("<li><b>Hospital Price Transparency</b> (in effect", '<li><b><a href="https://www.cms.gov/priorities/key-initiatives/hospital-price-transparency" target="_blank" rel="noopener">Hospital Price Transparency</a></b> (in effect'),
        ("<li><b>Transparency in Coverage</b> (in effect", '<li><b><a href="https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-B/part-147/section-147.212" target="_blank" rel="noopener">Transparency in Coverage</a></b> (in effect'),
        ('can ask for a written "good faith estimate" before scheduled care.</p>',
         'can ask for a written "good faith estimate" before scheduled care (<a href="https://www.cms.gov/nosurprises" target="_blank" rel="noopener">CMS: No Surprises Act</a>).</p>'),
    ],
    'price-file-watch/index.html': [
        ("<h3>The files are hard to read by design</h3>", "<h3>The files are hard to read as published</h3>"),
        ("<h1>Who isn't publishing their prices</h1>", "<h1>Who isn't publishing usable price files</h1>"),
        ("<h3>Fixed</h3>", "<h3>Now posted</h3>"),
        ("more than twice what Medicare pays for the same procedure ($950.10)",
         "more than twice Medicare's national hospital outpatient rate for the same procedure ($950.10, before local wage adjustment)"),
        ('<div class="asof">Checked September 29, 2026</div>', '<div class="asof">Last checked October 13, 2026</div>'),
    ],
    'methodology/index.html': [
        ("We don't estimate, average, round or fill in prices. If a price isn't published, we don't show it.</p>",
         "We don't estimate, average, round or fill in prices. If a price isn't published, we don't show it. The one calculated figure is the Medicare benchmark for hospital stays, worked out from CMS's published formula (see below).</p>"),
        ("CMS's separate charity-care subsidy (which at some safety-net hospitals is larger than the stay payment itself)", "CMS's separate uncompensated care payments"),
        ("As of the October 2026 data, 68,644 of 74,532 providers are placed (92%)",
         "In the provider list the map was last built from (October 2026, 74,532 providers), 68,644 are placed (92%)"),
    ],
}
PF_FACT = [
    ("It can become a billed procedure if the doctor removes a polyp or takes a biopsy, which is when the codes and prices below start to matter. Ask your insurer how your plan handles that before you schedule.",
     f'Under federal rules, removing a polyp during a screening colonoscopy shouldn\'t add cost-sharing on most private plans (<a href="{DOL_XII}" target="_blank" rel="noopener">ACA FAQs Part XII</a>). A colonoscopy done to check symptoms is diagnostic, and that\'s when the codes and prices below matter. Ask your insurer how your plan handles it before you schedule.'),
    ("Every DFW provider in the federal NPI Registry is included", "Every DFW provider that appears in the insurer files we read is included"),
    ("are on the list of 70 that CMS requires every hospital to price.", "are on the list of 70 that CMS requires every hospital to price, if the hospital offers them."),
    ("data through September 2026)", "CMS's release as of September 2026)"),
    ("dated August to October 2026, read September 29, 2026:", "dated August to October 2026:"),
    ("come from 79 DFW hospital price files", "come from 83 DFW hospital price files"),
]
PF_FACT_RE = [(re.compile(r'Every provider in the federal NPI Registry with a practice address (.*?) is included'),
               r'Every provider with a practice address \1 that appears in the insurer files we read is included')]


def fact(rel):
    def fn(s):
        for a, b in FACT.get(rel, []):
            if b not in s:
                s = s.replace(a, b)
        return s
    return fn


def fact_pf(s):
    for a, b in PF_FACT:
        s = s.replace(a, b)
    for rx, b in PF_FACT_RE:
        s = rx.sub(b, s)
    return s


def renumber_disclaimers(s):
    """Sections were numbered 1-13, 15-18, 14: number them in page order."""
    n = [0]
    def f(m):
        n[0] += 1
        return f'<strong>{n[0]}. '
    return re.sub(r'<strong>\d+\. ', f, s)


# ---------------------------------------------------------------- Oct 18 (later): leftover fact-check items
AET = 'https://mrf.healthsparq.com/aetnacvs-egress.nophi.kyruushsq.com/prd/mrf/AETNACVS_I/ALICFI/2026-09-05/inNetworkRates/2026-09-05_pl-5it-hr23_Aetna-Life-Insurance-Company.json.gz'
BTX = 'https://app0004702110a5prdnc685.blob.core.windows.net/output/'
BTX_HMO = BTX + '2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_MyBlue-Health-HMO_in-network-rates.json.gz'
BTX_PPO = BTX + '2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.json.gz'
BTX_PAR = BTX + '2026-09-14_Blue-Cross-and-Blue-Shield-of-Texas_ParPlan_in-network-rates.json.gz'
UHC_CP = 'https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/download/2026-09-01/2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.json.gz'
OPPS_B = 'https://www.cms.gov/medicare/payment/prospective-payment-systems/hospital-outpatient-pps/quarterly-addenda-updates/july-2026-addendum-b'
PARPLAN_URL = 'https://bwww.bcbstx.com/provider/network/parplan.html'
CENSUS_DELIN = 'https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html'


def _a(u, t):
    return f'<a href="{u}" target="_blank" rel="noopener">{t} ↗</a>'


COLON_ROWS = [
    ('<div class="pline"><div class="who"><b>Aetna</b> · all 7 networks we read<div class="meta">Aetna files, September 5, 2026</div></div>',
     f'<div class="pline"><div class="who"><b>Aetna</b> · the 5 Aetna networks that list this hospital<div class="meta">{_a(AET, "Aetna PPO file dated September 5, 2026")}, same rate in the other 4</div></div>'),
    ('<div class="meta">CMS OPPS Addendum B, July 2026, national rate</div>',
     f'<div class="meta">{_a(OPPS_B, "CMS OPPS Addendum B, July 2026")}, national rate before <a href="/methodology/#medicare-local">local adjustment</a></div>'),
    ('<div class="meta">BCBSTX file, August 14, 2026</div>', f'<div class="meta">{_a(BTX_HMO, "BCBSTX file dated September 15, 2026")}</div>'),
    ('<div class="meta">BCBSTX file, August 15, 2026</div>', f'<div class="meta">{_a(BTX_PPO, "BCBSTX file dated September 15, 2026")}</div>'),
    ('<div class="meta">UHC file, September 1, 2026</div>', f'<div class="meta">{_a(UHC_CP, "UHC file dated September 1, 2026")}</div>'),
    ('<div class="meta">BCBSTX\'s rate for plans where the hospital is not in the member\'s network</div>',
     f'<div class="meta">Not a network a member picks: BCBSTX\'s contract with providers in or out of its networks, who accept its allowed amount '
     f'and don\'t bill the member above it ({_a(PARPLAN_URL, "BCBSTX")}) · {_a(BTX_PAR, "file dated September 14, 2026")}</div>'),
]
FACT2 = {
    'start-here/index.html': COLON_ROWS + [
        ("at Texas Health Presbyterian Hospital Allen, from each insurer's own September 2026 file:",
         "at Texas Health Presbyterian Hospital Allen, from each insurer's own rate file (files dated September 1 to 15, 2026):"),
        ("Facility fee only; the doctor and anesthesia bill separately. Full list and sources on the",
         "Facility fee only; the doctor and anesthesia bill separately. Each row links to its file. More on the"),
    ],
    'price-file-watch/index.html': COLON_ROWS + [
        ("This is the hospital's standard rate for the full procedure, from each insurer's September 2026 file.",
         "This is the hospital's standard rate for the full procedure, from each insurer's own rate file (dated September 1 to 15, 2026)."),
        ('<div class="who">Gainesville, just north of the DFW metro</div>',
         '<div class="who">Gainesville, outside the DFW metro (inside our DFW area, which goes by ZIP code)</div>'),
    ],
    'index.html': [
        ("a.innerHTML='Word is, Blue Cross Blue Shield of Texas (ParPlan) pays the most: <b>$6,702.28</b>, which is 7.05× Medicare\\'s $950.10. Aetna pays the least: $771.06.<br><br>RECEIPT: Texas Health Presbyterian Allen price file, checked Sept 29, 2026.<br><br><i>This demo answers one question. The real Chargemaster will answer from all 33 million rates.</i>';",
         "a.innerHTML='Word is, UnitedHealthcare (Choice Plus) pays the most: <b>$3,185.00</b>, which is 3.35× Medicare\\'s national rate of $950.10 (before local adjustment). Aetna pays the least: $771.06.<br><br>RECEIPT: each insurer\\'s own rate file for Texas Health Presbyterian Hospital Allen, dated September 1 to 15, 2026.<br><br><i>This demo answers one question. The real Chargemaster will answer from all 33 million rates.</i>';"),
        ('"spread": 8.7, "hosp": "Texas Health Presbyterian Hospital Allen"', '"spread": 4.1, "hosp": "Texas Health Presbyterian Hospital Allen"'),
        ('[["Aetna", "", 771.06, null], ["UnitedHealthcare", "Choice Plus", 3185.0, null], ["Blue Cross Blue Shield of Texas", "ParPlan", 6702.28, null]]',
         '[["Aetna", "", 771.06, null], ["Blue Cross Blue Shield of Texas", "Blue Choice PPO", 2099.14, null], ["UnitedHealthcare", "Choice Plus", 3185.0, null]], '
         f'"srcs": [["Aetna PPO file, Sept 5, 2026", "{AET}"], ["BCBSTX Blue Choice PPO file, Sept 15, 2026", "{BTX_PPO}"], ["UHC Choice Plus file, Sept 1, 2026", "{UHC_CP}"]]'),
        ("straight from the hospital's own price file. Same hospital, same procedure.`",
         "${r.srcs?'from each insurer’s own rate file':'straight from the hospital’s own price file'}. Same hospital, same procedure.`"),
        ("document.getElementById('rs').innerHTML=`SOURCE: ${r.hosp}, federally required standard charges file",
         "document.getElementById('rs').innerHTML=r.srcs?`SOURCE: each insurer’s own rate file: ${r.srcs.map(x=>`<a href=\"${x[1]}\" target=\"_blank\" rel=\"noopener\">${x[0]} ↗</a>`).join(' · ')}<br>MEDICARE: CMS hospital outpatient national rate, July 2026, before local adjustment`:`SOURCE: ${r.hosp}, federally required standard charges file"),
    ],
    'methodology/index.html': [
        ("We save a copy of every original file we use and send copies to the Internet Archive, so any price can be traced back to the exact file it came from, even after the source changes.",
         "We keep a copy of every original file we use, so any price can be traced back to the exact file it came from, even after the source changes. "
         "Hospital price files also go to the Internet Archive, one collection per state per month "
         "(<a href=\"https://archive.org/search?query=upfront-hospital-price-files\" target=\"_blank\" rel=\"noopener\">see them there</a>). "
         "Insurer files are too large for that and stay in our own storage."),
        ("<tr><td>El Paso</td><td>798–799</td></tr>\n</tbody></table></div>",
         "<tr><td>El Paso</td><td>798–799</td></tr>\n</tbody></table></div>\n"
         "<p>Our Dallas–Fort Worth area, drawn by ZIP code, is wider than the Census Bureau's Dallas–Fort Worth–Arlington metro area "
         f"(11 counties: Collin, Dallas, Denton, Ellis, Hunt, Kaufman, Rockwall, Johnson, Parker, Tarrant and Wise; {_a(CENSUS_DELIN, 'Census delineation files')}). "
         "Places outside those counties, such as Gainesville, Sherman, Corsicana or Granbury, stay on the DFW pages and are tagged “outside the DFW metro.”</p>"),
        ("<h2>Hospital stays compared with Medicare</h2>", """<h2 id="medicare-local">How Medicare adjusts for local costs</h2>
<p>Medicare sets one national rate for each service, then adjusts it for local costs, mostly wages. Our pages show facility fees at the national rate so every hospital and surgery center is compared on the same footing. The amount Medicare actually pays a given place can be a little higher or lower.</p>
<ul>
<li><strong>Hospital outpatient (most procedures, scans and tests at a hospital):</strong> 60% of the national rate is treated as labor cost and multiplied by the hospital's area wage index; the other 40% isn't adjusted (CMS, calendar year 2026 hospital outpatient rule; """ + _a('https://www.team-iha.org/getmedia/0ac1a3dd-fdba-4a75-b218-1801387c9720/CY-2026-Medicare-OPPS-FR-Rule-Summary.pdf?ext=.pdf', 'rule summary') + """; national rates: """ + _a(OPPS_B, 'Addendum B') + """).</li>
<li><strong>Surgery centers:</strong> half of the payment is treated as labor cost and adjusted by the same wage index (""" + _a('https://www.medpac.gov/wp-content/uploads/2026/10/MedPAC_Payment_Basics_26_ASC_FINAL_SEC.pdf', 'MedPAC, Ambulatory surgical center payment basics') + """).</li>
<li><strong>Doctors (Physician Fee Schedule):</strong> each part of a doctor's fee (the doctor's work, the practice's costs, malpractice insurance) is multiplied by its own local index for the Medicare payment locality. In Texas, Dallas County is the "Dallas" locality and Tarrant County is "Fort Worth"; every other county around them, including Collin and Denton, is "Rest of Texas." For 2026 the indexes are 1.009, 0.996 and 0.858 for Dallas, 1.009, 0.986 and 0.871 for Fort Worth, and 1.000, 0.949 and 0.903 for Rest of Texas (CMS 2026 fee schedule files, """ + _a('https://www.cms.gov/medicare/payment/fee-schedules/physician', 'RVU26D, Addendum E') + """). Our doctor-fee figures for Dallas–Fort Worth use the Dallas locality.</li>
<li><strong>Hospital stays:</strong> 66% of the base rate is adjusted by the hospital's wage index when that index is above 1, and 62% when it isn't (CMS fiscal year 2027 inpatient rule, """ + _a('https://www.cms.gov/files/zip/fy2027-ipps-fr-table-1a-1e.zip', 'Tables 1A–1B') + """). Our hospital-stay comparison already uses each hospital's own amount, as described below.</li>
<li><strong>Lab tests:</strong> Medicare's lab fee schedule is one national payment limit, with no local adjustment.</li>
</ul>
<h2>Hospital stays compared with Medicare</h2>"""),
    ],
}
ER_NAMES = [('Emergency room visit (minor)', 'Emergency room visit (straightforward)'),
            ('Emergency room visit (low severity)', 'Emergency room visit (low complexity)'),
            ('Emergency room visit (moderately severe)', 'Emergency room visit (moderate complexity)'),
            ('Emergency room visit (high severity)', 'Emergency room visit (high complexity)')]


def fact2(rel):
    def fn(s):
        for a, b in FACT2.get(rel, []):
            ins = b.replace(a, '', 1) if a in b else ''
            while ins and ins + ins in s:   # undo earlier double inserts (before Oct 18 this ran on every pass)
                s = s.replace(ins + ins, ins)
            while ins and len(ins) > 40 and s.count(ins) > 1:   # copies not side by side (another section landed between)
                j = s.rfind(ins); s = s[:j] + s[j + len(ins):]
            if b not in s:          # idempotent: some replacements contain their own search text
                s = s.replace(a, b)
        while s.count('<h2 id="medicare-local">') > 1:   # a later copy (older wording) after the per-hospital section: drop it
            i = s.find('<h2 id="medicare-local">', s.find('<h2 id="medicare-local">') + 5)
            k = s.find('<h2', i + 5)
            s = s[:i] + s[k:]
        return s
    return fn


def er_names(s):
    for a, b in ER_NAMES:
        s = s.replace(a, b)
    return s

# Oct 18: Betsy's Oct 16 drafted Price File Watch entries (project doc claude/price-file-watch-drafts-oct16.md) go into the
# password-only notes (functions/api/watch-notes.js), outside the bot's PLACEHOLDERS block, until she approves the wording.
DRAFTS_OCT16 = """
<h3>Drafted October 16: waiting for your OK before they go public</h3>
<p class="sub">Each finding was checked against the insurer's own file or link on October 16, 2026. Approve the wording and the entry moves to the public page.</p>
<div class="item"><div>
  <h4>Community Health Choice (Texas marketplace)</h4>
  <div class="who">Files cut off partway</div>
  <p>Six of its nine marketplace rate files stop at exactly 128,000 bytes, partway through the data, so no program can read them: Premier Bronze, Silver and Gold, and Limited Network Bronze, Silver and Gold. Our bot failed on all six, three tries each. The three Ultra Select files arrive whole but are only about 65 KB.</p>
  <div class="ev">Source: na1.ai.dm-us.informaticacloud.com/active-bpel/public/rt/aFX3KczjLiVkdXv6DLHUy6/p_price_transparency_inr_premier_bronze (and the others in the same family). Checked October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
<div class="item"><div>
  <h4>Molina (Texas marketplace)</h4>
  <div class="who">Links lead to an error page (update to the public entry)</div>
  <p>All 47 rate-file links Molina lists for Texas return a page titled "Error Page" instead of a file. Example: molinamarketplace.com/PricingTransparency/263574/TX/INN/innetwork-G-GMZCT24818.json</p>
  <div class="ev">Checked again October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
<div class="item"><div>
  <h4>Highmark Blue Cross Blue Shield of Western New York</h4>
  <div class="who">Main PPO file is empty</div>
  <p>Network 301_71A0, listed in Anthem's national index for about 132,000 employer plan groups, is under 1 KB. So are 301_71B0 and 301_71I0. The Highmark Blue Shield of Northeastern NY files 800_72A0 and 800_72B0 also show 0.0 GB and still need a direct check.</p>
  <div class="ev">Anthem's October index, checked October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
<div class="item"><div>
  <h4>Other empty files (under 1 KB, Anthem's October index)</h4>
  <div class="who">Highmark BCBS Delaware · Highmark PA · Anthem California</div>
  <p>Highmark BCBS Delaware Blue Classic (070_09D0), Highmark PA National Performance Blue (378_49T0), and Anthem California CA_ELRKMEDELRK and CA_ENKHMEDENKH.</p>
  <div class="ev">Checked October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
<div class="item"><div>
  <h4>Aetna: 13 self-funded employer files whose links don't answer</h4>
  <div class="who">October list</div>
  <p>For example pl-184-tr25, pl-1az-tr25 and pl-2t9-tr25. Details in the Aetna catalog's watch.csv in R2 (bot/catalog/aetna/2026-10/).</p>
  <div class="ev">Checked October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
<div class="item"><div>
  <h4>UnitedHealthcare: one listed file that doesn't answer</h4>
  <div class="who">"uc", posted by Alliance Comprehensive Network</div>
  <p>The full list will be in the UHC catalog's watch.csv once the full run finishes.</p>
  <div class="ev">Checked October 16, 2026.</div>
</div><span class="stamp s-note">Draft</span></div>
"""


def patch_watch_notes(s):
    if 'Drafted October 16: waiting for your OK' in s or '<!-- PLACEHOLDERS:END -->' not in s:
        return s
    return s.replace('<!-- PLACEHOLDERS:END -->', '<!-- PLACEHOLDERS:END -->\n' + DRAFTS_OCT16, 1)


# Oct 18: Betsy's answers. Contact address corrections@files.healthcare (Email Routing to be switched on in Cloudflare);
# the Price File Watch right-of-reply promise made true (nobody has been emailed yet); filled placeholders she approved.
MAIL = 'corrections@files.healthcare'
LEGAL_DATE = 'October 18, 2026'
LEGAL = {
    'disclaimers/index.html': [('Last updated: [date]', 'Last updated: ' + LEGAL_DATE), ('[corrections@domain]', '<a href="mailto:' + MAIL + '">' + MAIL + '</a>'),
                               ('usually within [X] business days', 'usually within 10 business days')],
    'corrections/index.html': [('Last updated: October 12, 2026', 'Last updated: ' + LEGAL_DATE), ('[corrections@domain]', '<a href="mailto:' + MAIL + '">' + MAIL + '</a>'),
                               ('usually within [5] business days', 'usually within 10 business days'),
                               ("re-check it within [10] business days", "re-check it within 10 business days")],
    'methodology/index.html': [('Before an entry goes up, we email the organization and give them [10] business days to respond, and we post their reply if they send one.',
                                'Before this page goes public, we will email every organization named on it, give each one 10 business days to respond, '
                                'and post any reply in full next to its entry. As of October 18, 2026, no organization has been contacted yet: '
                                'the page is a private preview and not open to the public.')],
    'accessibility/index.html': [('[accessibility@domain]', '<a href="mailto:' + MAIL + '">' + MAIL + '</a>')],
    'privacy/index.html': [('[privacy@domain]', '<a href="mailto:' + MAIL + '">' + MAIL + '</a>')],
    'terms/index.html': [('[legal@domain]', '<a href="mailto:' + MAIL + '">' + MAIL + '</a>'), ('use of [domain] and', 'use of files.healthcare and'),
                         ('Our [Disclaimers] page', 'Our <a href="/disclaimers/">Disclaimers</a> page')],
}


def legal(rel):
    def f(s):
        for a, b in LEGAL[rel]:
            s = s.replace(a, b)
        return s
    return f


ML_JS = '\n/*uxML*/\nvar UXML = null;\ntry { fetch(\'ml.json\').then(function (r) { return r.ok ? r.json() : null; }).then(function (j) { UXML = j; var el = document.getElementById(\'uxML\'); if (el && el.dataset.code) el.innerHTML = mlHTML(el.dataset.code); }).catch(function () {}); } catch (e) {}\nfunction mlHTML(code) {\n  if (!UXML || !UXML.r) return \'\';\n  var m = D.med.codes[code]; if (!m) return \'\';\n  var out = [];\n  [[\'H\', \'opps\', 0.6, \'Hospital outpatient facility fee\', \'hospitals\'], [\'A\', \'asc\', 0.5, \'Surgery center facility fee\', \'surgery centers\']].forEach(function (x) {\n    var r = UXML.r[x[0]]; if (!r || !m[x[1]]) return;\n    var nat = m[x[1]][0], sh = x[2], lo = Math.round(nat * (sh * r[0] + 1 - sh) * 100) / 100, hi = Math.round(nat * (sh * r[1] + 1 - sh) * 100) / 100;\n    out.push(\'<div class="pline"><div class="who"><b>\' + x[3] + \', after local adjustment</b><div class="meta">at the \' + r[2] + \' \' + x[4] +\n      \' in this area we matched to their Medicare records · our calculation from the national rate and each place’s FY2026 wage index · <a href="/methodology/#medicare-local">how</a></div></div>\' +\n      \'<span class="lead"></span><div class="right"><span class="price">\' + (lo === hi ? money(lo) : money(lo) + \'–\' + money(hi)) + \'</span></div></div>\');\n  });\n  return out.join(\'\');\n}\nfunction mlLocal(code) { return \'<div id="uxML" data-code="\' + code + \'">\' + mlHTML(code) + \'</div>\'; }\n/*/uxML*/\n'


def patch_pf_ml(s):
    """Price Finder: Medicare's facility rate range after the local wage adjustment (site/med_local.py; ml.json next to the page)."""
    if '/*uxML*/' in s or 'function medBlock(code) {' not in s:
        return s
    s = s.replace('function medBlock(code) {', ML_JS + 'function medBlock(code) {', 1)
    return re.sub(r"(L\.map\(\(\[a, b, v, k\]\) => `<div class=\"pline\">.*?`\)\.join\(''\))(;\n\})", r"\1 + mlLocal(code)\2", s, count=1, flags=re.S)


def write_ml(d):
    """ml.json next to each Price Finder page: the range of local Medicare factors for the area's matched hospitals and surgery centers."""
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    if not all(E.values()):
        return 0
    import boto3
    s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
    B = E['R2_BUCKET']
    try:
        ML = json.loads(s3.get_object(Bucket=B, Key='site/med_local/2026.json')['Body'].read())['npi']
    except Exception:
        return 0
    site, n = os.path.join(d, 'site'), 0
    for a in json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8')):
        page = os.path.join(site, a['path'].strip('/'), 'index.html')
        if not os.path.isfile(page):
            continue
        try:
            if a['slug'] == 'dfw':
                root = 'site/every/' + s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip() + '/'
            else:
                fn = os.path.join(d, 'functions', a['slug'], 'price-finder', 'pf', 't', '[code].js')
                root = re.search(r'PREFIX = "([^"]+)"', open(fn, encoding='utf-8').read()).group(1)
                root = root[:-2] if root.endswith('t/') else root
            npis = json.loads(s3.get_object(Bucket=B, Key=root + 'npis.json')['Body'].read())
            t = open(page, encoding='utf-8').read()
            i = t.find('id="data"')
            fac = json.loads(t[t.find('>', i) + 1:t.find('</script>', i)])['fac']
        except Exception:
            continue
        if len(fac) != len(npis):
            continue
        r = {}
        for f, npi in zip(fac, npis):
            m = ML.get(npi)
            kd = 'H' if f[2] == 'A' and re.search(r'\bhospital\b', f[0], re.I) else f[2]
            if m and m[0] == kd:
                x = r.setdefault(kd, [m[1], m[1], 0])
                x[0], x[1], x[2] = min(x[0], m[1]), max(x[1], m[1]), x[2] + 1
        if r:
            open(os.path.join(os.path.dirname(page), 'ml.json'), 'w').write(json.dumps({'r': r, 'src': 'site/med_local.py'}))
            n += 1
    return n


METHOD_ML = '<h3 id="medicare-each-place">Medicare\'s rate for each hospital and surgery center</h3>\n<p>Next to each hospital and surgery center on our procedure pages, and as a range on each Price Finder, we show what Medicare\'s facility rate comes to for that place after this local adjustment. These are our calculations from CMS\'s own numbers, not amounts CMS publishes for each place:</p>\n<ul>\n<li><strong>Hospitals:</strong> national hospital outpatient rate × (0.60 × the hospital\'s wage index + 0.40). The calendar-2026 outpatient rule uses the fiscal-2026 inpatient wage index, including reclassifications, so we take each hospital\'s "FY 2026 Wage Index" from CMS\'s <a href="https://www.cms.gov/files/zip/fy2026-ipps-fr-impact-file.zip" target="_blank" rel="noopener">FY 2026 IPPS final rule impact file ↗</a>.</li>\n<li><strong>Surgery centers:</strong> national surgery-center rate × (0.50 × wage index + 0.50), using the hospital wage index for the metro area where the center is, before floors and reclassifications (<a href="https://www.cms.gov/files/zip/fy2026-ipps-fr-tables-2-3-4a-4b.zip" target="_blank" rel="noopener">FY 2026 IPPS Table 3 ↗</a>).</li>\n<li><strong>Matching a place to its Medicare record:</strong> the provider\'s practice address in the federal NPI registry and the facility\'s address in CMS\'s <a href="https://data.cms.gov/sites/default/files/2026-10/e5a8afbb-a1f4-4d3b-bdb9-3968e194da0e/Hospital_and_other.DATA.Q3_2026.csv" target="_blank" rel="noopener">Provider of Services file ↗</a> (Q3 2026) must share the ZIP code, street number and street name. When there\'s no match, or more than one facility at that address with different wage indexes, we show only the national rate. Critical access hospitals and others Medicare pays on their own costs have no figure.</li>\n<li><strong>Check:</strong> for six Dallas–Fort Worth hospitals (Baylor University Medical Center, Methodist Dallas, Baylor Grapevine, Granbury, PRHC Ennis, Nocona), the wage index we use matches CMS\'s separate Table 2 of the same rule, including Granbury\'s and Grapevine\'s out-migration adjustments.</li>\n<li>Doctor fees stay at the locality shown on each page (Dallas for Dallas–Fort Worth); we don\'t yet compute them doctor by doctor.</li>\n</ul>\n'


def patch_method_ml(s):
    if 'id="medicare-each-place"' in s or 'id="medicare-local"' not in s:
        return s
    i = s.find('id="medicare-local"')
    j = s.find('</ul>', i)
    return s[:j + 5] + '\n' + METHOD_ML + s[j + 5:] if j > 0 else s


def unwrap(u):  # same as bot/discover.py unwrap (kept here so this script needs no bot packages)
    import urllib.parse
    m = re.match(r"(?i)^https?://linkprotect\.cudasvc\.com/url\?a=([^&]+)", u)
    if m:
        return urllib.parse.unquote(m.group(1))
    m = re.match(r"(?i)^https?://urldefense\.com/v3/__(.+?)__;", u)
    if m:
        return m.group(1)
    m = re.match(r"(?i)^https?://[a-z0-9.]*safelinks\.protection\.outlook\.com/\?url=([^&]+)", u)
    return urllib.parse.unquote(m.group(1)) if m else u


WRAP = re.compile(r'(href=)?"(https?://(?:linkprotect\.cudasvc\.com/url\?a=|urldefense\.com/v3/__|[a-z0-9.]*safelinks\.protection\.outlook\.com/\?url=)[^"]+)"', re.I)


def unwrap_links(s):
    """Email-security wrappers around a hospital's file link (in links and in Price Finder data)."""
    if 'cudasvc.com' not in s and 'urldefense.com' not in s and 'safelinks.protection' not in s:
        return s
    def rep(m):
        if m.group(1):
            return 'href="' + html.escape(unwrap(html.unescape(m.group(2))), quote=True) + '"'
        return '"' + unwrap(m.group(2)) + '"'
    return WRAP.sub(rep, s)


def misc_fixes(s):
    """Oct 18 pre-launch fixes that apply to any page: unwrapped file links, full procedure footer, deductible wording,
    a name for the phone search button."""
    s = unwrap_links(s)
    s = s.replace('<a href="/privacy/">Privacy</a></span></div></footer>',
                  '<a href="/privacy/">Privacy</a> · <a href="/terms/">Terms</a> · <a href="/accessibility/">Accessibility</a></span></div></footer>')
    s = s.replace('Until then, the negotiated rate is your bill.',
                  'Until then, you usually pay the negotiated rate (some care, like preventive screenings, is covered before the deductible).')
    return s.replace('class="sbtn" aria-expanded', 'class="sbtn" aria-label="Search" aria-expanded')


def write_sitemap(site):
    """Oct 18 pre-launch: /sitemap.xml = index of /sitemap-pages.xml (every page outside /costs/) and /costs/sitemap.xml
    (written by procedure_pages.py). robots.txt keeps blocking crawlers until launch."""
    from datetime import date
    urls = []
    for root, _, fs in os.walk(site):
        if 'index.html' not in fs:
            continue
        rel = os.path.relpath(root, site).replace(os.sep, '/')
        if rel.split('/')[0] in ('costs', 'control', 'v2', 'looks') :
            continue
        urls.append('https://files.healthcare/' + ('' if rel == '.' else rel + '/'))
    urls.sort(key=lambda u: (u.count('/'), u))
    today = date.today().isoformat()
    open(os.path.join(site, 'sitemap-pages.xml'), 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + ''.join(f'<url><loc>{u}</loc><lastmod>{today}</lastmod></url>\n' for u in urls) + '</urlset>\n')
    idx = ['https://files.healthcare/sitemap-pages.xml']
    if os.path.isfile(os.path.join(site, 'costs', 'sitemap.xml')):
        idx.append('https://files.healthcare/costs/sitemap.xml')
    open(os.path.join(site, 'sitemap.xml'), 'w', encoding='utf-8').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + ''.join(f'<sitemap><loc>{u}</loc><lastmod>{today}</lastmod></sitemap>\n' for u in idx) + '</sitemapindex>\n')
    return len(urls)


def run(d):
    site = os.path.join(d, 'site')
    done = []
    def edit(rel, fn):
        p = os.path.join(site, rel)
        s = open(p, encoding='utf-8').read()
        t = fn(s)
        if t != s:
            open(p, 'w', encoding='utf-8').write(t)
            done.append(rel)
    edit('index.html', patch_home)
    edit('start-here/index.html', patch_start)
    edit('plan-calculator/index.html', patch_calc)
    edit('price-file-watch/index.html', patch_watch)
    edit('looks/looks.css', patch_looks_css)
    edit('looks/looks.css', patch_units_css)
    edit('looks/looks.js', patch_looks_js)
    edit('start-here/index.html', patch_start_band)
    edit('index.html', patch_home_hero)
    edit('disclaimers/index.html', patch_disclaimers)
    edit('methodology/index.html', patch_method)
    edit('methodology/index.html', patch_method_ml)
    for rel in FACT:
        if os.path.isfile(os.path.join(site, rel)):
            edit(rel, fact(rel))
    edit('disclaimers/index.html', renumber_disclaimers)
    for rel in LEGAL:
        if os.path.isfile(os.path.join(site, rel)):
            edit(rel, legal(rel))
    for rel in FACT2:
        if os.path.isfile(os.path.join(site, rel)):
            edit(rel, fact2(rel))
    for rel in ('surprise-bills/index.html', 'employer-plans/index.html', 'insurers/index.html', 'plan-calculator/index.html', 'price-file-watch/index.html'):
        if os.path.isfile(os.path.join(site, rel)):
            edit(rel, add_trust)
    nf = os.path.join(site, '404.html')
    if not os.path.isfile(nf) or 'href="/hospitals/">Hospitals' not in open(nf, encoding='utf-8').read():
        open(nf, 'w', encoding='utf-8').write(NOT_FOUND); done.append('404.html')
    wn = os.path.join(d, 'functions', 'api', 'watch-notes.js')
    if os.path.isfile(wn):
        t0 = open(wn, encoding='utf-8').read(); t1 = patch_watch_notes(t0)
        if t1 != t0:
            open(wn, 'w', encoding='utf-8').write(t1); done.append('functions/api/watch-notes.js')
    mw = os.path.join(d, 'functions', '_middleware.js')
    t0 = open(mw, encoding='utf-8').read(); t1 = patch_mw(t0)
    if t1 != t0:
        open(mw, 'w', encoding='utf-8').write(t1); done.append('functions/_middleware.js')
    for root, _, fs in os.walk(site):
        if 'index.html' not in fs or os.sep + 'costs' in root:
            continue
        rel = os.path.relpath(os.path.join(root, 'index.html'), site)
        if root.endswith('price-finder'):
            edit(rel, lambda x: patch_pf_ml(er_names(fact_pf(patch_pf(x)))))
        elif rel not in ('index.html', 'start-here/index.html', 'plan-calculator/index.html', 'price-file-watch/index.html'):
            edit(rel, patch_nav)
    print(f'local Medicare ranges written for {write_ml(d)} Price Finder pages')
    # Oct 18 pre-launch: unwrap email-security link wrappers and give every page its missing basics
    # (canonical, share tags, favicon, site-information links). Hospital pages have their own generator.
    nw = 0
    for root, _, fs in os.walk(site):
        for f in fs:
            if f.endswith('.html'):
                pth = os.path.join(root, f); t0 = open(pth, encoding='utf-8').read()
                t1 = misc_fixes(t0)
                if t1 != t0:
                    open(pth, 'w', encoding='utf-8').write(t1); nw += 1
    print(f'sitemap: {write_sitemap(site)} pages listed outside /costs/')
    print(f'{nw} pages had wrapped links or the old costs footer fixed; {page_meta.run(site, skip=("hospitals/",))} pages given missing page basics')
    print(f'{len(done)} pages changed:', ', '.join(sorted(done)[:12]), '...' if len(done) > 12 else '')


def run_r2():
    import boto3
    E = {k: ''.join(os.environ.get(k, '').split()) for k in ('R2_ACCOUNT_ID', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')}
    s3 = boto3.client('s3', endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E['R2_ACCESS_KEY_ID'],
                      aws_secret_access_key=E['R2_SECRET_ACCESS_KEY'], region_name='auto')
    B = E['R2_BUCKET']
    keys = ['site/deploy/price-finder.html'] + [o['Key'] for pg in s3.get_paginator('list_objects_v2').paginate(Bucket=B, Prefix='site/deploy/cities/')
                                               for o in pg.get('Contents', []) if o['Key'].endswith('/price-finder.html')]
    n = 0
    for k in keys:
        s = s3.get_object(Bucket=B, Key=k)['Body'].read().decode('utf-8')
        t = page_meta.normalize(misc_fixes(patch_pf_ml(er_names(fact_pf(patch_pf(s))))), k.split('site/deploy/', 1)[-1].replace('price-finder.html', 'price-finder/index.html'))
        if t != s:
            s3.put_object(Bucket=B, Key=k, Body=t.encode('utf-8'), ContentType='text/html; charset=utf-8')
            n += 1
    print(f'{n} of {len(keys)} R2 Price Finder layouts patched')


if __name__ == '__main__':
    if sys.argv[1] == '--r2':
        run_r2()
    else:
        run(sys.argv[1])
