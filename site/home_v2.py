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
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import procedure_pages as pp   # noqa: E402  (money, esc, slugs, area URLs: one set of rules for every page)

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


def section(summ, slugs, n_places, files_found, files_total, areas_opts, every):
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
                  f'<h2>One hospital. {sp["n"]} insurance networks. {pp.short_money(sp["lo"]["v"])} to {pp.short_money(sp["hi"]["v"])}.</h2>'
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
    sec = section(summ, slugs, n_places, int(found.group(1).replace(',', '')) if found else 0, int(found.group(2).replace(',', '')) if found else 0,
                  m.group(1) if m else '', every)
    page = re.sub(r'<!-- NATIONAL:START.*?<!-- NATIONAL:END -->', lambda _: sec, home, count=1, flags=re.S)
    if page == home:
        sys.exit('STOP: homepage has no NATIONAL block; /v2/ not written')
    page = page.replace('<title>', '<title>(v2) ', 1)
    out = os.path.join(site, 'v2', 'index.html')
    old = open(out, encoding='utf-8').read() if os.path.isfile(out) else ''
    if old == page:
        return False
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'w', encoding='utf-8').write(page)
    print('wrote site/v2/index.html')
    return True


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
    pv = os.path.join(d, 'site', 'privacy', 'index.html')
    if os.path.isfile(pv):
        s = open(pv, encoding='utf-8').read()
        a = 'we keep a simple record of which pages they view and when, so we can see what is useful.'
        b = ('we keep a simple record of which pages they view and when, what they tap or click, how far down a page they scroll, '
             'and their answer if they reply to a one-question survey, so we can see what is useful. We do not record what they type into search boxes.')
        if a in s:
            open(pv, 'w', encoding='utf-8').write(s.replace(a, b, 1))
            changed = True
    return changed


# ---------------------------------------------------------------- control center: show the tracker's data (Visitors tab)
CTL = [
    ("const sec = (p) => { const a = (p || '/').split('?')[0]; if (a === '/' || a === '') return 'Homepage';",
     "const sec = (p) => { const a = (p || '/').split('?')[0].split('#')[0]; if (a === '/' || a === '') return 'Homepage'; if (a === '/v2/') return 'Homepage v2';"),
    ("""    <div class="card">
      <div class="head"><div><h3>Every page view</h3>""", """    <div class="card">
      <div class="head"><div><h3>What testers did on the page</h3><p class="muted">Newest first: taps, searches, the guess game, how long they stayed and how far they scrolled, and answers to the homepage question "What were you hoping to find?". Collected since Oct 18, 2026.</p></div>
        <div class="controls"><input type="search" id="v-eq" placeholder="Search tester, page or action" aria-label="Search tester, page or action"></div></div>
      <div class="tbl" style="max-height:28rem"><table id="v-events" data-source="visitors_events" data-row-key="id">
        <thead><tr><th data-field="t"><button>When</button></th><th data-field="tester"><button>Tester</button></th><th data-field="page"><button>Page</button></th><th data-field="event"><button>What</button></th><th data-field="detail"><button>Detail</button></th><th data-field="device"><button>Device</button></th></tr></thead><tbody></tbody></table></div>
    </div>
    <div class="card">
      <div class="head"><div><h3>Every page view</h3>"""),
    ("""    const q = ($('#v-q').value || '').trim().toLowerCase(), log = rowsOf('visitors_log');""",
     """    const eq = ($('#v-eq').value || '').trim().toLowerCase(), evs = rowsOf('visitors_events');
    T($('#v-events'), evs && evs.filter((r) => !eq || [r.tester, r.page, r.event, r.detail].join(' ').toLowerCase().includes(eq)),
      [{f: 't', fmt: when}, {f: 'tester'}, {f: 'page'}, {f: 'event'}, {f: 'detail'}, {f: 'device'}], {sort: 't', dir: -1});
    const q = ($('#v-q').value || '').trim().toLowerCase(), log = rowsOf('visitors_log');"""),
    ("""    $('#v-q').addEventListener('input', redraw); } redraw(); }};""",
     """    $('#v-q').addEventListener('input', redraw); $('#v-eq').addEventListener('input', redraw); } redraw(); }};"""),
]


def patch_control(d):
    """Visitors tab: a "What testers did on the page" table and in-page views grouped under Homepage. Idempotent; a
    missing anchor (the page was rebuilt differently) is reported, never fatal."""
    p = os.path.join(d, 'site', 'control', 'index.html')
    if not os.path.isfile(p):
        return False
    s = open(p, encoding='utf-8').read()
    if 'id="v-events"' in s:
        return False
    for a, b in CTL:
        if s.count(a) != 1:
            print('control center layout changed; tracker table not added')
            return False
        s = s.replace(a, b)
    open(p, 'w', encoding='utf-8').write(s)
    return True


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
