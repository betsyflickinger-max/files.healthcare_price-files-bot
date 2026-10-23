"""Pick-list coverage and status (Oct 23, 2026; Betsy: yes).

The pick lists read each insurer's most-used medical networks. This makes the cut visible and measurable:

  coverage  for every area and big insurer (Anthem, Cigna, UnitedHealthcare, Aetna, HCSC catalogs):
              - coverage: of the employers whose plans use any medical network for that area's states (or a national
                one), the share whose plans use at least one network we read. From the insurer's own index
                (catalog employers.csv.gz + network_sets.csv.gz), so it counts employers, not people.
              - status of every relevant network: read / queued / failed (from the area's manifest), or skipped with
                the reason (not medical, add-on/ancillary, file problem, below the cut).
            Output R2 bot/pickcoverage/<date>/<area>.csv (one row per network) and summary.md.
  aco       list accountable-care, high-performance and value networks in each catalog (the kind of network NEXUS ACO
            is), with employers, size and whether any area reads them.

Run:  python insurers/pick_coverage.py coverage [--areas il,n5]
      python insurers/pick_coverage.py aco
"""
import argparse
import csv
import gzip
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import catalog  # noqa: E402

INSURERS = ["anthem", "cigna", "uhc", "aetna", "hcsc"]
NAMES = {"anthem": "Anthem", "cigna": "Cigna", "uhc": "UnitedHealthcare", "aetna": "Aetna", "hcsc": "HCSC (BCBS TX, IL, OK, NM, MT)"}
AREAS = {"dfw": ["TX"], "tx": ["TX"], "s7": ["TN", "CO", "OK", "AL", "MS", "MO", "GA"], "nc": ["NC"], "ct": ["CT"], "il": ["IL"],
         "ar": ["AR"]}
try:
    for k, v in json.load(open(os.path.join(HERE, "..", "site", "state_scopes.json"))).items():
        if not k.startswith("_") and isinstance(v, dict):
            AREAS[k] = sorted(v)
except Exception:
    pass
LISTS = {"dfw": "networks.csv", "tx": "networks.csv"}
# Networks shown to carry the same prices as one we read (claude/skipped-network-check.md, Illinois, Oct 22-23, 2026:
# 100% of price rows identical). Reading the first covers the employers of the others.
SAME_AS = {("uhc", "Choice-Plus_C2"): ["Choice-Plus_8", "PS1-50_C2"],
           ("aetna", "pl-1s7-tr25_Aetna-Life-Insurance-Company"): ["pl-31e-tr25_Aetna-Life-Insurance-Company",
                                                                   "pl-1gp-tr25_Aetna-Life-Insurance-Company"]}
# Cigna's regional partner networks (Priority Health in Michigan, Upper Midwest partners) are listed on most national
# Cigna plans with "national" providers in the catalog; they aren't Cigna's own network outside those regions.
PARTNER = re.compile(r"priority_health|upper-midwest-affiliation|sagamore", re.I)
MANIFEST = {"dfw": "bot/insurers/manifest.csv"}
ANCILLARY = re.compile(r"chiro|acupunct|speech|behavior|optum|ohph|therap|transplant|pharm|vision|dental|hearing|\blab\b|\bdme\b|\beap\b", re.I)
VALUE = re.compile(r"\baco\b|nexusaco|accountable|whole[- _]?health|collaborative|\bcaa\b|high[- _]?performance|value[- _]?based|"
                   r"premium[- _]?designation|tiered|\btier\b|performance[- _]?network|clinically[- _]?integrated|\bcin\b|"
                   r"blue[- _]?premier|enhanced[- _]?personal|localplus|surest|harmony|signaturevalue|navigate|compass|"
                   r"\bepo\b.*(select|focus)|narrow", re.I)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def latest(st, ins):
    m = (st.get(f"bot/catalog/{ins}/latest.json") or {}).get("month")
    return (m, st.get(f"bot/catalog/{ins}/{m}/catalog.json")) if m else (None, None)


def area_list(area):
    p = os.path.join(HERE, LISTS.get(area, f"networks_{area}.csv"))
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def manifest(st, area):
    key = MANIFEST.get(area, f"bot/insurers/{area}/manifest.csv")
    try:
        body = st.c.get_object(Bucket=st.b, Key=key)["Body"].read().decode()
        return {r["slot"]: r for r in csv.DictReader(io.StringIO(body))}
    except Exception:
        return {}


