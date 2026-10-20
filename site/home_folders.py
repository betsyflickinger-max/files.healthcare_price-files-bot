"""Folder view of the homepage (Oct 19, 2026), at /folders/ beside the current homepage so Betsy can switch between them.

The site's sections as a drawer of colored file folders: Prices and My plan up front, Hospitals & insurers in the middle,
the "check our work" folders (Price File Watch, The files, Newsroom) thinner at the back. Pointing at a folder pulls it up
and shows what's inside; clicking opens it as an open-folder spread. The Prices folder shows a real receipt: the same
procedure on the same plan at the lowest- and highest-priced places in DFW, from the same saved summaries the price pages
use (no estimates, every price linked to its file). The other folders hold words only, no figures.

The page is site/folders_template.html (the design, from Betsy's mockup) plus this file's data. home_v2.build() calls
build() on every run, and adds a "Try the folder view" switch to the current homepage, so both stay in step.
"""
import datetime
import html
import json
import os

MARK = '<!-- FOLDER-VIEW SWITCH (site/home_folders.py) -->'
SWITCH = (MARK + '<a href="/folders/" style="position:fixed;left:max(16px,env(safe-area-inset-left,0px));bottom:max(16px,env(safe-area-inset-bottom,0px));'
          'z-index:50;background:#F7C925;color:#151515;font:700 14px/1 system-ui,sans-serif;padding:11px 14px;text-decoration:none;'
          'box-shadow:0 2px 8px rgba(0,0,0,.25)">Try the folder view</a>\n')


def esc(s):
    return html.escape(str(s), quote=True)


def sig(a, b, c=''):
    return f'<div class="sig"><b>{a}</b><i>{b}</i>{c}</div>'


def prices_folder(S, money, plan_name, what_word, low):
    """The open Prices folder: a receipt of one real same-plan price gap, both prices linked to their files."""
    g = S['gap']
    lo, hi = g['lo'], g['hi']
    fee, extra = what_word(S)
    common = low(S['common'])
    x = hi['v'] / lo['v']
    plan = plan_name(lo)
    rc = ('<div class="rcpt" role="group" aria-label="Receipt">'
          '<div class="c hd">THE HEALTHCARE FILES</div>'
          f'<div class="c">Receipt · {esc(S["common"])}</div><div class="c">Dallas–Fort Worth</div>'
          f'<div class="c">Plan: {esc(plan)}</div><hr>'
          f'<div class="ln"><span>{esc(lo["name"])}</span><b>{money(lo["v"])}</b></div>'
          f'<div class="ln"><span>{esc(hi["name"])}</span><b>{money(hi["v"])}</b></div><hr>'
          f'<div class="ln tot"><span>Same plan</span><b>{x:.1f}× as much</b></div><hr>'
          f'<div class="c">Files dated {esc(lo["date"])}</div><div class="c">* {esc(fee.capitalize())} only *</div></div>')
    return {
        'rc': True,
        'l': (f'<h4>{esc(S["common"])}</h4><h4>Dallas–Fort Worth</h4><p>&nbsp;</p>'
              f'<p class="answer">Same plan, two places: {money(lo["v"])} or {money(hi["v"])}.</p>' + rc),
        'ls': sig('From the files', 'Insurer price files',
                  f'<a href="{esc(lo["url"])}" target="_blank" rel="noopener">file dated {esc(lo["date"])} ↗</a><br>'
                  f'<a href="{esc(hi["url"])}" target="_blank" rel="noopener">file dated {esc(hi["date"])} ↗</a>'),
        'strip': 'What it costs',
        'r': ('<p>Expect more than one bill.</p>'
              f'<p>These prices are {esc(fee)}. {esc(extra)}</p>'
              f'<p>Every {esc(common)} price in Dallas–Fort Worth is one click away.</p>'),
        'rs': sig('How to read this price', esc(fee.capitalize()), 'From the files hospitals and insurers have to publish'),
        'n': [['Pick your insurer’s network to see what it pays each place.', 'Tip', 'Price Finder'],
              ['Paying cash? Ask for the cash price in writing before you book.', 'Tip', 'Your rights']],
    }


WORDS = {   # folders that hold words only (no figures)
    'plan': {'l': ('<h4>What you’d owe</h4><p>&nbsp;</p><p class="answer">Pick your plan. We do the deductible math.</p>'
                   '<p>The Plan Calculator shows what you’d pay at each place on a HealthCare.gov plan.</p>'),
             'ls': sig('Plan Calculator', 'HealthCare.gov plans', 'Dallas–Fort Worth'),
             'strip': 'Your rights',
             'r': ('<p>Uninsured or paying cash? You can ask any provider for a good-faith estimate before your care.</p>'
                   '<p>If the bill comes in $400 or more above it, you can dispute it.</p>'),
             'rs': sig('No Surprises Act', 'Federal law', 'In effect since 2022'),
             'n': [['Emergency care out of network? You owe your in-network share.', 'Your rights', 'Surprise bills'],
                   ['Keep the estimate. You’ll need it to dispute.', 'Tip', 'Your rights']]},
    'watch': {'r': ('<p>Before anyone is named here, they get a notice and 10 business days to answer.</p>'
                    '<p>Their replies are printed beside their names.</p>')},
    'news': {'l': ('<h4>The story</h4><p>&nbsp;</p><p class="answer">What the files show, in seven steps.</p>'
                   '<p>Each step comes with the data behind it, so you can check our work.</p>'),
             'ls': sig('The story', 'Newsroom', 'From the price files'),
             'r': '<p>Found something wrong? We post corrections in public.</p>',
             'rs': sig('Corrections', 'Posted in public', 'Tell us what you found'),
             'n': [['Every figure links to the file it came from.', 'Our rule', 'Methodology'],
                   ['Want to know who runs this site?', 'About', 'Who we are']]},
}

