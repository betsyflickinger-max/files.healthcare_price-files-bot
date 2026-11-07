"""Plain notes on pages that cover one area only (Nov 7, 2026; testers in Ohio, Houston and Atlanta used the Plan Calculator,
Hospitals and Employer Plans pages and got Dallas or Texas results with nothing saying so). Applied by sitewide.apply on
every deploy: one short note right under the page's main heading, once. Remove a page's line here when it covers more."""
import os
import re

STYLE = 'border-left:4px solid currentColor;padding:8px 12px;margin:12px 0 16px;font-weight:600;max-width:62ch'
NOTES = {
    'plan-calculator/index.html': "For now this covers Dallas–Fort Worth marketplace (HealthCare.gov) plans only. Somewhere else? "
                                  "Your area's Price Finder shows what each insurer pays; working out your own share there isn't ready yet.",
    'hospitals/index.html': "For now this lists Dallas–Fort Worth hospitals only. Other areas' hospitals and their prices are in each area's Price Finder.",
    'employer-plans/index.html': "For now this lists Texas employers only (from their federal Form 5500 filings).",
}


def apply(site):
    n = 0
    for rel, text in NOTES.items():
        p = os.path.join(site, rel)
        if not os.path.isfile(p):
            continue
        s = open(p, encoding='utf-8').read()
        if 'class="scope-note"' in s:
            continue
        m = re.search(r'</h1>', s, re.I)
        if not m:
            continue
        s = s[:m.end()] + f'<p class="scope-note" role="note" style="{STYLE}">{text}</p>' + s[m.end():]
        open(p, 'w', encoding='utf-8').write(s)
        n += 1
    return n
