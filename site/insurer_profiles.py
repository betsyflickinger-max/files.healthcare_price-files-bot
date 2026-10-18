"""Insurer profile pages (/insurers/<slug>/): one page per parent insurer with Texas members, built only from public
records already in this project. Facts, not grades: every section names its source and when it was read.

  python site/insurer_profiles.py SITE_DIR        (SITE_DIR = a pulled site dir, the one that holds site/)
writes SITE_DIR/site/insurers/<slug>/index.html for each parent in PARENTS.

Inputs
  insurers/mlr/master_insurers.csv, parents.csv, site_insurers.json   CMS Medical Loss Ratio file, reporting year 2024
  site/insurers_page.py                                               the BLUE licensee map (one source of truth)
  SITE_DIR/site/price-finder/index.html                               DFW networks and codes priced (data block)
  insurers/networks.csv                                               date of each network's rate file we read
  SITE_DIR/site/employer-plans/employers.json                         Texas employers in insurer price-file indexes
  R2 data/idr/site/texas.json                                         No Surprises Act arbitration, Texas (nsa/arb_build.py)
"""
import csv
import collections
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "site"))
sys.path.insert(0, str(ROOT / "bot"))
import insurers_page  # noqa: E402

E = html.escape

# Parent insurers with members in Texas (MLR 2024 Texas filings, 10,000+ people), plus Elevance, whose Wellpoint
# marketplace network is in the DFW Price Finder.
PARENTS = ["Health Care Service Corp (HCSC)", "UnitedHealth Group", "Centene (Ambetter)", "CVS Health (Aetna)",
           "Baylor Scott & White Health Plan", "Cigna Group", "Oscar Health", "Community Health Choice, Inc.",
           "CHRISTUS HEALTH PLAN", "Curative Inc Grp", "US Health and Life Insurance Company", "Molina Healthcare",
           "Sendero Health Plans, inc.", "Memorial Hermann Commercial Health Plan", "Elevance Health (Anthem)"]
SHORT = {"Health Care Service Corp (HCSC)": "Health Care Service Corp (HCSC)", "CHRISTUS HEALTH PLAN": "CHRISTUS Health Plan",
         "Curative Inc Grp": "Curative", "Sendero Health Plans, inc.": "Sendero Health Plans", "Community Health Choice, Inc.": "Community Health Choice"}

MLR_PAGE = "https://www.cms.gov/marketplace/resources/data/medical-loss-ratio-data-systems-resources"
MLR_FILE = "https://www.cms.gov/files/zip/mlr-public-use-file-2024.zip"
MLR_READ = "2026-10-16"
IDR_PAGE = "https://www.cms.gov/nosurprises/policies-and-resources/Reports"
EMP_READ = "2026-10-17"      # Employer Plans page: "read October 17, 2026"

# Price Finder insurer key -> parent
PF_PARENT = {"Aetna": "CVS Health (Aetna)", "Ambetter": "Centene (Ambetter)", "BCBSTX": "Health Care Service Corp (HCSC)",
             "BSW Health Plan": "Baylor Scott & White Health Plan", "Cigna": "Cigna Group", "Curative": "Curative Inc Grp",
             "Molina": "Molina Healthcare", "Oscar": "Oscar Health", "UnitedHealthcare": "UnitedHealth Group",
             "Wellpoint": "Elevance Health (Anthem)"}
# Employer Plans insurer label -> parent
EMP_PARENT = {"UnitedHealthcare": "UnitedHealth Group", "Anthem": "Elevance Health (Anthem)", "Cigna": "Cigna Group",
              "Aetna": "CVS Health (Aetna)", "BCBS TX/IL/OK/NM/MT (HCSC)": "Health Care Service Corp (HCSC)"}
# Arbitration: plan email domains that clearly belong to the parent (others, e.g. repricers, are left out)
IDR_PARENT = {"bcbstx.com": "Health Care Service Corp (HCSC)", "bcbsil.com": "Health Care Service Corp (HCSC)",
              "aetna.com": "CVS Health (Aetna)", "uhc.com": "UnitedHealth Group", "cigna.com": "Cigna Group",
              "centene.com": "Centene (Ambetter)"}
