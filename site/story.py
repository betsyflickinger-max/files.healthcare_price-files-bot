"""The story page (/story/), Oct 18, 2026: what a colonoscopy costs in Dallas–Fort Worth, told in 7 short steps.

One idea, one picture and one plain sentence per step (rules from Betsy's ADHD / autism / Montessori research canvas:
concrete before abstract, one idea per screen, show then tell, let people touch it, same shape = same meaning, say
exactly what you mean). The same colors mean the same thing everywhere: insurer rate = the site's accent (round dot),
cash price = orange (square), Medicare = grey (diamond, a yardstick). Nothing moves on its own; every picture has a
"Show as a table" switch; a sticky step bar shows where you are, with "Skip to search" always there.

Every figure is a real published price: the saved summaries (R2 site/deploy/costs_state.json) plus the DFW colonoscopy
page's own prices.csv (every line behind the page). Nothing estimated or averaged.

Built by site/home_v2.py (build/deploy) so it updates with the price pages.
"""
import csv
import html
import json
import os
import re

import home_bits
import visuals

esc = lambda s: html.escape(str(s if s is not None else ''), quote=True)
money = lambda v: '$' + f'{v:,.2f}'
short = lambda v: '$' + (f'{v:,.0f}' if v >= 100 else f'{v:,.2f}')
STEPS = ['Same plan, two hospitals', 'Every price, on one line', 'Your insurance changes it too', "It's not one bill",
         'What would you pay?', "Who's still hiding prices?", 'Now look up yours']


def src(url, date, text=None):
    return f'<a class="st-src" href="{esc(url)}" target="_blank" rel="noopener">{esc(text or ("file dated " + (date or "with no date")))} ↗</a>'


def plan(e):
    return f"{e['ins']} {e['plan']}".strip()


def rows_of(site, area_url, slug):
    p = os.path.join(site, 'costs', area_url, slug, 'prices.csv')
    if not os.path.isfile(p):
        return []
    r = list(csv.reader(open(p, encoding='utf-8')))
    return [dict(zip(r[1], x)) for x in r[2:] if len(x) == len(r[1])]


