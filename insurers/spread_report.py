"""Monthly spread report: how far apart one insurer's rates are for the same service in Dallas-Fort Worth, month by month.

Nov 7, 2026. For a handful of high-volume DFW codes, by code x insurer, from the saved monthly versions of each insurer
file (R2 data/full/rates/ for the current month, history/insurers/<yyyy-mm>/data_full/rates/ for replaced ones):
  10th, 25th, 50th, 75th, 90th percentile rates in dollars and as a multiple of Medicare's rate,
  the 90th-to-10th percentile ratio, the interquartile range (75th minus 25th), bottom- and top-quartile levels.
Every figure is one of the listed rates (nearest rank, the next-higher listed rate when it falls between two, the
same rule CMS gives hospitals); nothing is averaged or estimated.

Which rates count:
  - A "pair" is one provider (NPI) x code x insurer x network (the insurer file's network label), kept apart for
    facility and doctor fees (billing class). Only pairs present in at least 3 consecutive versions of that network's
    file count (STABLE). A pair that appears and disappears month to month says more about the file than the price.
  - Dollar rates above $0, no modifier. Percent-of-charges rates have no dollar amount and are left out.
  - The same amount repeated for one pair in one version counts once. Different amounts for one pair (for example
    two settings) each count; nothing is averaged.
  - Every figure is shown twice: with all rates, and without the rates labeled "may never be used"
    (insurers/pipeline/rate_labels.py). Labels never remove a rate from the tables or the site.
Series breaks (comparisons across them are marked, not adjusted):
  2026-12  the Transparency in Coverage final rule (CMS-9882-F) takes effect
  2027-03  in-network files become one per network, quarterly (about five months after the rule was published)
Secondary figure, report only: the middle of the insurers' medians weighted by people covered in Texas
(reports/people-weights/tx.csv, insurers/people_weights.py). The headline stays the plain median.

Cost: this reads the full DFW insurer tables for each month (tens of GB from R2), so it is meant for a rented machine
or a run Betsy starts on purpose. It never writes to the site.

Run:  python insurers/spread_report.py [--months 2026-10,2026-11] [--codes 70551,...] [--local DIR]
      --local DIR reads <DIR>/<yyyy-mm>/*.parquet instead of R2 (for tests and for tables already downloaded).
Output: reports/spread/<latest month>.md and reports/spread/series.csv (one row per month x code x insurer x with/without).
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "pipeline"))
import rate_labels  # noqa: E402

# 70551 MRI brain, 73721 MRI knee, 74177 CT abdomen and pelvis, 45378 colonoscopy, 470 hip or knee replacement (MS-DRG),
# 99204 new-patient office visit, 77067 screening mammogram, 80053 metabolic panel (all on the site's featured list)
CODES = ["70551", "73721", "74177", "45378", "470", "99204", "77067", "80053"]
NAMES = {"70551": "MRI brain", "73721": "MRI knee", "74177": "CT abdomen and pelvis", "45378": "Colonoscopy",
         "470": "Hip or knee replacement (hospital stay, DRG 470)", "99204": "New-patient office visit",
         "77067": "Screening mammogram", "80053": "Metabolic blood panel"}
STABLE = 3
BREAKS = [("2026-12", "new Transparency in Coverage rule takes effect"), ("2027-03", "in-network files become one per network, quarterly")]
PCTS = (10, 25, 50, 75, 90)
OUT = ROOT / "reports" / "spread"


def nearest_rank(sorted_vals, p):
    """p-th percentile as a listed value: the smallest value with at least p% of values at or below it."""
    n = len(sorted_vals)
    if not n:
        return None
    k = max(1, -(-p * n // 100))   # ceil(p * n / 100)
    return sorted_vals[int(k) - 1]


def weighted_middle(values_weights):
    """The value where the running share of weight first reaches half (a listed value, not an average)."""
    vw = sorted((v, w) for v, w in values_weights if v is not None and w)
    tot = sum(w for _, w in vw)
    run = 0
    for v, w in vw:
        run += w
        if run * 2 >= tot:
            return v
    return None


def break_note(month):
    return "; ".join(f"after {m}: {t}" for m, t in BREAKS if month >= m)


# ------------------------------------------------------------------ reading the monthly tables

def tables(months, local):
    """[(month, path or s3 key)] for DFW insurer tables. Current tables count as this month's version."""
    out = []
    if local:
        for m in months:
            out += [(m, str(p)) for p in sorted((Path(local) / m).glob("*.parquet"))]
        return out
    sys.path.insert(0, str(ROOT / "bot"))
    import store
    s3, b = store.r2()
    cur = date.today().strftime("%Y-%m")

    def ls(pfx):
        return [o["Key"] for pg in s3.get_paginator("list_objects_v2").paginate(Bucket=b, Prefix=pfx)
                for o in pg.get("Contents", []) if o["Key"].endswith(".parquet")]
    for m in months:
        if m == cur:
            out += [(m, k) for k in ls("data/full/rates/")]
        # a table replaced in month m was the version in use before m
        out += [(m, k) for k in ls(f"history/insurers/{m}/data_full/rates/")]
    return out


