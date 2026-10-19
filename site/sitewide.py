"""Site-wide rules applied to the whole site tree right before every deploy (Oct 18, 2026).

  python site/sitewide.py DIR     (DIR holds site/ and functions/, like every deploy step)

0. Wordmark (Oct 19): "Files" is yellow on every page and the wordmark is lighter than the headings (BRAND_RX, EXTRA_CSS).
1. Name: the site is "The Healthcare Files" (Betsy, Oct 18). Any page or data file a builder made from an older
   template that still says "What It Costs" is renamed here, so no deploy path can bring the old name back.
2. Units look, built in: /units.css (the Units rules from /looks/looks.css, with their fonts) is linked from every
   page, and every page's <html> carries data-look="units" data-theme="light". The preview's look switcher
   (functions/_middleware.js, /looks/) is optional now: turning it off (LOOKS_OFF) or removing the password keeps Units.
3. Tagline (Oct 19): "The receipt for the U.S. healthcare system." replaces the older line on every page (OLD_TAGLINES).
4. Share image: site/assets/og.jpg (made from site/assets/og-source.html) is copied to /og.jpg.
Idempotent; only files that change are rewritten.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
NAME = 'The Healthcare Files'
OLD_TAGLINES = ['What care really costs, from the price files hospitals and insurers have to publish.']
TAGLINE = 'The receipt for the U.S. healthcare system.'   # Betsy, Oct 19: her Sept 30 framing, "the receipt for the U.S. healthcare system"
RENAME = [('What It <span>Costs</span>', 'The Healthcare <span>Files</span>'), ('What It Costs', NAME), ('WHAT IT COSTS', NAME.upper())]
LINK = '<link rel="stylesheet" href="/units.css">'
SRCJS = '<script src="/hcf-src.js" defer></script>'   # warns before a source link starts a giant file download (Oct 19)
# One wordmark on every page (Betsy, Oct 19): "Files" always yellow (tool pages, profiles and Price Finders had it plain),
# and lighter than the page headings so the name doesn't read as one more headline.
BRAND_RX = re.compile(r'(<a class="(?:sn-brand|brand)"[^>]*>)The Healthcare Files</a>')
BRAND_TO = r'\1The Healthcare <span>Files</span></a>'
EXTRA_CSS = '''
/* Oct 19, 2026 (Betsy): one wordmark everywhere, FILES in yellow, set apart from the page headings */
html[data-look="units"]:not(#_):not(#__) :is(.logo,.sn-brand,.brand){font:500 22px/1 "Look Hanken",sans-serif!important;text-transform:none!important;letter-spacing:0!important;color:#fff!important;white-space:nowrap;text-decoration:none}
html[data-look="units"]:not(#_):not(#__) :is(.logo,.sn-brand,.brand) span{font-weight:800;text-transform:uppercase;letter-spacing:.02em;color:#F7C925!important}
@media (max-width:480px){html[data-look="units"]:not(#_):not(#__) :is(.logo,.sn-brand,.brand){font-size:19px!important}}
/* Oct 19, 2026 (Betsy): prices stand out from the text around them (deep Units blue, 7:1 on the page ground) */
html[data-look="units"]:not(#_) :is(.price,.n,.tv,td.num[data-l="Lowest"],td.num[data-l="Highest"]){color:#1F45C4}
'''
# The look switcher was for choosing a look; Units is chosen (Oct 19), so the preview stops adding it (tester tracking stays).
MW_FROM = ("'<link rel=\"stylesheet\" href=\"/looks/looks.css\"><script src=\"/looks/looks.js\"></script>' + (tester ? "
           "'<style>.look-pick{display:none!important}</style><script src=\"/hcf-t.js\" defer></script>' : '')")
MW_TO = "(tester ? '<script src=\"/hcf-t.js\" defer></script>' : '')"
TEXT = ('.html', '.htm', '.webmanifest', '.xml', '.js', '.css', '.csv')   # not .txt/.json (price data); .csv only gets the name


def units_css(looks_css):
    """Top-level statements of looks.css that mention the Units look, plus the @font-face rules they use."""
    out, buf, depth = [], [], 0
    for ch in looks_css:
        buf.append(ch)
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                out.append(''.join(buf).strip()); buf = []
    keep = [st for st in out if 'data-look="units"' in st]
    fams = set(re.findall(r'"(Look [^"]+)"', ' '.join(keep)))
    faces = [st for st in out if st.startswith('@font-face') and any(f'"{f}"' in st for f in fams)]
    return ('/* The Healthcare Files: Units look, built into every page (made by site/sitewide.py from /looks/looks.css). */\n'
            + '\n'.join(faces + keep) + '\n' + EXTRA_CSS)


def bake(s):
    m = re.search(r'<html\b([^>]*)>', s[:4000], re.I)
    if not m:
        return s
    attrs = m.group(1)
    if 'data-look=' not in attrs:
        new = '<html' + attrs + ' data-look="units" data-theme="light" data-theme-by="look">'
        s = s[:m.start()] + new + s[m.end():]
    if LINK not in s:
        i = s.lower().find('</head>')
        if i >= 0:
            s = s[:i] + LINK + s[i:]
    if SRCJS not in s:
        i = s.lower().find('</head>')
        if i >= 0:
            s = s[:i] + SRCJS + s[i:]
    return s


def apply(d):
    site = os.path.join(d, 'site')
    looks = os.path.join(site, 'looks', 'looks.css')
    if os.path.exists(looks):
        css = units_css(open(looks, encoding='utf-8').read())
        p = os.path.join(site, 'units.css')
        if not os.path.exists(p) or open(p, encoding='utf-8').read() != css:
            open(p, 'w', encoding='utf-8').write(css)
    if os.path.isdir(site):
        shutil.copyfile(os.path.join(HERE, 'assets', 'hcf-src.js'), os.path.join(site, 'hcf-src.js'))
    og = os.path.join(HERE, 'assets', 'og.jpg')
    if os.path.exists(og) and os.path.isdir(site):
        shutil.copyfile(og, os.path.join(site, 'og.jpg'))
    changed = 0
    for root in (site, os.path.join(d, 'functions')):
        for dp, dn, fn in os.walk(root):
            if '.wrangler' in dp or os.path.join('site', 'looks') in dp:
                continue
            for f in fn:
                if not f.endswith(TEXT) or f == 'units.css':
                    continue
                p = os.path.join(dp, f)
                try:
                    s = open(p, encoding='utf-8').read()
                except UnicodeDecodeError:
                    continue
                t = s
                if 'What It' in t or 'WHAT IT COSTS' in t:
                    for a, b in RENAME:
                        t = t.replace(a, b)
                for old in OLD_TAGLINES:   # tagline swap (Oct 19) reaches pages built before the change
                    if old in t:
                        t = t.replace(old, TAGLINE)
                if 'The Healthcare Files</a>' in t:
                    t = BRAND_RX.sub(BRAND_TO, t)
                if f.endswith(('.html', '.htm')):
                    t = bake(t)
                if t != s:
                    open(p, 'w', encoding='utf-8').write(t); changed += 1
    mw = os.path.join(d, 'functions', '_middleware.js')
    if os.path.isfile(mw):
        t0 = open(mw, encoding='utf-8').read()
        if MW_FROM in t0:
            open(mw, 'w', encoding='utf-8').write(t0.replace(MW_FROM, MW_TO)); changed += 1
    try:   # Price File Watch: "Report it to CMS yourself" + private notes (Oct 19)
        import watch_extras
        changed += watch_extras.apply(d)
    except Exception as e:
        print(f'sitewide: Price File Watch additions not applied ({type(e).__name__}: {e})')
    try:   # Price Finder "Compare" view (Oct 19): its two files, the page tags, and ml.json where a rebuild made it stale
        import pf_table
        changed += pf_table.apply(d)
        if os.environ.get('R2_ACCESS_KEY_ID'):
            pf_table.write_ml(d, only_stale=True)
    except Exception as e:
        print(f'sitewide: Price Finder compare view not applied ({type(e).__name__}: {e})')
    print(f'sitewide: {changed} files updated (name, Units look, share image)')
    return changed


if __name__ == '__main__':
    apply(sys.argv[1])
