"""Homepage, version 2 (Oct 18, 2026), at /v2/ beside the current homepage so Betsy can compare them.

Why: testers opened the homepage and either went straight to a price or drifted to the Start here guide and left. The old
front section explains the site for 7 phone screens before showing a single price. Version 2 leads with a real local
price gap, lets people try a one-tap guess, shows a slice of the actual price board, then offers three ways in.
Every figure comes from the same saved summaries the price pages use (R2 site/deploy/costs_state.json, written by
procedure_pages.py), so nothing is estimated and each price links to the file it came from.

It also adds the tester tracking that the page-view log was missing (taps on in-page receipts, the Chargemaster,
searches, how far people scroll, one optional "what were you hoping to find?" question). See patch_tracking().

  python site/home_v2.py build DIR        # DIR holds site/ and functions/ (e.g. from site_files.py pull DIR); needs costs_state.json in DIR
  python site/home_v2.py deploy           # pull the live site, write /v2/ + tracking, deploy, save back (skips if nothing changed)

Safe to run again: every step checks a marker first. The procedure-pages workflow runs `deploy` after its own deploy,
so /v2/ always shows the same figures as the price pages.
"""
import csv
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procedure_pages as pp   # noqa: E402
import story   # noqa: E402  (money, esc, slugs, area URLs: one set of rules for every page)

esc, money = pp.esc, pp.money
AREA = 'dfw'
HERO = '45378'                                   # colonoscopy: the site's default procedure (and the Mark Cuban email page)
GUESS = ['73721', '74177', '47562', '27447', '29881', '70551']   # knee MRI, CT, gallbladder, knee replacement, knee scope, brain MRI
V2_MARK = '<!-- HOME-V2 (written by price-files-bot site/home_v2.py; edits here are replaced on the next run) -->'


def nice_sig(v):
    """Round to two significant figures for guess choices ("about $4,200"). Never shown as a price."""
    if v < 100:
        return f'${round(v):,}'
    d = 10 ** (len(str(int(v))) - 2)
    return f'${int(round(v / d) * d):,}'


def low(t):
    """Lower-case a plain name for mid-sentence use, keeping acronyms (MRI, CT)."""
    return ' '.join(w if (len(w) > 1 and w[1].isupper()) or w.isupper() else w.lower() for w in t.split())


def plan_name(e):
    return f"{e['ins']} {e['plan']}".strip()


def src(e):
    return f'<a class="v2-src" href="{esc(e["url"])}" target="_blank" rel="noopener">file dated {esc(e["date"])} ↗</a>'


def place(e):
    return f'<span>{esc(e["name"])} <span class="v2-city">{esc(e["city"])}</span></span>'


def proc_url(slugs, code):
    return f'/costs/{pp.area_url_slug(AREA)}/{slugs[code]}/'


def what_word(S):
    """What the figure is, in plain words (rules: say what a price includes and leaves out)."""
    if S['kind'] == 'doc':
        return "the clinician's fee", "The hospital or birthing-center fee is billed separately."
    if S['cat'] == 'Imaging':
        return 'the facility fee for the scan', 'The radiologist who reads the scan bills separately.'
    if S['cat'] == 'Lab tests':
        return 'the lab fee', ''
    return 'the facility fee', "The doctor's fee and anesthesia are billed separately."


