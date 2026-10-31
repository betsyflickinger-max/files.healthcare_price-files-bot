"""V2 Redesign pages (Oct 31, 2026). Writes the V2 journey into SITE/v2/: home, results, provider receipt, plan
calculator and the "not ready yet" page. Page logic is v2/v2.js; data comes from the same files the Original reads.

  python site/redesign/v2_pages.py SITE      (SITE = the folder that holds index.html)
"""
import html
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
E = html.escape
TAGLINE = 'The receipt for the U.S. healthcare system.'
NAV = [('find', 'Find prices', '/v2/price-finder/'), ('costs', 'My costs', '/v2/plan-calculator/'),
       ('files', 'Explore the files', '/v2/#files'), ('how', 'How it works', '/v2/not-ready/?from=%2Fstart-here%2F')]
FOOT = [('About', '/about/'), ('Methodology', '/methodology/'), ('Corrections', '/corrections/'), ('Disclaimers', '/disclaimers/'),
        ('Privacy', '/privacy/'), ('Terms', '/terms/'), ('Accessibility', '/accessibility/'), ('Copyright', '/copyright/')]
HEAD_SCRIPTS = ('<link rel="stylesheet" href="/shared/version-switch.css"><script src="/shared/hcf-data.js"></script>'
                '<script src="/shared/version-switch.js" defer></script>')


def shell(page, title, desc, body, cur='', extra_head=''):
    ac = ' aria-current="page"'
    nav = ''.join(f'<li><a href="{u}"{ac if k == cur else ""}>{E(t)}</a></li>' for k, t, u in NAV)
    foot = ''.join(f'<li><a href="{u}">{E(t)}</a></li>' for t, u in FOOT)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc)}"><meta name="robots" content="noindex,nofollow">
<link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="stylesheet" href="/v2/v2.css">{HEAD_SCRIPTS}{extra_head}
</head><body data-page="{page}">
<a class="skip" href="#main">Skip to content</a>
<header class="mast"><div class="wrap"><a class="brand" href="/v2/">The Healthcare <span>Files</span></a>
<nav aria-label="Main"><ul>{nav}</ul></nav></div></header>
<main id="main">{body}</main>
<footer class="foot"><div class="wrap"><p><b>The Healthcare Files</b> · {E(TAGLINE)} Free. No ads. Every price links to its source.</p>
<ul>{foot}</ul><p>Footer pages open in the Original design; their V2 versions aren’t built yet. This is a private preview of the V2 Redesign, with the same data as the Original site.</p></div></footer>
<script src="/v2/v2.js" defer></script></body></html>
'''


ICON_LIST = '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>'
ICON_SHIELD = '<svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/></svg>'

POPULAR = [('73721', 'Knee MRI'), ('45378', 'Colonoscopy'), ('66984', 'Cataract surgery'), ('70450', 'CT scan of the head'),
           ('47562', 'Gallbladder removal'), ('59510', 'C-section'), ('29881', 'Knee arthroscopy'), ('77067', 'Screening mammogram')]

# the file drawer: five colored folders (Prices, My plan, Hospitals, Insurers, Check our work). A V2 page where one is built;
# otherwise the "not ready yet" page, which offers the Original page.
NR = lambda p: '/v2/not-ready/?from=' + p.replace('/', '%2F')
FOLDERS = [('Prices', '#2E5BE6', '#FFFFFF', '/v2/price-finder/', 'Search prices by procedure and place', True, 66),
           ('My plan', '#F7C925', '#151515', '/v2/plan-calculator/', 'Estimate your share on a marketplace plan or your own', True, 62),
           ('Hospitals', '#F08A24', '#151515', NR('/hospitals/'), 'Ownership, prices and price files, hospital by hospital', False, 60),
           ('Insurers', '#3DB86B', '#151515', NR('/insurers/'), 'Parent companies, brands and networks', False, 58),
           ('Check our work', '#E6402E', '#FFFFFF', NR('/price-file-watch/'), 'Who publishes usable price files, and our sources', False, 60)]
MORE = [('Employers', '#3DB86B', NR('/employer-plans/'), 'Find your employer plan, its carrier and network'),
        ('Surprise-bill research', '#E6402E', NR('/surprise-bills/'), 'Federal arbitration of out-of-network bills'),
        ('Price file watch', '#E6402E', NR('/price-file-watch/'), 'Which hospitals and insurers post usable files'),
        ('The story, in 8 steps', '#2E5BE6', NR('/story/'), 'What a colonoscopy costs in Dallas–Fort Worth'),
        ('Folder view', '#F7C925', '/folders/', 'The full filing cabinet: every section as a drawer of folders (opens the Original folder view)')]


def drawer():
    tabs = ''.join(f'<a class="ftab" href="{u}" style="--c:{c};--t:{t};--h:{h}px">{E(n)}</a>' for n, c, t, u, _, _, h in FOLDERS)
    rows = ''.join(f'<li><a href="{u}"><span class="sw" style="--c:{c}"></span><b>{E(n)}</b><span class="go" aria-hidden="true">→</span>'
                   f'<span class="d">{E(d)}{"" if ok else " · <span class=nr>Original page for now</span>"}</span></a></li>'
                   for n, c, _, u, d, ok, _ in FOLDERS)
    more = ''.join(f'<li><a href="{u}"><span class="sw" style="--c:{c}"></span><b>{E(n)}</b><span class="go" aria-hidden="true">→</span><span class="d">{E(d)}</span></a></li>'
                   for n, c, u, d in MORE)
    return f'''<section class="sec" id="files" aria-labelledby="filesH"><div class="wrap">