# Price File Watch findings, in that page's words (site/price-file-watch/)
PFW = {
    "UnitedHealth Group": ("UnitedHealthcare of Texas (marketplace plans): its October 1, 2026 index lists seven networks, "
                           "including its Texas Provider Network, and every one has an empty in-network file list. "
                           "UnitedHealthcare's Choice Plus employer network does publish, and those rates are in our Price Finder.",
                           "re-checked October 11, 2026"),
    "Molina Healthcare": ("Molina Healthcare of Texas (marketplace plans): Molina's marketplace price page lists Texas with the note "
                          "“Table of Contents Update will appear soon.” The Texas index we read in August no longer loads, "
                          "and its file links now redirect.", "read October 11, 2026"),
    "Elevance Health (Anthem)": ("Wellpoint, Texas Essential plans: every plan points to one file. We found 1.9 million DFW rates in it "
                                 "for the 89 procedures we track. All of them are doctors' fees; none is a facility fee for a DFW "
                                 "hospital or surgery center.", "file dated September 1, 2026, read September 29, 2026"),
}


def slug(n):
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", str(n).lower().replace("&", " and ")))


def num(x):
    return f"{int(x):,}"


def day(iso):
    y, m, d = (int(v) for v in iso[:10].split("-"))
    return date(y, m, d).strftime("%B %-d, %Y")


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "—"


def blue_map():
    """The BLUE object in the Insurers page script: parent -> brand text, or 1 (parent name is the brand)."""
    t = insurers_page.TEMPLATE
    body = t[t.index("var BLUE={") + 10:t.index("};", t.index("var BLUE={"))]
    return {k: (v if v != "1" else 1) for k, v in re.findall(r"'([^']+)':(?:'([^']*)'|1)", body.replace("':1", "':'1'"))}


def tidy(x):
    up = {"LLC", "LP", "LLP", "PA", "PLLC", "USA", "II", "III"}
    return " ".join(w.upper() if w.upper().strip(",.") in up else w for w in str(x).title().replace(" -", " ").split())


def src(text):
    return f'<p class="src">Source: {text}</p>'


def load(site):
    R = list(csv.DictReader(open(ROOT / "insurers/mlr/master_insurers.csv")))
    P = {r["parent_group"]: r for r in csv.DictReader(open(ROOT / "insurers/mlr/parents.csv"))}
    S = {p["n"]: p for p in json.load(open(ROOT / "insurers/mlr/site_insurers.json"))}
    pf = open(site / "price-finder/index.html", encoding="utf-8").read()
    i = pf.index('<script type="application/json" id="data">') + len('<script type="application/json" id="data">')
    D = json.loads(pf[i:pf.index("</script>", i)])
    nets = collections.defaultdict(list)
    for n in D["nets"]:
        k, label = n.split("|", 1)
        if k in PF_PARENT:
            nets[PF_PARENT[k]].append((k, label, len(D["scope"].get(n, []))))
    fdates = collections.defaultdict(set)
    for r in csv.DictReader(open(ROOT / "insurers/networks.csv")):
        if r["last_updated_on"]:
            fdates[r["insurer"]].add(r["last_updated_on"])
    emp = collections.defaultdict(list)
    for r in json.load(open(site / "employer-plans/employers.json")):
        for k in r[3]:
            if k in EMP_PARENT:
                emp[EMP_PARENT[k]].append(r)
    import store
    s3, b = store.r2()
    T = json.loads(s3.get_object(Bucket=b, Key="data/idr/site/texas.json")["Body"].read())
    idr = collections.defaultdict(list)
    for row in T["insurers"]:
        if row[0] in IDR_PARENT:
            idr[IDR_PARENT[row[0]]].append(row)
    return R, P, S, nets, fdates, emp, idr, T