def collect(con, tabs, codes, bench, work):
    """One row per listed rate for the target codes, with labels, network, insurer and version month."""
    con.execute("""create or replace table s (month varchar, version varchar, network varchar, insurer varchar, npi varchar,
                   tin varchar, billing_code varchar, billing_class varchar, setting varchar, v double,
                   medicare_amount double, far_from_medicare boolean, repeated_amount boolean, one_amount_many_codes boolean)""")
    clist = ", ".join(f"'{c}'" for c in codes)
    # insurer = the short name in the DFW network list (insurers/networks.csv) for the file's network label, so the
    # people-covered weights (keyed by that name) line up; the file's own reporting entity name otherwise
    nets = [(r["network_label"], r["insurer"]) for r in csv.DictReader(open(HERE / "networks.csv"))]
    con.execute("create or replace temp table nets (network_label varchar, insurer varchar)")
    con.executemany("insert into nets values (?, ?)", sorted(set(nets)))
    for month, src in tabs:
        path = src
        if not os.path.exists(src):       # an R2 key: download once, read locally, delete
            sys.path.insert(0, str(ROOT / "bot"))
            import store
            s3, b = store.r2()
            path = str(Path(work) / "t.parquet")
            s3.download_file(b, src, path)
        t = f"read_parquet('{path}')"
        have = rate_labels._columns(con, t)
        g = lambda c: f"cast({c} as varchar)" if c in have else "''"
        mod = "coalesce(cast(billing_code_modifier as varchar), '') = ''" if "billing_code_modifier" in have else "true"
        con.execute(f"""insert into s select '{month}', coalesce(nullif({g('last_updated_on')}, ''), '{month}'),
                          coalesce(nullif({g('file_label')}, ''), {g('source_file')}),
                          coalesce((select any_value(insurer) from nets where network_label = {g('file_label')}), {g('reporting_entity_name')}), npi, tin,
                          case when billing_code in ({clist}) then billing_code else ltrim(billing_code, '0') end, lower({g('billing_class')}), {g('setting')}, v, medicare_amount,
                          far_from_medicare, repeated_amount, one_amount_many_codes
                        from ({rate_labels.labeled_sql(t, bench, have)})
                        where dollar_rate and {mod} and (billing_code in ({clist}) or ltrim(billing_code, '0') in ({clist}))""")
        if path != src:
            os.remove(path)
        print(f"  {month} {src.rsplit('/', 1)[-1]}", flush=True)


def stable_pairs(con):
    """Keep rows whose pair (NPI x code x insurer x network x billing class) is part of a run of 3+ consecutive versions
    of its network's file (every version in that run counts; a pair seen in only one or two versions in a row doesn't)."""
    con.execute(f"""create or replace table s2 as
      with vers as (select network, version, dense_rank() over (partition by network order by version) k
                    from (select distinct network, version from s)),
           p as (select distinct s.network, npi, billing_code, insurer, billing_class, vers.k
                 from s join vers using (network, version)),
           runs as (select *, k - row_number() over (partition by network, npi, billing_code, insurer, billing_class order by k) grp from p),
           ok as (select network, npi, billing_code, insurer, billing_class, k from runs
                  qualify count(*) over (partition by network, npi, billing_code, insurer, billing_class, grp) >= {STABLE})
      select distinct s.month, s.version, s.network, s.insurer, s.npi, s.billing_code, s.billing_class, s.v, s.medicare_amount,
             s.far_from_medicare or s.repeated_amount or s.one_amount_many_codes labeled
      from s join vers using (network, version)
      join ok on ok.network = s.network and ok.npi = s.npi and ok.billing_code = s.billing_code and ok.insurer = s.insurer
              and ok.billing_class = s.billing_class and ok.k = vers.k""")


def stats(con, weights=None):
    """[{month, code, insurer, labels, n, p10..p90, ratio_90_10, iqr, x_medicare...}]"""
    rows = con.execute("select month, billing_code, insurer, billing_class, v, medicare_amount, labeled from s2").fetchall()
    groups = defaultdict(lambda: ([], []))
    med = {}
    for month, code, ins, cls, v, m, lab in rows:
        key = (month, code, ins, cls)
        groups[key][0].append(v)
        if not lab:
            groups[key][1].append(v)
        if m:
            med[(code, cls)] = m
    out = []
    for (month, code, ins, cls), (allv, keep) in sorted(groups.items()):
        for which, vals in (("all rates", allv), ("without labeled rates", keep)):
            vals = sorted(vals)
            r = dict(month=month, code=code, insurer=ins, billing_class=cls, rates=which, n=len(vals), series_break=break_note(month))
            for p in PCTS:
                r[f"p{p}"] = nearest_rank(vals, p)
            r["ratio_90_10"] = round(r["p90"] / r["p10"], 2) if r["p10"] else None
            r["iqr"] = round(r["p75"] - r["p25"], 2) if vals else None
            m = med.get((code, cls))
            r["medicare"] = m
            for p in PCTS:
                r[f"p{p}_x_medicare"] = round(r[f"p{p}"] / m, 2) if m and r[f"p{p}"] is not None else None
            out.append(r)
    if weights:
        for r in out:
            r["insurer_weight"] = weights.get(r["insurer"])
    return out