def section(summ, slugs, n_places, files_found, files_total, areas_opts, every, signup=''):
    S = summ[HERO]
    g = S['gap']
    lo, hi = g['lo'], g['hi']
    x = hi['v'] / lo['v']
    fee, extra = what_word(S)
    common = low(S['common'])

    # guess rounds: one network, lowest vs highest place, from the same "biggest gap inside one network" figure the pages use
    rounds = []
    for i, c in enumerate(c for c in GUESS if c in summ):
        s = summ[c]
        gg = s.get('gap')
        if not gg or gg['lo']['v'] < 50 or not 3 <= gg['hi']['v'] / gg['lo']['v'] <= 60:
            continue
        a, b = gg['lo'], gg['hi']
        pats = [(a['v'] * 1.8, b['v'] * .4, b['v']), (b['v'] * .3, b['v'], b['v'] * 2.3), (a['v'] * 2.2, b['v'], b['v'] * 2.6), (b['v'] * .35, b['v'] * .6, b['v'])]
        opts = pats[len(rounds) % len(pats)]
        f_, ex_ = what_word(s)
        rounds.append({'code': c, 'what': low(s['common']), 'plan': plan_name(a), 'loName': a['name'], 'loCity': a['city'], 'lo': money(a['v']),
                       'loSrc': a['url'], 'loDate': a['date'], 'hiName': b['name'], 'hiCity': b['city'], 'hi': money(b['v']), 'hiSrc': b['url'],
                       'hiDate': b['date'], 'x': f"{b['v'] / a['v']:.1f}", 'opts': [nice_sig(v) for v in opts], 'right': opts.index(b['v']),
                       'fee': f_, 'extra': ex_, 'url': proc_url(slugs, c)})
        if len(rounds) == 4:
            break

    # a slice of the real price board: three lowest and three highest places, each once
    low3, high3 = S['lowest'][:3], list(reversed(S['highest'][:3]))
    med = (S.get('med') or {}).get('opps')
    msrc = (S.get('med_src') or {}).get('opps')
    rows = ''.join(f'<li><span class="v2-who">{place(e)}<small>{esc(plan_name(e))} · {src(e)}</small></span><b>{money(e["v"])}</b></li>' for e in low3)
    rows += f'<li class="v2-gapline"><span>{S["providers"] - 6:,} more places in between</span></li>'
    rows += ''.join(f'<li class="hi"><span class="v2-who">{place(e)}<small>{esc(plan_name(e))} · {src(e)}</small></span><b>{money(e["v"])}</b></li>' for e in high3)
    bench = (f'<p class="v2-bench">For comparison, Medicare\'s national rate for a hospital outpatient {esc(common)} is <b>{money(med[0])}</b> '
             f'(<a href="{esc(msrc[1])}" target="_blank" rel="noopener">{esc(msrc[0])} ↗</a>, before local wage adjustment).</p>') if med and msrc else ''

    sp = S.get('spread')
    spread = ''
    if sp and sp['x'] >= 3:
        spread = (f'<div class="v2-card v2-story"><p class="kicker">Your insurer matters too</p>'
                  f'<h2>One hospital. Different insurers. {pp.short_money(sp["lo"]["v"])} to {pp.short_money(sp["hi"]["v"])}.</h2>'
                  f'<p>At {esc(sp["name"])} in {esc(sp["city"])}, {fee} for a {esc(common)} depends on who is paying: '
                  f'{esc(plan_name(sp["lo"]))} has agreed to {money(sp["lo"]["v"])} ({src(sp["lo"])}); {esc(plan_name(sp["hi"]))} has agreed to '
                  f'{money(sp["hi"]["v"])} ({src(sp["hi"])}). That\'s {sp["x"]:.1f} times as much, for the same procedure in the same building.</p></div>')

    pop = [('45378', 'Colonoscopy'), ('73721', 'Knee MRI'), ('66984', 'Cataract surgery'), ('27447', 'Knee replacement'), ('59400', 'Having a baby'), ('80053', 'Blood panel')]
    chips = ''.join(f'<a class="v2-chip" data-slug="{slugs[c]}" href="{proc_url(slugs, c)}">{esc(t)}</a>' for c, t in pop if c in slugs)
    qbox = pp.home_bits.qbox(''.join(f"<option value='{esc(slugs[c])}'{' selected' if c == HERO else ''}>{esc(n)}</option>"
                                     for c, n in sorted(((c, s['name']) for c, s in summ.items() if c in slugs), key=lambda t: t[1])), every)
    qbox = qbox.replace('value="Colonoscopy (diagnostic)"', 'value=""').replace(f'placeholder="Search {every} procedures, tests and services"',
                                                                                 'placeholder="Try &ldquo;MRI&rdquo; or &ldquo;colonoscopy&rdquo;"')
    data = json.dumps(rounds, ensure_ascii=False).replace('</', '<\\/')

    return f'''<!-- NATIONAL:START -->{V2_MARK}
<style>
{pp.home_bits.HOME_CSS2}
@media(max-width:1600px){{.menu-btn{{display:inline-block}}.nav{{display:none;position:absolute;left:0;right:0;top:100%;background:var(--board);flex-direction:column;align-items:stretch;padding:8px 16px 16px;border-bottom:3px solid var(--stamp)}}.nav.open{{display:flex}}.nav a{{padding:14px 4px;border-bottom:1px solid #6b3a3a}}.nav .ask{{margin-top:10px}}}}
.board .wrap{{grid-template-columns:minmax(0,1fr)}}
.v2-hero{{padding:clamp(28px,6vw,64px) 0 clamp(26px,5vw,48px)}}
.v2 .v2-eyebrow{{font:700 14px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:#F7C925;margin:0 0 18px}}
.v2 .v2-why{{margin:6px 0 0}}.v2 .v2-fine{{margin:14px 0 0}}.v2 .v2-set{{margin:0 0 6px}}
.v2-set{{font:600 clamp(19px,2.6vw,26px)/1.3 var(--body);color:var(--board-ink);margin:0;max-width:30em}}
.v2 .v2-hero h1.letters{{margin:.12em 0 .2em;font-size:clamp(56px,12vw,132px)!important;line-height:.95!important;letter-spacing:-.02em}}
.v2 .v2-hero h1 .or{{font-size:.38em;vertical-align:.4em;padding:0 .12em;opacity:.85;font-style:normal;color:var(--board-ink)}}
@media(max-width:600px){{.v2 .v2-hero h1 span,.v2 .v2-hero h1 em:not(.or){{display:block}}.v2 .v2-hero h1 .or{{display:block;vertical-align:0;padding:4px 0}}}}
.v2-why{{font-size:clamp(17px,2.1vw,20px);line-height:1.5;color:var(--board-sub);max-width:40em;margin:0}}
.v2-why b{{color:var(--board-ink)}}.v2-why a{{color:var(--board-ink);text-underline-offset:3px}}
.v2-fine{{font:14px/1.5 var(--body);color:var(--board-sub);margin:10px 0 0;max-width:46em}}.v2-fine a{{color:inherit}}
.v2-find{{margin-top:clamp(22px,4vw,34px);display:grid;gap:10px;max-width:780px}}
.v2-find label{{font:700 14px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--hi)}}
.v2-find .row{{display:flex;flex-wrap:wrap;gap:10px}}
.v2-find select{{flex:1 1 200px;min-width:0;background:var(--paper);color:var(--ink);border:0;padding:14px 12px;font-size:18px;min-height:52px}}
.v2-find button{{background:var(--hi);color:#151515;border:0;padding:14px 22px;font-weight:800;min-height:52px;cursor:pointer;text-transform:uppercase;letter-spacing:.04em}}
.v2-chips{{display:flex;flex-wrap:wrap;gap:8px}}
.v2-chip{{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;background:rgba(255,255,255,.12);color:var(--board-ink)!important;border:1px solid rgba(255,255,255,.45);text-decoration:none!important;font-weight:600;font-size:16px}}
.v2-chip:hover,.v2-chip:focus-visible{{background:var(--hi);color:#151515!important;border-color:var(--hi)}}
.v2-trust{{display:flex;flex-wrap:wrap;gap:6px 20px;margin:18px 0 0;padding-top:14px;border-top:1px solid rgba(255,255,255,.25);font-size:15px;color:var(--board-sub)}}
.v2-trust span::before{{content:"\\2713";color:var(--hi);font-weight:800;margin-right:7px}}
.v2 .sec{{padding:clamp(34px,6vw,56px) 0 0}}
.v2 .kicker{{margin:0 0 6px}}
.v2 h2{{margin:0 0 10px}}
.v2-card{{background:var(--paper);border:2px solid var(--rule);padding:clamp(18px,3.5vw,30px)}}
.v2-game{{max-width:760px}}
.v2-q{{font-size:clamp(19px,2.4vw,23px);line-height:1.45;margin:4px 0 16px}}
.v2-q b{{font-family:var(--mono);white-space:nowrap}}
.v2-opts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.v2-opts button{{min-height:56px;border:2px solid var(--rule);background:var(--paper);color:var(--ink);font:700 20px var(--mono);cursor:pointer}}
.v2-opts button:hover,.v2-opts button:focus-visible{{background:var(--ground)}}
.v2-opts button[aria-pressed=true]{{outline:3px solid var(--stamp);outline-offset:2px}}
.v2-opts button.right{{background:var(--hi);color:#151515}}
.v2-reveal{{margin-top:16px;font-size:17px;line-height:1.55}}.v2-reveal[hidden]{{display:none}}
.v2-reveal .big{{font:800 clamp(26px,4vw,36px)/1.1 var(--display);margin:0 0 8px}}
.v2-nav{{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin-top:16px}}
.v2-nav button{{min-height:46px;padding:0 18px;border:0;background:var(--ink);color:var(--paper);font:700 15px var(--body);cursor:pointer}}
.v2-nav .skip{{background:none;color:var(--ink);text-decoration:underline;padding:0}}
.v2-count{{font:13px var(--mono);letter-spacing:.08em;text-transform:uppercase;opacity:.75}}
.v2-src{{font:13px var(--mono);white-space:nowrap}}.v2-city{{font-weight:400;opacity:.8}}.v2-city::before{{content:"· "}}
.v2-board ol{{list-style:none;margin:14px 0 0;padding:0;border-top:2px solid var(--rule)}}
.v2-board li{{display:flex;justify-content:space-between;align-items:baseline;gap:14px;padding:12px 0;border-bottom:1px solid var(--rule)}}
.v2-board li b{{font:700 clamp(18px,2.4vw,22px) var(--mono);white-space:nowrap}}
.v2-board li.hi b{{color:var(--stamp)}}
.v2-who{{display:flex;flex-direction:column;gap:2px;font-weight:600;min-width:0}}.v2-who small{{font-weight:400;font-size:14px;opacity:.85}}
.v2-gapline{{justify-content:center!important;font:13px var(--mono);letter-spacing:.06em;text-transform:uppercase;opacity:.7;border-bottom-style:dashed!important}}
.v2-bench{{font-size:15px;margin:14px 0 0;opacity:.9}}
.v2-doors{{display:grid;gap:12px}}@media(min-width:800px){{.v2-doors{{grid-template-columns:repeat(3,1fr)}}}}
.v2-door{{display:flex;flex-direction:column;gap:8px;padding:22px;border:2px solid var(--rule);background:var(--paper);color:var(--ink);text-decoration:none}}
.v2-door:hover,.v2-door:focus-visible{{background:var(--ground)}}.v2-door h3{{margin:0;font-size:22px}}.v2-door .go{{margin-top:auto;font-weight:800;color:var(--stamp)}}
.v2-who-built{{display:grid;gap:18px}}@media(min-width:800px){{.v2-who-built{{grid-template-columns:3fr 2fr}}}}
.v2-rules{{list-style:none;margin:0;padding:0;display:grid;gap:8px;font-size:16px}}.v2-rules li::before{{content:"\\2713";font-weight:800;margin-right:8px;color:var(--stamp)}}
.v2-storylink{{margin:16px 0 0;font-weight:800}}.v2-storylink a{{color:var(--hi)!important;text-underline-offset:4px}}
.v2-more{{display:flex;flex-wrap:wrap;gap:10px 24px;margin:0;padding:24px 0 8px;font-weight:700}}
@media(max-width:600px){{.v2-board li{{flex-direction:column;gap:4px}}.v2-opts{{grid-template-columns:1fr}}}}
</style>
<section data-view="home" class="v2">
<div class="board"><div class="wrap"><div class="v2-hero">
<p class="v2-eyebrow">What is this going to cost me?</p>
<p class="v2-set">Same {esc(common)}. Same {esc(plan_name(lo))} plan. Two Dallas&ndash;Fort Worth hospitals.</p>
<h1 class="letters"><span>{pp.short_money(lo['v'])}</span> <em class="or">or</em> <em>{pp.short_money(hi['v'])}</em></h1>
<p class="v2-why">That's {esc(lo['name'])} and {esc(hi['name'])}: <b>{x:.1f} times as much</b> for the same procedure on the same insurance.
Hospitals and insurers have to publish these prices, in files too big to open. <b>We opened them.</b></p>
<p class="v2-fine">Exactly {money(lo['v'])} and {money(hi['v'])}, {fee}. {esc(extra)} Sources: {src(lo)} · {src(hi)}</p>
<form class="v2-find" id="natForm" action="/costs/" method="get">
<label for="natQ">Look up yours</label>
<div class="row">{qbox}
<select id="natArea" aria-label="Where">{areas_opts}</select><button type="submit">Show me</button></div>
<div class="v2-chips" aria-label="Popular">{chips}</div>
</form>
<p class="v2-storylink"><a href="/story/">New here? See the whole story in 7 steps →</a></p>
<p class="v2-trust"><span>Free, no ads</span><span>Every price linked to its source</span><span>Prices, not your medical records</span></p>
<p class="msg" style="display:none" id="msg"></p><div id="homeChips" hidden></div><form id="searchForm" hidden><input id="q"></form>
</div></div></div>
<div class="wrap">
{('<div class="sec"><p class="kicker">Try one</p><h2>Guess what the same plan pays somewhere else</h2>'
  '<div class="v2-card v2-game" id="v2game" aria-live="polite"></div></div>') if rounds else ''}
<div class="sec v2-board"><p class="kicker">The receipt</p><h2>{esc(S['common'])} in Dallas&ndash;Fort Worth</h2>
<p>{S['providers']:,} places, {len(S['networks'])} insurance networks, from the insurers' own files. This is {fee}; {esc(extra[0].lower() + extra[1:]) if extra else ''}</p>
<ol>{rows}</ol>{bench}
<p style="margin-top:18px"><a class="btn" href="{proc_url(slugs, HERO)}">See all {S['providers']:,} places</a></p></div>
{('<div class="sec">' + spread + '</div>') if spread else ''}
<div class="sec"><p class="kicker">Start where you are</p><h2>What brings you here?</h2><div class="v2-doors">
<a class="v2-door" href="/costs/"><h3>Something's coming up</h3><span>A scan, a surgery, a baby. See the lowest and highest real prices where you live, and what your insurer has agreed to pay.</span><span class="go">Find a price →</span></a>
<a class="v2-door" href="/surprise-bills/"><h3>I got a bill</h3><span>Check it against what insurers actually pay for the same thing, and what the surprise-billing law says.</span><span class="go">Check a bill →</span></a>
<a class="v2-door" href="/employer-plans/"><h3>I run or buy a health plan</h3><span>See which networks a plan uses and what those networks pay, provider by provider.</span><span class="go">Employer plans →</span></a>
</div></div>
<div class="sec v2-who-built"><div><p class="kicker">Who keeps the receipts</p><h2>Built by someone who used to sit on the other side of the table</h2>
<p class="lede">{esc(pp.AUTHOR['bio'])}</p></div>
<ul class="v2-rules"><li>Every price links to the file it came from</li><li>Every price shows the date it was published; old files are flagged</li><li>Nothing is estimated or averaged</li><li><a href="/methodology/">How we read the files</a></li></ul></div>
<div class="sec">{signup}</div>
<p class="v2-more"><a href="/costs/">Prices in {n_places} places →</a><a href="/price-file-watch/">{files_found:,} of {files_total:,} hospitals have a price file we could find →</a></p>
</div>
<script>(function(){{
var f=document.getElementById('natForm'),q=document.getElementById('natQ'),A=document.getElementById('natArea');
f.addEventListener('submit',function(e){{if(!q.value.trim()){{e.preventDefault();e.stopImmediatePropagation();q.focus();q.setAttribute('placeholder','Type a procedure, like \\u201cMRI\\u201d');}}}});
function chipHrefs(){{[].forEach.call(document.querySelectorAll('.v2-chip'),function(a){{a.href='/costs/'+A.value+'/'+a.dataset.slug+'/'}})}}
A.addEventListener('change',chipHrefs);chipHrefs();
var pill=document.querySelector('.bar .start-pill');if(pill){{pill.textContent='Find a price';pill.setAttribute('href','/v2/');pill.addEventListener('click',function(e){{e.preventDefault();location.hash='';q.scrollIntoView({{block:'center'}});q.focus()}})}}
var R={data},el=document.getElementById('v2game');if(!el||!R.length)return;var i=0;
function h(s){{return String(s).replace(/[&<>"]/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]}})}}
function src(u,d){{return '<a class="v2-src" href="'+h(u)+'" target="_blank" rel="noopener">file dated '+h(d)+' \\u2197</a>'}}
function ev(o){{try{{window.hcfTrack&&window.hcfTrack(o)}}catch(e){{}}}}
function draw(){{var r=R[i];
el.innerHTML='<p class="v2-count">'+(i+1)+' of '+R.length+'</p><p class="v2-q">'+h(r.plan)+' pays '+h(r.loName)+' in '+h(r.loCity)+' <b>'+h(r.lo)+'</b> for a '+h(r.what)+'. What\\u2019s the most the same plan pays another place in Dallas\\u2013Fort Worth?</p>'
+'<div class="v2-opts" role="group" aria-label="Your guess">'+r.opts.map(function(o,k){{return '<button type="button" data-k="'+k+'">About '+h(o)+'</button>'}}).join('')+'</div><div class="v2-reveal" hidden></div>'
+'<div class="v2-nav"><button type="button" class="skip" data-skip>Skip, let me look up my own</button></div>';
[].forEach.call(el.querySelectorAll('.v2-opts button'),function(b){{b.onclick=function(){{pick(+b.dataset.k)}}}});
el.querySelector('[data-skip]').onclick=function(){{ev({{ev:'guess-skip',detail:r.what}});q.scrollIntoView({{block:'center'}});q.focus()}};}}
function pick(k){{var r=R[i],ok=k===r.right;ev({{ev:'guess',detail:r.what+(ok?' (right)':' (wrong)')}});
[].forEach.call(el.querySelectorAll('.v2-opts button'),function(b,j){{b.disabled=true;b.setAttribute('aria-pressed',String(j===k));if(j===r.right)b.classList.add('right')}});
var v=el.querySelector('.v2-reveal');v.hidden=false;
v.innerHTML='<p class="big">'+h(r.hi)+'</p><p>'+(ok?'You got it. ':'')+'That\\u2019s what '+h(r.plan)+' pays '+h(r.hiName)+' in '+h(r.hiCity)+': <b>'+h(r.x)+' times as much</b> for the same '+h(r.what)+', on the same plan. ('+h(r.fee.charAt(0).toUpperCase()+r.fee.slice(1))+'. '+h(r.extra)+')</p>'
+'<p>Sources: '+h(r.lo)+' '+src(r.loSrc,r.loDate)+' · '+h(r.hi)+' '+src(r.hiSrc,r.hiDate)+'</p>';
var n=el.querySelector('.v2-nav');n.innerHTML=(i+1<R.length?'<button type="button" data-next>Try another</button>':'')+'<a href="'+h(r.url)+'">Every '+h(r.what)+' price in Dallas\\u2013Fort Worth \\u2192</a>';
var nx=n.querySelector('[data-next]');if(nx)nx.onclick=function(){{i++;draw();el.querySelector('button').focus()}};}}
draw();}})();</script>
{pp.home_bits.HOME_JS.replace('__EVERY__', every)}
</section>
<!-- NATIONAL:END -->'''