<h2 id="filesH">Follow the money. Open the files.</h2>
<p class="lede">Hospitals, insurers, employer plans and the price files themselves, for anyone who wants to dig deeper. Each folder tab and each line below goes to the same place.</p>
<div class="files"><div><div class="drawer"><nav class="tabs" aria-label="File drawer">{tabs}</nav>
<div class="box" aria-hidden="true"><div class="holder">The Healthcare<br>Files</div><div class="pull"></div></div></div></div>
<div><ul class="flist" aria-label="The files">{rows}</ul>
<ul class="flist" style="margin-top:12px" aria-label="More from the files">{more}</ul></div></div></div></section>'''


def home():
    pop = ''.join(f'<li><a href="/v2/price-finder/?code={c}" data-code="{c}">{E(n)}</a></li>' for c, n in POPULAR)
    body = f'''<section class="hero on-blue"><div class="wrap">
<p class="tagline">{E(TAGLINE)}</p>
<h1>What is this going to <em>cost me?</em></h1>
<p class="lede">Hospitals and insurers have to publish their prices. They’re in files too big to open. We opened them.</p>
<form class="search" id="hForm" role="search" aria-label="Find prices" novalidate>
<div class="fld cb"><label for="hProc">Procedure or billing code</label><input id="hProc" type="text" autocomplete="off" spellcheck="false" placeholder="e.g. knee MRI, colonoscopy" aria-describedby="hErr"><ul id="hProcList" hidden></ul></div>
<div class="fld"><label for="hArea">Where</label><select id="hArea"></select></div>
<button class="btn y" type="submit">Find prices →</button>
<p id="hErr" class="note warn" role="alert" hidden style="grid-column:1/-1;margin:0"></p></form>
<div class="tasks"><a class="task" href="/v2/price-finder/">{ICON_LIST}<span><b>Compare care prices</b><span>See real prices in your area, from the files.</span></span></a>
<a class="task" href="/v2/plan-calculator/">{ICON_SHIELD}<span><b>Understand my costs</b><span>Estimate your share with your plan’s numbers.</span></span></a></div>
<div class="pop"><h2>Popular searches</h2><ul class="chips" id="hPop">{pop}</ul></div>
</div></section>
<div class="trust"><div class="wrap"><ul><li>Free</li><li>No ads</li><li>Every price links to its source file</li><li>No one pays to be listed</li></ul></div></div>
<section class="sec" aria-labelledby="howH"><div class="wrap"><h2 id="howH">How it works</h2>
<ol class="steps"><li><b>Find the price</b><span class="muted">Search a procedure and a place. We show every published rate, lowest first.</span></li>
<li><b>Read the receipt</b><span class="muted">See what the price covers, who published it and when, and what may be billed separately.</span></li>
<li><b>Estimate your share</b><span class="muted">Put the rate through your plan’s deductible and coinsurance.</span></li></ol></div></section>
{drawer()}'''
    return shell('home', 'The Healthcare Files (V2 Redesign)', 'Real healthcare prices from the files hospitals and insurers have to publish.', body)


def results():
    body = '''<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/v2/">Find care</a></li><li><span id="crProc">Procedure</span></li><li aria-current="page">Results</li></ol></nav>
