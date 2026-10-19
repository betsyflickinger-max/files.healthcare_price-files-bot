"""Extras on every price page (/costs/<area>/<procedure>/), Oct 19, 2026. Added by site/home_v2.py after each daily build.

  - share card: a 1200x630 picture (share.png) with the page's lowest and highest published price, used as the page's
    og:image, so a link texted or posted shows the real numbers instead of the site-wide picture
  - "Before you book: what to ask": a short call script (insured and cash) plus the No Surprises Act good-faith-estimate
    right, with a copy button and the CMS source
  - "Out of every 100 prices here": 100 squares split by the page's own Medicare yardstick
  - the price map (Dallas–Fort Worth pages, where the Price Finder has locations): every place on a map of the metro,
    one insurance network at a time, prices labeled, ZIP lookup in the browser

Every figure comes from the page's own prices.csv (the same lines the page's figures use) and its Medicare figure.
"""
import html
import json
import os

esc = lambda s: html.escape(str(s if s is not None else ''), quote=True)
GFE_URL = 'https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights'
MARK_ASK, MARK_SQ, MARK_MAP = '<!-- ASK (site/page_extras.py) -->', '<!-- SQUARES (site/page_extras.py) -->', '<!-- PMAP (site/page_extras.py) -->'
FONT = [p for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf') if os.path.isfile(p)]
FONT_R = [p for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans.ttf') if os.path.isfile(p)]


def short(v):
    return '$' + (f'{v:,.0f}' if v >= 100 else f'{v:,.2f}')


# ---------------------------------------------------------------- share card
def share_card(path, what, area, lo, hi, n, site_name):
    """Write a 1200x630 PNG. Returns False if Pillow or a font isn't available (the page keeps the site-wide picture)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    if not FONT or not FONT_R:
        return False
    W, H = 1200, 630
    im = Image.new('RGB', (W, H), '#2E5BE6')
    d = ImageDraw.Draw(im)
    for i, c in enumerate(('#2E5BE6', '#F7C925', '#F08A24', '#3DB86B', '#E6402E')):
        d.rectangle([i * W // 5, 0, (i + 1) * W // 5, 14], fill=c)
    f = lambda s, b=True: ImageFont.truetype((FONT if b else FONT_R)[0], s)
    head = f'{what.upper()} · {area.upper()}'
    sz = 34
    while d.textlength(head, font=f(sz)) > W - 120 and sz > 20:
        sz -= 2
    d.text((60, 70), head, font=f(sz), fill='#F7C925')
    a, b = short(lo), short(hi)
    big = 150
    while d.textlength(f'{a} to {b}', font=f(big)) > W - 120 and big > 70:
        big -= 6
    y = 150
    d.text((60, y), a, font=f(big), fill='#FFFFFF')
    x = 60 + d.textlength(a + ' ', font=f(big))
    d.text((x, y + big * 0.42), 'to', font=f(int(big * 0.42)), fill='#DCE5FC')
    x += d.textlength('to ', font=f(int(big * 0.42))) + 12
    d.text((x, y), b, font=f(big), fill='#F7C925')
    d.text((60, y + big + 40), f'Same procedure, same area. {n:,} prices insurers agreed to pay,', font=f(30, False), fill='#FFFFFF')
    d.text((60, y + big + 82), 'straight from their own files.', font=f(30, False), fill='#FFFFFF')
    d.rectangle([0, H - 90, W, H], fill='#151515')
    d.text((60, H - 66), site_name.upper(), font=f(32), fill='#FFFFFF')
    d.text((W - 60 - d.textlength('files.healthcare', font=f(30, False)), H - 64), 'files.healthcare', font=f(30, False), fill='#F7C925')
    im = im.convert('P', palette=Image.ADAPTIVE, colors=64)
    im.save(path, optimize=True)
    return True


# ---------------------------------------------------------------- what to ask + your rights
def ask_block(name, code):
    cl = f'billing code {code}' if code else 'its billing code'
    ins = [f'I\'m scheduling a {name.lower()} ({cl}). Is your facility in-network for my plan, [your plan\'s name]?',
           f'What rate has my plan agreed to pay you for {code or "this code"}? (This page shows the published rates, so you can check.)',
           'Will the doctor, the anesthesia team and any lab or pathology also be in-network?',
           'Can you send that to me in writing?']
    cash = [f'What is your cash price for a {name.lower()} ({cl})?',
            'Does that include the doctor, anesthesia and any lab work, or are those billed separately?',
            'Please send me a good faith estimate in writing.']
    li = lambda xs: ''.join(f'<li>{esc(x)}</li>' for x in xs)
    plain = 'If you have insurance:\n' + '\n'.join(f'- {x}' for x in ins) + '\n\nIf you\'re paying cash:\n' + '\n'.join(f'- {x}' for x in cash)
    return (f'{MARK_ASK}<section class="sec hcf-ask2" aria-labelledby="hcfAskH"><p class="kicker">Before you book</p><h2 id="hcfAskH">What to ask when you call</h2>'
            '<div class="hcf-ask2-g"><div><h3>If you have insurance</h3><ol>' + li(ins) + '</ol></div>'
            '<div><h3>If you\'re paying cash</h3><ol>' + li(cash) + '</ol>'
            '<div class="hcf-right"><p class="hcf-right-k">Your right</p><p>If you don\'t have insurance or aren\'t using it, providers usually must give you a '
            '<b>good faith estimate</b> of the cost when you ask, or when you schedule care at least 3 business days ahead. If your bill comes in '
            '<b>at least $400 more</b> than the estimate, you may be able to dispute it.</p>'
            f'<p class="hcf-right-s">Source: <a href="{GFE_URL}" target="_blank" rel="noopener">CMS, Medical bill rights ↗</a></p></div></div></div>'
            f'<p><button type="button" class="hcf-copy" data-copy="{esc(plain)}">Copy these questions</button> <span class="hcf-copied" aria-live="polite"></span></p>'
            '<style>.hcf-ask2-g{display:grid;gap:22px}@media(min-width:800px){.hcf-ask2-g{grid-template-columns:1fr 1fr}}.hcf-ask2 h3{margin:0 0 6px;font-size:19px}'
            '.hcf-ask2 ol{margin:0;padding-left:22px;display:grid;gap:8px;font-size:16px;line-height:1.45}'
            '.hcf-right{margin-top:16px;padding:14px 16px;border:2px solid var(--ink);background:var(--paper)}.hcf-right p{margin:0 0 6px;font-size:15px;line-height:1.5}'
            '.hcf-right-k{font:700 12px var(--mono)!important;letter-spacing:.12em;text-transform:uppercase}.hcf-right-s{font-size:13px!important}'
            '.hcf-copy{min-height:44px;padding:0 16px;border:0;background:var(--ink);color:var(--paper);font:700 15px var(--body);cursor:pointer}</style>'
            '<script>(function(){var b=document.querySelector(".hcf-copy");if(!b)return;b.addEventListener("click",function(){var t=b.getAttribute("data-copy"),s=b.nextElementSibling;'
            '(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){s.textContent="Copied. Paste it in your notes or a text."},'
            'function(){s.textContent="Select the questions above to copy them."});try{window.hcfTrack&&window.hcfTrack({ev:"tap",detail:"copied call questions"})}catch(e){}})})();</script></section>')


# ---------------------------------------------------------------- 100 squares
def squares_block(pairs, note):
    """pairs: (price, Medicare yardstick for that kind of place). note: which Medicare rates were used, in words."""
    n = len(pairs)
    if n < 20:
        return ''
    c = [sum(1 for v, m in pairs if v <= m), sum(1 for v, m in pairs if m < v <= 2 * m), sum(1 for v, m in pairs if v > 2 * m)]
    raw = [x * 100 / n for x in c]
    k = [int(r) for r in raw]
    for i in sorted(range(3), key=lambda i: -(raw[i] - k[i]))[:100 - sum(k)]:
        k[i] += 1
    cells = ''.join(f'<i class="q{b}"></i>' for b in range(3) for _ in range(k[b]))
    lab = ['at or below Medicare', 'up to double Medicare', 'more than double Medicare']
    return (f'{MARK_SQ}<div class="hcf-sq"><p class="hcf-sq-k">Out of every 100 prices here</p><div class="hcf-sq-g" role="img" '
            f'aria-label="{k[0]} at or below Medicare, {k[1]} up to double, {k[2]} more than double">{cells}</div><ul>'
            + ''.join(f'<li><i class="q{b}"></i><b>{k[b]}</b> {lab[b]}</li>' for b in range(3))
            + f'</ul><p class="hcf-sq-s">Real counts: {c[0]:,}, {c[1]:,} and {c[2]:,} of {n:,} published prices, each against {esc(note)}.</p></div>'
            '<style>.hcf-sq{margin:14px 0 0;max-width:640px;padding:14px 16px;border:2px solid var(--ink);background:var(--paper);color:var(--ink)}'
            '.hcf-sq-k{margin:0 0 8px;font:700 13px var(--mono);letter-spacing:.1em;text-transform:uppercase}'
            '.hcf-sq-g{display:grid;grid-template-columns:repeat(20,1fr);gap:3px;max-width:420px}.hcf-sq-g i,.hcf-sq li i{display:block;aspect-ratio:1;border-radius:2px}'
            '.q0{background:#3D8B5A}.q1{background:#9DB6F5}.q2{background:#E6402E}.hcf-sq ul{list-style:none;margin:10px 0 0;padding:0;display:grid;gap:4px}'
            '.hcf-sq li{display:flex;align-items:center;gap:8px;font-size:16px}.hcf-sq li i{width:14px}.hcf-sq li b{font:700 20px var(--mono)}'
            '.hcf-sq-s{margin:8px 0 0;font-size:13px;line-height:1.45;opacity:.85}</style>')


# ---------------------------------------------------------------- price map (pages with locations)
def map_data(rows, flat, loc, med_by_kind):
    places, pidx, srcs, sidx, nets = [], {}, [], {}, {}
    for r in rows:
        if r.get('type') != 'insurer rate' or (r['insurer'], r['network or label']) in flat:
            continue
        k = (r['provider'], r['city'])
        if k not in loc:
            continue
        if k not in pidx:
            pidx[k] = len(places)
            kd = 'H' if r['kind'] == 'hospital' else 'A' if r['kind'] == 'surgery center' else 'O'
            places.append([r['provider'], r['city'], kd, round(loc[k][0], 5), round(loc[k][1], 5)])
        su = (r['source'], r['file date'])
        if su not in sidx:
            sidx[su] = len(srcs)
            srcs.append(list(su))
        cur = nets.setdefault(f"{r['insurer']} {r['network or label']}", {})
        v = float(r['price'])
        if pidx[k] not in cur or v < cur[pidx[k]][1]:
            cur[pidx[k]] = [pidx[k], v, sidx[su]]
    if len(places) < 5:
        return None
    lats = sorted(x[3] for x in places)
    lons = sorted(x[4] for x in places)
    q = lambda xs, f: xs[min(len(xs) - 1, int(f * len(xs)))]
    box = [q(lons, .03) - .05, q(lats, .03) - .05, q(lons, .97) + .05, q(lats, .97) + .05]
    order = sorted(nets, key=lambda k: (-len(nets[k]), k))
    return {'P': places, 'N': [[k, sorted(nets[k].values(), key=lambda e: e[1])] for k in order], 'U': srcs, 'M': med_by_kind, 'box': box}


def map_block(md, zips):
    if not md:
        return ''
    b = md['box']
    md = dict(md, Z={z: ll for z, ll in zips.items() if b[1] <= ll[0] <= b[3] and b[0] <= ll[1] <= b[2]})
    opts = ''.join(f'<option value="{i}">{esc(k)} ({len(v)} places)</option>' for i, (k, v) in enumerate(md['N']))
    data = json.dumps(md, separators=(',', ':')).replace('</', '<\\/')
    return (f'{MARK_MAP}<section class="sec hcf-pm"><p class="kicker">On the map</p><h2>Where is it cheaper near you?</h2>'
            '<p class="lede">Each dot is a place that lists this price. Bigger and redder means it\'s paid more. The 5 cheapest and 3 most expensive are labeled; tap any dot for its source.</p>'
            f'<div class="hcf-pm-c"><label for="hpNet">Insurance</label><select id="hpNet">{opts}</select>'
            '<label for="hpZip">Your ZIP code (optional)</label><input id="hpZip" inputmode="numeric" maxlength="5" placeholder="75201" autocomplete="postal-code">'
            '<label class="hcf-pm-chk"><input type="checkbox" id="hpAll"> Show every price (where they fit)</label></div>'
            '<div class="hcf-pm-m"><svg id="hpMap" viewBox="0 0 600 520" role="group" aria-label="Map of prices for this procedure"></svg></div>'
            '<p class="hcf-pm-k"><span><i class="q0"></i>At or below Medicare</span><span><i class="q1"></i>Up to double</span><span><i class="q2"></i>More than double</span>'
            '<span><i style="background:#B9B4A8"></i>No matching Medicare rate</span></p>'
            '<p class="hcf-pm-i" id="hpInfo" aria-live="polite">Tap a dot.</p><details><summary>Show as a list</summary><ol id="hpList" class="hcf-pm-l"></ol></details>'
            '<p class="cap">Locations: each place\'s public NPI address. Your ZIP stays in your browser. Medicare is like with like: hospitals against its hospital rate, surgery centers against its surgery-center rate.</p>'
            f'<script type="application/json" id="hpData">{data}</script>'
            '<style>.hcf-pm-c{display:grid;gap:6px;max-width:640px;margin:10px 0}.hcf-pm-c label{font-weight:700}.hcf-pm-c select{width:100%}'
            '.hcf-pm-c select,.hcf-pm-c input{min-height:46px;font:16px var(--body);border:2px solid var(--ink);background:var(--paper);color:var(--ink);padding:0 10px}'
            '.hcf-pm-c input{max-width:160px;font-family:var(--mono)}.hcf-pm-chk{display:flex;gap:8px;align-items:center;font-weight:400!important;min-height:44px}'
            '.hcf-pm-m{max-width:760px;border:2px solid var(--ink);background:#EDEAE2;overflow:hidden}.hcf-pm-m svg{display:block;width:100%;height:auto}'
            '.hcf-pm-k{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14px;margin:8px 0 0}.hcf-pm-k i{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px}'
            '.q0{background:#3D8B5A}.q1{background:#9DB6F5}.q2{background:#E6402E}.hcf-pm-i{min-height:3em;font-size:16px;line-height:1.5;max-width:760px}'
            '.hcf-pm-l{font-size:14px;line-height:1.6;padding-left:22px}</style><script src="/hcf-map.js" defer></script></section>')


MAP_JS = r"""/* Price map on price pages (site/page_extras.py, Oct 19, 2026). Data: #hpData. Basemap: /price-finder/basemap.json. */
(function(){var D=document.getElementById('hpData');if(!D)return;var d=JSON.parse(D.textContent),svg=document.getElementById('hpMap'),sel=document.getElementById('hpNet'),
zi=document.getElementById('hpZip'),info=document.getElementById('hpInfo'),list=document.getElementById('hpList'),allL=document.getElementById('hpAll');
var b=d.box,W=600,H=520,k=Math.cos((b[1]+b[3])/2*Math.PI/180),sc=Math.min(W/((b[2]-b[0])*k),H/(b[3]-b[1])),ox=(W-(b[2]-b[0])*k*sc)/2,oy=(H-(b[3]-b[1])*sc)/2;
function X(l){return ox+(l-b[0])*k*sc}function Y(l){return oy+(b[3]-l)*sc}var NS='http://www.w3.org/2000/svg';
function el(t,a,p){var e=document.createElementNS(NS,t);for(var x in a)e.setAttribute(x,a[x]);(p||svg).appendChild(e);return e}
function ev(o){try{window.hcfTrack&&window.hcfTrack(o)}catch(e){}}
var bg=el('g',{}),gd=el('g',{}),gl=el('g',{}),gy=el('g',{});function kk(){return Math.max(1,Math.min(1.8,600/(svg.getBoundingClientRect().width||600)))}
function path(rs){return rs.map(function(r){return 'M'+r.map(function(p){return X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1)}).join('L')}).join('')}
fetch('/price-finder/basemap.json',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(m){var f=kk();
(m.water||[]).forEach(function(w){el('path',{d:path(w.g)+'Z',fill:'#c9dcef'},bg)});(m.counties||[]).forEach(function(c){el('path',{d:path(c.g),fill:'none',stroke:'#cfc8b8'},bg)});
(m.roads||[]).forEach(function(r){if(r.c==='p')el('path',{d:path(r.t==='LineString'?[r.g]:r.g),fill:'none',stroke:'#fff','stroke-width':3},bg)});
(m.places||[]).slice(0,9).forEach(function(p){var x=X(p.lon),y=Y(p.lat);if(x>20&&x<W-20&&y>14&&y<H-6){var t=el('text',{x:x,y:y,'text-anchor':'middle','font-size':(11*f).toFixed(1),'font-weight':700,fill:'#6b665c'},bg);t.textContent=p.name.toUpperCase()}})}).catch(function(){});
var m$=function(v){return '$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})},COL=['#3D8B5A','#9DB6F5','#E6402E','#B9B4A8'];
function band(pl,v){var m=d.M[pl[2]];return !m?3:v<=m?0:v<=2*m?1:2}
var you=null;function mi(a,c){var R=3959,t=Math.PI/180,dl=(c[0]-a[0])*t,dn=(c[1]-a[1])*t,h=Math.sin(dl/2)*Math.sin(dl/2)+Math.cos(a[0]*t)*Math.cos(c[0]*t)*Math.sin(dn/2)*Math.sin(dn/2);return 2*R*Math.asin(Math.sqrt(h))}
function show(e){var pl=d.P[e[0]],u=d.U[e[2]],m=d.M[pl[2]];info.innerHTML='';var s=document.createElement('b');s.textContent=pl[0]+', '+pl[1];info.appendChild(s);
info.appendChild(document.createTextNode(': '+m$(e[1])+' from '+d.N[+sel.value][0]+(m?' ('+(e[1]/m).toFixed(1)+'× Medicare)':'')+(you?', '+mi(you,[pl[3],pl[4]]).toFixed(1)+' miles away':'')+'. '));
var a=document.createElement('a');a.href=u[0];a.target='_blank';a.rel='noopener';a.textContent='file dated '+(u[1]||'(no date)')+' ↗';info.appendChild(a);ev({ev:'tap',detail:'price map dot: '+pl[0]})}
function draw(){gd.innerHTML='';gl.innerHTML='';var es=d.N[+sel.value][1],mx=es[es.length-1][1],f=kk(),fs=12*f;
es.slice().sort(function(a,c){return c[1]-a[1]}).forEach(function(e){var pl=d.P[e[0]],c=el('circle',{cx:X(pl[4]).toFixed(1),cy:Y(pl[3]).toFixed(1),r:((4+11*Math.sqrt(e[1]/mx))*Math.sqrt(f)).toFixed(1),fill:COL[band(pl,e[1])],stroke:'#151515','stroke-width':1.2,tabindex:'0',style:'cursor:pointer'},gd);
var t=el('title',{},c);t.textContent=pl[0]+', '+pl[1]+': '+m$(e[1]);c.addEventListener('click',function(){show(e)});c.addEventListener('keydown',function(x){if(x.key==='Enter'||x.key===' '){x.preventDefault();show(e)}})});
var rows=es.map(function(e){var pl=d.P[e[0]];return {e:e,pl:pl,dist:you?mi(you,[pl[3],pl[4]]):null}});if(you)rows=rows.filter(function(r){return r.dist<=10});
var boxes=[],cand=[],done={};if(you)rows.slice(0,3).forEach(function(r){cand.push(r.e)});es.slice(0,5).forEach(function(e){cand.push(e)});es.slice(-3).reverse().forEach(function(e){cand.push(e)});if(allL.checked)es.forEach(function(e){cand.push(e)});
cand.forEach(function(e){if(done[e[0]])return;var pl=d.P[e[0]],x=X(pl[4]),y=Y(pl[3]),tx='$'+Math.round(e[1]).toLocaleString('en-US'),w=tx.length*fs*.62+8,h=fs*1.4,bx=x+9*f,by=y-h/2;
if(bx+w>W)bx=x-9*f-w;if(bx<0||by<0||by+h>H)return;for(var i=0;i<boxes.length;i++){var o=boxes[i];if(bx<o[0]+o[2]&&bx+w>o[0]&&by<o[1]+o[3]&&by+h>o[1])return}
boxes.push([bx,by,w,h]);done[e[0]]=1;var bd=band(pl,e[1]);el('rect',{x:bx.toFixed(1),y:by.toFixed(1),width:w.toFixed(1),height:h,fill:bd===2?'#E6402E':bd===0?'#E3F1E7':'#fff',stroke:'#151515'},gl);
var t=el('text',{x:(bx+4).toFixed(1),y:(by+h*.74).toFixed(1),'font-size':fs.toFixed(1),'font-family':'monospace','font-weight':700,fill:bd===2?'#fff':'#151515'},gl);t.textContent=tx});
list.innerHTML='';rows.forEach(function(r){var li=document.createElement('li');li.textContent=r.pl[0]+', '+r.pl[1]+' — '+m$(r.e[1])+(r.dist!=null?' · '+r.dist.toFixed(1)+' mi':'');list.appendChild(li)});
if(you){var n3=rows.slice(0,3);info.textContent=n3.length?'Cheapest within 10 miles on this insurance: '+n3.map(function(r){return r.pl[0]+' ('+m$(r.e[1])+', '+r.dist.toFixed(1)+' mi)'}).join('; ')+'.':'No places on this insurance within 10 miles of that ZIP. Try another insurance.'}}
sel.addEventListener('change',draw);allL.addEventListener('change',draw);
zi.addEventListener('input',function(){var z=zi.value.replace(/\D/g,'');gy.innerHTML='';you=null;if(z.length===5&&d.Z[z]){you=d.Z[z];el('circle',{cx:X(you[1]),cy:Y(you[0]),r:9,fill:'#F7C925',stroke:'#151515','stroke-width':2},gy);var t=el('text',{x:X(you[1])+12,y:Y(you[0])+4,'font-weight':800},gy);t.textContent='You';ev({ev:'tap',detail:'price map ZIP entered'})}else if(z.length===5)info.textContent='That ZIP is outside the map area.';draw()});
draw()})();
"""