def table(head, rows, cap):
    return ('<details class="st-tbl"><summary>Show as a table</summary><table><caption>' + esc(cap) + '</caption><thead><tr>'
            + ''.join(f'<th>{esc(h)}</th>' for h in head) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></details>')


def chapter(i, kicker_extra, title, body):
    nxt = (f'<p class="st-next"><a href="#step{i + 2}" data-step="{i + 2}">Next: {esc(STEPS[i + 1])} ↓</a></p>' if i + 1 < len(STEPS) else '')
    return (f'<section class="st-ch" id="step{i + 1}" data-n="{i + 1}" aria-labelledby="sth{i + 1}"><div class="wrap">'
            f'<p class="kicker">Step {i + 1} of {len(STEPS)}{kicker_extra}</p><h2 id="sth{i + 1}">{title}</h2>{body}{nxt}</div></section>')


def ch1(S):
    g = S['gap']
    lo, hi = g['lo'], g['hi']
    unit = 250
    def stack(v, cls):
        n_full, part = int(v // unit), (v % unit) / unit
        bills = ''.join(f'<rect x="0" y="{-(k + 1) * 13}" width="120" height="10" rx="1"/>' for k in range(n_full))
        if part > 0.02:
            bills += f'<rect x="0" y="{-(n_full + 1) * 13}" width="{120 * part:.1f}" height="10" rx="1"/>'
        return f'<g class="{cls}">{bills}</g>', (n_full + 1) * 13
    a, ha = stack(lo['v'], 'st-bill')
    b, hb = stack(hi['v'], 'st-bill')
    H = max(ha, hb) + 10
    svg = (f'<svg class="st-stacks" viewBox="0 -{H} 320 {H + 4}" role="img" aria-label="Stacks of $250 bills: {short(lo["v"])} is about '
           f'{lo["v"] / unit:.1f} bills; {short(hi["v"])} is about {hi["v"] / unit:.1f} bills">'
           f'<g transform="translate(10,0)">{a}</g><g transform="translate(190,0)">{b}</g></svg>')
    x = hi['v'] / lo['v']
    body = (f'<div class="st-two"><div class="st-pic">{svg}<div class="st-legs"><p><b>{short(lo["v"])}</b>{esc(lo["name"])}<span>{esc(lo["city"])}</span></p>'
            f'<p><b>{short(hi["v"])}</b>{esc(hi["name"])}<span>{esc(hi["city"])}</span></p></div>'
            f'<p class="st-unit"><span class="st-swatch"></span> = $250</p></div>'
            f'<div class="st-say"><p class="st-big">{x:.1f}×</p><p>Same colonoscopy. Same insurance plan ({esc(plan(lo))}). '
            f'One hospital is paid <b>{x:.1f} times</b> what the other is paid.</p>'
            f'<p class="st-fine">These are facility fees: what the hospital gets for the room, staff and equipment. '
            f'Sources: {src(lo["url"], lo["date"])} · {src(hi["url"], hi["date"])}</p></div></div>'
            + table(['Hospital', 'City', 'Plan', 'Facility fee', 'Source'],
                    [[esc(e['name']), esc(e['city']), esc(plan(e)), money(e['v']), src(e['url'], e['date'])] for e in (lo, hi)],
                    'Same colonoscopy, same plan, two hospitals'))
    return chapter(0, '', 'Same plan. Two hospitals.', body)


def ch2(S, rows, med):
    ins = [r for r in rows if r['type'] == 'insurer rate']
    flat = {(n['ins'], n['plan']) for n in S['networks'] if n.get('flat') or n.get('par')}
    ins = [r for r in ins if (r['insurer'], r['network or label']) not in flat]
    cash = [r for r in rows if r['type'] != 'insurer rate']
    vs = sorted(float(r['price']) for r in ins)
    if not vs:
        return ''
    step = 500 if vs[-1] > 4000 else 250
    top = max(vs[-1], max((float(r['price']) for r in cash), default=0)) + step
    nb = int(top // step) + 1
    bins = [[] for _ in range(nb)]
    for r in ins:
        bins[int(float(r['price']) // step)].append(r)
    mx = max(len(b) for b in bins)
    W, Hh = 400, 200
    bw = W / nb
    bars = ''
    for k, b in enumerate(bins):
        if not b:
            continue
        h = max(2, len(b) / mx * Hh)
        lo_b = min(b, key=lambda r: float(r['price']))
        hi_b = max(b, key=lambda r: float(r['price']))
        lab = (f"{len(b):,} prices from ${k * step:,} to ${(k + 1) * step:,}. Lowest: {lo_b['provider']}, {money(float(lo_b['price']))} "
               f"({lo_b['insurer']} {lo_b['network or label']}). Highest: {hi_b['provider']}, {money(float(hi_b['price']))}.")
        bars += (f'<rect class="st-bin" tabindex="0" x="{k * bw + 1:.1f}" y="{Hh - h:.1f}" width="{bw - 2:.1f}" height="{h:.1f}" '
                 f'data-say="{esc(lab)}" data-lo="{esc(lo_b["source"])}" data-hi="{esc(hi_b["source"])}"><title>{esc(lab)}</title></rect>')
    ticks = ''.join(f'<text x="{(v / step) * bw:.1f}" y="{Hh + 18}" class="st-ax">${v // 1000}k</text>' for v in range(0, int(top), 1000))
    cash_marks = ''.join(f'<rect class="st-cash" x="{float(r["price"]) / step * bw - 4:.1f}" y="{Hh + 26 + (i % 3) * 9}" width="8" height="8">'
                         f'<title>Cash price {money(float(r["price"]))}: {esc(r["provider"])}</title></rect>' for i, r in enumerate(cash))
    meds = ''
    for v, lab in med:
        x = v / step * bw
        meds += (f'<g class="st-med"><line x1="{x:.1f}" x2="{x:.1f}" y1="0" y2="{Hh}"/><rect x="{x - 5:.1f}" y="-6" width="10" height="10" '
                 f'transform="rotate(45 {x:.1f} -1)"><title>Medicare, {esc(lab)}: {money(v)}</title></rect></g>')
    # like with like: hospital lines vs Medicare's hospital rate, surgery-center lines vs its surgery-center rate
    mm = dict((lab, v) for v, lab in med)
    over = tot = 0
    for r in ins:
        m = mm.get('hospital') if r['kind'] == 'hospital' else mm.get('surgery center') if r['kind'] == 'surgery center' else None
        if m:
            tot += 1
            over += float(r['price']) > 2 * m
    stat = (f'<p><b>{over:,} of {tot:,}</b> are more than double what Medicare pays the same kind of place.</p>' if tot else '')
    svg = (f'<svg class="st-hist" viewBox="-4 -14 {W + 8} {Hh + 60}" role="group" aria-label="{len(vs):,} insurer prices for a colonoscopy '
           f'in Dallas–Fort Worth, from {money(vs[0])} to {money(vs[-1])}, in ${step} steps. Tap a bar for details.">{bars}{meds}'
           f'<line x1="0" x2="{W}" y1="{Hh}" y2="{Hh}" class="st-axis"/>{ticks}{cash_marks}</svg>')
    tb = [[f'${k * step:,}–${(k + 1) * step:,}', f'{len(b):,}'] for k, b in enumerate(bins) if b]
    cc = (S['hcash'][0], 'hospital') if S.get('hcash') else None
    mh = (med[0][0], 'hospital outpatient, national rate') if med else None
    body = (f'<div class="st-say st-wide"><p>Each bar is a group of prices insurers agreed to pay DFW hospitals and surgery centers: '
            f'<b>{len(vs):,} prices</b>, from <b>{short(vs[0])}</b> to <b>{short(vs[-1])}</b>.</p>{stat}</div>'
            f'<div class="st-pic">{svg}<p class="st-tap" aria-live="polite">Tap a bar to see who is in it.</p>'
            f'<p class="st-keyrow"><span><i class="k-ins"></i>Insurer price</span><span><i class="k-cash"></i>Cash price (hospital files)</span>'
            f'<span><i class="k-med"></i>Medicare: ' + ' · '.join(f'{esc(l)} {short(v)}' for v, l in med) + ' (a yardstick, not a price you can get)</span></p></div>'
            f'<p class="st-fine">Every line behind this picture: <a href="/costs/dallas-fort-worth/colonoscopy/prices.csv">download all {len(vs):,} prices (CSV)</a>, each with its source file. '
            f'Networks that list the same amount at most places are left out of the picture.</p>'
            + visuals.word_cards(S, 'facility fee', mh, cc)
            + table(['Price range', 'How many prices'], tb, 'Colonoscopy facility fees in Dallas–Fort Worth, grouped'))
    return chapter(1, '', 'Every price, on one line', body)


def ch3(S, rows):
    sp = S.get('spread')
    if not sp:
        return ''
    flat = {(n['ins'], n['plan']) for n in S['networks'] if n.get('flat') or n.get('par')}
    best = {}
    for r in rows:
        if r['type'] == 'insurer rate' and r['provider'] == sp['name'] and r['city'] == sp['city'] and (r['insurer'], r['network or label']) not in flat:
            k = (r['insurer'], r['network or label'])
            if k not in best or float(r['price']) < float(best[k]['price']):
                best[k] = r
    nets = sorted(best.values(), key=lambda r: float(r['price']))
    if len(nets) < 3:
        return ''
    mx = float(nets[-1]['price'])
    bars = ''.join(f'<li><span class="st-n">{esc(r["insurer"])} <small>{esc(r["network or label"])}</small></span>'
                   f'<span class="st-bar"><i style="width:{float(r["price"]) / mx * 100:.1f}%"></i></span><b>{short(float(r["price"]))}</b></li>' for r in nets)
    x = float(nets[-1]['price']) / float(nets[0]['price'])
    body = (f'<div class="st-say st-wide"><p>At <b>{esc(sp["name"])}</b> in {esc(sp["city"])}, the colonoscopy facility fee depends on who is paying. '
            f'<b>{len(nets)} insurance networks</b>, from {short(float(nets[0]["price"]))} to {short(float(nets[-1]["price"]))}: '
            f'{x:.1f} times as much, in the same building.</p></div><ol class="st-bars">{bars}</ol>'
            + table(['Insurer', 'Network', 'Facility fee', 'Source'], [[esc(r['insurer']), esc(r['network or label']), money(float(r['price'])),
                     src(r['source'], r['file date'])] for r in nets], f'{sp["name"]}: colonoscopy facility fee by network'))
    return chapter(2, '', 'Your insurance changes it too', body)


def ch4(S, anes, path):
    def rng(s, doc=False):
        lo, hi = (s.get('doc_lo'), s.get('doc_hi')) if doc else (s.get('lo'), s.get('hi'))
        if not lo or not hi:
            return 'Ask for this one', ''
        return f'{short(lo["v"])}–{short(hi["v"])}', f'{src(lo["url"], lo["date"], "lowest")} · {src(hi["url"], hi["date"], "highest")}'
    slips = [('The place', 'Room, staff, equipment: the facility fee', rng(S), False),
             ('The doctor', 'Who does the colonoscopy', rng(S, True), False),
             ('Anesthesia', 'Often a separate company', rng(anes) if anes else ('Ask for this one', ''), False),
             ('Lab work', 'Only if tissue is sent to a pathologist', rng(path) if path else ('Ask for this one', ''), True)]
    out = ''.join(f'<div class="slip{" maybe" if m else ""}"><p class="slip-n">Bill {i + 1} of 4{" · maybe" if m else ""}</p><p class="slip-t">{esc(t)}</p>'
                  f'<p class="slip-w">{esc(w)}</p><p class="slip-v"><span>DFW RANGE</span><b>{esc(v)}</b></p>' + (f'<p class="slip-s">{s}</p>' if s else '') + '</div>'
                  for i, (t, w, (v, s), m) in enumerate(slips))
    body = ('<div class="st-say st-wide"><p>A colonoscopy usually comes as <b>3 or 4 separate bills</b>, often from different companies. '
            'Most price lists, including the big numbers above, show one bill at a time.</p></div>'
            f'<div class="slips">{out}</div><p class="st-fine">Ranges are the lowest and highest published in Dallas–Fort Worth for each bill. '
            'A <b>screening</b> colonoscopy is usually covered at no cost by most plans; these prices are for a <b>diagnostic</b> one (for symptoms or a follow-up).</p>')
    return chapter(3, '', "It's not one bill", body)


def ch5(S):
    g = S['gap']
    lo, hi = g['lo'], g['hi']
    body = (f'<div class="st-say st-wide"><p>Until you meet your deductible, you pay the whole negotiated price. Move the slider to your deductible '
            f'and see your share at the two hospitals from step 1.</p></div>'
            f'<form class="st-jar" onsubmit="return false" data-lo="{lo["v"]:.2f}" data-hi="{hi["v"]:.2f}">'
            f'<label for="stDed">Your deductible: <b id="stDedV">$3,000</b></label>'
            f'<input id="stDed" type="range" min="0" max="10000" step="250" value="3000">'
            f'<label for="stCo">After the deductible, you pay</label><select id="stCo"><option value="0">0%</option><option value="10">10%</option>'
            f'<option value="20" selected>20%</option><option value="30">30%</option><option value="40">40%</option></select>'
            f'<div class="st-jars"><div class="st-j"><svg viewBox="0 0 100 130" aria-hidden="true"><path class="jar" d="M20 10h60v8l8 10v95H12V28l8-10z"/>'
            f'<rect class="you" x="14" y="123" width="72" height="0"/></svg><p><b class="st-you">—</b> you pay<br><span>of {money(lo["v"])} at {esc(lo["name"])}</span></p></div>'
            f'<div class="st-j"><svg viewBox="0 0 100 130" aria-hidden="true"><path class="jar" d="M20 10h60v8l8 10v95H12V28l8-10z"/>'
            f'<rect class="you" x="14" y="123" width="72" height="0"/></svg><p><b class="st-you">—</b> you pay<br><span>of {money(hi["v"])} at {esc(hi["name"])}</span></p></div></div>'
            f'<p class="st-fine" aria-live="polite" id="stJarSay"></p></form>'
            '<p class="st-fine">Worked out in your browser; nothing is saved. Facility fee only (the doctor and anesthesia bill separately), '
            'and it assumes none of your deductible is used yet and leaves out your plan\'s out-of-pocket maximum.</p>')
    return chapter(4, '', 'What would you pay?', body)


def ch6(map_html, found, total):
    body = (f'<div class="st-say st-wide"><p>Since 2021, every U.S. hospital has had to post its prices in a file anyone can download. '
            f'We found files for <b>{found:,} of {total:,}</b> hospitals so far. Darker states have more hospitals posting.</p></div>'
            f'{map_html}<p class="st-next-alt"><a href="/price-file-watch/">Who isn\'t posting usable files, by name →</a></p>')
    return chapter(5, '', "Who's still hiding prices?", body)


def ch7(qbox, area_opts, chips, signup):
    body = (f'<form class="v2-find st-find" id="natForm" action="/costs/" method="get"><label for="natQ">What do you need?</label>'
            f'<div class="row">{qbox}<select id="natArea" aria-label="Where">{area_opts}</select><button type="submit">Show me</button></div>'
            f'<div class="v2-chips st-chips" aria-label="Popular">{chips}</div></form>'
            '<p class="msg" style="display:none" id="msg"></p><div id="homeChips" hidden></div><form id="searchForm" hidden><input id="q"></form>'
            + signup)
    return chapter(6, '', 'Now look up yours', body)


CSS = r'''
@media(max-width:1600px){.menu-btn{display:inline-block}.nav{display:none;position:absolute;left:0;right:0;top:100%;background:var(--board);flex-direction:column;align-items:stretch;padding:8px 16px 16px;border-bottom:3px solid var(--stamp)}.nav.open{display:flex}.nav a{padding:14px 4px;border-bottom:1px solid #6b3a3a}.nav .ask{margin-top:10px}}
.board .wrap{grid-template-columns:minmax(0,1fr)}
.story .v2-eyebrow{font:700 14px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:#F7C925;margin:0 0 14px}
.v2-find{display:grid;gap:10px;max-width:780px}.v2-find label{font:700 14px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--hi)}
.v2-find .row{display:flex;flex-wrap:wrap;gap:10px}.v2-find select{flex:1 1 200px;min-width:0;background:var(--paper);color:var(--ink);border:0;padding:14px 12px;font-size:18px;min-height:52px}
.v2-find button{background:var(--hi);color:#151515;border:0;padding:14px 22px;font-weight:800;min-height:52px;cursor:pointer;text-transform:uppercase;letter-spacing:.04em}
.v2-chips{display:flex;flex-wrap:wrap;gap:8px}.v2-chip{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;background:rgba(255,255,255,.12);color:var(--board-ink)!important;border:1px solid rgba(255,255,255,.45);text-decoration:none!important;font-weight:600;font-size:16px}
.v2-chip:hover,.v2-chip:focus-visible{background:var(--hi);color:#151515!important}
.st-find label{color:#F7C925}
.st-hero{padding:clamp(28px,6vw,60px) 0 clamp(22px,4vw,40px)}
.story .st-hero h1.letters{font-size:clamp(40px,7vw,84px)!important;line-height:1!important;margin:.1em 0 .25em}
.st-hero p{font-size:clamp(17px,2.2vw,21px);color:var(--board-sub);max-width:38em;margin:0}
.st-prog{position:sticky;top:0;z-index:20;background:var(--paper);border-bottom:2px solid var(--rule)}
.st-prog .wrap{display:flex;align-items:center;gap:12px;min-height:52px;flex-wrap:wrap;padding-top:6px;padding-bottom:6px}
.st-dots{display:flex;gap:6px;list-style:none;margin:0;padding:0}.st-dots a{display:block;width:26px;height:26px;border:2px solid var(--rule);font:700 12px/22px var(--mono);text-align:center;text-decoration:none;color:var(--ink)}
.st-dots a.seen{background:var(--ground)}.st-dots a[aria-current=step]{background:var(--ink);color:var(--paper)}
.st-now{font:600 15px var(--body);flex:1 1 160px}
.st-skip{min-height:40px;padding:0 14px;border:0;background:var(--hi);color:#151515;font:800 14px var(--body);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}
.st-ch{padding:clamp(40px,8vw,84px) 0;border-bottom:1px solid var(--rule)}.st-ch:nth-child(even){background:var(--ground)}
.st-ch h2{font-size:clamp(32px,5vw,54px);line-height:1;margin:4px 0 18px}
.st-two{display:grid;gap:24px;align-items:end}@media(min-width:860px){.st-two{grid-template-columns:1fr 1fr}}
.st-say{font-size:clamp(18px,2.2vw,21px);line-height:1.5;max-width:36em}.st-say p{margin:0 0 10px}.st-wide{max-width:44em}
.st-big{font:900 clamp(64px,11vw,120px)/1 var(--display)!important;color:var(--stamp);margin:0 0 6px!important}
.st-fine{font-size:15px;line-height:1.5;color:var(--muted);max-width:52em}.st-fine a,.st-src{color:inherit}
.st-src{font:13px var(--mono);white-space:nowrap}
.st-stacks{width:100%;max-width:340px;height:auto;display:block}.st-bill rect{fill:#3D8B5A;stroke:#1F4F31;stroke-width:1}
.st-legs{display:grid;grid-template-columns:1fr 1fr;gap:12px;max-width:340px;margin-top:8px}.st-legs p{margin:0;display:flex;flex-direction:column;font-size:14px}
.st-legs b{font:700 24px var(--mono)}.st-legs span{opacity:.75}
.st-unit{font:13px var(--mono);display:flex;align-items:center;gap:6px}.st-swatch{display:inline-block;width:28px;height:8px;background:#3D8B5A;border:1px solid #1F4F31}
.st-hist{width:100%;max-width:720px;height:auto;display:block;overflow:visible}.st-bin{fill:var(--stamp);cursor:pointer}.st-bin:hover,.st-bin:focus{fill:var(--ink);outline:none}
.st-axis{stroke:var(--ink);stroke-width:2}.st-ax{font:12px var(--mono);fill:var(--ink);text-anchor:middle}
.st-cash{fill:#C2571A}.st-med line{stroke:var(--muted);stroke-width:2;stroke-dasharray:5 4}.st-med rect{fill:var(--paper);stroke:var(--muted);stroke-width:2}
.st-med text{font:700 12px var(--mono);fill:var(--muted)}
.st-tap{min-height:3em;margin:8px 0 0;font-size:15px}
.st-keyrow{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:14px;margin:4px 0 0}.st-keyrow i{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:-1px}
.k-ins{background:var(--stamp);border-radius:50%}.k-cash{background:#C2571A}.k-med{border:2px solid var(--muted);transform:rotate(45deg);width:9px!important;height:9px!important}
.st-bars{list-style:none;margin:12px 0 0;padding:0;display:grid;gap:10px;max-width:760px}
.st-bars li{display:grid;grid-template-columns:minmax(120px,1.1fr) 2fr auto;gap:12px;align-items:center}
.st-n{font-weight:700;font-size:15px}.st-n small{display:block;font-weight:400}
.st-bar{height:22px;background:transparent;border-bottom:1px solid var(--rule)}.st-bar i{display:block;height:100%;background:var(--stamp);transform-origin:left;transition:transform .6s ease}
.st-bars li b{font:700 17px var(--mono)}
.st-ch:not(.seen) .st-bar i{transform:scaleX(.02)}
@media(prefers-reduced-motion:reduce){.st-bar i{transition:none}.st-ch:not(.seen) .st-bar i{transform:none}}
.st-jar{display:grid;gap:10px;max-width:640px}.st-jar label{font-weight:700}.st-jar input[type=range]{width:100%;min-height:44px;accent-color:var(--stamp)}
.st-jar select{min-height:44px;max-width:160px;font:inherit;border:2px solid var(--rule);background:var(--paper);color:var(--ink)}
.st-jars{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:8px}.st-j svg{width:100%;max-width:150px;display:block}
.st-j .jar{fill:var(--paper);stroke:var(--ink);stroke-width:3}.st-j .you{fill:var(--stamp)}.st-j p{margin:6px 0 0;font-size:15px}.st-j b{font:700 24px var(--mono)}
.st-tbl{margin-top:16px}.st-tbl summary{cursor:pointer;font-weight:700;min-height:44px;display:flex;align-items:center}
.st-tbl table{border-collapse:collapse;font-size:14px;margin-top:6px;background:var(--paper)}.st-tbl th,.st-tbl td{border:1px solid var(--rule);padding:6px 10px;text-align:left}
.st-tbl caption{text-align:left;font-weight:700;padding:4px 0}
.st-next{margin:26px 0 0}.st-next a,.st-next-alt a{font-weight:800;color:var(--stamp)}
.st-find{background:var(--board);padding:20px;margin-bottom:28px}
.story .nat-map svg{width:100%;max-width:680px;height:auto;display:block}.story .nat-map rect{stroke:var(--paper);stroke-width:2}
.story .nat-map .b0{fill:#D9CDB0}.story .nat-map .b1{fill:#B9A27E}.story .nat-map .b2{fill:#8A6A4E}.story .nat-map .b3{fill:#4A1C1C}.story .nat-map rect.live{stroke:var(--stamp);stroke-width:5}
.story .nat-map text{text-anchor:middle;pointer-events:none}.story .nat-map .st{font:700 14px var(--mono)}.story .nat-map .pc{font:11px var(--mono)}
.story .nat-map .b0+text,.story .nat-map .b0+text+text,.story .nat-map .b1+text,.story .nat-map .b1+text+text{fill:var(--ink)}.story .nat-map .b2+text,.story .nat-map .b2+text+text,.story .nat-map .b3+text,.story .nat-map .b3+text+text{fill:#FBF6EA}
.story .nat-key{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:14px;color:var(--muted);margin-top:10px}.story .nat-key i{display:inline-block;width:14px;height:14px;vertical-align:-2px;margin-right:6px}
.story .cap{font-size:13px;color:var(--muted)}
@media(max-width:600px){.st-bars li{grid-template-columns:1fr auto}.st-bars .st-bar{grid-column:1/-1;order:3}}
'''

JS = r'''<script>(function(){
var ch=[].slice.call(document.querySelectorAll('.st-ch')),dots=[].slice.call(document.querySelectorAll('.st-dots a')),now=document.querySelector('.st-now'),seen={};
function ev(o){try{window.hcfTrack&&window.hcfTrack(o)}catch(e){}}
function mark(n){dots.forEach(function(d,i){if(i+1===n)d.setAttribute('aria-current','step');else d.removeAttribute('aria-current');if(seen[i+1])d.classList.add('seen')});
var c=ch[n-1];if(now&&c)now.textContent='Step '+n+' of '+ch.length+': '+c.querySelector('h2').textContent}
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){var n=+e.target.dataset.n;
e.target.classList.add('seen');if(!seen[n]){seen[n]=1;ev({ev:'chapter',detail:n+' of '+ch.length+': '+e.target.querySelector('h2').textContent})}mark(n)}})},{rootMargin:'-40% 0px -50% 0px'});
ch.forEach(function(c){io.observe(c)})}else ch.forEach(function(c){c.classList.add('seen')});
document.addEventListener('click',function(e){var a=e.target.closest('a[href^="#step"]');if(a){e.preventDefault();var t=document.getElementById(a.getAttribute('href').slice(1));
if(t){t.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});var h=t.querySelector('h2');h.setAttribute('tabindex','-1');h.focus({preventScroll:true})}}});
var tap=document.querySelector('.st-tap');[].forEach.call(document.querySelectorAll('.st-bin'),function(b){function say(){tap.innerHTML='';tap.textContent=b.dataset.say+' ';
var a=document.createElement('a');a.href=b.dataset.lo;a.target='_blank';a.rel='noopener';a.textContent='lowest source ↗';var c=document.createElement('a');c.href=b.dataset.hi;c.target='_blank';c.rel='noopener';c.textContent='highest source ↗';
tap.appendChild(a);tap.appendChild(document.createTextNode(' · '));tap.appendChild(c);ev({ev:'tap',detail:'price bar: '+b.dataset.say.split('.')[0]})}
b.addEventListener('click',say);b.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();say()}})});
var J=document.querySelector('.st-jar');if(J){var lo=+J.dataset.lo,hi=+J.dataset.hi,D=document.getElementById('stDed'),C=document.getElementById('stCo'),V=document.getElementById('stDedV'),S=document.getElementById('stJarSay'),js=J.querySelectorAll('.st-j');
var m=function(v){return '$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})};
function you(p,d,c){return p<=d?p:d+(p-d)*c/100}
function draw(){var d=+D.value,c=+C.value;V.textContent='$'+d.toLocaleString('en-US');[[lo,js[0]],[hi,js[1]]].forEach(function(x){var y=you(x[0],d,c),r=x[1].querySelector('.you'),h=Math.max(0,y/hi*105);
r.setAttribute('height',h.toFixed(1));r.setAttribute('y',(123-h).toFixed(1));x[1].querySelector('.st-you').textContent=m(y)});
var a=you(lo,d,c),b=you(hi,d,c);S.textContent='At these settings you would pay '+m(a)+' at the first hospital and '+m(b)+' at the second: '+m(b-a)+' more for the same procedure on the same plan.'}
D.addEventListener('input',draw);C.addEventListener('change',draw);D.addEventListener('change',function(){ev({ev:'jar',detail:'deductible $'+D.value+', '+C.value+'%'})});draw()}
var pill=document.querySelector('.bar .start-pill');if(pill){pill.textContent='Find a price';pill.setAttribute('href','#step7')}
})();</script>'''


def section(summ, site, qbox, area_opts, chips, signup, map_html, found, total, home_js):
    S = summ['45378']
    rows = rows_of(site, 'dallas-fort-worth', 'colonoscopy')
    m = S.get('med') or {}
    med = [(v[0], lab) for v, lab in ((m.get('opps'), 'hospital'), (m.get('asc'), 'surgery center')) if v]
    dots = ''.join(f'<li><a href="#step{i + 1}" aria-label="Step {i + 1}: {esc(t)}">{i + 1}</a></li>' for i, t in enumerate(STEPS))
    chs = ch1(S) + ch2(S, rows, med) + ch3(S, rows) + ch4(S, summ.get('00811'), summ.get('88305')) + ch5(S) + ch6(map_html, found, total) + ch7(qbox, area_opts, chips, signup)
    return f'''<!-- NATIONAL:START --><!-- STORY (written by price-files-bot site/story.py via home_v2.py; edits here are replaced) -->
<style>{home_bits.HOME_CSS2}{visuals.CSS}{CSS}</style>
<section data-view="home" class="v2 story">
<div class="board"><div class="wrap"><div class="st-hero">
<p class="v2-eyebrow">The story, in {len(STEPS)} short steps</p>
<h1 class="letters">What does a colonoscopy <em>cost</em> in Dallas&ndash;Fort Worth?</h1>
<p>It depends on where you go, who's paying and how many bills you get. Here's how, one picture at a time, using real prices from the files.</p>
</div></div></div>
<nav class="st-prog" aria-label="Steps"><div class="wrap"><ol class="st-dots">{dots}</ol><span class="st-now" aria-live="polite">Step 1 of {len(STEPS)}: {esc(STEPS[0])}</span>
<a class="st-skip" href="#step{len(STEPS)}">Skip to search</a></div></nav>
{chs}
{visuals.JS}{JS}
{home_js}
</section>
<!-- NATIONAL:END -->'''