<div class="ph"><h1 id="rTitle">Find a price</h1><p class="where"><span id="rCode" class="mono"></span> · <span id="rWhere"></span></p></div>
<form class="qbar" id="qForm" role="search" aria-label="Edit search" style="margin-top:14px" novalidate>
<div class="fld cb"><label for="qProc">Procedure or billing code</label><input id="qProc" type="text" autocomplete="off" spellcheck="false"><ul id="qProcList" hidden></ul></div>
<div class="fld"><label for="qArea">Where</label><select id="qArea"></select></div>
<button class="btn k" type="submit">Update</button><p id="qErr" class="note warn" role="alert" hidden style="grid-column:1/-1;margin:0">Pick a procedure from the list.</p></form>
<p id="rStatus" class="loading" role="status"></p>
<div id="rBody" hidden>
<div class="ctrl"><div><span class="lab" id="payL">How are you paying?</span><div class="seg" id="paySeg" role="group" aria-labelledby="payL" style="display:grid;margin-top:4px">
<button type="button" data-pay="net">Insurance</button><button type="button" data-pay="cash">Cash</button><button type="button" data-pay="all">Not sure</button></div></div>
<div class="row"><div class="fld" id="netWrap"><label for="net">Your plan’s network</label><select id="net"></select><span class="hint">Networks we read for this area. We never assume one from an insurer’s name.</span></div>
<div><span class="lab" id="feeL">Which bill</span><div class="seg" id="feeSeg" role="group" aria-labelledby="feeL" style="display:grid;margin-top:4px"><button type="button" data-fee="fac">Facility fee</button><button type="button" data-fee="doc">Doctor’s fee</button></div></div></div></div>
<p class="meaning" id="rMeaning"></p>
<div class="bar"><p class="count" id="rCount" role="status" style="margin:0"></p>
<div class="views"><button type="button" class="btn" aria-pressed="true">List view</button><button type="button" class="btn" id="mapGo">Map view</button><button type="button" class="btn" id="csvGo">Download CSV</button></div></div>
<div class="note warn" id="mapNote" tabindex="-1" hidden>The map isn’t built in V2 yet. <a id="mapOrig" href="#">Open this search on the Original map</a> (same procedure, payment and network), or use the ZIP code filter below for distances.</div>
<div class="filters"><div class="fld"><label for="fKind">Kind of place</label><select id="fKind"><option value="">All</option><option value="H">Hospitals</option><option value="A">Surgery centers</option><option value="G">Practices, clinics, labs, imaging</option><option value="P">Individual clinicians</option></select></div>
<div class="fld"><label for="fZip">Near ZIP code</label><div style="display:flex;gap:6px"><input id="fZip" type="text" inputmode="numeric" maxlength="5" autocomplete="postal-code" style="max-width:120px"><button type="button" class="btn" id="fZipGo">Apply</button></div><span class="hint" id="fZipMsg" role="status"></span></div>
<div class="fld"><label for="fRad">Within</label><select id="fRad"><option value="10">10 miles</option><option value="25" selected>25 miles</option><option value="50">50 miles</option></select></div>
<div class="fld"><label for="fSort">Sort</label><select id="fSort"><option value="price">Lowest price</option><option value="near">Nearest (with a ZIP)</option></select></div></div>
<ul class="cards" id="rList" aria-label="Providers"></ul>
<button type="button" class="btn more" id="rMore" hidden></button>
<p style="margin:16px 0"><a class="btn y" id="rCalc" href="/v2/plan-calculator/">Estimate my share →</a></p>
<div id="rExtra"></div>
</div></div>
<div class="cmpbar" id="cmpBar" hidden><div class="wrap"><span><b id="cmpN">0 selected</b> <span id="cmpHint" class="small"></span></span>
<span style="display:flex;gap:8px;flex-wrap:wrap"><button type="button" class="btn" id="cmpClr">Clear</button><button type="button" class="btn k" id="cmpGo">Compare selected providers →</button></span></div></div>
<dialog class="cmp" id="cmpDlg" aria-labelledby="cmpH"><div class="hd"><h2 id="cmpH" style="margin:0;font-size:20px">Compare providers</h2><button type="button" class="btn" id="cmpX">Close</button></div>
<div class="bd" id="cmpBody"></div><p class="small muted" style="padding:0 18px 16px;margin:0">Prices can differ by place, kind of facility and what is included. None of these is your bill.</p></dialog>'''
    return shell('results', 'Find prices · The Healthcare Files (V2)', 'Every published price for a procedure in your area, lowest first, with its source.', body, cur='find')


def receipt():
    body = '''<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/v2/">Find care</a></li><li><a id="crProc" href="/v2/price-finder/">Procedure</a></li><li aria-current="page">Receipt</li></ol></nav>
