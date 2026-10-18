"""Visual explainers on every price page (/costs/<area>/<procedure>/), Oct 18, 2026.

Three pieces, all built from figures already on the page (nothing estimated):
  - the price line: lowest and highest negotiated rate, lowest cash price and Medicare on one log-scale line, with a
    "how many times" headline and a "Got a quote?" box that drops the visitor's own number on the line (worked out in
    the browser; nothing is saved or sent)
  - bill slips: the separate bills a visitor should expect for this kind of service, as receipt slips; only this page's
    own figure and the doctor's published range (when the files have it) carry dollar amounts
  - word cards: the terms on the page, opened one at a time as a card (picture, word, meaning, what it means here)
Styled with the shared tokens in costs.css, so the site look (Units) carries over.
"""
import html
import math

esc = lambda s: html.escape(str(s), quote=True)


def _money(v):
    return f"${v:,.2f}"


def _times(x):
    return f"{x:.1f}" if x < 10 else f"{x:,.0f}"


ICON = {
    'negotiated': '<path d="M6 12h52v34H6z"/><path d="M6 22h52M14 32h18M14 39h10"/><path d="M38 52l6 6 12-12"/>',
    'facility': '<path d="M8 56V24l24-14 24 14v32z"/><path d="M26 56V40h12v16"/><path d="M32 18v10M27 23h10"/>',
    'cash': '<path d="M6 18h52v30H6z"/><circle cx="32" cy="33" r="8"/><path d="M12 24v18M52 24v18"/>',
    'medicare': '<path d="M6 46h52"/><path d="M14 46V30M24 46V22M34 46V34M44 46V18"/><path d="M28 12l4-4 4 4"/>',
    'deductible': '<path d="M18 12h28v6l4 6v30H14V24l4-6z"/><path d="M14 40h36"/>',
    'flat': '<path d="M8 32h48"/><path d="M8 22h48M8 42h48" stroke-dasharray="4 4"/>',
}


def word_cards(S, sg, mh, cc):
    lo = S.get('lo')
    cards = [('negotiated', 'Negotiated rate', 'The total an insurer agreed to pay this place. Until you meet your deductible, you pay all of it.',
              f"Here: the lowest is {_money(lo['v'])}." if lo else '')]
    if S.get('kind') == 'fac':
        cards.append(('facility', 'Facility fee', "What the hospital or surgery center charges for the room, staff, equipment and supplies. "
                      "The doctor's fee is a separate bill.", "Here: it's this page's main figure."))
    if cc:
        cards.append(('cash', 'Cash price', 'What a provider says it charges if you pay yourself, without insurance.',
                      f"Here: the lowest found is {_money(cc[0]['v'])}."))
    if mh:
        cards.append(('medicare', 'Medicare rate', "What Medicare pays for the same service. A yardstick for judging a price, not a price you can get. "
                      "Medicare adjusts its national rates for local wages and costs; facility fees here are shown at the national rate.",
                      f"Here: {_money(mh[0])} ({mh[1]})."))
    cards.append(('deductible', 'Deductible', 'What you pay each year before your plan starts sharing the cost. Until then, the negotiated rate is your bill.',
                  'Your plan documents or insurer app show yours.'))
    if any(n.get('flat') for n in S.get('networks') or []):
        cards.append(('flat', 'Flat rate', 'The same amount listed for many places in one network. It says little about what any one place charges.',
                      'Here: networks marked "same rate everywhere".'))
    chips = ''.join(f'<button type="button" class="wc-chip" data-wc="{k}">{esc(t)}</button>' for k, t, _, _ in cards)
    dlg = ''.join(
        f'<dialog class="wc" id="wc-{k}" aria-labelledby="wct-{k}"><p class="wc-n">Word card · {i + 1} of {len(cards)}</p>'
        f'<div class="wc-h"><svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">{ICON[k]}</svg>'
        f'<h3 id="wct-{k}">{esc(t)}</h3></div><p class="wc-m">{esc(m)}</p>' + (f'<p class="wc-here">{esc(h)}</p>' if h else '')
        + '<p class="wc-btns">' + (f'<button type="button" data-wc="{cards[i + 1][0]}">Next card: {esc(cards[i + 1][1].lower())} →</button>' if i + 1 < len(cards) else '')
        + '<button type="button" data-close>Close</button></p></dialog>'
        for i, (k, t, m, h) in enumerate(cards))
    return f'<div class="wc-row"><span>Words on this page:</span>{chips}</div>{dlg}'