FOLDERS = {   # what each folder links to (first link = the folder's main page)
    'prices': {'what': 'What a procedure costs, place by place', 'links': ['Look up a price', 'Price Finder', 'Start here'],
               'hrefs': ['/costs/', '/price-finder/', '/start-here/']},
    'plan': {'what': 'What you’d owe on your plan, and your rights', 'meta': 'HealthCare.gov plans in Dallas–Fort Worth',
             'links': ['Plan Calculator', 'Employer plans', 'Surprise bills'], 'hrefs': ['/plan-calculator/', '/employer-plans/', '/surprise-bills/']},
    'who': {'meta': 'Every fact linked to its public source', 'links': ['Hospitals', 'Insurers'], 'hrefs': ['/hospitals/', '/insurers/']},
    'watch': {'links': ['Price File Watch', 'Who isn’t publishing'], 'hrefs': ['/price-file-watch/', '/price-file-watch/']},
    'files': {'links': ['How we read the files', 'Corrections', 'About'], 'hrefs': ['/methodology/', '/corrections/', '/about/']},
    'news': {'meta': 'With the data behind every step', 'links': ['The story', 'About', 'Corrections'], 'hrefs': ['/story/', '/about/', '/corrections/']},
}


def build(site, S, money, plan_name, what_word, low, more=()):
    """Write site/folders/index.html and the switch on the current homepage. Returns True if anything changed."""
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'folders_template.html'), encoding='utf-8').read()
    f = {k: dict(v) for k, v in FOLDERS.items()}
    f['prices']['meta'] = f"Example: {low(S['common'])}, the same plan at two places"
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-5)))
    # receipts (Betsy, Oct 19: at least 5 good examples of the huge spread): the colonoscopy first, then the same widest
    # same-plan gaps the /v2/ hero uses, with a "Show me another" button on the receipt
    rcs = [prices_folder(x, money, plan_name, what_word, low) for x in [S, *more]]
    n = len(rcs)
    for i, r in enumerate(rcs):
        if n > 1:
            r['l'] += f'<p class="rc-nav"><button type="button" class="rc-next">Show me another</button> <span>{i + 1} of {n}</span></p>'
    data = {'date': today.strftime('%b %-d, %Y'), 'f': f, 'sp': dict(WORDS, prices=rcs[0]), 'receipts': rcs}
    # WORDS entries for watch only change part of a folder: merge onto the template's own words in the browser
    data['sp']['watch'] = {**data['sp']['watch'], '_merge': True}
    blob = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    page = tpl.replace('/*__DATA__*/null', blob, 1)
    page = page.replace('Object.assign(SP,FD.sp||{});', 'Object.keys(FD.sp||{}).forEach(k=>{SP[k]=FD.sp[k]._merge?Object.assign(SP[k],FD.sp[k]):FD.sp[k]});', 1)
    page = page.replace("drawer('prices');", "drawer('prices');var RI=0;document.addEventListener('click',function(e){if(!e.target.closest('.rc-next'))return;"
                        "RI=(RI+1)%FD.receipts.length;SP.prices=FD.receipts[RI];drawer('prices');var b=document.querySelector('.rc-next');if(b)b.focus()});", 1)
    page = page.replace('</style>', '.rc-nav{position:relative;z-index:3;margin:0 0 24px;max-width:40%;flex-wrap:wrap;display:flex;gap:10px;align-items:center;font:13px var(--type)}'
                        '.rc-next{font:700 14px var(--type);background:#151515;color:#FBFBF6;border:0;padding:8px 12px;cursor:pointer}'
                        '@media(max-width:760px){.rc-nav{max-width:none}}</style>', 1)
    out = os.path.join(site, 'folders', 'index.html')
    old = open(out, encoding='utf-8').read() if os.path.isfile(out) else ''
    changed = False
    if _strip_date(old) != _strip_date(page):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'w', encoding='utf-8').write(page)
        print('wrote site/folders/index.html')
        changed = True
    hp = os.path.join(site, 'index.html')
    home = open(hp, encoding='utf-8').read()
    if MARK not in home and '</body>' in home:
        open(hp, 'w', encoding='utf-8').write(home.replace('</body>', SWITCH + '</body>', 1))
        changed = True
    return changed


def _strip_date(s):
    """The build date alone doesn't count as a change (no redeploy just because the day turned over)."""
    import re
    return re.sub(r'"date": "[^"]*"', '', s)
