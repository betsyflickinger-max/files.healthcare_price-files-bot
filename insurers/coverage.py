"""Coverage checklist: every insurer the price-transparency rule covers, and where we stand with each (Oct 20, 2026).

Betsy: "how do we make sure we're covering every single insurer that would be required to participate."

Who is on the list: every company that filed a federal Medical Loss Ratio report for comprehensive medical coverage
(individual, small group or large group) and reported members (insurers/mlr/master_insurers.csv, 2025 filings). That
filing is required of every insurer selling that coverage, so it is the full list of insurers the Transparency in
Coverage rule (45 CFR 147.212) applies to. Companies that filed with no members are listed apart, not counted.
Self-funded employer plans publish through their insurer or administrator; administrators are a later step.

Each company gets the best status any of its state companies has, in this order:
  reading         its rate files are on a pick list and the bot reads them (insurers/networks*.csv)
  files found     we know where its files are (an index or file link, its national listing, or a working price page)
  broken          we know where its files are, but the daily watch finds them broken (insurers/index_watch.py)
  portal only     its files sit behind a portal or click-through we can't link to directly
  not found       searched (insurers/find_insurers.py), no files found
  not searched    on the federal list, never searched (most are large-group-only, off the marketplace)

Matching is by name within the same state (MLR and marketplace ids differ); every match is written to the output
so it can be checked, and nothing is guessed: a company with no match stays "not searched".

Run:  python insurers/coverage.py [--out DIR]
Output: <out>/insurers.csv (one row per company), states.csv (one row per company x state), summary.json, report.md;
        copied to R2 bot/coverage/ and the control center (control/data/coverage_*.json) when R2 keys are set.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from rapidfuzz import fuzz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "bot"))

ORDER = ["reading", "files found", "broken", "portal only", "not found", "not searched"]
DISTINCT = {"city", "northeastern", "western", "eastern", "southern", "northern", "central", "vip", "mutual", "life"}
FOUND = {"found toc", "found file", "known (national insurer)", "already reading"}
NOISE = r"\b(inc|incorporated|company|co|corp|corporation|of|the|insurance|ins|health|plan|plans|llc|d ?b ?a)\b"


def norm(s):
    return re.sub(r"\s+", " ", re.sub(NOISE, " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()))).strip()


def lives(r):
    try:
        return float(r.get("total_lives") or 0)
    except ValueError:
        return 0.0


def read_list():
    """(state, reading-list insurer) pairs the bot reads, with the name pattern for each."""
    import find_insurers as fi
    return [(states, name, fi.ALIASES[name]) for states, name in fi.known_networks()], fi.NATIONAL


def watch_status():
    """url -> status from the daily index watch (R2), when keys are set."""
    try:
        import store
        s3, b = store.r2()
        return {r["url"]: r["status"] for r in store.read_csv(s3, b, "bot/watch/indexes/latest.csv")}
    except Exception as e:
        print("daily watch results not read (no R2 keys here?):", str(e)[:120])
        return {}


def deep_missing():
    """index url -> rate files missing, from the newest monthly deep check (insurers/index_watch.py --deep)."""
    try:
        import store
        s3, b = store.r2()
        keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=b, Prefix="bot/watch/indexes/deep/").get("Contents", [])
                      if re.search(r"deep/\d{4}-\d{2}\.csv$", o["Key"]))
        if not keys:
            return {}
        return {r["url"]: int(r["missing"] or 0) for r in store.read_csv(s3, b, keys[-1]) if (r["missing"] or "0") != "0"}
    except Exception:
        return {}


# ---- plan administrators (Form 5500 Schedule C) ----
F5500 = "https://www.askebsa.dol.gov/FOIA%20Files/{y}/Latest/{f}_{y}_Latest.zip"
# Owners named in the administrator's own name (UMR is UnitedHealthcare's, Meritain is Aetna's, Luminare is HCSC's)
OWNED = [(r"\bumr\b|united ?health|optum(?!rx)", "UnitedHealth Group"), (r"meritain|aetna", "CVS Health (Aetna)"),
         (r"cigna|evernorth(?! care)", "Cigna Group"), (r"luminare|health care service corp|\bhcsc\b", "HCSC"),
         (r"anthem|empire health|wellpoint|elevance|carelon", "Elevance (Anthem)"), (r"humana", "Humana"),
         (r"kaiser", "Kaiser Permanente"), (r"independence administrators|independence blue", "Independence Blue Cross"),
         (r"highmark", "Highmark"), (r"blue ?cross|blue ?shield|\bbcbs|blue ?care|regence|premera|wellmark|carefirst|"
                                     r"excellus|horizon blue|florida blue|capital ?blue", "a Blue Cross Blue Shield plan")]
# Not medical claims administrators: the medical-price rule doesn't reach their files (stand-alone dental and vision
# are excepted benefits; pharmacy files are on hold under the rule; FSA/HSA, life, disability, EAP aren't health
# coverage). Judged by the name only, so the output says so.
NOT_MEDICAL = r"dental|\bdelta\b|vision|\bvsp\b|eye ?med|opti|scripts|\brx\b|rx[ ,]|pharm|caremark|\bpbm\b|" \
              r"\bwex\b|flex|\bhsa\b|\bfsa\b|hra\b|\blife\b|metlife|metropolitan life|prudential|disabilit|\beap\b|" \
              r"employee assistance|cobra|hearing|chiropract|behavioral|guardian|unum|lincoln|principal|hartford|" \
              r"reliance standard|concordia|dentemax|rxbenefit|wageworks|navia|compsych|health advocate|alight|one exchange|" \
              r"healthequity|multiplan|prime therapeutics|\bddmn\b|evernorth care|benefitmall|vimly"


def admins(a, master_names):
    """Every claims or contract administrator (Schedule C service codes 12 and 13) named on a health plan's 2024
    Form 5500, with how many health plans and active participants name it."""
    import zipfile
    import duckdb
    import requests
    wd = Path(a.work)
    wd.mkdir(parents=True, exist_ok=True)
    csvs = {}
    for f in ("F_5500", "F_SCH_C_PART1_ITEM2", "F_SCH_C_PART1_ITEM2_CODES"):
        z = wd / f"{f}.zip"
        if not z.exists():
            with requests.get(F5500.format(y=a.year, f=f), stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(z, "wb") as out:
                    for ch in r.iter_content(1 << 20):
                        out.write(ch)
        with zipfile.ZipFile(z) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            zf.extract(name, wd)
            csvs[f] = str(wd / name)
    c = duckdb.connect()
    rd = lambda f: f"read_csv_auto('{csvs[f]}', all_varchar=true, ignore_errors=true)"
    c.execute(f"create table h as select ACK_ID, try_cast(TOT_ACTIVE_PARTCP_CNT as int) as act from {rd('F_5500')} "
              "where TYPE_WELFARE_BNFT_CODE like '%4A%'")   # 4A = health benefits
    c.execute(f"""create table g as select pid, any_value(pname) as pname, mode(pst) as pst, count(distinct ack) as nplans,
                  sum(act) as participants from (select distinct
                    coalesce(nullif(p.PROVIDER_OTHER_EIN,''), 'name:'||upper(trim(p.PROVIDER_OTHER_NAME))) as pid,
                    upper(trim(p.PROVIDER_OTHER_NAME)) as pname, p.PROVIDER_OTHER_US_STATE as pst, h.ACK_ID as ack, h.act as act
                  from {rd('F_SCH_C_PART1_ITEM2')} p join h on h.ACK_ID = p.ACK_ID
                  join {rd('F_SCH_C_PART1_ITEM2_CODES')} k on k.ACK_ID = p.ACK_ID and k.ROW_ORDER = p.ROW_ORDER
                  where k.SERVICE_CODE in ('12', '13')) group by pid order by nplans desc""")
    health_plans = c.execute("select count(*) from h").fetchone()[0]
    with_c = c.execute("select count(distinct ack) from (select p.ACK_ID as ack from "
                       f"{rd('F_SCH_C_PART1_ITEM2')} p join h on h.ACK_ID = p.ACK_ID)").fetchone()[0]
    out = []
    for pid, name, st, plans, part in c.execute("select * from g").fetchall():
        name = name or ""
        owner = next((o for pat, o in OWNED if re.search(pat, name, re.I)), "")
        if re.search(NOT_MEDICAL, name, re.I) and not owner:
            kind, status = "not a medical administrator (by name)", "not required"
        elif owner:
            kind, status = f"insurer-owned: {owner}", "through its insurer"
        else:
            m = max(((fuzz.token_sort_ratio(norm(name), norm(n)), n) for n in master_names), default=(0, ""))
            kind, status = ("insurer", "through its insurer") if m[0] >= 92 else ("independent administrator", "not searched")
        pid = pid or ""
        out.append(dict(ein="" if pid.startswith("name:") else pid, name=name, state=st or "", health_plans=plans,
                        participants=part or 0, kind=kind, status=status))
    return out, dict(year=a.year, health_plans=health_plans, health_plans_with_schedule_c=with_c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/coverage")
    ap.add_argument("--admins", action="store_true", help="also list plan administrators from Form 5500 Schedule C")
    ap.add_argument("--year", default="2024", help="Form 5500 filing year for --admins")
    ap.add_argument("--work", default="/tmp/coverage_f5500")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    master = [r for r in csv.DictReader(open(HERE / "mlr" / "master_insurers.csv"))]
    parents = {r["parent_group"]: r for r in csv.DictReader(open(HERE / "mlr" / "parents.csv"))}
    sources = list(csv.DictReader(open(ROOT / "data" / "insurer_sources.csv")))
    by_state = defaultdict(list)
    for s in sources:
        by_state[s["state"]].append(s)
    reading, national = read_list()
    watch = watch_status()
    deep = deep_missing()

    def matched_source(r):
        """The insurer_sources row for this state company: same state, names alike (best score >= 90)."""
        names = [n for n in (r["issuer_name"], r.get("dba_marketing_name"), r["parent_group"]) if n]
        best, score = None, 0
        for s in by_state.get(r["state"], []):
            for n in names:
                a, b = norm(n), norm(s["issuer"])
                sc = fuzz.token_sort_ratio(a, b)
                # one name inside the other ("Arizona Complete Health" / "Ambetter from Arizona Complete Health") counts,
                # unless the extra words tell two companies apart (Blue Cross Blue Shield of Kansas / of Kansas City)
                extra = set(a.split()) ^ set(b.split())
                if fuzz.token_set_ratio(a, b) == 100 and not extra & DISTINCT:
                    sc = max(sc, 95)
                if sc > score:
                    best, score = s, sc
        return (best, score) if score >= 90 else (None, score)

    rows = []
    for r in master:
        if lives(r) <= 0:
            continue
        names = " | ".join(n for n in (r["issuer_name"], r.get("dba_marketing_name"), r["parent_group"]) if n)
        status, how, link = "not searched", "", ""
        for states, name, pat in reading:
            if r["state"] in states and re.search(pat, names, re.I):
                status, how = "reading", f"pick list: {name}"
                break
        if status != "reading":
            src, score = matched_source(r)
            nat = next((n for n, pat in national.items() if re.search(pat, names, re.I)), "")
            if src and src["result"] in FOUND or nat:
                status = "files found"
                how = f"{src['result']} ({src['issuer']}, name match {score:.0f})" if src and src["result"] in FOUND \
                    else f"national listing: {nat}"
                link = (src or {}).get("url", "")
            elif src and src["result"] == "portal only":
                status, how, link = "portal only", f"{src['issuer']} (name match {score:.0f})", src.get("url", "")
            elif src and src["result"] in ("not found", "held", "error"):
                status, how = "not found", f"searched {src.get('searched_at', '')}: {src['result']} ({src['issuer']})"
            page = r.get("tic_landing_page") or (parents.get(r["parent_group"]) or {}).get("tic_landing_page", "")
            if status in ("not searched", "not found") and page:
                status, how, link = "files found", "price-file page on the parent company's site", page
            if link and watch.get(link) in ("broken", "web page, not a file") and status == "files found":
                status, how = "broken", f"daily watch: {watch[link]} ({how})"
            if link and deep.get(link) and status == "files found":
                status, how = "broken", f"monthly check: {deep[link]} rate files its index names are missing ({how})"
        rows.append(dict(parent=r["parent_group"], company=r["issuer_name"], dba=r.get("dba_marketing_name", ""),
                         state=r["state"], naic=r["naic_code"], members=int(lives(r)), status=status, how=how,
                         link=link))

    comp = {}
    for x in rows:
        c = comp.setdefault(x["parent"], dict(company=x["parent"], members=0, states=set(), status="not searched",
                                              counts=Counter()))
        c["members"] += x["members"]
        c["states"].add(x["state"])
        c["counts"][x["status"]] += 1
        if ORDER.index(x["status"]) < ORDER.index(c["status"]):
            c["status"] = x["status"]
    comp_rows = [dict(company=c["company"], status=c["status"], members=c["members"], states=len(c["states"]),
                      state_companies=sum(c["counts"].values()),
                      detail="; ".join(f"{k} {v}" for k, v in sorted(c["counts"].items(), key=lambda kv: ORDER.index(kv[0]))))
                 for c in comp.values()]
    comp_rows.sort(key=lambda c: (ORDER.index(c["status"]), -c["members"]))
    zero = sorted({r["parent_group"] for r in master} - set(comp))

    tot_m = sum(c["members"] for c in comp_rows)
    summ = dict(built=date.today().isoformat(), source="Federal Medical Loss Ratio filings (2025), insurers/mlr/master_insurers.csv",
                companies=len(comp_rows), state_companies=len(rows), no_members=len(zero),
                by_status={s: sum(1 for c in comp_rows if c["status"] == s) for s in ORDER},
                members_by_status={s: sum(c["members"] for c in comp_rows if c["status"] == s) for s in ORDER},
                members_total=tot_m,
                state_companies_by_status={s: sum(1 for x in rows if x["status"] == s) for s in ORDER},
                state_members_by_status={s: sum(x["members"] for x in rows if x["status"] == s) for s in ORDER})
    for name, data, fields in (("insurers", comp_rows, list(comp_rows[0])), ("states", rows, list(rows[0]))):
        with open(f"{a.out}/{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            w.writerows(data)
    json.dump(summ, open(f"{a.out}/summary.json", "w"), indent=1)

    known = sum(summ["by_status"][s] for s in ("reading", "files found", "broken"))
    pct = lambda n: f"{100 * n / tot_m:.0f}%" if tot_m else "-"
    md = [f"# Insurer coverage checklist ({summ['built']})", "",
          f"**{known} of {len(comp_rows)}** insurance companies with members: we know where their price files are. "
          f"{summ['by_status']['reading']} of them are read by the bot.", "",
          "Who is on the list: every company that filed a federal Medical Loss Ratio report for comprehensive medical "
          f"coverage and reported members ({len(zero)} more filed with no members and are not counted).", "",
          "| Status | Companies | Members | Share of members |", "|---|---|---|---|"]
    md += [f"| {s} | {summ['by_status'][s]} | {summ['members_by_status'][s]:,} | {pct(summ['members_by_status'][s])} |"
           for s in ORDER]
    md += ["", "Members are insured lives from the MLR filings; self-funded employer plans are not in these counts.", "",
           "## Companies still to find (biggest first)", "", "| Company | Status | Members | States |", "|---|---|---|---|"]
    md += [f"| {c['company']} | {c['status']} | {c['members']:,} | {c['states']} |"
           for c in sorted((c for c in comp_rows if c["status"] in ("portal only", "not found", "not searched", "broken")),
                           key=lambda c: -c["members"])]
    if a.admins:
        names = sorted({r["parent_group"] for r in master} | {r["issuer_name"] for r in master})
        ad, meta = admins(a, names)
        # Oct 22, 2026: administrators searched by find_insurers.py --who admins (rows with source "Form 5500 administrator")
        res = {norm(s["issuer"]): s for s in sources if s.get("source") == "Form 5500 administrator"}
        for x in ad:
            x.setdefault("link", "")
            s = res.get(norm(x["name"]))
            if s and x["status"] == "not searched":
                x["status"] = ("files found" if s["result"] in FOUND else s["result"] if s["result"] in ("portal only", "not found")
                               else "not found" if s["result"] in ("held", "error") else x["status"])
                x["link"] = s.get("url", "")
        with open(f"{a.out}/admins.csv", "w", newline="") as f:
            w = csv.DictWriter(f, list(ad[0]))
            w.writeheader()
            w.writerows(ad)
        big = [x for x in ad if x["health_plans"] >= 5]
        cnt = Counter(x["status"] for x in big)
        summ["admins"] = dict(meta, administrators=len(ad), on_5_plus_plans=len(big), by_status_5_plus=dict(cnt))
        json.dump(summ, open(f"{a.out}/summary.json", "w"), indent=1)
        md += ["", f"## Plan administrators (Form 5500, {meta['year']} filings)", "",
               f"{meta['health_plans']:,} employer health plans filed a {meta['year']} Form 5500. "
               f"{meta['health_plans_with_schedule_c']:,} of them attached Schedule C (service providers). Most "
               "self-funded plans pay claims from the employer's general assets and don't attach it, so this list "
               "is a start, not the whole field.", "",
               f"{len(ad):,} claims or contract administrators are named; {len(big)} on 5 or more health plans:", "",
               "| Status | Administrators (5+ plans) |", "|---|---|"]
        md += [f"| {k} | {v} |" for k, v in cnt.most_common()]
        md += ["", "Independent administrators still to search (5+ plans, biggest first):", "",
               "| Administrator | Health plans | Active participants | State |", "|---|---|---|---|"]
        md += [f"| {x['name']} | {x['health_plans']} | {x['participants']:,} | {x['state']} |"
               for x in big if x["status"] == "not searched"][:60]
    open(f"{a.out}/report.md", "w").write("\n".join(md) + "\n")
    print("\n".join(md[:14]))

    try:   # R2 copies, and the control center's data folder
        import store
        s3, b = store.r2()
        for f in ("insurers.csv", "states.csv", "summary.json", "report.md", "admins.csv"):
            if os.path.exists(f"{a.out}/{f}"):
                s3.upload_file(f"{a.out}/{f}", b, f"bot/coverage/{f}")
        json.dump(dict(summary=summ, companies=comp_rows), open(f"{a.out}/coverage_insurers.json", "w"))
        s3.upload_file(f"{a.out}/coverage_insurers.json", b, "control/data/coverage_insurers.json",
                       ExtraArgs={"ContentType": "application/json", "CacheControl": "no-cache"})
        print("copied to R2 bot/coverage/ and control/data/coverage_insurers.json")
    except Exception as e:
        print("not copied to R2:", str(e)[:120])


if __name__ == "__main__":
    main()