def price_line(S, sg, mh, cc, med_asc):
    lo, hi = S.get('lo'), S.get('hi')
    if not lo:
        return ''
    pts = [(lo['v'], 'ins', f"lowest negotiated {sg}", f"{lo['name']}{', ' + lo['city'] if lo.get('city') else ''} · {lo['ins']}")]
    flat_hi = False
    if hi and S.get('lines', 0) > 1 and hi['v'] > lo['v']:
        flat_hi = any(n.get('flat') and n['ins'] == hi['ins'] and n['plan'] == hi['plan'] for n in S.get('networks') or [])
        pts.append((hi['v'], 'ins', f"highest negotiated {sg}", f"{hi['name']}{', ' + hi['city'] if hi.get('city') else ''} · {hi['ins']}"
                    + (' · same rate at many places' if flat_hi else '')))
    if cc:
        e = cc[0]
        pts.append((e['v'], 'cash', 'lowest cash price', f"{e['name']}" + ('' if cc[1] == 'posted' or e.get('date') else ' · no date in file')))
    meds = []
    if mh:
        meds.append((mh[0], mh[1]))
    if med_asc and (not mh or abs(med_asc - mh[0]) > 0.01):
        meds.append((med_asc, 'surgery center facility fee, national rate before local adjustment'))
    for v, lab in meds:
        pts.append((v, 'med', 'Medicare rate', f"{lab} · a yardstick, not a price you can get"))
    vals = [p[0] for p in pts if p[0] > 0]
    a, b = min(vals) * 0.8, max(vals) * 1.25
    la, lb = math.log10(a), math.log10(b)
    pos = lambda v: max(0.0, min(100.0, (math.log10(v) - la) / (lb - la) * 100))
    marks = ''.join(f'<span class="vr-m vr-{c}" style="left:{pos(v):.2f}%" title="{esc(_money(v))} {esc(t)}"></span>' for v, c, t, _ in pts if v > 0)
    key = ''.join(f'<li><span class="vr-k vr-{c}" aria-hidden="true"></span><b>{_money(v)}</b> {esc(t)}<span class="m">{esc(s)}</span></li>'
                  for v, c, t, s in sorted(pts, key=lambda p: p[0]))
    big = ''
    if hi and S.get('lines', 0) > 1 and hi['v'] / lo['v'] >= 1.5:
        big = (f'<div class="vr-big"><span class="vr-x">{_times(hi["v"] / lo["v"])}×</span><span>The highest negotiated {esc(sg)} here is about '
               f'{_times(hi["v"] / lo["v"])} times the lowest, for the same service in the same area.</span></div>')
    medv = meds[0][0] if meds else 0
    medl = meds[0][1] if meds else ''
    return (f'<section class="sec vis-range"><p class="kicker">The range at a glance</p>{big}'
            f'<div class="vr-line" role="img" aria-label="{esc("; ".join(_money(v) + " " + t for v, c, t, s in pts))}" '
            f'data-a="{a:.4f}" data-b="{b:.4f}" data-lo="{lo["v"]:.2f}" data-med="{medv:.2f}" data-medl="{esc(medl)}">'
            f'<span class="vr-axis"></span>{marks}<span class="vr-q" hidden><i></i><b>your quote</b></span></div>'
            f'<ul class="vr-key">{key}</ul>'
            f'<form class="vr-quote" onsubmit="return false"><label for="vrq">Got a quote? Put it on the line</label>'
            f'<div class="vr-in"><span>$</span><input id="vrq" type="number" min="1" step="any" inputmode="decimal" placeholder="1800"></div>'
            f'<p class="vr-say" aria-live="polite">Type the price you were quoted for the same {esc(sg)}. Worked out in your browser; nothing is saved or sent.</p></form>'
            f'{word_cards(S, sg, mh, cc)}</section>')