def build(d):
    """d holds site/, functions/ and costs_state.json. Writes site/v2/index.html; returns True if it changed."""
    site = os.path.join(d, 'site')
    pp.site_settings(site)
    st = json.load(open(os.path.join(d, 'costs_state.json'), encoding='utf-8'))
    summ = {k.split('|', 1)[1]: v for k, v in st['summaries'].items() if k.startswith(AREA + '|')}
    if HERO not in summ or not summ[HERO].get('gap'):
        sys.exit(f'STOP: no {AREA} summary with a same-network gap for {HERO}; /v2/ not written')
    names = {c: s['name'] for c, s in summ.items()}
    slugs = pp.load_slugs(sorted(names), names)
    home = open(os.path.join(site, 'index.html'), encoding='utf-8').read()
    m = re.search(r'<select id="natArea"[^>]*>(.*?)</select>', home, re.S)
    every = (re.search(r'Search (\S+) procedures, tests and services', home) or [None, 'every'])[1]
    found = re.search(r'<h2>([\d,]+) of ([\d,]+) hospitals</h2>', home)
    n_places = len(json.load(open(os.path.join(site, 'cities.json'), encoding='utf-8')))
    nf, nt = (int(found.group(1).replace(',', '')), int(found.group(2).replace(',', ''))) if found else (0, 0)
    area_opts = m.group(1) if m else ''
    proc_opts = ''.join(f"<option value='{esc(slugs[c])}'{' selected' if c == HERO else ''}>{esc(n)}</option>"
                        for c, n in sorted(((c, s['name']) for c, s in summ.items() if c in slugs), key=lambda t: t[1]))
    sec = section(summ, slugs, n_places, nf, nt, area_opts, every, signup_block(proc_opts, area_opts))
    changed = write_page(site, 'v2', home, sec, '(v2) ')
    # the story page: same shell, same figures
    qbox = pp.home_bits.qbox(proc_opts, every).replace('value="Colonoscopy (diagnostic)"', 'value=""')
    pop = [('45378', 'Colonoscopy'), ('73721', 'Knee MRI'), ('66984', 'Cataract surgery'), ('27447', 'Knee replacement'), ('59400', 'Having a baby'), ('80053', 'Blood panel')]
    chips = ''.join(f'<a class="v2-chip" data-slug="{slugs[c]}" href="{proc_url(slugs, c)}">{esc(t)}</a>' for c, t in pop if c in slugs)
    mm = re.search(r'<div class="nat-map">.*?</div>\s*<p class="cap">.*?</p></div>', home, re.S)
    chips_js = ("<script>(function(){var A=document.getElementById('natArea');function c(){[].forEach.call(document.querySelectorAll('.v2-chip'),"
                "function(a){a.href='/costs/'+A.value+'/'+a.dataset.slug+'/'})}A.addEventListener('change',c);c();})();</script>")
    pf = os.path.join(site, 'price-finder', 'index.html')
    D = pp.page_data(pf)[0] if os.path.isfile(pf) else None
    gp = os.path.join(d, 'geo.json')
    geo = json.load(open(gp, encoding='utf-8')) if os.path.isfile(gp) else None
    sec2 = story.section(summ, site, qbox, area_opts, chips, signup_block(proc_opts, area_opts), mm.group(0) if mm else '', nf, nt,
                         chips_js + pp.home_bits.HOME_JS.replace('__EVERY__', every), D=D, geo=geo, nice=pp.nice)
    del D
    changed = write_page(site, 'story', home, sec2, 'The story: ') or changed
    # sign-ups on the current homepage (its front section is rewritten daily, so this is re-added each run)
    hp = os.path.join(site, 'index.html')
    if SU_MARK not in home and '<!-- NATIONAL:END -->' in home:
        add = (f'<div class="wrap"><div class="sec">{signup_block(proc_opts, area_opts)}</div>'
               '<p style="margin:18px 0 0;font-weight:800"><a href="/story/">New here? See the whole story in 7 steps →</a></p></div>\n')
        open(hp, 'w', encoding='utf-8').write(home.replace('<!-- NATIONAL:END -->', add + '<!-- NATIONAL:END -->', 1))
        changed = True
    # networks each price page leaves out of its figures (same rate at most places, BCBSTX ParPlan), by page
    fbp = {}
    for k, v in st['summaries'].items():
        a_, c_ = k.split('|', 1)
        if c_ in slugs:
            fbp[(pp.area_url_slug(a_), slugs[c_])] = {(n['ins'], n['plan']) for n in v.get('networks') or [] if n.get('flat') or n.get('par')}
    return patch_price_pages(site, fbp) or changed


