"""Price File Watch additions (Oct 19, 2026, Betsy), applied by site/sitewide.py before every deploy (idempotent).

1. "Report it to CMS yourself": the two official CMS complaint forms, on the public page (sources saved in
   Healthcare/research/CMS Complaint Routes/). The page doesn't say we've filed our own reports until Betsy has.
2. A private note (password notes, functions/api/watch-notes.js) on Aetna's unexplained low office-visit fees.
"""
import os

REPORT = '''<section id="report-cms" style="max-width:72ch;margin:32px 0;padding:20px 22px;background:#fff;border:2px solid #151515;border-left:8px solid #F7C925">
<p style="font:500 13px 'Look DM Mono',ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:#2E5BE6;margin:0 0 6px">Your turn</p>
<h2 style="margin:0 0 8px">Report it to CMS yourself</h2>
<p>Hospitals and insurers are required to post these files. CMS, the federal agency that enforces those rules, takes complaints from anyone: patients, employers, researchers. If a file on this page is missing, broken or out of date, or you couldn't find one yourself, you can tell CMS in a few minutes.</p>
<p style="display:flex;flex-wrap:wrap;gap:10px;margin:14px 0">
<a href="https://surveys.cms.gov/jfe/form/SV_5db4s0KOvVns5gy" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;min-height:44px;padding:0 16px;background:#151515;color:#fff;font-weight:700;text-decoration:none">Report a hospital to CMS ↗</a>
<a href="https://mats-cms-ccrms.my.salesforce-sites.com/pt" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;min-height:44px;padding:0 16px;background:#fff;color:#151515;border:2px solid #151515;font-weight:700;text-decoration:none">Report an insurer or health plan to CMS ↗</a>
</p>
<p style="font-size:15px;margin:0 0 6px"><b>What to include:</b> the hospital's or plan's name, the web page or file you tried, what was wrong (no file, a broken link, a file with no prices, or one that's out of date) and the date you checked. You're welcome to copy the wording and dates from our listing above.</p>
<p style="font-size:13.5px;color:#4A4A4A;margin:0">Both forms are run by CMS. CMS suggests asking an insurer first where its files are posted (<a href="https://www.cms.gov/priorities/healthplan-price-transparency/overview/use-pricing-information-published-under-transparency-coverage-final-rule" target="_blank" rel="noopener">CMS guidance</a>). Questions about hospital rules: <a href="https://www.cms.gov/hospital-price-transparency/contact-us" target="_blank" rel="noopener">CMS hospital price transparency contact page</a>.</p>
</section>
'''

NOTE = '''<div class="item" id="note-aetna-low-visits"><div>
  <h4>Aetna: office-visit fees far below Medicare, with no explanation in the file</h4>
  <div class="who">Dallas–Fort Worth · CPT 99213 (established patient, low complexity)</div>
  <p>Aetna lists about $25–$28 for a routine office visit for some DFW doctors, labeled only "fee schedule", in Choice POS II and the Texas HMO networks. That's about 0.3× Medicare's office rate ($94.96, Dallas) and under half Medicare's rate when the visit is in a hospital clinic ($57.37). The file gives no setting, modifier or note that would explain it. Separate from these: Aetna's Texas HMO networks also list $14.65 "derived" amounts at about 2,400 places, which are bookkeeping figures, not prices (labeled that way on the site).</p>
  <p>Possible questions for Aetna: is $28 the full fee for the visit, or part of a larger arrangement such as a per-patient monthly payment? If it's partial, why isn't it marked?</p>
  <div class="ev">Seen in the October 2026 DFW build (Price Finder, code 99213). Not on the public page.</div>
</div><span class="stamp s-note">Draft</span></div>
'''


def apply(d):
    n = 0
    p = os.path.join(d, 'site', 'price-file-watch', 'index.html')
    if os.path.isfile(p):
        s = open(p, encoding='utf-8').read()
        if 'id="report-cms"' not in s and '<section class="notes">' in s:
            s = s.replace('<section class="notes">', REPORT + '<section class="notes">', 1)
            open(p, 'w', encoding='utf-8').write(s); n += 1
    w = os.path.join(d, 'functions', 'api', 'watch-notes.js')
    if os.path.isfile(w):
        s = open(w, encoding='utf-8').read()
        anchor = '<h3>How we got around problems</h3>'
        if 'note-aetna-low-visits' not in s and anchor in s:
            s = s.replace(anchor, '<h3>Office-visit fees to ask about</h3>\n' + NOTE + anchor, 1)
            open(w, 'w', encoding='utf-8').write(s); n += 1
    return n