def picked_for(rows, ins, cat):
    """{catalog network key: slot} for the area's list rows that read this insurer's networks."""
    out = {}
    tables = [(norm(r.get("current_table")) + norm(r.get("current_url")), r["slot"]) for r in rows]
    for r in rows:
        fa = (r.get("finder_arg") or "").split("|")
        if r.get("finder") == "catalog" and len(fa) >= 2 and fa[0] == ins:
            out[fa[1]] = r["slot"]
    for n in cat["networks"]:   # rows with a fixed link (e.g. UnitedHealthcare's Choice Plus C2 file): match by file name
        k = norm(n["network"])
        if n["network"] not in out and len(k) >= 6:
            for t, slot in tables:
                if k in t:
                    out[n["network"]] = slot
                    break
    return out


def plan_sets(st, ins, m):
    """[(employer, set of networks)] from the catalog's employer file (one row per plan)."""
    base = f"bot/catalog/{ins}/{m}/"
    try:
        sets = {}
        with gzip.open(io.BytesIO(st.c.get_object(Bucket=st.b, Key=base + "network_sets.csv.gz")["Body"].read()), "rt") as f:
            for r in csv.DictReader(f):
                sets[r["network_set"]] = frozenset(r["networks"].split("|"))
        local = f"/tmp/{ins}_employers.csv.gz"
        st.c.download_file(st.b, base + "employers.csv.gz", local)
        return sets, local
    except Exception as e:
        print(f"{ins}: no employer file ({str(e)[:100]})", flush=True)
        return None, None


def coverage(a):
    st = catalog.Store()
    areas = [x for x in (a.areas.split(",") if a.areas else AREAS) if x in AREAS]
    info = {area: (area_list(area), manifest(st, area), {s.upper() for s in AREAS[area]}) for area in areas}
    out = defaultdict(list)        # area -> network rows
    table = defaultdict(dict)      # area -> insurer -> summary
    for ins in INSURERS:
        m, cat = latest(st, ins)
        if not cat:
            continue
        per = {}
        for area, (rows, man, states) in info.items():
            picked = picked_for(rows, ins, cat)
            if not picked:
                continue
            for (i2, k), same in SAME_AS.items():
                if i2 == ins and k in picked:
                    for x in same:
                        picked.setdefault(x, picked[k] + " (same prices)")
            med = set()
            for n in cat["networks"]:
                stt = (n.get("state") or "").upper()
                in_area = stt in states or stt == "NATIONAL"
                medical = n.get("coverage", "medical") == "medical" and not ANCILLARY.search(f"{n['network']} {n.get('description', '')}")
                if PARTNER.search(n["network"]) and n["network"] not in picked:
                    medical = False
                if n["network"] in picked:
                    slot = picked[n["network"]]
                    s = (man.get(slot.replace(" (same prices)", "")) or {}).get("status") or "new"
                    status = {"processed": "read", "new": "listed, not yet checked"}.get(s, s)
                    if slot.endswith("(same prices)"):
                        status = "covered: same prices as a network we read"
                elif not in_area:
                    continue
                elif n.get("coverage", "medical") != "medical":
                    status = f"skipped: {n.get('coverage')}"
                elif PARTNER.search(n["network"]):
                    status = "skipped: regional partner network"
                elif not medical:
                    status = "skipped: add-on or ancillary network"
                elif n["problems"]:
                    status = "skipped: file problem (" + "; ".join(n["problems"])[:80] + ")"
                else:
                    status = "skipped: below the cut"
                if medical:
                    med.add(n["network"])
                out[area].append(dict(area=area, insurer=NAMES[ins], catalog_month=m, network=n["network"],
                                      description=(n.get("description") or "")[:80], state=n.get("state") or "",
                                      employers=n.get("employers") or 0, gb=n.get("gb"), status=status))
            per[area] = (med, set(picked) & {n['network'] for n in cat['networks']}, set(), set())
        if not per:
            continue
        sets, local = plan_sets(st, ins, m)
        if sets:   # one pass over the insurer's employer plans for every area at once
            with gzip.open(local, "rt", newline="") as f:
                for r in csv.DictReader(f):
                    ns = sets.get(r["network_set"])
                    if not ns:
                        continue
                    e = hash((r["plan_sponsor_name"] or r["plan_id"] or "").strip().upper())
                    for med, pk, rel, cov in per.values():
                        if ns & med:
                            rel.add(e)
                            if ns & pk:
                                cov.add(e)
            os.remove(local)
        for area, (med, pk, rel, cov) in per.items():
            top = sorted([o for o in out[area] if o["insurer"] == NAMES[ins] and o["status"] == "skipped: below the cut"],
                         key=lambda o: -o["employers"])[:4]
            table[area][ins] = dict(read=len(pk), relevant=len(med),
                                    cov=f"{100 * len(cov) / len(rel):.1f}% of {len(rel):,}" if rel else "-",
                                    top="; ".join(f"{o['network']} ({o['employers']:,})" for o in top))
            print(f"{area} {ins}: read {len(pk)}, coverage {table[area][ins]['cov']}", flush=True)
    md = [f"# Pick-list coverage, {date.today().isoformat()}", "",
          "Coverage = of the employers whose plans use any medical network for the area's states (or a national network) in "
          "the insurer's own index, the share whose plans use at least one network we read. It counts employers, not people.", ""]
    os.makedirs("out", exist_ok=True)
    for area in areas:
        md += [f"## {area.upper()} ({', '.join(sorted(info[area][2]))})", "",
               "| Insurer | Networks read | Relevant medical networks | Employers covered | Biggest networks not read (employers) |",
               "|---|---:|---:|---:|---|"]
        for ins, t in table[area].items():
            md.append(f"| {NAMES[ins]} | {t['read']} | {t['relevant']} | {t['cov']} | {t['top']} |")
        md.append("")
        buf = io.StringIO()
        if out[area]:
            w = csv.DictWriter(buf, fieldnames=list(out[area][0])); w.writeheader()
            w.writerows(sorted(out[area], key=lambda o: (o["insurer"], o["status"], -o["employers"])))
        st.put(f"bot/pickcoverage/{date.today().isoformat()}/{area}.csv", buf.getvalue(), "text/csv")
        open(f"out/{area}.csv", "w").write(buf.getvalue())
    text = "\n".join(md)
    st.put(f"bot/pickcoverage/{date.today().isoformat()}/summary.md", text, "text/markdown")
    open("out/summary.md", "w").write(text)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")


