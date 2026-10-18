"""Page basics every page needs (Oct 18 pre-launch check): canonical URL, description, share tags (Open Graph and
Twitter) with the site's share image, favicon, and one line of site-information links (About, Methodology,
Disclaimers, Corrections, Privacy, Terms, Accessibility). Only ADDS what a page is missing; never changes what it has.

    import page_meta; html = page_meta.normalize(html, "costs/dallas-fort-worth/acl-reconstruction/index.html")
    python site/page_meta.py SITE_DIR [--skip hospitals/]     # every .html under SITE_DIR/site
"""
import html as H
import os
import re
import sys

BASE = "https://files.healthcare"
IMG = BASE + "/og.jpg"
DESC = {  # pages that had no description of their own
    "disclaimers/index.html": "What the prices on this site are and aren't: published rates from hospital and insurer files, not a quote or a bill, and not medical, legal or financial advice.",
    "corrections/index.html": "How to report a wrong price or fact, and how and when we correct it.",
    "privacy/index.html": "What this site collects when you use it, what it doesn't, and how long anything is kept.",
    "terms/index.html": "The terms for using this site and its data.",
    "accessibility/index.html": "How this site is built to be usable by everyone, and how to tell us when something isn't.",
    "copyright/index.html": "Who owns what on this site, and how you may reuse the data and text.",
    "404.html": "That page isn't here. Search a procedure or start from the home page.",
}
FOOT = [("/about/", "About"), ("/methodology/", "Methodology"), ("/disclaimers/", "Disclaimers"),
        ("/corrections/", "Corrections"), ("/privacy/", "Privacy"), ("/terms/", "Terms"), ("/accessibility/", "Accessibility")]


def url_for(rel):
    rel = rel.replace("\\", "/")
    if rel == "index.html":
        return BASE + "/"
    if rel.endswith("/index.html"):
        return BASE + "/" + rel[: -len("index.html")]
    return BASE + "/" + rel


def _get(s, rx):
    m = re.search(rx, s, re.I | re.S)
    return H.unescape(m.group(1)).strip() if m else ""


def normalize(s, rel):
    if "<head" not in s or "</head>" not in s:
        return s
    add = []
    title = _get(s, r"<title>(.*?)</title>")
    desc = _get(s, r'<meta name="description" content="([^"]*)"')
    if not desc and rel in DESC:
        desc = DESC[rel]
        add.append(f'<meta name="description" content="{H.escape(desc)}">')
    if rel != "404.html" and not re.search(r'rel="canonical"', s):
        add.append(f'<link rel="canonical" href="{url_for(rel)}">')
    if not re.search(r'property="og:title"', s) and title:
        add.append(f'<meta property="og:title" content="{H.escape(title)}">')
    if not re.search(r'property="og:description"', s) and desc:
        add.append(f'<meta property="og:description" content="{H.escape(desc)}">')
    if not re.search(r'property="og:url"', s) and rel != "404.html":
        add.append(f'<meta property="og:url" content="{url_for(rel)}">')
    if not re.search(r'property="og:type"', s):
        add.append('<meta property="og:type" content="website">')
    if not re.search(r'property="og:image"', s):
        add.append(f'<meta property="og:image" content="{IMG}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">')
    if not re.search(r'name="twitter:card"', s):
        add.append('<meta name="twitter:card" content="summary_large_image">')
    if not re.search(r'rel="icon"', s):
        add.append('<link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png">')
    if add:
        s = s.replace("</head>", "".join(add) + "</head>", 1)
    missing = [h for h, _ in FOOT if f'href="{h}"' not in s]
    if len(missing) >= 3 and 'class="pm-foot"' not in s and "</body>" in s:
        links = " · ".join(f'<a href="{h}">{t}</a>' for h, t in FOOT)
        foot = ('<nav class="pm-foot" aria-label="Site information" style="max-width:72ch;margin:24px auto 32px;padding:12px 16px 0;'
                'border-top:1px solid var(--rule,#d6cbb8);font-size:13.5px;text-align:center">' + links + "</nav>")
        i = s.rfind("</body>")
        s = s[:i] + foot + s[i:]
    return s


def run(site_dir, skip=()):
    n = 0
    for d, _, fs in os.walk(site_dir):
        for f in fs:
            if not f.endswith(".html"):
                continue
            p = os.path.join(d, f)
            rel = os.path.relpath(p, site_dir).replace("\\", "/")
            if any(rel.startswith(x) for x in skip) or rel.startswith(("control/", "looks/", "v2/")):
                continue
            s = open(p, encoding="utf-8").read()
            t = normalize(s, rel)
            if t != s:
                open(p, "w", encoding="utf-8").write(t)
                n += 1
    return n


if __name__ == "__main__":
    a = sys.argv[1:]
    skip = tuple(a[a.index("--skip") + 1].split(",")) if "--skip" in a else ()
    print(run(os.path.join(a[0], "site"), skip), "pages given missing basics")