def write_page(site, name, home, sec, title_prefix):
    page = re.sub(r'<!-- NATIONAL:START.*?<!-- NATIONAL:END -->', lambda _: sec, home, count=1, flags=re.S)
    if page == home:
        sys.exit(f'STOP: homepage has no NATIONAL block; /{name}/ not written')
    page = page.replace('<title>', '<title>' + title_prefix, 1)
    out = os.path.join(site, name, 'index.html')
    old = open(out, encoding='utf-8').read() if os.path.isfile(out) else ''
    if old == page:
        return False
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write(page)
    print(f'wrote site/{name}/index.html')
    return True


# ---------------------------------------------------------------- email sign-ups (weekly receipt, price alerts)
SU_MARK = '<!-- SIGNUP (site/home_v2.py) -->'
SU_CSS = (".su{background:var(--paper);color:var(--ink);border:2px solid var(--rule);padding:clamp(18px,3vw,28px);position:relative}"
          ".su-cut{margin:-6px 0 14px;font:700 13px var(--mono);letter-spacing:.14em;text-transform:uppercase;border-bottom:2px dashed var(--rule);padding-bottom:10px}"
          ".su-grid{display:grid;gap:22px}@media(min-width:800px){.su-grid{grid-template-columns:1fr 1fr}}"
          ".su-f{display:grid;gap:8px;align-content:start}.su-f h3{margin:0;font-size:22px}.su-f p{margin:0;font-size:16px;line-height:1.45}"
          ".su-f label{font:700 13px var(--mono);letter-spacing:.06em;text-transform:uppercase;margin-top:4px}"
          ".su-f input[type=email],.su-f select{min-height:46px;border:2px solid var(--rule);padding:0 10px;font:16px var(--body);background:var(--paper);color:var(--ink);width:100%;box-sizing:border-box}"
          ".su-f button{min-height:48px;border:0;background:var(--ink);color:var(--paper);font:800 15px var(--body);cursor:pointer;margin-top:6px}"
          ".su-hp{position:absolute!important;left:-9999px!important;width:1px;height:1px}"
          ".su-msg{min-height:1.4em;font-weight:700}.su-fine{margin:16px 0 0;font-size:14px;line-height:1.5;color:var(--muted)}")