CSS = """
.prof h2{font:600 26px/1.15 var(--display);margin:40px 0 6px}
.prof .tags{display:flex;flex-wrap:wrap;gap:8px}
.prof section{border-top:2px solid var(--ink);margin-top:36px;padding-top:4px}
.prof section > p{max-width:70ch}
.prof .src{font-size:13px;color:var(--ink-2);margin:12px 0 0;max-width:76ch}
.prof .src a{color:inherit}
.stats{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}
.stat{padding:10px 14px;border:1.5px solid var(--ink);border-radius:2px;display:grid;gap:2px;min-width:150px}
.stat b{font:700 24px var(--type);font-variant-numeric:tabular-nums}
.stat span{font-size:13.5px;color:var(--ink-2)}
.tbl{width:100%;border-collapse:collapse;font-size:14.5px;margin-top:8px}
.tbl th{text-align:left;font:700 12px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);padding:6px 8px 6px 0;border-bottom:1.5px solid var(--ink)}
.tbl td{padding:8px 8px 8px 0;border-bottom:1px solid var(--rule);vertical-align:top}
.tbl td.n,.tbl th.n{text-align:right;font-family:var(--type);font-variant-numeric:tabular-nums;white-space:nowrap}
.tw{overflow-x:auto}
.note{padding:12px 14px;border:2px solid var(--ink);border-left-width:8px;max-width:72ch;margin:10px 0}
.back{display:inline-block;margin-top:18px;font-weight:600}
.prof > header{border-bottom:0}
"""


