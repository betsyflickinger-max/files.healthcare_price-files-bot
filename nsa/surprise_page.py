"""The Surprise Bills page (/surprise-bills/): Texas No Surprises Act arbitration, from nsa/arb_build.py output.

  python nsa/surprise_page.py TEXAS_JSON ARB_TX_JSON PLANS_JSON MANIFEST_CSV OUT_DIR
writes OUT_DIR/index.html, OUT_DIR/plans.json (employer / plan search), OUT_DIR/providers.json (provider search).
Every number comes from the JSON files (counts, or CMS values taken at the middle rank). Nothing is averaged.
"""
import csv
import html
import json
import sys
from datetime import date
from pathlib import Path

E = html.escape
TYPE = {"Either partially or fully self-insured private (employment-based) group health plan": "Self-funded employer plan",
        "Fully insured private group health plan": "Fully insured employer plan",
        "Individual health insurance issuer": "Individual plan (e.g. HealthCare.gov)",
        "Non-federal government plan (or state or local government plan)": "State or local government plan",
        "Federal Employees Health Benefits (FEHB) Carrier": "Federal employee plan (FEHB)",
        "No Plan/Issuer Response": "Plan didn't say", "Church Plan": "Church plan"}
ER_LEVEL = {"99281": "Emergency room visit (may not need a doctor)", "99282": "Emergency room visit (straightforward)",
            "99283": "Emergency room visit (low complexity)", "99284": "Emergency room visit (moderate complexity)",
            "99285": "Emergency room visit (high complexity)"}
VISITS = ("99281", "99282", "99283", "99284", "99285", "99291", "99292")


def spec(x):
    return "specialty not reported" if str(x).strip() in ("N/R", "NR", "", "None", "N/A") else x


SHORT = {"fser": "freestanding ERs", "hosp": "hospitals", "erdoc": "ER doctor groups", "rad": "radiology", "anes": "anesthesia",
         "uc": "urgent care", "other": "other provider types"}


UPPER = {"ER", "LLC", "USA", "PLLC", "PA", "LP", "LLP", "WRFER", "II", "III"}


def tidy(x):
    return " ".join(w.upper() if w.upper().strip(",.") in UPPER else w for w in str(x).title().split())


def kind_tag(rows):
    """What the NPI registry lists for this domain's lines (primary taxonomy of each line's NPI), as a short tag."""
    tot = sum(c for _, c in rows)
    known = [(k, c) for k, c in rows if k != "unk"]
    kn = sum(c for _, c in known)
    if not tot:
        return ""
    if kn < tot / 2:
        return '<span class="ktag">most lines list no NPI</span>'
    parts = [f"{round(100 * c / kn)}% {SHORT.get(k, k)}" for k, c in known[:2] if c / kn >= .15]
    fser = known[0][0] == "fser"
    return (f'<a class="ktag{" k-fser" if fser else ""}" href="#freestanding-er">' if fser else '<span class="ktag">') + \
        "Registry: " + " · ".join(parts) + ("</a>" if fser else "</span>")


def n(x):
    return f"{x:,}"


def money(x):
    return "—" if x is None else f"${x:,.2f}"


def pct(a, b):
    return f"{round(100 * a / b)}%" if b else "—"


def qtr(q):
    y, k = q.split("-q")
    return f"Q{k} {y}"


def long_date(d):
    d = date.fromisoformat(d)
    return f"{d:%B} {d.day}, {d.year}"