SU_JS = r'''<script>(function(){if(window.hcfSu)return;window.hcfSu=1;document.addEventListener('submit',function(e){var f=e.target.closest&&e.target.closest('.su-f');if(!f)return;e.preventDefault();
var m=f.querySelector('.su-msg'),em=f.querySelector('input[type=email]').value.trim(),w=f.querySelector('[name=what]'),a=f.querySelector('[name=area]');
var what=w?(w.tagName==='SELECT'?w.options[w.selectedIndex].text:w.value):'';if(a)what+=' in '+a.options[a.selectedIndex].text;
if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(em)){m.textContent='Please check the email address.';return}
m.textContent='Sending…';fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',
body:JSON.stringify({list:f.dataset.list,email:em,what:what,page:location.pathname,website:f.querySelector('.su-hp').value})})
.then(function(r){return r.json()}).then(function(j){m.textContent=j.ok?(f.dataset.list==='alert'?'You’re on the list for '+what+'.':'You’re on the list for the weekly receipt.'):(j.error||'That didn’t work. Please try again.');
if(j.ok){try{window.hcfTrack&&window.hcfTrack({ev:'signup',detail:f.dataset.list==='alert'?'price alert: '+what:'weekly receipt'})}catch(x){}}})
.catch(function(){m.textContent='That didn’t work. Please try again.'})},true)})();</script>'''


def signup_block(proc_opts='', area_opts='', fixed=''):
    """The "Detach and return" sign-up card: the weekly receipt and price alerts. fixed = the alert's subject on a price page."""
    uid = 'su' + hashlib.sha1((fixed or proc_opts[:200] or 'x').encode()).hexdigest()[:6]
    if fixed:
        pick = f'<input type="hidden" name="what" value="{esc(fixed)}"><p><b>For:</b> {esc(fixed)}</p>'
    else:
        pick = (f'<label for="{uid}p">What</label><select id="{uid}p" name="what">{proc_opts}</select>'
                f'<label for="{uid}a">Where</label><select id="{uid}a" name="area">{area_opts}</select>')
    return (f'{SU_MARK}<style>{SU_CSS}</style><div class="su" id="signup"><p class="su-cut"><span aria-hidden="true">✂ </span>Detach and return</p><div class="su-grid">'
            f'<form class="su-f" data-list="weekly"><h3>The weekly receipt</h3><p>One real price from the files every Friday: what it was, where it came from, and what it means for you.</p>'
            f'<label for="{uid}w">Your email</label><input id="{uid}w" type="email" autocomplete="email" required>'
            f'<input class="su-hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">'
            f'<button type="submit">Send me the weekly receipt</button><p class="su-msg" aria-live="polite"></p></form>'
            f'<form class="su-f" data-list="alert"><h3>Price alerts</h3><p>We\'ll email you when a price changes for what you looked up.</p>{pick}'
            f'<label for="{uid}e">Your email</label><input id="{uid}e" type="email" autocomplete="email" required>'
            f'<input class="su-hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">'
            f'<button type="submit">Alert me when it changes</button><p class="su-msg" aria-live="polite"></p></form></div>'
            '<p class="su-fine">We use your email only for what you sign up for. No ads, never sold or shared, and you can unsubscribe any time. '
            'While the site is a private preview we\'re only collecting sign-ups; the emails start when it goes public.</p></div>' + SU_JS)


GA_MARK = '<!-- GAUGE (site/home_v2.py) -->'
GAUGE_JS = r"""/* Quote gauge on price pages (site/home_v2.py, Oct 19, 2026). Reads the page's own "Got a quote?" box (#vrq) and the
   page's published prices (embedded from its prices.csv). Worked out in the browser; nothing is saved or sent. */
(function(){var B=document.querySelector('.hcf-g');if(!B)return;var a=JSON.parse(B.querySelector('.hcf-gd').textContent),n=a.length,M=+B.dataset.med,ML=B.dataset.medl,
G=B.querySelector('svg'),say=B.querySelector('.hcf-gsay'),q=document.getElementById('vrq'),NS='http://www.w3.org/2000/svg',cx=170,cy=170,R=130;
function pt(f,r){var t=Math.PI*(1-f);return [cx+r*Math.cos(t),cy-r*Math.sin(t)]}
function mk(t,at){var e=document.createElementNS(NS,t);for(var k in at)e.setAttribute(k,at[k]);G.appendChild(e);return e}
function arc(f0,f1,c){if(f1-f0<.001)return;var p=pt(f0,R),r=pt(f1,R);mk('path',{d:'M'+p[0]+' '+p[1]+' A'+R+' '+R+' 0 0 1 '+r[0]+' '+r[1],fill:'none',stroke:c,'stroke-width':26})}
function below(v){var lo=0,hi=n;while(lo<hi){var m=(lo+hi)>>1;if(a[m]<v)lo=m+1;else hi=m}return lo}
function txt(x,y,s,an){var e=mk('text',{x:x,y:y,'font-size':12,'font-family':'monospace','text-anchor':an||'middle',fill:'currentColor'});e.textContent=s}
var $=function(v){return '$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})},r$=function(v){return '$'+Math.round(v).toLocaleString('en-US')};
function draw(){G.innerHTML='';if(M>0){var f1=below(M+.005)/n,f2=below(2*M+.005)/n;arc(0,f1,'#3D8B5A');arc(f1,f2,'#9DB6F5');arc(f2,1,'#E6402E');var mp=pt(f1,R+24);txt(mp[0],mp[1],'Medicare '+r$(M))}else arc(0,1,'#9DB6F5');
txt(14,192,r$(a[0])+' lowest','start');txt(326,192,r$(a[n-1])+' highest','end');
var v=parseFloat(q&&q.value);if(!(v>0)){say.textContent='Type your quote in the box above and the needle shows where it lands among the '+n.toLocaleString('en-US')+' prices published here.';return}
var b=below(v),p=pt(Math.min(1,Math.max(0,b/n)),R-30);mk('line',{x1:cx,y1:cy,x2:p[0],y2:p[1],stroke:'currentColor','stroke-width':6,'stroke-linecap':'round'});mk('circle',{cx:cx,cy:cy,r:10,fill:'currentColor'});
say.textContent=$(v)+' is higher than '+b.toLocaleString('en-US')+' of the '+n.toLocaleString('en-US')+' prices insurers published here'+(b===0?' (lower than all of them)':b===n?' (higher than all of them)':'')+(M>0?', and '+(v/M).toFixed(1)+'× Medicare’s rate ('+ML+').':'.')}
if(q){q.addEventListener('input',draw);q.addEventListener('change',function(){try{window.hcfTrack&&window.hcfTrack({ev:'tap',detail:'price-page gauge quote entered'})}catch(e){}})}draw()})();
"""
GA_CSS = ('<style>.hcf-g{margin:14px 0 0;max-width:640px;padding:14px 16px;border:2px solid var(--ink);background:var(--paper);color:var(--ink)}'
          '.hcf-g p.hcf-gk{margin:0 0 4px;font:700 13px var(--mono);letter-spacing:.1em;text-transform:uppercase}.hcf-g svg{width:100%;max-width:400px;height:auto;display:block}'
          '.hcf-gsay{margin:6px 0 0;font-size:16px;line-height:1.5}.hcf-gkey{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;margin:6px 0 0}'
          '.hcf-gkey i{display:inline-block;width:11px;height:11px;margin-right:5px;vertical-align:-1px}</style>')