def page(name, R, P, S, nets, fdates, emp, idr, T, BLUE):
    p = S.get(name)
    tx = [r for r in R if r["parent_group"] == name and r["state"] == "TX"]
    title = SHORT.get(name, name)
    sec = []
    mutual = p and any("mutual" in c[0].lower() for c in p["c"])
    tags = []
    if name in BLUE:
        tags.append('<span class="tag blue">Blue Cross Blue Shield</span>')
    if mutual:
        tags.append('<span class="tag">Member-owned</span>')

    # Who it is
    who = []
    b = BLUE.get(name)
    if b:
        who.append(f"<p>{'Sells as <b>' + E(b) + '</b>. It is one' if b != 1 else 'One'} of the separate local companies the "
                   '<a href="https://www.bcbs.com/bcbs-companies-and-licensees" target="_blank" rel="noopener">Blue Cross Blue Shield '
                   "Association</a> licenses to use the Blue name.</p>")
    if mutual:
        who.append("<p>Its filing names it a mutual company: owned by its policyholders, with no stockholders.</p>")
    if p:
        who.append(f"<p>In the federal filings it is the parent of {num(len(p['c']))} insurance compan{'y' if len(p['c']) == 1 else 'ies'}, "
                   f"with members in {num(p['st'])} state{'' if p['st'] == 1 else 's'}. "
                   f'<a href="/insurers/#{slug(name)}">See its family tree</a>.</p>')
    if tx:
        rows = "".join(f"<tr><td>{E(r['issuer_name'])}</td><td class=\"n\">{num(float(r['total_lives'] or 0))}</td>"
                       f"<td>{'Yes' if r['not_for_profit'] == '1' else 'No'}</td></tr>" for r in sorted(tx, key=lambda r: -float(r['total_lives'] or 0)))
        who.append('<div class="tw"><table class="tbl"><thead><tr><th>Its companies filing in Texas</th><th class="n">People in Texas</th>'
                   f"<th>Filed as not-for-profit</th></tr></thead><tbody>{rows}</tbody></table></div>")
    else:
        who.append("<p>None of its companies reported fully insured members in Texas in the 2024 filings.</p>")
    who.append(src(f'CMS Medical Loss Ratio public use file, reporting year 2024 (<a href="{MLR_FILE}">file</a>, '
                   f'<a href="{MLR_PAGE}" target="_blank" rel="noopener">CMS page</a>) · read {day(MLR_READ)}'
                   + (" · Blue licensees: BCBS Association list" if b else "")))
    sec.append(("Who it is", "".join(who)))

    # Size in Texas
    if tx:
        ind, sg, lg = (sum(float(r[k] or 0) for r in tx) for k in ("individual_lives", "small_group_lives", "large_group_lives"))
        tot = ind + sg + lg
        stats = [(tot, "people in Texas"), (ind, "individual plans"), (sg, "small employer plans"), (lg, "large employer plans")]
        body = '<div class="stats">' + "".join(f'<div class="stat"><b>{num(v)}</b><span>{s}</span></div>' for v, s in stats) + "</div>"
        if p:
            body += f"<p>Across every state: {num(p['l'])} people in its fully insured plans.</p>"
        body += ('<p class="note"><b>Fully insured plans only.</b> These are people in plans where the insurance company pays the claims. '
                 "Self-funded employer plans it only runs, Medicare Advantage and Medicaid are not in these filings, so the company "
                 'reaches more people than this. <a href="/insurers/#counted">Why</a>.</p>')
        body += src(f'CMS Medical Loss Ratio public use file, reporting year 2024, people covered on December 31, 2024 · read {day(MLR_READ)}')
        sec.append(("Size in Texas", body))

    # Price files
    pr = P.get(name, {})
    page_url, note = pr.get("tic_landing_page", ""), pr.get("tic_note", "")
    body = ""
    if page_url and "HTTP 200" in note:
        body += f'<p>Its price-file page: <a href="{E(page_url)}" target="_blank" rel="noopener">{E(page_url)}</a>. We opened it on {day(MLR_READ)} and it loaded.</p>'
    elif page_url:
        body += (f'<p>Its price-file page: <a href="{E(page_url)}" target="_blank" rel="noopener">{E(page_url)}</a>. '
                 f"We couldn't re-open it on {day(MLR_READ)}: the site's security certificate setup blocked our check.</p>")
    elif note.startswith("not found"):
        body += f"<p>On {day(MLR_READ)}, its price-transparency pages returned “Page Not Found” or redirected to another page.</p>"
    else:
        body += "<p>We haven't recorded a price-file page for this company yet.</p>"
    if name in PFW:
        t, when = PFW[name]
        body += f'<p class="note"><b>On our <a href="/price-file-watch/">Price File Watch</a>.</b> {E(t)} ({E(when)})</p>'
    body += src(f"the insurer's own website, checked {day(MLR_READ)}" + (" · DFW Price File Watch" if name in PFW else ""))
    sec.append(("Price files", body))

    # Networks in the DFW Price Finder
    if nets.get(name):
        rows = "".join(f'<tr><td>{E(label)}</td><td class="n">{num(c)}</td></tr>' for _, label, c in nets[name])
        keys = sorted({k for k, _, _ in nets[name]})
        ds = sorted(d for k in keys for d in fdates.get(k, ()))
        when = (day(ds[0]) if ds[0] == ds[-1] else f"{day(ds[0])} to {day(ds[-1])}") if ds else ""
        body = ('<p>Its networks in our <a href="/price-finder/">Price Finder</a>, and how many billing codes have at least one '
                "published Dallas–Fort Worth rate in each.</p>"
                f'<div class="tw"><table class="tbl"><thead><tr><th>Network</th><th class="n">Codes with a DFW rate</th></tr></thead><tbody>{rows}</tbody></table></div>')
        body += src("the insurer's own in-network rate files (federal Transparency in Coverage rule)" + (f", dated {when}" if when else ""))
        sec.append(("Networks in Dallas–Fort Worth", body))

    # Arbitration
    if idr.get(name):
        q = T["src"]["quarters"]
        per = f"{q[0][:4]} Q{q[0][-1]} to {q[-1][:4]} Q{q[-1][-1]}"
        rows = "".join(f'<tr><td>@{E(d)}</td><td class="n">{num(disp)}</td><td class="n">{num(lines)}</td><td class="n">{pct(won, lines)}</td>'
                       f'<td class="n">{pct(sf, lines)}</td></tr>' for d, lines, disp, won, sf, _ in idr[name])
        body = ("<p>Texas surprise-bill disputes decided in federal No Surprises Act arbitration where the plan's side used this "
                f"company's email address, as reported to CMS, {per}.</p>"
                '<div class="tw"><table class="tbl"><thead><tr><th>Plan email domain</th><th class="n">Disputes</th><th class="n">Lines</th>'
                f'<th class="n">Provider\'s offer picked</th><th class="n">Self-funded plans</th></tr></thead><tbody>{rows}</tbody></table></div>'
                '<p>An award is the offer the arbitrator chose, not proof of payment. More on the <a href="/surprise-bills/">Surprise Bills</a> page.</p>')
        body += src(f'CMS federal independent dispute resolution public use files (<a href="{IDR_PAGE}" target="_blank" rel="noopener">CMS reports</a>) · read {day(T["src"]["checked"])}')
        sec.append(("Surprise-bill arbitration in Texas", body))

    # Employers
    if emp.get(name):
        rows_e = emp[name]
        fund = collections.Counter(r[4] for r in rows_e)
        top = sorted(rows_e, key=lambda r: -(r[5] or 0))[:8]
        body = (f"<p>{num(len(rows_e))} Texas employers' health plans are named in this insurer's price-file indexes"
                + ": " + "; ".join(f"{num(c)} {k.lower()}" for k, c in fund.most_common()) + ".</p>")
        body += ('<div class="tw"><table class="tbl"><thead><tr><th>Largest, by people in the plan</th><th class="n">People</th><th>Funding</th>'
                 "<th>Plan year</th></tr></thead><tbody>"
                 + "".join(f'<tr><td>{E(tidy(r[0]))}<div style="font-size:13px;color:var(--ink-2)">{E(r[1])}</div></td><td class="n">{num(r[5] or 0)}</td>'
                           f"<td>{E(r[4])}</td><td>{E(str(r[6]))}</td></tr>" for r in top)
                 + '</tbody></table></div><p>Search every employer on <a href="/employer-plans/">Employer Plans</a>.</p>')
        body += src(f"the insurer's price-file indexes and each employer's Form 5500 filing (U.S. Department of Labor) · read {day(EMP_READ)}")
        sec.append(("Texas employers whose plans use it", body))

    head = insurers_page.TEMPLATE[:insurers_page.TEMPLATE.index("</nav>") + 6]
    url = f"https://files.healthcare/insurers/{slug(name)}/"
    desc = f"{title}: public records on its Texas companies, members, price files, networks and surprise-bill arbitration."
    head = (head.replace('content="https://files.healthcare/insurers/"', f'content="{url}"')
            .replace("Who Owns Your Health Plan · What It Costs", f"{E(title)} · Insurer profile · What It Costs")
            .replace(head[head.index('<meta name="description" content="'):head.index('">', head.index('<meta name="description" content="')) + 2],
                     f'<meta name="description" content="{E(desc)}">')
            .replace("</style>\n</head>", CSS + "</style>\n</head>", 1))
    body = "".join(f'<section><h2>{E(h)}</h2>{b}</section>' for h, b in sec)
    return (head + f"""
<main class="prof">
<header>
  <div class="eyebrow">Insurer profile · public records only</div>
  <h1>{E(title)}</h1>
  <p class="lede">Everything here comes from public filings and the company's own files. Each section names its source and when we read it. Nothing is estimated or graded.</p>
  {'<div class="tags">' + "".join(tags) + '</div>' if tags else ''}
</header>
{body}
<a class="back" href="/insurers/#{slug(name)}">← Back to every insurer</a>
<p class="src" style="margin-top:28px">See something wrong? <a href="/corrections/">Report it</a>. Checked {day(date.today().isoformat())}.</p>
</main>
</div>
</body></html>
""")


def main(site_dir):
    site = Path(site_dir) / "site"
    R, P, S, nets, fdates, emp, idr, T = load(site)
    BLUE = blue_map()
    for name in PARENTS:
        out = site / "insurers" / slug(name)
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(page(name, R, P, S, nets, fdates, emp, idr, T, BLUE), encoding="utf-8")
    print(f"wrote {len(PARENTS)} insurer profiles under {site}/insurers/")


if __name__ == "__main__":
    main(sys.argv[1])