def main(texas, arb, plans, manifest, out):
    T = json.load(open(texas)); A = json.load(open(arb)); P = json.load(open(plans))
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    urls = {}
    for r in csv.DictReader(open(manifest)):
        if r.get("kind") == "puf" and r.get("period"):
            urls[r["period"]] = r["url"]
    tot = T["totals"]; q = T["src"]["quarters"]; per = f"{qtr(q[0])} to {qtr(q[-1])}"
    checked = long_date(T["src"]["checked"])
    tx_share = pct(tot["tx_lines"], tot["us_lines"])
    na = tot["tx_lines"] - tot["tx_won"] - tot["tx_plan_won"]
    board = T["dfw_board"]
    for b in board:                      # CPT's own wording for ER visit levels (2023 descriptors: medical decision making)
        if b["code"] in ER_LEVEL:
            b["name"] = ER_LEVEL[b["code"]]
    er = next((b for b in board if b["code"] == "99284"), board[0])
    self_funded = next((r for r in T["plan_types"] if r[0].startswith("Either partially")), [None, 0, 0])

    # ---------------------------------------------------------------- sections
    rows_dfw = "".join(
        f"<tr><td><b>{E(b['name'])}</b><div class=\"meta\">CPT {E(b['code'])}</div></td><td>{n(b['n'])}</td>"
        f"<td>{money(b['plan'])}</td><td>{money(b['qpa'])}</td><td>{money(b['prov'])}</td><td class=\"hi\">{money(b['award'])}</td>"
        f"<td>{pct(b['won'], b['n'])}</td></tr>" for b in board[:15])
    trend_max = max(r[1] for r in T["trend"])
    trend = "".join(
        f"<div class=\"tr\"><span class=\"tq\">{qtr(p)}</span><span class=\"tb\"><i class=\"a\" style=\"width:{100 * t / trend_max:.2f}%\"></i>"
        f"<i class=\"b\" style=\"width:{100 * (u - t) / trend_max:.2f}%\"></i></span><span class=\"tn\">{n(t)} <small>of {n(u)}</small></span></div>"
        for p, u, t in T["trend"])
    states = " · ".join(f"{E(s)} {n(c)}" for s, c in tot["states"])
    FK = T.get("filer_kinds") or {}
    filers = "".join(
        f"<tr><td><b>{E(d)}</b><div class=\"meta\">{E(spec(sp))}</div>{kind_tag(FK.get(d) or [])}</td><td>{n(npis)}</td><td>{n(disp)}</td><td>{n(lines)}</td><td>{pct(won, lines)}</td></tr>"
        for d, lines, disp, won, npis, sp in T["filers"][:12])
    fser = ""
    if T.get("fser_top"):
        ft, fn_ = T["fser_total"]
        fser_rows = "".join(f"<tr><td><b>{E(tidy(nm))}</b><div class=\"meta\">{E(tidy(city))} · filed through {E(dom)}</div></td><td>{n(dp)}</td><td>{n(ln)}</td></tr>"
                            for nm, city, ln, dp, dom in T["fser_top"])
        fser = FSER.replace("{{FT}}", n(ft)).replace("{{FN}}", n(fn_)).replace("{{FS}}", pct(ft, tot["tx_lines"])).replace("{{FROWS}}", fser_rows).replace("{{PER}}", per)
    groups = "".join(
        f"<tr><td><b>{E(g)}</b><div class=\"meta\">{E(spec(sp))} · {E(dom)}</div></td><td>{n(disp)}</td><td>{n(lines)}</td><td>{pct(won, lines)}</td></tr>"
        for g, lines, disp, won, dom, sp in T["groups"][:12])
    services = "".join(
        f"<tr><td><b>{E(desc)}</b><div class=\"meta\">CPT {E(c)}</div></td><td>{n(lines)}</td><td>{pct(won, lines)}</td></tr>"
        for c, desc, lines, won in T["services"][:12])
    insurers = "".join(
        f"<tr><td><b>{E(d)}</b><div class=\"meta\">most often named as “{E(nm)}”</div></td><td>{n(disp)}</td><td>{n(lines)}</td><td>{pct(won, lines)}</td><td>{pct(sf, lines)}</td></tr>"
        for d, lines, disp, won, sf, nm in T["insurers"][:12])
    ptypes = "".join(
        f"<div class=\"pline\"><div class=\"who\"><b>{E(TYPE.get(t, t))}</b><div class=\"meta\">provider's offer picked on {pct(w, c)}</div></div>"
        f"<span class=\"lead\"></span><span class=\"price\">{n(c)}</span></div>" for t, c, w in T["plan_types"])
    visits = [b for b in board if b["code"] in VISITS and b.get("doc_arb")]
    qrows = "".join(
        f"<tr><td><b>{E(b['name'])}</b><div class=\"meta\">CPT {E(b['code'])}</div></td><td>{money(b['med'])}</td><td>{money(b['qpa'])}</td>"
        f"<td>{money(b['doc_arb'][0])}<div class=\"meta\">{n(b['doc_arb'][1])} rates, {n(b['doc_arb'][2])} providers</div></td>"
        f"<td>{money(b['doc'][0]) if b.get('doc') else '—'}<div class=\"meta\">{n(b['doc'][1]) if b.get('doc') else 0} rates</div></td>"
        f"<td class=\"hi\">{money(b['award'])}</td></tr>" for b in visits)
    ratio = er["award"] / er["qpa"] if er.get("qpa") else None
    v84 = next((b for b in visits if b["code"] == "99284"), None)
    src_links = " · ".join(f"<a href=\"{E(urls[p])}\" target=\"_blank\" rel=\"noopener\">{qtr(p)}</a>" for p in q if p in urls)
    med = T.get("medicare_src") or ["Medicare Physician Fee Schedule", "https://www.cms.gov/medicare/payment/fee-schedules/physician", ""]

    # ---------------------------------------------------------------- search data
    json.dump([[p[0], p[1], TYPE.get(p[2], p[2]), p[3], p[4], p[5]] for p in P["plans"]],
              open(out / "plans.json", "w"), separators=(",", ":"))
    json.dump(sorted(([k] + v[:2] + [v[2], v[3], v[4], v[5]] for k, v in A["providers"].items()), key=lambda r: -r[1]),
              open(out / "providers.json", "w"), separators=(",", ":"))   # [npi, lines, disputes, chosen, name, group, specialty]

    page = TEMPLATE
    for k, v in dict(PER=per, CHECKED=checked, TX_LINES=n(tot["tx_lines"]), TX_SHARE=tx_share, TX_DISPUTES=n(tot["tx_disputes"]),
                     TX_WON=pct(tot["tx_won"], tot["tx_lines"]), TX_PLAN_WON=pct(tot["tx_plan_won"], tot["tx_lines"]), TX_NA=pct(na, tot["tx_lines"]),
                     US_LINES=n(tot["us_lines"]), DFW_LINES=n(T["dfw_lines"]), DFW_DOLLAR=n(T["dfw_dollar_lines"]),
                     ER_NAME=E(er["name"]), ER_QPA=money(er["qpa"]), ER_AWARD=money(er["award"]), ER_PLAN=money(er["plan"]),
                     ER_PROV=money(er["prov"]), ER_N=n(er["d"]), ER_RATIO=f"{ratio:.1f}" if ratio else "—",
                     ROWS_DFW=rows_dfw, TREND=trend, STATES=states, FILERS=filers, FSER=fser, GROUPS=groups, SERVICES=services,
                     INSURERS=insurers, PTYPES=ptypes, SF_LINES=n(self_funded[1]), SF_SHARE=pct(self_funded[1], tot["tx_lines"]),
                     QROWS=qrows, V84_ARB=money(v84["doc_arb"][0]) if v84 else "—", V84_QPA=money(v84["qpa"]) if v84 else "—",
                     V84_MED=money(v84["med"]) if v84 else "—", V84_AWARD=money(v84["award"]) if v84 else "—",
                     ARB_PROVS=n(T["arb_on_page"][0]), SRC_LINKS=src_links, MED_SRC=E(med[0]), MED_URL=E(med[1]),
                     PF_BUILD=E(T.get("price_finder_build", "")), N_PLANS=n(len(P["plans"])), N_PROVS=n(len(A["providers"]))).items():
        page = page.replace("{{" + k + "}}", v)
    if "{{" in page:
        raise SystemExit("STOP: unfilled placeholder " + page[page.index("{{"):page.index("{{") + 40])
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"wrote {out}/index.html ({len(page) / 1e3:.0f} KB), plans.json, providers.json")