def bill_slips(S, sg, pf_path):
    lo = S.get('lo')
    cat, code = S.get('cat') or '', S.get('code') or ''
    this = (_money(lo['v']), 'lowest published') if lo else ('—', 'none published yet')
    doc = ((f"{_money(S['doc_lo']['v'])}–{_money(S['doc_hi']['v'])}", "the doctor's published range")
           if S.get('doc_lo') and S.get('doc_n', 0) > 1 else ('Ask for this one', ''))
    ask = ('Ask for this one', '')
    q = lambda w, t: f'<a href="{esc(pf_path)}?q={esc(w)}">{esc(t)} →</a>'
    if code.startswith('00'):
        slips = [('The anesthesia team', 'this page', this), ('The place', 'facility fee, a separate bill', ask), ('The doctor', 'who does the procedure', ask)]
    elif S.get('drg'):
        slips = [('The hospital stay', 'this page', this), ('The doctors', 'who see you in the hospital bill separately', ask),
                 ('Surgery and anesthesia', 'if you have an operation, they bill separately', ask)]
    elif S.get('kind') == 'doc':
        slips = [('The clinician', 'this page', this), ('A facility fee, maybe', 'only at clinics a hospital owns', ask)]
    elif cat == 'Imaging':
        slips = [('The place', f'{sg}, this page', this), ('The radiologist', 'who reads the scan', doc)]
    elif cat == 'Lab tests':
        slips = [('The lab', 'this page', this), ('Drawing the blood, maybe', 'sometimes a small separate charge', ask)]
    elif cat in ('Office visits', 'Behavioral health', 'Physical therapy', 'Heart'):
        slips = [('The place', f'{sg}, this page', this), ('The clinician', "the clinician's own fee", doc)]
    else:
        slips = [('The place', f'{sg}: room, staff, equipment', this), ('The doctor', 'who does the procedure', doc),
                 ('Anesthesia', 'often a separate company', ask + (q('anesthesia', 'Look up anesthesia prices'),)),
                 ('Lab work, maybe', 'only if tissue is sent to a pathologist', ask + (q('pathologist', 'Look up pathology prices'),))]
    n = len(slips)
    out = []
    for i, s in enumerate(slips):
        title, what, val = s
        maybe = 'maybe' in title.lower()
        link = val[2] if len(val) > 2 else ''
        out.append(f'<div class="slip{" maybe" if maybe else ""}"><p class="slip-n">Bill {i + 1} of {n}</p><p class="slip-t">{esc(title)}</p>'
                   f'<p class="slip-w">{esc(what)}</p><p class="slip-v"><span>{"TOTAL" if val[0].startswith("$") else "PRICE"}</span><b>{esc(val[0])}</b></p>'
                   + (f'<p class="slip-s">{esc(val[1])}</p>' if val[1] else '') + (f'<p class="slip-l">{link}</p>' if link else '') + '</div>')
    return (f'<section class="sec vis-bills"><p class="kicker">You\'ll likely get these bills</p><h2>Expect more than one bill</h2>'
            f'<p class="lede">Each slip is a separate bill, often from a different company. Prices on this site are one slip at a time.</p>'
            f'<div class="slips">{"".join(out)}</div></section>')


def sections(S, sg, pf_path, mh, cc):
    med_asc = ((S.get('med') or {}).get('asc') or [None])[0] if S.get('kind') == 'fac' else None
    return price_line(S, sg, mh, cc, med_asc) + bill_slips(S, sg, pf_path)


