"""Site text from the Nov 7, 2026 research follow-ups. PREVIEW ONLY: nothing here is wired into a deploy.

Each function takes a page's HTML and returns it changed (or unchanged if its marker is already there, so it is safe to
run twice). site/research_preview.py applies them to a copy of the live pages and writes before/after files to
reports/research-preview/. To make them live later, Betsy moves the calls into site/ux_polish.py run() (methodology,
employer plans, insurer pages) and site/hospital_profiles.py (the quality strip).

  methodology(s)      "Contracted rates, not what was paid" and "Price and quality" notes, with sources
  employer_plans(s)   frames the Form 5500 employer plan lists as "which network files your plan uses"
  insurer_page(s)     the same framing on an insurer page's employer list
  quality_strip(rows) the CMS measures for one hospital as a labeled, unranked strip (rows from
                      reports/care-compare/dfw-measures.csv, site/care_quality_dfw.py)
  add_strip(s, strip) puts the strip right after the hospital page's "Medicare's quality rating" section
"""
import html
import re

E = html.escape
MARK = "<!-- RESEARCH-NOV7"


def _a(url, text):
    return f'<a href="{E(url)}" target="_blank" rel="noopener">{text} ↗</a>'


METHOD = f"""{MARK} (site/research_text.py) -->
<h2 id="contracted-not-paid">Contracted rates, not what was paid</h2>
<p>These are contracted rates, not what was paid. Many listed rates may never be used.</p>
<p>Insurers' files list a rate for every provider and service in a contract, including services a provider doesn't
offer. A study of 61 insurers' files found that 91.8% of listed rates were for providers unlikely to perform the
service (Muhlestein, <i>Health Affairs Scholar</i>, November 2025, {_a('https://pmc.ncbi.nlm.nih.gov/articles/PMC12631121/', 'study')}).
When Milliman compared Indiana claims with posted rates, about 21% of claim dollars matched a posted rate exactly
({_a('https://secure.in.gov/gov/files/EO-25-21-Memo,-Executive-Summary,-and-Study.pdf', 'Indiana study')}).</p>
<p>We keep every listed rate and link it to its file. Where a rate shows the usual signs of one that may never be used
(far from Medicare's rate, the same amount repeated, or one amount for many unrelated services), we label it
"may never be used". The label never removes or reorders a price.</p>
<h2 id="price-and-quality">Price and quality</h2>
<p>Studies find prices track hospital size and market power, and often show no link to quality (Harris and others,
<i>JBJS Open Access</i>, 2025, {_a('https://researchexperts.utmb.edu/en/publications/size-not-hospital-quality-and-performance-influences-commercial-p/', 'study')};
Wei and others, <i>Journal of the American Heart Association</i>, 2024, {_a('https://pmc.ncbi.nlm.nih.gov/articles/PMC11010067', 'study')}).
We show Medicare's quality measures next to prices as CMS publishes them. We don't combine them into a score or sort
by them.</p>
<!-- RESEARCH-NOV7:END -->
"""


def _before_end(s, block):
    for tag in ("</main>", "</article>", "</body>"):
        i = s.rfind(tag)
        if i > 0:
            return s[:i] + block + "\n" + s[i:]
    return s + block


def methodology(s):
    return s if MARK in s else _before_end(s, METHOD)


EMP_NOTE = (f'{MARK} --><p class="sub" data-research="framing"><b>What this shows.</b> Which network files your plan uses: '
            "the networks an insurer's index lists for the plan, and their listed rates. It does not show what the plan pays; "
            "a plan's own claims aren't public.</p>")
EMP_SWAPS = [
    ("<h1>Look up an employer's health plan</h1>", "<h1>Which network files your plan uses</h1>"),
    ("<h1>Look up an employer&#x27;s health plan</h1>", "<h1>Which network files your plan uses</h1>"),
    ("See its rates in the Dallas–Fort Worth Price Finder:", "Network files this plan uses, with their listed rates, in the Dallas–Fort Worth Price Finder:"),
]


