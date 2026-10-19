"""Site-wide rules applied to the whole site tree right before every deploy (Oct 18, 2026).

  python site/sitewide.py DIR     (DIR holds site/ and functions/, like every deploy step)

1. Name: the site is "The Healthcare Files" (Betsy, Oct 18). Any page or data file a builder made from an older
   template that still says "What It Costs" is renamed here, so no deploy path can bring the old name back.
2. Units look, built in: /units.css (the Units rules from /looks/looks.css, with their fonts) is linked from every
   page, and every page's <html> carries data-look="units" data-theme="light". The preview's look switcher
   (functions/_middleware.js, /looks/) is optional now: turning it off (LOOKS_OFF) or removing the password keeps Units.
3. Share image: site/assets/og.jpg (made from site/assets/og-source.html) is copied to /og.jpg.
Idempotent; only files that change are rewritten.
"""
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'The Healthcare Files'
TAGLINE = 'What care really costs, from the price files hospitals and insurers have to publish.'
RENAME = [('What It <span>Costs</span>', 'The Healthcare <span>Files</span>'), ('What It Costs', NAME), ('WHAT IT COSTS', NAME.upper())]
LINK = '<link rel="stylesheet" href="/units.css">'
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
            + '\n'.join(faces + keep) + '\n')


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
    return s


def apply(d):
    site = os.path.join(d, 'site')
    looks = os.path.join(site, 'looks', 'looks.css')
    if os.path.exists(looks):
        css = units_css(open(looks, encoding='utf-8').read())
        p = os.path.join(site, 'units.css')
        if not os.path.exists(p) or open(p, encoding='utf-8').read() != css:
            open(p, 'w', encoding='utf-8').write(css)
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
                if f.endswith(('.html', '.htm')):
                    t = bake(t)
                if t != s:
                    open(p, 'w', encoding='utf-8').write(t); changed += 1
    print(f'sitewide: {changed} files updated (name, Units look, share image)')
    return changed


if __name__ == '__main__':
    apply(sys.argv[1])