<div class="ph"><p class="muted" style="margin:0"><a id="crBack" href="/v2/price-finder/">← Back to results</a></p><h1>Read the receipt</h1><p class="sub">One provider, one procedure: the price, what it covers, and where it comes from. <span id="crName" class="sr"></span></p></div>
<div id="rcBody"><p class="loading" role="status">Loading…</p></div></div>'''
    return shell('receipt', 'Receipt · The Healthcare Files (V2)', 'One provider’s published price for one procedure, with its source.', body, cur='find')


def calculator():
    body = '''<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="/v2/">Find care</a></li><li aria-current="page">Estimate my costs</li></ol></nav>
<div class="ph"><h1>Understand my costs</h1><p class="sub">Put a published rate through your plan’s deductible, copay and coinsurance. An estimate, not a quote.</p></div>
<div class="ctabs" role="tablist" aria-label="Kind of plan"><button role="tab" id="tMkt" aria-controls="pMkt">Marketplace plan</button><button role="tab" id="tOwn" aria-controls="pOwn">Employer plan</button><button role="tab" id="tMine" aria-controls="pMine">Enter my plan</button></div>
<section role="tabpanel" id="pMkt" aria-labelledby="tMkt"><p id="mStatus" class="loading" role="status">Loading marketplace plans…</p><div id="mCodeNote"></div>
<div id="mBody" hidden><div class="calc"><div class="inputs">
<div class="two"><div class="fld"><label for="mYear">Plan year</label><select id="mYear"></select></div><div class="fld"><label for="mIns">Insurer</label><select id="mIns"></select></div></div>
<div class="fld"><label for="mPlan">Plan</label><select id="mPlan"></select></div>
<div class="fld"><label for="mProc">Procedure</label><select id="mProc"></select></div>
<div class="fld"><label for="mPaid">Already paid toward your deductible this year</label><div style="display:flex;gap:6px;flex-wrap:wrap"><input id="mPaid" type="number" min="0" step="1" inputmode="decimal" style="max-width:160px" placeholder="0"><button type="button" class="btn" id="m0">None yet</button><button type="button" class="btn" id="mAll">All of it</button></div></div>
<div class="est" id="mTicket" aria-label="Plan numbers"></div><p class="small muted" id="mCount"></p></div>
<div><div class="est" id="mEst" role="status" aria-live="polite"></div></div></div>
<h2 id="mHead" style="font-size:20px;margin:0"></h2><div class="kinds" role="group" aria-label="Bill type"><button type="button" id="mkFac">Facility fees</button><button type="button" id="mkPro">Doctor fees</button></div>
<p id="mN" class="small" style="font-weight:700;margin:10px 0 0" role="status"></p><ul class="olist" id="mList"></ul><button type="button" class="btn more" id="mMore" hidden></button>
<details class="card" style="margin-top:16px"><summary><b>Assumptions</b></summary><p>Your share uses this plan’s own cost sharing for the kind of service, from its federal plan files. We use one-person amounts; on a family plan, what others have spent can lower your share. A per-day copay counts one day.</p></details>
<details class="card" style="margin-top:10px"><summary><b>What’s not included</b></summary><p>A facility fee usually doesn’t include the surgeon, anesthesia, pathology or follow-up visits. Each is a separate bill with its own share.</p></details></div></section>
<section role="tabpanel" id="pOwn" aria-labelledby="tOwn" hidden><div class="nr-box" style="margin:20px 0"><h2 style="margin:0 0 8px">Employer plans aren’t in V2 yet</h2>
<p>The Original calculator handles employer and other plans: look up your employer, read your Summary of Benefits (it stays in your browser), or enter your plan by hand.</p>
<div class="acts"><a class="btn k" id="ownOrig" href="/plan-calculator/#own">Open it in the Original design</a><button type="button" class="btn" onclick="document.getElementById('tMine').click()">Enter my plan here</button></div></div></section>
<section role="tabpanel" id="pMine" aria-labelledby="tMine" hidden><div class="calc"><div class="inputs">
<div class="fld"><label for="oRate">Negotiated rate for the service</label><input id="oRate" type="number" min="0" step="0.01" inputmode="decimal"><span class="hint" id="oRateSrc">Open a receipt and choose “Estimate my share” to bring its rate here, or type one.</span></div>
<div class="two"><div class="fld"><label for="oDed">Deductible left to meet</label><input id="oDed" type="number" min="0" step="1" inputmode="decimal"></div>
<div class="fld"><label for="oCo">Coinsurance after the deductible (%)</label><input id="oCo" type="number" min="0" max="100" step="1" inputmode="decimal"></div></div>
<div class="two"><div class="fld"><label for="oCp">Copay, if any</label><input id="oCp" type="number" min="0" step="1" inputmode="decimal"></div>
<div class="fld"><label for="oOop">Out-of-pocket max left (optional)</label><input id="oOop" type="number" min="0" step="1" inputmode="decimal"></div></div></div>
<div><div class="est" id="oEst" role="status" aria-live="polite"></div></div></div></section>
</div>'''
    return shell('calculator', 'Understand my costs · The Healthcare Files (V2)', 'Estimate your share of a published rate.', body, cur='costs',
                 extra_head='<script src="/shared/calc-core.js"></script>')


def not_ready():
    body = '''<div class="wrap"><div class="nr-box" role="region" aria-labelledby="nrH">