def gauge_block(prices, med, medl):
    key = ('<p class="hcf-gkey"><span><i style="background:#3D8B5A"></i>at or below Medicare</span><span><i style="background:#9DB6F5"></i>up to double</span>'
           '<span><i style="background:#E6402E"></i>more than double</span></p>') if med > 0 else ''
    return (f'{GA_MARK}{GA_CSS}<div class="hcf-g" data-med="{med:.2f}" data-medl="{esc(medl)}"><p class="hcf-gk">Where your quote lands</p>'
            f'<svg viewBox="0 0 340 200" aria-hidden="true"></svg><p class="hcf-gsay" aria-live="polite"></p>{key}'
            f'<script type="application/json" class="hcf-gd">{json.dumps(prices, separators=(",", ":"))}</script></div>'
            '<script src="/hcf-gauge.js" defer></script>')


def patch_price_pages(site, flat_by_page=None):
    """Every /costs/<area>/<procedure>/ page gets the sign-up card (alert fixed to that page) and, where the page has its
    prices.csv and a "Got a quote?" box, the quote gauge under that box. Both re-added after each daily rebuild."""
    n_su = n_ga = 0
    base = os.path.join(site, 'costs')
    if not os.path.isdir(base):
        return False
    gj = os.path.join(site, 'hcf-gauge.js')
    changed = False
    if not os.path.isfile(gj) or open(gj, encoding='utf-8').read() != GAUGE_JS:
        open(gj, 'w', encoding='utf-8').write(GAUGE_JS)
        changed = True
    for area in os.listdir(base):
        ad = os.path.join(base, area)
        if not os.path.isdir(ad):
            continue
        for proc in os.listdir(ad):
            p = os.path.join(ad, proc, 'index.html')
            if not os.path.isfile(p):
                continue
            s0 = s = open(p, encoding='utf-8').read()
            if SU_MARK not in s and '<footer' in s:
                h1 = re.search(r'<h1[^>]*>(.*?)</h1>', s, re.S)
                label = html.unescape(re.sub(r'<[^>]+>|\s+', ' ', h1.group(1))).strip() if h1 else proc.replace('-', ' ')
                s = s.replace('<footer', f'<div class="wrap" style="margin:28px auto">{signup_block(fixed=label)}</div>\n<footer', 1)
                n_su += 1
            pc = os.path.join(ad, proc, 'prices.csv')
            if GA_MARK not in s and '<form class="vr-quote"' in s and os.path.isfile(pc):
                rows = list(csv.reader(open(pc, encoding='utf-8')))
                if len(rows) > 2:
                    h = rows[1]
                    flat = (flat_by_page or {}).get((area, proc), set())   # same-amount-everywhere networks: left out of the page's figures, so out of the gauge too
                    vals = sorted(float(r[h.index('price')]) for r in rows[2:] if len(r) == len(h) and r[0] == 'insurer rate' and r[h.index('price')]
                                  and (r[h.index('insurer')], r[h.index('network or label')]) not in flat)
                    m = re.search(r'class="vr-line"[^>]*data-med="([\d.]+)" data-medl="([^"]*)"', s)
                    if vals:
                        i = s.index('<form class="vr-quote"')
                        k = s.index('</form>', i) + len('</form>')
                        s = s[:k] + gauge_block(vals, float(m.group(1)) if m else 0.0, html.unescape(m.group(2)) if m else '') + s[k:]
                        n_ga += 1
            if s != s0:
                open(p, 'w', encoding='utf-8').write(s)
    if n_su or n_ga:
        print(f'price pages: sign-up card added to {n_su}, quote gauge added to {n_ga}')
    return changed or n_su > 0 or n_ga > 0


# ---------------------------------------------------------------- tester tracking
TRACK_JS = r"""/* Preview tester tracking (site/home_v2.py, Oct 18, 2026). Loaded only for invited testers by functions/_middleware.js.
   Records what the page-view log can't see: in-page views (receipts, the Chargemaster), taps, searches, how far people
   scroll and how long they stay, and one optional question on the homepage. Sent to /__ev; nothing goes anywhere else. */
(function () {
  if (window.hcfTrack) return;
  var start = Date.now(), maxDepth = 0, sent = false, page = location.pathname;
  function send(o, beacon) {
    o.page = page + (location.hash || '');
    var body = JSON.stringify(o);
    try {
      fetch('/__ev', { method: 'POST', body: body, headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', keepalive: true });
    } catch (e) {}
  }
  window.hcfTrack = function (o) { send(o); };
  if (location.hash.length > 2) send({ ev: 'view' });
  addEventListener('hashchange', function () { if (location.hash.length > 2) send({ ev: 'view' }); });
  addEventListener('scroll', function () {
    var h = document.documentElement, d = (h.scrollTop + innerHeight) / Math.max(1, h.scrollHeight);
    if (d > maxDepth) maxDepth = d;
  }, { passive: true });
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a,button');
    if (!a || a.closest('.look-pick')) return;
    var t = (a.getAttribute('aria-label') || a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80);
    send({ ev: 'tap', detail: t, to: a.tagName === 'A' ? (a.getAttribute('href') || '').slice(0, 200) : '' });
  }, true);
  document.addEventListener('submit', function (e) {
    var i = e.target.querySelector && e.target.querySelector('input[type=search],input[type=text],input:not([type])');
    send({ ev: 'search', detail: i && i.value ? 'typed a search' : 'pressed search with nothing typed' });
  }, true);
  function leave() {
    if (sent) return; sent = true;
    send({ ev: 'leave', secs: Math.round((Date.now() - start) / 1000), depth: Math.round(Math.min(1, Math.max(maxDepth, innerHeight / Math.max(1, document.documentElement.scrollHeight))) * 100) }, true);
  }
  addEventListener('pagehide', leave);
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'hidden') leave(); else sent = false; });

  // one optional question, homepage only, once per browser
  if (!/^\/(v2\/)?$/.test(page)) return;
  var KEY = 'hcf-ask-v1';
  try { if (localStorage.getItem(KEY)) return; } catch (e) { return; }
  var shown = false;
  function ask() {
    if (shown || location.hash.length > 2) return; shown = true;
    try { localStorage.setItem(KEY, 'shown'); } catch (e) {}
    var css = document.createElement('style');
    css.textContent = '.hcf-ask{position:fixed;left:12px;right:12px;bottom:12px;z-index:60;max-width:440px;margin-left:auto;background:#fff;color:#151515;border:2px solid #151515;box-shadow:6px 6px 0 #151515;padding:16px 18px;font:16px/1.4 system-ui,sans-serif}' +
      '.hcf-ask p{margin:0 0 10px;font-weight:700}.hcf-ask .o{display:flex;flex-wrap:wrap;gap:8px}.hcf-ask button{min-height:44px;padding:0 12px;border:1px solid #151515;background:#fff;color:#151515;font:inherit;cursor:pointer}' +
      '.hcf-ask button:hover{background:#F7C925}.hcf-ask .x{position:absolute;top:4px;right:6px;border:0;font-size:22px;min-height:36px}.hcf-ask input{width:100%;box-sizing:border-box;min-height:44px;margin-top:8px;padding:8px;border:1px solid #151515;font:inherit}';
    document.head.appendChild(css);
    var b = document.createElement('div'); b.className = 'hcf-ask'; b.setAttribute('role', 'dialog'); b.setAttribute('aria-label', 'Quick question');
    b.innerHTML = '<button class="x" aria-label="Close">\u00d7</button><p>Quick question: what were you hoping to find here?</p><div class="o">' +
      ['A price for something specific', 'What my insurance pays', 'Just curious', 'Something else'].map(function (t) { return '<button type="button">' + t + '</button>'; }).join('') + '</div>';
    document.body.appendChild(b);
    b.querySelector('.x').onclick = function () { send({ ev: 'answer', detail: '(closed without answering)' }); b.remove(); };
    [].forEach.call(b.querySelectorAll('.o button'), function (x) {
      x.onclick = function () {
        if (x.textContent === 'Something else') {
          b.querySelector('.o').innerHTML = '<input aria-label="What were you hoping to find?" maxlength="200" placeholder="Tell us in a few words"><button type="button" style="margin-top:8px">Send</button>';
          var inp = b.querySelector('input'); inp.focus();
          b.querySelector('.o button').onclick = function () { send({ ev: 'answer', detail: 'Something else: ' + inp.value.slice(0, 200) }); b.innerHTML = '<p>Thank you!</p>'; setTimeout(function () { b.remove(); }, 1500); };
          return;
        }
        send({ ev: 'answer', detail: x.textContent }); b.innerHTML = '<p>Thank you!</p>'; setTimeout(function () { b.remove(); }, 1500);
      };
    });
  }
  setTimeout(ask, 40000);
  addEventListener('scroll', function () { if (maxDepth > 0.6) ask(); }, { passive: true });
})();
"""

