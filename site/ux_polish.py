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
  const after = () => { try { listFirst(); } catch (err) {} try { tidyIn(document.getElementById('patient')); tidyIn(document.getElementById('board')); tidyIn(document.getElementById('mapv')); } catch (err) {} };
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


def patch_pf(s):
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


def patch_looks_css(s):
    if '/* ux: start pill */' not in s:
        s += ('\n/* ux: start pill */html[data-look="hotline"]:not(#_) .start-pill{background:#45F0AE!important;color:#050807!important}\n')
    if '/* ux: phone */' in s:
        return s
    return s + ('\n/* ux: phone */@media(max-width:700px){.look-pick{left:auto;right:8px;bottom:8px;padding:4px 6px;gap:4px;font-size:12px;opacity:.9}'
                '.look-pick select{max-width:118px;min-height:28px;font-size:12px}}\n')


def patch_disclaimers(s):
    old = re.search(r'\[Choose one:\]\s*- \[(What It Costs does not currently accept payment[^\]]*)\]\s*- \[Some providers pay[^\]]*\]', s)
    return s.replace(old.group(0), old.group(1)) if old else s


def patch_method(s):
    old = ('Each price shows two dates: when the source says it was last updated, and when we last checked it. Prices more than 12 months old, '
           'or with no date in the source, carry an "Older price" flag.')
    new = ('Each hospital and insurer price shows the date its source file gives. Prices from files more than six months old, or from files '
           'with no date, are flagged. Posted cash prices show the date we last checked the provider\'s page.')
    return s.replace(old, new) if old in s else s


NOT_FOUND = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Page not found · What It Costs</title>
<style>body{margin:0;background:#f6f1e7;color:#231f1a;font:17px/1.6 "Public Sans",system-ui,sans-serif;padding:0 16px}main{max-width:640px;margin:12vh auto}
h1{font:600 40px/1.1 Georgia,serif;margin:0 0 12px}a{color:#9b3a2a}ul{padding-left:20px}</style></head><body><main>
<p style="font:700 13px monospace;letter-spacing:.12em;text-transform:uppercase;color:#9b3a2a">404</p><h1>We couldn't find that page</h1>
<p>The link may be old or mistyped. Try one of these:</p>
<ul><li><a href="/">Home</a></li><li><a href="/start-here/">Start here: how the site works</a></li><li><a href="/costs/">Look up a price</a></li><li><a href="/price-finder/">Price Finder (every billing code)</a></li></ul>
</main></body></html>
'''


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
    edit('disclaimers/index.html', patch_disclaimers)
    edit('methodology/index.html', patch_method)
    for rel in ('surprise-bills/index.html', 'employer-plans/index.html', 'insurers/index.html', 'plan-calculator/index.html', 'price-file-watch/index.html'):
        if os.path.isfile(os.path.join(site, rel)):
            edit(rel, add_trust)
    nf = os.path.join(site, '404.html')
    if not os.path.isfile(nf):
        open(nf, 'w', encoding='utf-8').write(NOT_FOUND); done.append('404.html')
    mw = os.path.join(d, 'functions', '_middleware.js')
    t0 = open(mw, encoding='utf-8').read(); t1 = patch_mw(t0)
    if t1 != t0:
        open(mw, 'w', encoding='utf-8').write(t1); done.append('functions/_middleware.js')
    for root, _, fs in os.walk(site):
        if 'index.html' not in fs or os.sep + 'costs' in root:
            continue
        rel = os.path.relpath(os.path.join(root, 'index.html'), site)
        if root.endswith('price-finder'):
            edit(rel, patch_pf)
        elif rel not in ('index.html', 'start-here/index.html', 'plan-calculator/index.html', 'price-file-watch/index.html'):
            edit(rel, patch_nav)
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
        t = patch_pf(s)
        if t != s:
            s3.put_object(Bucket=B, Key=k, Body=t.encode('utf-8'), ContentType='text/html; charset=utf-8')
            n += 1
    print(f'{n} of {len(keys)} R2 Price Finder layouts patched')


if __name__ == '__main__':
    if sys.argv[1] == '--r2':
        run_r2()
    else:
        run(sys.argv[1])