def aco(a):
    st = catalog.Store()
    read = set()
    for fn in os.listdir(HERE):
        if fn.startswith("networks") and fn.endswith(".csv") and "skip" not in fn:
            for r in csv.DictReader(open(os.path.join(HERE, fn))):
                fa = (r.get("finder_arg") or "").split("|")
                if len(fa) >= 2:
                    read.add((fa[0], fa[1]))
    md = [f"# Accountable-care and value networks in the insurer catalogs, {date.today().isoformat()}", ""]
    for ins in INSURERS:
        m, cat = latest(st, ins)
        if not cat:
            continue
        hits = [n for n in cat["networks"] if n.get("coverage", "medical") == "medical" and not n["problems"]
                and VALUE.search(f"{n['network']} {n.get('description', '')}")]
        hits.sort(key=lambda n: -(n.get("employers") or 0))
        md += [f"## {NAMES[ins]} (catalog {m}): {len(hits)} networks", "",
               "| network | name | state | employers | GB | read anywhere? |", "|---|---|---|---:|---:|---|"]
        for n in hits[:40]:
            md.append(f"| {n['network']} | {(n.get('description') or '')[:50]} | {n.get('state') or ''} | {(n.get('employers') or 0):,} | "
                      f"{n.get('gb')} | {'yes' if (ins, n['network']) in read else ''} |")
        md.append("")
    text = "\n".join(md)
    st.put(f"bot/pickcoverage/{date.today().isoformat()}/aco.md", text, "text/markdown")
    os.makedirs("out", exist_ok=True)
    open("out/aco.md", "w").write(text)
    print(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coverage"); c.add_argument("--areas", default="")
    sub.add_parser("aco")
    a = ap.parse_args()
    coverage(a) if a.cmd == "coverage" else aco(a)