MW_EV = r"""
// Tester actions (Oct 18, 2026; site/home_v2.py): the tracker /hcf-t.js posts here. Only invited testers' actions are kept,
// to R2 logs/preview-events/<date>/ (what they tapped, in-page views, scroll depth, the one-question answer). Betsy's not logged.
async function logEvent(env, waitUntil, who, request) {
  let o = {};
  try { o = JSON.parse((await request.text()).slice(0, 4000)) || {}; } catch (e) {}
  const s = (v, n) => (typeof v === 'string' ? v.slice(0, n) : '');
  const now = new Date();
  const rec = { t: now.toISOString(), who, ev: s(o.ev, 20), page: s(o.page, 200), detail: s(o.detail, 220), to: s(o.to, 200),
    secs: Number.isFinite(o.secs) ? Math.min(o.secs, 86400) : undefined, depth: Number.isFinite(o.depth) ? Math.min(o.depth, 100) : undefined,
    device: /Mobi/.test(request.headers.get('User-Agent') || '') ? 'phone' : 'computer' };
  const key = 'logs/preview-events/' + rec.t.slice(0, 10) + '/' + rec.t + '-' + who + '-' + Math.random().toString(36).slice(2, 8) + '.json';
  try { waitUntil(env.PF.put(key, JSON.stringify(rec), { httpMetadata: { contentType: 'application/json' } })); } catch (e) {}
}
"""


SIGNUP_FN = r"""// Email sign-ups (Oct 18, 2026; site/home_v2.py): the weekly receipt and price alerts. POST /api/signup.
// Saved privately to R2 signups/<list>/<id>.json; nothing is sent yet (emails start when the site goes public).
async function sha(s) { const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)); return [...new Uint8Array(b)].map((x) => x.toString(16).padStart(2, '0')).join(''); }
const out = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
export async function onRequestPost({ request, env }) {
  let o = {};
  try { o = JSON.parse((await request.text()).slice(0, 4000)) || {}; } catch (e) {}
  if (o.website) return out({ ok: true });                       // filled-in hidden field: a bot
  const email = String(o.email || '').trim().toLowerCase().slice(0, 254);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return out({ ok: false, error: 'Please check the email address.' }, 400);
  const list = o.list === 'alert' ? 'alert' : 'weekly';
  const what = list === 'alert' ? String(o.what || '').slice(0, 200) : '';
  if (list === 'alert' && !what) return out({ ok: false, error: 'Pick what you want alerts for.' }, 400);
  if (!env.PF) return out({ ok: false, error: 'Sign-ups are not available right now.' }, 503);
  const id = (await sha(email + '|' + what)).slice(0, 32);
  const rec = { t: new Date().toISOString(), email, list, what, page: String(o.page || '').slice(0, 200),
    device: /Mobi/.test(request.headers.get('User-Agent') || '') ? 'phone' : 'computer', confirmed: false };
  await env.PF.put('signups/' + list + '/' + id + '.json', JSON.stringify(rec), { httpMetadata: { contentType: 'application/json' } });
  return out({ ok: true });
}
"""


def patch_tracking(d):
    """Middleware: accept tester events at /__ev and load /hcf-t.js for testers. Idempotent; returns True if anything changed."""
    changed = False
    t = os.path.join(d, 'site', 'hcf-t.js')
    if not os.path.isfile(t) or open(t, encoding='utf-8').read() != TRACK_JS:
        open(t, 'w', encoding='utf-8').write(TRACK_JS)
        changed = True
    p = os.path.join(d, 'functions', '_middleware.js')
    js = open(p, encoding='utf-8').read()
    if 'async function logEvent(' not in js:
        anchor = 'export async function onRequest('
        if anchor not in js:
            sys.exit('STOP: middleware layout changed (no onRequest); tracking not added')
        js = js.replace(anchor, MW_EV.lstrip() + '\n' + anchor, 1)
        old = "        const res = await next();\n        if (tester && env.PF && request.method === 'GET'"
        new = ("        if (u.pathname === '/__ev') {\n"
               "          if (tester && env.PF && request.method === 'POST') await logEvent(env, waitUntil, tester, request);\n"
               "          return new Response(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });\n"
               "        }\n" + old)
        if old not in js:
            sys.exit('STOP: middleware layout changed (tester logging line); tracking not added')
        js = js.replace(old, new, 1)
        old = "(tester ? '<style>.look-pick{display:none!important}</style>' : '')"
        if old not in js:
            sys.exit('STOP: middleware layout changed (look switcher line); tracking not added')
        js = js.replace(old, "(tester ? '<style>.look-pick{display:none!important}</style><script src=\"/hcf-t.js\" defer></script>' : '')", 1)
        open(p, 'w', encoding='utf-8').write(js)
        changed = True
    f = os.path.join(d, 'functions', 'api', 'signup.js')
    os.makedirs(os.path.dirname(f), exist_ok=True)
    if not os.path.isfile(f) or open(f, encoding='utf-8').read() != SIGNUP_FN:
        open(f, 'w', encoding='utf-8').write(SIGNUP_FN)
        changed = True
    pv = os.path.join(d, 'site', 'privacy', 'index.html')
    if os.path.isfile(pv):
        s = open(pv, encoding='utf-8').read()
        a = 'we keep a simple record of which pages they view and when, so we can see what is useful.'
        b = ('we keep a simple record of which pages they view and when, what they tap or click, how far down a page they scroll, '
             'and their answer if they reply to a one-question survey, so we can see what is useful. We do not record what they type into search boxes.')
        if a in s:
            s = s.replace(a, b, 1)
            changed = True
        su = ('<p id="email"><strong>Email sign-ups.</strong> If you sign up for the weekly receipt or a price alert, we keep your email address, '
              'what you asked to hear about, and when you signed up. We use it only to send what you asked for. We never sell or share it, and every email '
              'will have a one-click unsubscribe. You can ask us to delete it at any time.</p>')
        if 'id="email"' not in s and '<p><strong>4. Health-related data.' in s:
            s = s.replace('<p><strong>4. Health-related data.', su + '\n<p><strong>4. Health-related data.', 1)
            changed = True
        if changed:
            open(pv, 'w', encoding='utf-8').write(s)
    return changed