def employer_plans(s):
    if MARK in s:
        return s
    for old, new in EMP_SWAPS:
        s = s.replace(old, new)
    i = s.find('<p class="lede">')
    if i > 0:
        j = s.find("</p>", i)
        s = s[:j + 4] + "\n  " + EMP_NOTE + s[j + 4:]
    return s


def insurer_page(s):
    if MARK in s:
        return s
    return re.sub(r"(Texas employers(?:'|&#x27;) health plans are named in this insurer(?:'|&#x27;)s price-file indexes)",
                  r"\1 (" + MARK + " -->which network files each plan uses, not what the plan pays)", s)


# ------------------------------------------------------------------ quality strip (one hospital page, preview only)
SHOW_HCAHPS = [("H_STAR_RATING", "Patient survey summary star"), ("H_HSP_RATING_9_10", "Rated the hospital 9 or 10"),
               ("H_RECMND_DY", "Would definitely recommend")]
GROUP_ORDER = ["group:MORT", "group:Safety", "group:READM", "group:Pt Exp", "group:TE"]


def quality_strip(rows):
    """rows: this hospital's rows from dfw-measures.csv. A labeled list in a fixed order (CMS's own groups), never ranked."""
    by = {r["measure_id"]: r for r in rows}
    star = by.get("overall_star")
    if not star:
        return ""
    def cell(r):
        if not r:
            return "<td>not in CMS's file</td><td></td>"
        v = r["value"]
        shown = (f"{v} of 5" if r["unit"] == "stars" else f"{v}%" if r["unit"].startswith("%") else E(v)) if v != "" else "not rated"
        note = E(r["not_rated_reason"]) if v == "" else E(r["cms_comparison"] or r["national_value"])
        return f"<td>{shown}</td><td class=\"sub\">{note}</td>"
    trs = [f"<tr><th scope=\"row\">Overall star rating</th>{cell(star)}</tr>"]
    for g in GROUP_ORDER:
        r = by.get(g)
        if r:
            name = r["measure_name"].split(":")[0]
            used = (r["national_value"] or "").replace("CMS uses ", "")
            v = f"{r['value']} of {used} measures reported" if r["value"] != "" else "none reported"
            trs.append(f"<tr><th scope=\"row\">{E(name)}</th><td>{E(v)}</td><td class=\"sub\">{E(r['cms_comparison'])}</td></tr>")
    for mid, label in SHOW_HCAHPS:
        r = by.get(mid)
        if r:
            trs.append(f"<tr><th scope=\"row\">{E(label)}</th>{cell(r)}</tr>")
    hc = next((by[m] for m, _ in SHOW_HCAHPS if m in by), None)
    flag = ('<p class="sub"><b>Fewer measures reported.</b> This hospital reported under half of the measures CMS uses '
            "for the star rating, so the rating (if any) rests on less information.</p>") if star.get("fewer_measures_reported") else ""
    period = f"Patient survey period: {E(hc['data_period'])}. " if hc else ""
    return (f'<section class="qstrip" data-research="quality-strip">{MARK} preview only -->\n'
            "<h2>Medicare quality measures</h2>\n"
            '<p class="sub">As CMS publishes them, in CMS\'s own groups. Not a score and not a ranking; we don\'t sort hospitals or '
            "prices by these.</p>\n" + flag +
            '<div class="tw"><table class="tbl"><thead><tr><th>Measure</th><th>This hospital</th><th>Compared with the nation (CMS)</th></tr></thead>'
            f"<tbody>{''.join(trs)}</tbody></table></div>\n"
            f'<p class="sub">{period}Source: {_a(star["source_link"], E(star["source_title"]))}, CMS release {E(star["cms_release"])}; '
            f'{_a(hc["source_link"], E(hc["source_title"])) if hc else ""}.</p>\n</section>')


def add_strip(s, strip):
    if not strip or 'data-research="quality-strip"' in s:
        return s
    m = re.search(r"<h2>Medicare(?:'|&#x27;)s quality rating</h2>", s)
    if m:
        j = s.find("</section>", m.end())
        if j > 0:
            return s[:j + 10] + strip + s[j + 10:]
    return _before_end(s, strip)