<h1 id="nrH">This page isn’t in V2 yet</h1>
<p>The V2 Redesign so far covers the main journey: the homepage, price results, a provider’s receipt and the plan calculator. <b id="nrWhat">This page</b> is still only in the Original design, with the same information.</p>
<div class="acts"><a class="btn k" id="nrOrig" href="/">Open the Original page</a><a class="btn" href="/v2/">V2 homepage</a><button type="button" class="btn" onclick="history.back()">Go back</button></div>
<p class="small muted" style="margin-top:16px">Nothing was lost: the Original page is the one this link points to, and you can switch back to V2 from the bar at the top.</p></div></div>
<script>(function(){var f=new URLSearchParams(location.search).get('from')||'/';if(!/^\\/(?!\\/)/.test(f))f='/';var a=document.getElementById('nrOrig');a.href=f;
var n={'/hospitals/':'Hospitals','/insurers/':'Insurers','/employer-plans/':'Employer plans','/price-file-watch/':'Price File Watch','/surprise-bills/':'Surprise bills','/story/':'The story','/start-here/':'Start here'};
var p=f.split(/[?#]/)[0];document.getElementById('nrWhat').textContent=n[p]?n[p]+' ('+p+')':'The page '+p;a.textContent='Open '+(n[p]||'the Original page');})();</script>'''
    return shell('notready', 'Not in V2 yet · The Healthcare Files', 'This page is only in the Original design for now.', body)


def write(site):
    v2 = os.path.join(site, 'v2')
    pages = {'': home(), 'price-finder/': results(), 'provider/': receipt(), 'plan-calculator/': calculator(), 'not-ready/': not_ready()}
    for sub, s in pages.items():
        os.makedirs(os.path.join(v2, sub), exist_ok=True)
        open(os.path.join(v2, sub, 'index.html'), 'w', encoding='utf-8').write(s)
    for f in ('v2.css', 'v2.js'):
        shutil.copyfile(os.path.join(HERE, 'v2', f), os.path.join(v2, f))
    return list(pages)


if __name__ == '__main__':
    print(write(sys.argv[1]))
