"""People covered in Texas, by insurer and market, from public counts the bot already has (Nov 7, 2026).

For a secondary "weighted by people covered" figure in research reports only. The headline on every page and report
stays the plain median and the plain price.

Two sources, each count labeled with its source and year, never added together into one blended number per row:

  insured     CMS Medical Loss Ratio public use file, reporting year 2024 (insurers/mlr/master_insurers.csv): people
              covered by comprehensive major medical on Dec 31, 2024, per market (individual, small group, large group),
              summed over the insurer's Texas filings in its MLR parent group.
              Also shown, separately: "self-funded lives reported to MLR" (uninsured_plans_yearly), which only some
              insurers report and which is partial.
  self-funded Form 5500 (U.S. Department of Labor), from the employer join (insurers/employers.py, R2
              bot/employers/<date>/employers.parquet): Texas employers (sponsor mailing state TX) whose filing says
              self-funded and whose plan the insurer lists in its own table of contents (that is the insurer whose
              network the plan uses). Count = active participants on the filing (employees, not family members),
              else participants at the start of the year. Plans listed by more than one insurer are counted in a
              separate "listed by more than one insurer" row, never split. Only plans that must file appear
              (most plans with 100+ participants); smaller self-funded plans are missing and are NOT estimated.

Insurers (as named in insurers/networks.csv, the DFW network list) map to MLR parent groups and to the five insurers
whose tables of contents the employer join reads (anthem, uhc, cigna, aetna, hcsc). The map is written out below.

Output: reports/people-weights/tx.csv and tx.md. Column people_total_listed = insured + self-funded participants where
both are known (a sum of two labeled public counts, not an estimate); blank when the self-funded side wasn't loaded.

Run: python insurers/people_weights.py [--employers PATH_OR_R2_KEY] [--no-5500]
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "reports" / "people-weights"
MLR = HERE / "mlr" / "master_insurers.csv"
MLR_SOURCE = "CMS MLR public use file, reporting year 2024 (lives on Dec 31, 2024)"
MLR_URL = "https://www.cms.gov/files/zip/mlr-public-use-file-2024.zip"

# networks.csv insurer -> (MLR parent group in Texas, employer-join insurer key, note)
MAP = {
    "BCBSTX": ("Health Care Service Corp (HCSC)", "hcsc", ""),
    "UnitedHealthcare": ("UnitedHealth Group", "uhc", ""),
    "Aetna": ("CVS Health (Aetna)", "aetna", ""),
    "Cigna": ("Cigna Group", "cigna", ""),
    "Anthem": ("", "anthem", "no Texas comprehensive lives under Elevance in the 2024 MLR file; counted only through employer plans that list Anthem networks"),
    "Wellpoint": ("Elevance Health (Anthem)", "", "Elevance brand; no Texas comprehensive lives under Elevance in the 2024 MLR file"),
    "Ambetter": ("Centene (Ambetter)", "", ""),
    "Oscar": ("Oscar Health", "", ""),
    "Molina": ("Molina Healthcare", "", ""),
    "BSW Health Plan": ("Baylor Scott & White Health Plan", "", ""),
    "Community Health Choice": ("Community Health Choice, Inc.", "", ""),
    "CHRISTUS Health Plan": ("CHRISTUS HEALTH PLAN", "", ""),
    "Curative": ("Curative Inc Grp", "", ""),
    "Moda": ("Oregon Dental Grp", "", "Moda Health Plan, Inc. files under the Oregon Dental group in the MLR file"),
}
FIELDS = ["insurer", "mlr_parent_group", "individual_lives", "small_group_lives", "large_group_lives", "insured_lives_total",
          "insured_source", "self_funded_lives_reported_to_mlr", "employer_join_key", "self_funded_employers_5500",
          "self_funded_participants_5500", "f5500_years", "self_funded_source", "people_total_listed", "rate_table_insurer", "note"]


def mlr_texas():
    g = defaultdict(lambda: defaultdict(int))
    for r in csv.DictReader(open(MLR)):
        if r["state"] != "TX":
            continue
        for k in ("individual_lives", "small_group_lives", "large_group_lives", "total_lives", "uninsured_lives"):
            g[r["parent_group"]][k] += int(float(r[k] or 0))
    return g


def f5500_texas(path):
    """{join key or 'more than one': (employers, participants, years)} for Texas self-funded plans. path: local parquet
    or an R2 key (downloaded once; a few MB)."""
    import duckdb
    if not os.path.exists(path):
        sys.path.insert(0, str(ROOT / "bot"))
        import store
        s3, b = store.r2()
        if path.endswith("/"):
            keys = sorted(o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=path)
                          for o in pg.get("Contents", []) if o["Key"].endswith("/employers.parquet"))
            if not keys:
                raise SystemExit(f"no employers.parquet under {path}")
            path = keys[-1]
        local = "/tmp/employers.parquet"
        s3.download_file(b, path, local)
        print(f"read {path}", flush=True)
        path = local
    con = duckdb.connect()
    rows = con.execute(f"""
        select case when listed_by like '%,%' then 'more than one' else trim(listed_by) end k,
               count(*) as employers, sum(coalesce(active_participants, participants_boy)) as people,
               string_agg(distinct f5500_year, ', ' order by f5500_year) as yrs
        from read_parquet('{path}')
        where state = 'TX' and funding = 'self-funded' and coalesce(listed_by, '') <> ''
          and coalesce(active_participants, participants_boy) is not null
        group by 1""").fetchall()
    return {k: (e, int(p or 0), y or "") for k, e, p, y in rows}


def build(f5500):
    mlr = mlr_texas()
    out = []
    for ins, (grp, key, note) in MAP.items():
        m = mlr.get(grp, {}) if grp else {}
        r = dict(insurer=ins, mlr_parent_group=grp, employer_join_key=key, rate_table_insurer=ins, note=note)
        if m:
            r.update(individual_lives=m["individual_lives"], small_group_lives=m["small_group_lives"],
                     large_group_lives=m["large_group_lives"], insured_lives_total=m["total_lives"], insured_source=MLR_SOURCE,
                     self_funded_lives_reported_to_mlr=m["uninsured_lives"] or "")
        else:
            r.update(insured_source="not in the MLR file for Texas")
        if f5500 is None:
            r["self_funded_source"] = "Form 5500 side not loaded in this run"
        elif key:
            e, p, y = f5500.get(key, (0, 0, ""))
            r.update(self_funded_employers_5500=e, self_funded_participants_5500=p, f5500_years=y,
                     self_funded_source="Form 5500 (DOL), Texas sponsors, self-funded, plan listed in this insurer's table of contents")
        else:
            r["self_funded_source"] = "insurer's table of contents not read by the employer join"
        if f5500 is not None and r.get("insured_lives_total") is not None and r.get("self_funded_participants_5500") is not None:
            r["people_total_listed"] = r["insured_lives_total"] + r["self_funded_participants_5500"]
        elif f5500 is not None and r.get("insured_lives_total") is not None and not key:
            r["people_total_listed"] = r["insured_lives_total"]
        elif f5500 is not None and r.get("self_funded_participants_5500") is not None and not grp:
            r["people_total_listed"] = r["self_funded_participants_5500"]
        out.append(r)
    if f5500 and "more than one" in f5500:
        e, p, y = f5500["more than one"]
        out.append(dict(insurer="(listed by more than one insurer)", self_funded_employers_5500=e, self_funded_participants_5500=p,
                        f5500_years=y, self_funded_source="Form 5500 (DOL); not split between insurers",
                        note="not used as a weight"))
    return out


def write(rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "tx.csv", "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    n = lambda v: f"{v:,}" if isinstance(v, int) else (v or "—")
    L = ["# People covered in Texas, by insurer (for weighting research figures only)", "",
         f"Built {date.today().isoformat()} by `insurers/people_weights.py`. Each count is labeled with its source and year. "
         "Nothing is estimated or scaled: self-funded plans that don't file a Form 5500 (most with under 100 participants) "
         "are missing, and a plan listed by more than one insurer is not split. The site's headline figures are never weighted.", "",
         f"Insured: {MLR_SOURCE}, {MLR_URL}.", "",
         "| Insurer | MLR parent group | Individual | Small group | Large group | Insured total | Self-funded employers (5500) | Self-funded participants (5500) | 5500 years | Total listed |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['insurer']} | {r.get('mlr_parent_group') or '—'} | {n(r.get('individual_lives'))} | {n(r.get('small_group_lives'))} | "
                 f"{n(r.get('large_group_lives'))} | {n(r.get('insured_lives_total'))} | {n(r.get('self_funded_employers_5500'))} | "
                 f"{n(r.get('self_funded_participants_5500'))} | {r.get('f5500_years') or '—'} | {n(r.get('people_total_listed'))} |")
    notes = [f"- {r['insurer']}: {r['note']}" for r in rows if r.get("note")]
    src = sorted({r.get("self_funded_source", "") for r in rows if r.get("self_funded_source")})
    L += ["", "Self-funded side: " + "; ".join(src) + ".",
          "Form 5500 participants are employees on the filing, not family members, so they undercount people covered.", ""]
    L += (["Notes:"] + notes) if notes else []
    (OUT / "tx.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--employers", default="bot/employers/", help="employers.parquet (local path, R2 key, or R2 folder: newest is used)")
    ap.add_argument("--no-5500", action="store_true", help="insured (MLR) side only")
    a = ap.parse_args()
    f5500 = None if a.no_5500 else f5500_texas(a.employers)
    rows = build(f5500)
    write(rows)
    print(f"{len(rows)} rows -> reports/people-weights/tx.md and .csv")


if __name__ == "__main__":
    main()