# ---------------------------------------------------------------- control center: show the tracker's data (Visitors tab)
CTL = [   # (marker that shows the step is done, anchor, replacement)
    ("if (a === '/v2/') return 'Homepage v2';",
     "const sec = (p) => { const a = (p || '/').split('?')[0]; if (a === '/' || a === '') return 'Homepage';",
     "const sec = (p) => { const a = (p || '/').split('?')[0].split('#')[0]; if (a === '/' || a === '') return 'Homepage'; if (a === '/v2/') return 'Homepage v2'; if (a === '/story/') return 'Story';"),
    ('id="v-events"', """    <div class="card">
      <div class="head"><div><h3>Every page view</h3>""", """    <div class="card">
      <div class="head"><div><h3>What testers did on the page</h3><p class="muted">Newest first: taps, searches, the guess game, story steps reached, how long they stayed and how far they scrolled, and answers to the homepage question "What were you hoping to find?". Collected since Oct 18, 2026.</p></div>
        <div class="controls"><input type="search" id="v-eq" placeholder="Search tester, page or action" aria-label="Search tester, page or action"></div></div>
      <div class="tbl" style="max-height:28rem"><table id="v-events" data-source="visitors_events" data-row-key="id">
        <thead><tr><th data-field="t"><button>When</button></th><th data-field="tester"><button>Tester</button></th><th data-field="page"><button>Page</button></th><th data-field="event"><button>What</button></th><th data-field="detail"><button>Detail</button></th><th data-field="device"><button>Device</button></th></tr></thead><tbody></tbody></table></div>
    </div>
    <div class="card">
      <div class="head"><div><h3>Every page view</h3>"""),
    ('id="v-signups"', """    <div class="card">
      <div class="head"><div><h3>What testers did on the page</h3>""", """    <div class="card">
      <div class="head"><div><h3>Email sign-ups</h3><p class="muted">Weekly receipt and price alerts, newest first. Collected only; nothing is emailed until launch.</p></div></div>
      <div class="tbl" style="max-height:22rem"><table id="v-signups" data-source="visitors_signups" data-row-key="id">
        <thead><tr><th data-field="t"><button>When</button></th><th data-field="list"><button>List</button></th><th data-field="email"><button>Email</button></th><th data-field="what"><button>For</button></th><th data-field="page"><button>Signed up on</button></th></tr></thead><tbody></tbody></table></div>
    </div>
    <div class="card">
      <div class="head"><div><h3>What testers did on the page</h3>"""),
    ("rowsOf('visitors_events')", """    const q = ($('#v-q').value || '').trim().toLowerCase(), log = rowsOf('visitors_log');""",
     """    const eq = ($('#v-eq').value || '').trim().toLowerCase(), evs = rowsOf('visitors_events');
    T($('#v-events'), evs && evs.filter((r) => !eq || [r.tester, r.page, r.event, r.detail].join(' ').toLowerCase().includes(eq)),
      [{f: 't', fmt: when}, {f: 'tester'}, {f: 'page'}, {f: 'event'}, {f: 'detail'}, {f: 'device'}], {sort: 't', dir: -1});
    const q = ($('#v-q').value || '').trim().toLowerCase(), log = rowsOf('visitors_log');"""),
    ("rowsOf('visitors_signups')", """    const eq = ($('#v-eq').value || '').trim().toLowerCase(), evs = rowsOf('visitors_events');""",
     """    T($('#v-signups'), rowsOf('visitors_signups'), [{f: 't', fmt: when}, {f: 'list'}, {f: 'email'}, {f: 'what'}, {f: 'page'}], {sort: 't', dir: -1});
    const eq = ($('#v-eq').value || '').trim().toLowerCase(), evs = rowsOf('visitors_events');"""),
    ("$('#v-eq').addEventListener", """    $('#v-q').addEventListener('input', redraw); } redraw(); }};""",
     """    $('#v-q').addEventListener('input', redraw); $('#v-eq').addEventListener('input', redraw); } redraw(); }};"""),
]


def patch_control(d):
    """Visitors tab: in-page views grouped under their page, "What testers did on the page" and "Email sign-ups" tables.
    Each step is skipped once done; a missing anchor (the page was rebuilt differently) is reported, never fatal."""
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s0 = s = open(p, encoding='utf-8').read()
    for done, a, b in CTL:
        if done in s:
            continue
        if s.count(a) != 1:
            print('control center layout changed; a Visitors-tab step was skipped:', done)
            continue
        s = s.replace(a, b)
    if s != s0:
        open(p, 'w', encoding='utf-8').write(s)
        return True
    return False


# ---------------------------------------------------------------- deploy (same pull / deploy / save-back steps as procedure_pages.py)
def deploy():
    import boto3
    E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "CLOUDFLARE_API_TOKEN")}
    s3 = boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")
    B, KEY, d = E["R2_BUCKET"], 'site/deploy/current.tgz', '/tmp/home_v2'
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    etag = s3.head_object(Bucket=B, Key=KEY)['ETag']
    s3.download_file(B, KEY, f'{d}/site.tgz')
    s3.download_file(B, 'site/deploy/costs_state.json', f'{d}/costs_state.json')
    try:   # the Price Finder map's locations, for the story's map step
        cur = s3.get_object(Bucket=B, Key='site/every/CURRENT')['Body'].read().decode().strip()
        s3.download_file(B, f'site/every/{cur}/geo.json', f'{d}/geo.json')
    except Exception as e:
        print('no map locations; the story skips its map step:', e)
    with tarfile.open(f'{d}/site.tgz') as t:
        t.extractall(d, filter='fully_trusted')
    if not os.path.isfile(f'{d}/site/index.html') or not os.path.isfile(f'{d}/functions/_middleware.js'):
        sys.exit('STOP: current.tgz is missing site/ or functions/; nothing deployed')
    changed = patch_tracking(d)
    changed = patch_control(d) or changed
    changed = build(d) or changed
    if not changed:
        print('/v2/ and tracking already up to date; nothing to deploy')
        return
    if s3.head_object(Bucket=B, Key=KEY)['ETag'] != etag:
        sys.exit('STOP: the live site changed while this ran; nothing deployed. Run again.')
    env = dict(os.environ, **E, CLOUDFLARE_ACCOUNT_ID=E['R2_ACCOUNT_ID'])
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sitewide.py'), d], check=True)   # name, Units look, share image (Oct 18)
    r = subprocess.run(['npx', '--yes', 'wrangler@3.114.0', 'pages', 'deploy', 'site', '--project-name', 'upfront-dfw-preview', '--branch', 'main',
                        '--commit-dirty=true'], cwd=d, env=env, capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-1500:])
    if r.returncode != 0:
        sys.exit('deploy failed; the preview site is unchanged')
    if s3.head_object(Bucket=B, Key=KEY)['ETag'] != etag:
        sys.exit('STOP: the live site changed during the deploy; not saving back. Run again so both changes are kept.')
    os.remove(f'{d}/site.tgz')
    os.remove(f'{d}/costs_state.json')
    if os.path.isfile(f'{d}/geo.json'):
        os.remove(f'{d}/geo.json')
    with tarfile.open('/tmp/home_v2-site.tgz', 'w:gz') as t:
        for name in os.listdir(d):
            if name != '.wrangler':
                t.add(f'{d}/{name}', arcname=f'./{name}')
    s3.upload_file('/tmp/home_v2-site.tgz', B, KEY)
    print('deployed and saved to', KEY)


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == 'deploy':
        deploy()
    elif len(sys.argv) >= 3 and sys.argv[1] == 'build':
        c1 = patch_tracking(sys.argv[2]) | patch_control(sys.argv[2])
        c2 = build(sys.argv[2])
        print('changed' if c1 or c2 else 'unchanged')
    else:
        sys.exit(__doc__)