FSER = """<section class="fser" id="freestanding-er">
<h3>Freestanding ERs: an emergency room that can look like an urgent care</h3>
<p>A freestanding ER is an emergency room in its own building, away from a hospital. From the street it can look like an urgent care: a small building, often in a shopping center. But Texas law makes it tell you it charges rates comparable to a hospital emergency room and may charge a facility fee.</p>
<p><b>{{FT}} Texas lines ({{FS}}) came from {{FN}} providers the federal NPI registry lists as emergency care centers, the type freestanding ERs use.</b> Some freestanding ERs list themselves as emergency medicine groups instead, so the real share may be higher.</p>
<div class="two">
<div><b>Freestanding ER</b><ul><li>Usually says "Emergency," "ER" or "Emergency Room" on the sign</li><li>Usually licensed by Texas as a freestanding emergency medical care facility (some are run as part of a hospital, under its license)</li><li>Must post a notice that it charges rates comparable to a hospital emergency room, may charge a facility fee, and that it or its doctors may be out of network</li><li>Its doctors may bill you separately from the facility</li></ul></div>
<div><b>Urgent care</b><ul><li>Usually says "Urgent Care" on the sign</li><li>Not licensed as an emergency room</li><li>Doesn't have to post that notice</li></ul></div>
</div>
<p><b>What protects you.</b> Texas law requires every freestanding ER to post that notice at its entrance, in each treatment room and where you pay, and on its website under "Insurance Information" (<a href="https://texas.public.law/statutes/tex._health_and_safety_code_section_254.155" target="_blank" rel="noopener">Health and Safety Code §254.155</a>). For a real emergency, the federal No Surprises Act limits what you owe an out-of-network ER to your in-network share. The rest is fought out between the ER and your plan, and that fight is what the numbers on this page count. Your plan, and through it your premiums or your employer, pays the award.</p>
<p><b>Not an emergency?</b> If it can wait for an urgent care or your doctor, ask at the front desk before you're seen: "Is this an emergency room? Are you in network with my plan?"</p>
<div class="tw"><table>
<thead><tr><th>Freestanding ERs with the most Texas arbitration</th><th>Disputes</th><th>Lines</th></tr></thead>
<tbody>{{FROWS}}</tbody></table></div>
<p class="meta">Freestanding ER here means the provider's primary type in the CMS NPI registry (<a href="https://download.cms.gov/nppes/NPI_Files.html" target="_blank" rel="noopener">NPPES file</a>) is "Clinic/Center, Emergency Care." Names are the registry's legal names; many use a different brand on the sign. Counts here are by registry match (each NPI), so they differ a little from the Largest provider groups table, which groups lines by the name as filed. Texas only, {{PER}}.</p>
</section>"""

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#f6f1e7"><link rel="icon" href="/favicon-32.png" sizes="32x32"><link rel="apple-touch-icon" href="/apple-touch-icon.png"><link rel="manifest" href="/manifest.webmanifest"><meta property="og:site_name" content="What It Costs"><meta property="og:type" content="website"><meta property="og:url" content="https://files.healthcare/surprise-bills/"><meta name="twitter:card" content="summary"><meta property="og:title" content="Surprise Bills · What It Costs"><meta name="description" content="Every Texas surprise-bill case decided in federal No Surprises Act arbitration, {{PER}}: who files, which plans, and what arbitrators award in Dallas–Fort Worth."><meta property="og:description" content="Every Texas surprise-bill case decided in federal No Surprises Act arbitration, {{PER}}: who files, which plans, and what arbitrators award in Dallas–Fort Worth."><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}html{scroll-padding-top:env(safe-area-inset-top,0px)}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#faf9f5;color:#141413}img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style></head><body>
<title>Surprise Bills · What It Costs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,600&family=Courier+Prime:wght@400;700&family=Public+Sans:wght@400;500;600&display=swap">
<style>
/* Same printed notice board as the Price File Watch, with ruled tables for the case counts. */
:root{
  --paper:#f6f1e7; --paper-2:#efe7d8; --ink:#231f1a; --ink-2:#5c5448; --rule:#d6cbb8;
  --brick:#9b3a2a; --brick-soft:#f1dcd4; --warn:#8a6412; --warn-soft:#f3e6c4; --ok:#3f6b3a; --ok-soft:#dde8d4;
  --display:"Newsreader",Georgia,"Times New Roman",serif;
  --body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --type:"Courier Prime","Courier New",ui-monospace,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#1c1916; --paper-2:#26221d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d;
  --brick:#e0806c; --brick-soft:#3a231d; --warn:#e2b75a; --warn-soft:#3a2f17; --ok:#9cc58f; --ok-soft:#24301f; color-scheme:dark}}
:root[data-theme="dark"]{
  --paper:#1c1916; --paper-2:#26221d; --ink:#eee6d8; --ink-2:#b3a893; --rule:#3d362d;
  --brick:#e0806c; --brick-soft:#3a231d; --warn:#e2b75a; --warn-soft:#3a2f17; --ok:#9cc58f; --ok-soft:#24301f; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);font:16px/1.6 var(--body);padding-inline:16px;padding-block:0 56px}
.wrap{max-width:860px;margin:0 auto}
a{color:var(--brick)}
a:focus-visible,input:focus-visible{outline:2px solid var(--brick);outline-offset:2px}
.topbar{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;padding-block:14px;border-bottom:1px solid var(--rule)}
.asof{font:13px var(--type);color:var(--ink-2)}
header{padding-block:36px 24px;border-bottom:2px solid var(--ink);display:grid;gap:12px}
.eyebrow{font:600 12px/1 var(--body);letter-spacing:.12em;text-transform:uppercase;color:var(--brick)}
h1{font:600 clamp(34px,6.5vw,56px)/1.04 var(--display);margin:0;text-wrap:balance}
.lede{margin:0;max-width:62ch;color:var(--ink-2);font-size:17px}
.tally{display:flex;flex-wrap:wrap;gap:8px 28px;font:14px var(--type);color:var(--ink-2);padding-top:6px}
.tally b{font:700 22px var(--type);color:var(--ink);margin-right:6px;font-variant-numeric:tabular-nums}
h2{font:600 28px/1.15 var(--display);margin:48px 0 6px;text-wrap:balance}
.sub{margin:0 0 16px;color:var(--ink-2);max-width:66ch;font-size:15px}
h3{font:600 13px var(--body);letter-spacing:.1em;text-transform:uppercase;color:var(--ink-2);margin:30px 0 0;padding-bottom:6px;border-bottom:1px solid var(--ink)}
.pline{display:flex;align-items:baseline;gap:8px;padding-block:8px;border-bottom:1px solid var(--rule)}
.pline .who{min-width:0}
.pline .who b{font-weight:600}
.meta{font-size:12.5px;color:var(--ink-2);font-weight:400}
.pline .lead{flex:1;border-bottom:1px dotted var(--ink-2);opacity:.45;transform:translateY(-4px);min-width:12px}
.price{font:700 17px var(--type);font-variant-numeric:tabular-nums;white-space:nowrap}
.finding{padding-block:8px 4px}
.finding .big{font:700 clamp(30px,5vw,42px)/1 var(--type);color:var(--brick);font-variant-numeric:tabular-nums}
.finding p{margin:8px 0 0;max-width:64ch}
.tw{overflow-x:auto;margin-top:6px;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font:600 11.5px var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--ink-2);text-align:right;padding:8px 0 6px 12px;border-bottom:1px solid var(--ink);vertical-align:bottom}
th:first-child,td:first-child{text-align:left;padding-left:0}
td{padding:9px 0 9px 12px;border-bottom:1px solid var(--rule);text-align:right;font:14px var(--type);font-variant-numeric:tabular-nums;vertical-align:top;white-space:nowrap}
td:first-child{font:15px/1.35 var(--body);white-space:normal;min-width:180px}
td:first-child b{font-weight:600}
td .meta{font-family:var(--body);white-space:normal}
td.hi{color:var(--brick);font-weight:700}
.ktag{display:inline-block;margin-top:4px;font:600 12px var(--body);padding:2px 8px;border:1.5px solid var(--rule);border-radius:999px;color:var(--ink-2);text-decoration:none}
a.ktag.k-fser{border-color:var(--brick);color:var(--brick)}
.fser{margin-top:40px;padding:20px;border:2px solid var(--ink);display:grid;gap:12px}
.fser h3{margin:0}.fser p{margin:0;max-width:70ch}
.fser .two{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.fser .two div{padding:12px 14px;border:1.5px solid var(--rule)}
.fser .two b{display:block;margin-bottom:4px}
.fser ul{margin:0;padding-left:18px}
.trend{margin-top:10px;display:grid;gap:4px}
.tr{display:grid;grid-template-columns:62px minmax(0,1fr) 200px;gap:10px;align-items:center;font:13px var(--type)}
.tb{display:flex;height:12px;background:var(--paper-2);border:1px solid var(--rule)}
.tb i{display:block;height:100%}
.tb .a{background:var(--brick)}
.tb .b{background:var(--ink-2);opacity:.35}
.tn{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tn small{color:var(--ink-2)}
.key{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--ink-2);margin-top:8px}
.key span::before{content:"";display:inline-block;width:10px;height:10px;margin-right:6px;vertical-align:-1px;background:var(--c)}
.search{margin-top:14px;display:grid;gap:8px}
.search input{font:16px var(--body);padding:10px 12px;border:1.5px solid var(--ink);border-radius:2px;background:transparent;color:var(--ink);width:100%;max-width:520px}
.res{min-height:24px}
.res h4{font:600 12px var(--body);letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);margin:16px 0 0}
.empty{color:var(--ink-2);font-size:14px}
.notes{margin-top:48px;padding-top:16px;border-top:2px solid var(--ink);display:grid;gap:12px;font-size:14px;color:var(--ink-2);max-width:70ch}
.notes b{color:var(--ink)}
@media (max-width:560px){.tr{grid-template-columns:52px minmax(0,1fr)}.tn{grid-column:2;text-align:left}}
</style>

<div class="wrap">
<style>.sn{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:6px 16px;padding:14px 0;border-bottom:1px solid var(--rule)}.sn-brand{font:600 20px var(--display);color:var(--ink)!important;text-decoration:none}.sn-links{display:flex;flex-wrap:wrap;gap:4px 16px;font:14px var(--body)}.sn-links a{color:var(--brick);text-decoration:none}.sn-links a:hover{text-decoration:underline}.sn-links a[aria-current]{color:var(--ink);font-weight:600}</style><nav class="sn" aria-label="Site"><a class="sn-brand" href="/">What It Costs</a><span class="sn-links"><a href="/start-here/">Start here</a><a href="/price-finder/">Price Finder</a><a href="/plan-calculator/">Plan Calculator</a><a href="/price-file-watch/">Price File Watch</a><a href="/surprise-bills/" aria-current="page">Surprise Bills</a><a href="/employer-plans/">Employer Plans</a><a href="/insurers/">Insurers</a></span></nav><div class="topbar" style="border-bottom:0;padding-block:8px 0"><div class="asof">CMS files read {{CHECKED}}</div></div>

<header>
  <div class="eyebrow">No Surprises Act · Texas</div>
  <h1>Where surprise bills go to arbitration</h1>
  <p class="lede">When an out-of-network doctor or hospital and a health plan can't agree on what a surprise bill is worth, either side can take it to arbitration. The arbitrator picks one side's number. For care the No Surprises Act covers, the patient is protected: their share stays at the in-network amount. In Texas, state-regulated insured plans and the ERS and TRS plans for state employees and teachers use Texas's own arbitration (<a href="https://www.tdi.texas.gov/medical-billing/faq.html" target="_blank" rel="noopener">Texas Department of Insurance</a>); this page counts the federal cases, which are mostly self-funded employer plans. The plan, and the employer or members who fund it, pay the result. CMS publishes every case. We read all of them. These are the cases decided {{PER}}.</p>
  <div class="tally"><span><b>{{TX_LINES}}</b>disputed lines in Texas</span><span><b>{{TX_SHARE}}</b>of the U.S. total</span><span><b>{{TX_WON}}</b>went the provider's way</span><span><b>{{DFW_LINES}}</b>in the Dallas–Fort Worth metro</span></div>
</header>

<h2>What arbitration paid in Dallas–Fort Worth</h2>
<p class="sub">The most-disputed services in the Dallas–Fort Worth–Arlington metro area, by lines with dollar amounts. Each figure is the middle value of CMS's rows: the plan's offer, the plan's qualifying payment amount (QPA), the provider's offer, and the offer the arbitrator picked. CMS withholds dollar amounts where a code had fewer than 10 lines in an area (<a href="https://www.cms.gov/nosurprises/policies-and-resources/Reports" target="_blank" rel="noopener">CMS's notes on these files</a>); {{DFW_DOLLAR}} of the {{DFW_LINES}} metro lines show them.</p>
<div class="finding">
  <div class="big">{{ER_RATIO}}×</div>
  <p>The most-disputed service, <b>{{ER_NAME}}</b> (CPT 99284): the middle award was <b>{{ER_AWARD}}</b>, {{ER_RATIO}} times the middle QPA of {{ER_QPA}}. The middle plan offer was {{ER_PLAN}}; the middle provider offer was {{ER_PROV}}. Based on {{ER_N}} lines with dollar amounts.</p>
</div>
<div class="tw"><table>
<thead><tr><th>Service</th><th>Lines</th><th>Plan offered</th><th>QPA</th><th>Provider asked</th><th>Award</th><th>Provider's offer picked</th></tr></thead>
<tbody>{{ROWS_DFW}}</tbody></table></div>
<p class="sub" style="margin-top:12px">These same figures appear in the <a href="/price-finder/?code=99284">Price Finder</a> on each procedure that went to arbitration, under the Medicare benchmark, for Dallas–Fort Worth and each Texas metro area.</p>

<h2>Texas is where the disputes are</h2>
<p class="sub">Disputed lines decided each quarter (emergency and non-emergency care; air ambulance is a separate CMS table). Texas in brick, the rest of the country in gray. One dispute can cover many lines.</p>
<div class="trend" role="img" aria-label="Disputed lines per quarter, Texas and the rest of the U.S.">{{TREND}}</div>
<div class="key"><span style="--c:var(--brick)">Texas</span><span style="--c:var(--ink-2)">Rest of the U.S.</span></div>
<p class="sub" style="margin-top:12px">States with the most lines, {{PER}}: {{STATES}}.</p>

<h3>Who files</h3>
<p class="sub" style="margin-top:10px">Texas lines by the provider's email domain as reported to CMS. A domain usually belongs to the practice or the billing company that files for it. The specialty is the one most often reported.</p>
<div class="tw"><table>
<thead><tr><th>Provider email domain</th><th>Providers (NPIs)</th><th>Disputes</th><th>Lines</th><th>Provider's offer picked</th></tr></thead>
<tbody>{{FILERS}}</tbody></table></div>

<h3>Largest provider groups</h3>
<div class="tw"><table>
<thead><tr><th>Group as named in the dispute</th><th>Disputes</th><th>Lines</th><th>Provider's offer picked</th></tr></thead>
<tbody>{{GROUPS}}</tbody></table></div>

<h3>Most-disputed services in Texas</h3>
<div class="tw"><table>
<thead><tr><th>Service</th><th>Lines</th><th>Provider's offer picked</th></tr></thead>
<tbody>{{SERVICES}}</tbody></table></div>
{{FSER}}

<h2 id="employers">For employers: which plans end up in arbitration</h2>
<p class="sub">{{SF_LINES}} of Texas's {{TX_LINES}} lines ({{SF_SHARE}}) involved a self-funded employer plan. When a self-funded plan loses, the award and the arbitration fee come out of the employer's plan, usually through the insurer or administrator that runs it.</p>
<h3>By type of plan</h3>
{{PTYPES}}
<h3>By the plan's email domain</h3>
<p class="sub" style="margin-top:10px">The domain belongs to whoever answered for the plan: the insurer, the administrator, or a repricing company hired by the plan. The name in quotes is the plan name most often given on those disputes.</p>
<div class="tw"><table>
<thead><tr><th>Plan email domain</th><th>Disputes</th><th>Lines</th><th>Provider's offer picked</th><th>Share from self-funded plans</th></tr></thead>
<tbody>{{INSURERS}}</tbody></table></div>

<h3 id="search">Look up a plan or a provider</h3>
<div class="search">
  <label for="q" class="sub" style="margin:0">Search {{N_PLANS}} plan names and {{N_PROVS}} Texas providers in the cases decided {{PER}}. Self-funded plans often appear under the employer's name.</label>
  <input id="q" type="search" placeholder="Employer, plan, insurer, provider or NPI" autocomplete="off">
  <div class="res" id="res" aria-live="polite"></div>
</div>

<h2>Is the QPA set too low?</h2>
<p class="sub">Providers say plans set the QPA too low, so arbitrators shouldn't lean on it. Insurers' own published in-network rates let us check. For emergency visits and critical care, the doctor's fee is the whole service, so the in-network files give a direct comparison. Below: the Medicare rate, the middle QPA in arbitration, the middle in-network rate that the {{ARB_PROVS}} Dallas–Fort Worth providers who went to arbitration in Texas publish with the networks they do contract with, the middle across every DFW provider, and the middle award.</p>
<div class="tw"><table>
<thead><tr><th>Service</th><th>Medicare</th><th>QPA</th><th>Same providers, in-network</th><th>All DFW providers, in-network</th><th>Award</th></tr></thead>
<tbody>{{QROWS}}</tbody></table></div>
<div class="finding">
  <p>For a moderate-complexity ER visit, the providers who went to arbitration publish a middle in-network fee of <b>{{V84_ARB}}</b>. The middle QPA was <b>{{V84_QPA}}</b>, above what those same providers accept in-network, and Medicare pays {{V84_MED}}. The middle award was <b>{{V84_AWARD}}</b>.</p>
  <p class="sub">Read with care. The QPA (<a href="https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-B/part-149/subpart-B/section-149.140" target="_blank" rel="noopener">45 CFR 149.140</a>) is the plan's median contracted rate from 2019, raised by inflation, for the specialty and area; the in-network rates are from insurers' October 2026 files (Price Finder build {{PF_BUILD}}). A listed rate means a contract exists, not that the provider bills that code often. Imaging and lab codes are left out because the files mix whole-service and reading-only fees.</p>
</div>

<h2 id="providers">Providers in the Price Finder</h2>
<p class="sub">In the <a href="/price-finder/">Price Finder</a>, a provider who went to federal arbitration in Texas {{PER}} shows a line under its name: how many disputes, how many lines, and how many times the arbitrator picked its offer. Providers are matched by their National Provider Identifier (NPI). A dispute may list a group's NPI or one doctor's, so a doctor in a group that files may show no line of their own.</p>

<section class="notes">
  <p><b>Where this comes from.</b> CMS's Federal Independent Dispute Resolution public use files: {{SRC_LINKS}} (<a href="https://www.cms.gov/nosurprises/policies-and-resources/Reports" target="_blank" rel="noopener">all CMS reports</a>). We save every CMS file untouched and read every row. Medicare: {{MED_SRC}} (<a href="{{MED_URL}}" target="_blank" rel="noopener">CMS</a>), Dallas locality. In-network rates: insurers' Transparency in Coverage files, as in the Price Finder.</p>
  <p><b>What the numbers are.</b> "Lines" are the line items CMS counts; one dispute can cover many. A "middle" value is CMS's own figure at the middle position when every line is sorted (for an even count, the lower of the two). Nothing is averaged or estimated. "Provider's offer picked" is the share of lines where the arbitrator chose the provider's offer; in Texas that was {{TX_WON}}, the plan's offer {{TX_PLAN_WON}}, and {{TX_NA}} had no offer chosen (CMS reports "N/A"). {{TX_DISPUTES}} Texas disputes in all; {{US_LINES}} lines nationally.</p>
  <p><b>What the numbers leave out.</b> CMS doesn't link the dollar table to provider or plan names, so a dollar figure can't be tied to a specific provider or plan. An award is the offer chosen, not proof of payment. Cases are counted in the quarter CMS reports them; services may be from earlier years. Names and email domains are as the parties reported them.</p>
  <p><b>For patients.</b> The No Surprises Act limits what you owe for emergency care, and for out-of-network care at an in-network hospital or surgery center, to your in-network cost-sharing. Arbitration is between the provider and the plan. If you get a surprise bill, CMS's help desk is at <a href="https://www.cms.gov/nosurprises" target="_blank" rel="noopener">cms.gov/nosurprises</a>.</p>
  <p>See every published rate in the <a href="/price-finder/">Price Finder</a>, or who isn't publishing in the <a href="/price-file-watch/">Price File Watch</a>.</p>
</section>
</div>
<script>
(function(){
  var P=null,V=null,q=document.getElementById('q'),res=document.getElementById('res');
  var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
  var num=function(x){return Number(x).toLocaleString('en-US');};
  var pc=function(a,b){return b?Math.round(100*a/b)+'%':'—';};
  function load(){ if(P) return Promise.resolve();
    return Promise.all([fetch('plans.json').then(function(r){return r.json();}),fetch('providers.json').then(function(r){return r.json();})])
      .then(function(x){P=x[0];V=x[1];}); }
  function line(name,meta,right){return '<div class="pline"><div class="who"><b>'+esc(name)+'</b><div class="meta">'+meta+'</div></div><span class="lead"></span><span class="price">'+right+'</span></div>';}
  function show(){ var t=q.value.trim().toLowerCase(); if(t.length<2){res.innerHTML='';return;}
    load().then(function(){
      var pl=P.filter(function(p){return p[0].toLowerCase().indexOf(t)>=0||String(p[1]).toLowerCase().indexOf(t)>=0;}).slice(0,25);
      var pv=V.filter(function(p){return p[0]===t||String(p[4]).toLowerCase().indexOf(t)>=0||String(p[5]).toLowerCase().indexOf(t)>=0;}).slice(0,25);
      var h='';
      if(pl.length) h+='<h4>Plans</h4>'+pl.map(function(p){return line(p[0],esc(p[2])+' · '+esc(p[1])+' · '+num(p[4])+' disputes · provider\'s offer picked on '+pc(p[5],p[3]),num(p[3])+' lines');}).join('');
      if(pv.length) h+='<h4>Providers</h4>'+pv.map(function(p){return line(p[4],(p[5]?esc(p[5])+' · ':'')+esc(p[6])+' · NPI '+esc(p[0])+' · '+num(p[2])+' disputes · offer picked on '+pc(p[3],p[1]),num(p[1])+' lines');}).join('');
      res.innerHTML=h||'<p class="empty">No plan or provider by that name in the Texas cases.</p>';
    }).catch(function(){res.innerHTML='<p class="empty">Could not load the search lists.</p>';});
  }
  var tm; q.addEventListener('input',function(){clearTimeout(tm);tm=setTimeout(show,180);});
})();
</script>
</body></html>
"""

if __name__ == "__main__":
    main(*sys.argv[1:6])