def people_weighted(out, weights):
    """Secondary figure: middle of the insurers' medians, weighted by people covered in Texas (listed values only)."""
    res = {}
    by = defaultdict(list)
    for r in out:
        by[(r["month"], r["code"], r["billing_class"], r["rates"])].append((r["p50"], weights.get(r["insurer"], 0)))
    for k, vw in by.items():
        res[k] = weighted_middle(vw)
    return res


def load_weights(path):
    """insurer name as written in the rate tables -> people covered (reports/people-weights/tx.csv, column
    rate_table_insurer). Rows without a count are skipped, never filled in."""
    w = {}
    if path and os.path.exists(path):
        for r in csv.DictReader(open(path)):
            n = r.get("people_total_listed") or ""
            if r.get("rate_table_insurer") and n.isdigit():
                for name in r["rate_table_insurer"].split("|"):
                    w[name.strip()] = w.get(name.strip(), 0) + int(n)
    return w


def money(x):
    return "—" if x is None else f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def write(out, weighted, months, codes):
    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["month", "code", "insurer", "billing_class", "rates", "n"] + [f"p{p}" for p in PCTS] + \
           ["ratio_90_10", "iqr", "medicare"] + [f"p{p}_x_medicare" for p in PCTS] + ["series_break"]
    with open(OUT / "series.csv", "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    last = max(r["month"] for r in out) if out else months[-1]
    L = [f"# Spread report: Dallas-Fort Worth, {last}", "",
         f"Built {date.today().isoformat()} by `insurers/spread_report.py` from the saved monthly insurer tables ({', '.join(months)}). "
         f"Only provider-code-insurer-network pairs listed in at least {STABLE} consecutive versions of the file count. "
         "Every figure is a listed rate (nearest rank); nothing is averaged. \"Without labeled rates\" leaves out rates labeled "
         "\"may never be used\" (docs/rate-labels.md); those rates stay in the tables and on the site.", ""]
    if break_note(last):
        L += [f"**Series break:** {break_note(last)}. Changes across this date may come from the new file rules, not prices.", ""]
    for code in codes:
        rs = [r for r in out if r["month"] == last and r["code"] == code]
        if not rs:
            continue
        L += [f"## {NAMES.get(code, code)} ({code})", "",
              "| Insurer | Fee | Rates | Pairs | 10th | 25th | Median | 75th | 90th | 90th ÷ 10th | 75th − 25th | Median × Medicare |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rs, key=lambda r: (r["insurer"], r["billing_class"], r["rates"])):
            L.append(f"| {r['insurer']} | {r['billing_class'] or '—'} | {r['rates']} | {r['n']:,} | {money(r['p10'])} | {money(r['p25'])} | "
                     f"{money(r['p50'])} | {money(r['p75'])} | {money(r['p90'])} | {r['ratio_90_10'] or '—'} | {money(r['iqr'])} | "
                     f"{r['p50_x_medicare'] or '—'} |")
        ww = [(k, v) for k, v in weighted.items() if k[0] == last and k[1] == code and v is not None]
        if ww:
            L += ["", "Secondary figure (report only): middle of the insurers' medians, weighted by people covered in Texas "
                  "(reports/people-weights/tx.md): " + "; ".join(f"{k[2] or 'all'}, {k[3]}: {money(v)}" for k, v in sorted(ww)) + "."]
        L.append("")
    L += ["Month-by-month figures (every code, insurer, fee kind, with and without labeled rates): `reports/spread/series.csv`."]
    (OUT / f"{last}.md").write_text("\n".join(L) + "\n")
    return last


def main():
    import duckdb
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--codes", default=",".join(CODES))
    ap.add_argument("--local", default="")
    ap.add_argument("--medicare", default="", help="the site's benchmark file (med_all.json); default: read it from R2")
    ap.add_argument("--weights", default=str(ROOT / "reports" / "people-weights" / "tx.csv"))
    ap.add_argument("--work", default="/tmp/spread")
    a = ap.parse_args()
    months = sorted(m.strip() for m in a.months.split(",") if m.strip())
    codes = [c.strip() for c in a.codes.split(",") if c.strip()]
    Path(a.work).mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    bench = None
    if a.medicare:
        bench = rate_labels.load_bench(con, json.load(open(a.medicare)))
    elif not a.local:
        bench = rate_labels.bench_from_storage(con, str(Path(a.work) / "med_all.json"))
    tabs = tables(months, a.local)
    print(f"{len(tabs)} tables for {months}", flush=True)
    collect(con, tabs, codes, bench, a.work)
    stable_pairs(con)
    weights = load_weights(a.weights)
    out = stats(con, weights)
    last = write(out, people_weighted(out, weights) if weights else {}, months, codes)
    print(f"-> reports/spread/{last}.md and series.csv ({len(out)} rows)")


if __name__ == "__main__":
    main()