CSS = r'''
/* visual explainers (site/visuals.py) */
.vis-range .vr-big{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 20px;margin:4px 0 18px}.vr-x{font:900 clamp(56px,9vw,96px)/1 var(--display);color:var(--stamp)}
.vr-big>span:last-child{font-size:20px;line-height:1.4;max-width:34em}
.vr-line{position:relative;height:56px;margin:8px 10px 6px}.vr-axis{position:absolute;left:0;right:0;top:27px;height:3px;background:var(--ink)}
.vr-m{position:absolute;top:20px;width:16px;height:16px;margin-left:-8px}.vr-ins{border-radius:50%;background:var(--stamp)}
.vr-cash{background:#C2571A}.vr-med{width:12px;height:12px;top:23px;margin-left:-6px;border:2px solid var(--muted);background:var(--paper);transform:rotate(45deg)}
.vr-q{position:absolute;top:0;margin-left:-2px;display:flex;flex-direction:column;align-items:center}.vr-q i{display:block;width:4px;height:44px;background:var(--ink)}
.vr-q b{font:700 12px var(--mono);text-transform:uppercase;white-space:nowrap;margin-top:4px}
.vr-key{list-style:none;margin:28px 0 0;padding:0;display:grid;gap:8px 28px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.vr-key li{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;font-size:15px}.vr-key b{font:700 17px var(--mono)}.vr-key .m{flex-basis:100%;padding-left:24px}
.vr-k{display:inline-block;width:13px;height:13px;flex:none}.vr-k.vr-ins{border-radius:50%}.vr-k.vr-med{width:9px;height:9px}
.vr-quote{margin:22px 0 0;padding:16px 18px;background:var(--paper);border:2px solid var(--ink);display:grid;gap:8px;max-width:640px}
.vr-quote label{font:700 13px var(--mono);letter-spacing:.1em;text-transform:uppercase}.vr-in{display:flex;align-items:center;gap:8px;font:700 22px var(--mono)}
.vr-in input{width:200px;min-height:46px;border:2px solid var(--ink);padding:0 10px;font:700 20px var(--mono);background:var(--paper);color:var(--ink)}
.vr-say{margin:0;font-size:15px}
.wc-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:20px;font-size:15px}.wc-row>span{font-weight:700;margin-right:4px}
.wc-chip{min-height:40px;padding:0 12px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);font:inherit;cursor:pointer;text-decoration:underline dotted;text-underline-offset:4px}
.wc-chip:hover{background:var(--hi)}
dialog.wc{max-width:420px;width:calc(100% - 32px);border:2px solid var(--ink);padding:20px 22px;background:var(--paper);color:var(--ink);box-shadow:8px 8px 0 var(--ink)}
dialog.wc::backdrop{background:rgba(0,0,0,.35)}.wc-n{margin:0 0 8px;font:700 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.wc-h{display:flex;align-items:center;gap:14px;color:var(--stamp)}.wc-h h3{margin:0;color:var(--ink);font:800 28px/1.05 var(--display)}
.wc-m{font-size:17px;line-height:1.5;margin:12px 0 6px}.wc-here{margin:0;font:14px var(--mono);color:var(--muted)}
.wc-btns{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 0}.wc-btns button{min-height:44px;padding:0 14px;border:2px solid var(--ink);background:var(--paper);color:var(--ink);font:700 15px var(--body);cursor:pointer}
.wc-btns button[data-wc]{background:var(--ink);color:var(--paper)}
.slips{display:grid;gap:18px;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-top:6px;padding:6px 4px 10px}
.slip{background:var(--paper);color:var(--ink);font-family:var(--mono);padding:14px 16px 16px;border-bottom:3px dashed var(--ground);box-shadow:0 4px 0 -1px var(--rule);display:flex;flex-direction:column;gap:6px}
.slip:nth-child(odd){transform:rotate(-.8deg)}.slip:nth-child(even){transform:rotate(.7deg);margin-top:8px}
.slip.maybe{background:transparent;border:2px dashed var(--ink);box-shadow:none}
.slip p{margin:0}.slip-n{font-size:11px;letter-spacing:.12em;text-transform:uppercase;text-align:center;border-bottom:1px dashed var(--ink);padding-bottom:6px}
.slip-t{font-weight:700;font-size:16px;text-transform:uppercase}.slip-w{font-size:13px}.slip-v{display:flex;justify-content:space-between;gap:8px;border-top:1px dashed var(--ink);padding-top:6px;font-weight:700}
.slip-s{font-size:12px;opacity:.8}.slip-l a{font:700 13px var(--body);color:var(--stamp)}
@media(prefers-reduced-motion:reduce){.slip{transform:none!important}}
'''

JS = r'''<script>(()=>{const L=document.querySelector('.vr-line'),inp=document.getElementById('vrq');
if(L&&inp){const a=+L.dataset.a,b=+L.dataset.b,lo=+L.dataset.lo,med=+L.dataset.med,medl=L.dataset.medl,Q=L.querySelector('.vr-q'),say=document.querySelector('.vr-say'),first=say.textContent;
const f=x=>x<10?x.toFixed(1):Math.round(x).toLocaleString('en-US');
inp.addEventListener('input',()=>{const q=parseFloat(inp.value);if(!(q>0)){Q.hidden=true;say.textContent=first;return}
const p=Math.max(0,Math.min(100,(Math.log10(q)-Math.log10(a))/(Math.log10(b)-Math.log10(a))*100));Q.style.left=p+'%';Q.hidden=false;
say.textContent=q<=lo?'That is at or below the lowest negotiated rate published here.':'That is '+f(q/lo)+' times the lowest negotiated rate published here'+(med>0?', and '+f(q/med)+' times Medicare’s rate ('+medl+').':'.')})}
document.addEventListener('click',e=>{const o=e.target.closest('[data-wc]');if(o){const d=document.getElementById('wc-'+o.dataset.wc);if(d){const open=document.querySelector('dialog.wc[open]');if(open)open.close();d.showModal()}}
if(e.target.closest('[data-close]'))e.target.closest('dialog').close();if(e.target.matches('dialog.wc'))e.target.close()})})();</script>'''
