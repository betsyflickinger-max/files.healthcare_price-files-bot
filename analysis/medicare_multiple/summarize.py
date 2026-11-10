"""Turn the per-table parts (rates.py) into the report: per code, per bucket, two totals, coverage, sanity check.

Rules (Betsy, Nov 10, 2026):
  - Percentiles are nearest-rank: the actual listed amount at that rank (a unit's amount / its own Medicare amount).
    Nothing is averaged. A code gets figures only with at least MIN_PROVIDERS different providers.
  - Per bucket: the middle of its codes' middles.
  - Total (a), Medicare-use weighted: sum(volume x middle private amount) / sum(volume x middle Medicare amount), over
    codes with a figure and a Medicare volume in the state. Label: "weighted by Medicare's mix of care, which skews older".
  - Total (b), equal weight: the middle of all codes' middles.
  - Every figure twice: all rates, and without rates labeled "may never be used" (docs/rate-labels.md).
  - In-network, out-of-network and unclear are separate figures, never pooled. Hospital files: commercial plans are the
    headline; Medicare Advantage, Medicaid and other public plans are reported on their own.
"""
import csv
import json
import math
from datetime import date
from pathlib import Path

MIN_PROVIDERS = 5
PCTS = (10, 50, 90)
WHICH = (("all rates", "units"), ("without likely-unused rates", "units_keep"))
# views kept out of both totals (still reported per code and per bucket): no like-for-like Medicare amount
NOT_IN_TOTALS = {"facility_unmatched": "Medicare amount is the national outpatient rate; the place isn't matched to a Medicare record",
                 "none": "no Medicare benchmark"}
NOT_IN_WEIGHTED = {"anesthesia": "Medicare counts anesthesia cases, the benchmark is per unit: volumes and amounts don't line up",
                   "asc": "no Medicare surgery-center volume file was in scope (only physician, outpatient hospital and inpatient files)"}
# Medicare volume used for each view (kinds in volumes.csv)
VOLUME_KINDS = {"professional": ("professional",), "lab": ("professional", "outpatient"), "drug": ("professional", "outpatient"),
                "ambulance": ("professional",), "outpatient_hospital": ("outpatient",), "inpatient": ("inpatient",), "dme": ("dme",)}
FIGURES = [  # (label, source, status, program filter)
    ("Insurer files, in-network", "insurer", "in-network", "commercial"),
    ("Insurer files, network unclear (\"Traditional\")", "insurer", "unclear", "commercial"),
    ("Insurer files, out-of-network (allowed amounts)", "allowed", "out-of-network", "commercial"),
    ("Hospital files, commercial in-network", "hospital", "in-network", "commercial"),
    ("Hospital files, commercial out-of-network", "hospital", "out-of-network", "commercial"),
    ("Hospital files, commercial plan unclear (\"Traditional\")", "hospital", "unclear", "commercial"),
    ("Hospital files, Medicare Advantage plans", "hospital", "in-network", "Medicare Advantage"),
    ("Hospital files, Medicaid / dual plans", "hospital", "in-network", "Medicaid / dual"),
]


def nearest_rank(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return vals[max(1, math.ceil(p * len(vals) / 100)) - 1]


def code_figures(con, parts_glob, codes_glob, wcol, state, by_segment=False):
    """Per (source, status, program, view, bucket, code[, segment]): units, nearest-rank p10/p50/p90 of the ratio, middle
    private amount and middle Medicare amount, providers (exact up to the 5-provider rule)."""
    seg = ", segment" if by_segment else ""
    con.execute(f"""create or replace temp table d as
      select source, status, program, view, bucket, code{seg}, rate / medicare_amount r, rate, medicare_amount m, sum({wcol}) w
      from read_parquet('{parts_glob}', union_by_name=true)
      where state = '{state}' and rate_kind = 'dollar' and rate is not null and medicare_amount > 0 and {wcol} > 0
      group by all""")
    key = "source, status, program, view, bucket, code" + seg
    nkey = 7 if by_segment else 6
    q = f"""
      with t as (select {key}, sum(w) tot from d group by all),
      cr as (select d.*, sum(w) over (partition by {key} order by r, rate rows unbounded preceding) cum from d),
      cp as (select d.*, sum(w) over (partition by {key} order by rate rows unbounded preceding) cum from d),
      cm as (select d.*, sum(w) over (partition by {key} order by m rows unbounded preceding) cum from d),
      a as (select {key}, {", ".join(f"min(r) filter (where cum >= ceil({p / 100} * tot)) p{p}" for p in PCTS)}
            from cr join t using ({key}) group by all),
      b as (select {key}, min(rate) filter (where cum >= ceil(0.5 * tot)) mid_private from cp join t using ({key}) group by all),
      c as (select {key}, min(m) filter (where cum >= ceil(0.5 * tot)) mid_medicare from cm join t using ({key}) group by all)
      select t.*, a.p10, a.p50, a.p90, b.mid_private, c.mid_medicare from t join a using ({key}) join b using ({key}) join c using ({key})"""
    figs = {tuple(r[:nkey]): dict(zip(["units", "p10", "p50", "p90", "mid_private", "mid_medicare"], r[nkey:]))
            for r in con.execute(q).fetchall()}
    nk = "n_npi_keep" if wcol == "units_keep" else "n_npi"
    fk = "first5_keep" if wcol == "units_keep" else "first5"
    # a big table is read in passes that split its providers: add the passes up per table, then take the largest table
    for r in con.execute(f"""select source, status, program, view, bucket, code{seg}, max(n), list_distinct(flatten(list(f5)))
                             from (select source, table_name, status, program, view, bucket, code{seg}, sum({nk}) n,
                                          list_distinct(flatten(list({fk}))) f5
                                   from read_parquet('{codes_glob}', union_by_name=true) where in_ratio and state = '{state}'
                                   group by all)
                             group by all""").fetchall():
        f = figs.get(tuple(r[:nkey]))
        if f is not None:
            f["providers_at_least"] = max(int(r[nkey] or 0), len(r[nkey + 1] or []))
            f["enough_providers"] = len(r[nkey + 1] or []) >= MIN_PROVIDERS
    return figs


def load_volumes(bench, state):
    v = {}
    for r in csv.DictReader(open(Path(bench) / "volumes.csv")):
        if r["state"] != state:
            continue
        v[(r["kind"], r["code"])] = v.get((r["kind"], r["code"]), 0) + float(r["volume"])
    return v


def volume_for(vols, view, code):
    kinds = VOLUME_KINDS.get(view)
    if not kinds or view in NOT_IN_WEIGHTED:
        return None
    t = sum(vols.get((k, code), 0) for k in kinds)
    return t or None


def summarize(con, parts_dir, bench, out, state):
    parts_dir, out = Path(parts_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pg, cg, ng = str(parts_dir / "*.part.parquet"), str(parts_dir / "*.codes.parquet"), str(parts_dir / "*.npis.parquet")
    vols = load_volumes(bench, state)
    code_rows, bucket_rows, total_rows = [], [], []
    for which, wcol in WHICH:
        figs = code_figures(con, pg, cg, wcol, state)
        for k, f in figs.items():
            src, status, program, view, bucket, code = k
            ok = f.get("enough_providers", False)
            vol = volume_for(vols, view, code)
            code_rows.append(dict(rates=which, source=src, status=status, program=program, view=view, bucket=bucket, code=code,
                                  units=int(f["units"]), providers_at_least=f.get("providers_at_least", 0),
                                  figure="yes" if ok else f"no: fewer than {MIN_PROVIDERS} providers",
                                  p10=_r(f["p10"]) if ok else None, middle=_r(f["p50"]) if ok else None, p90=_r(f["p90"]) if ok else None,
                                  middle_private_amount=f["mid_private"] if ok else None, middle_medicare_amount=f["mid_medicare"] if ok else None,
                                  medicare_volume_2024=vol))
    # buckets and totals, per figure
    for label, src, status, program in FIGURES:
        for which, _ in WHICH:
            rs = [r for r in code_rows if r["rates"] == which and r["source"] == src and r["status"] == status and r["program"] == program]
            if not rs:
                continue
            for b in sorted({r["bucket"] for r in rs}):
                br = [r for r in rs if r["bucket"] == b]
                ok = [r for r in br if r["figure"] == "yes"]
                wv = [r for r in ok if r["medicare_volume_2024"]]
                bucket_rows.append(dict(figure=label, rates=which, bucket=b, codes_with_figure=len(ok), codes_too_few_providers=len(br) - len(ok),
                                        units=sum(r["units"] for r in ok), middle_of_code_middles=nearest_rank([r["middle"] for r in ok], 50),
                                        medicare_use_weighted=_weighted(wv), codes_with_volume=len(wv)))
            ok = [r for r in rs if r["figure"] == "yes" and r["view"] not in NOT_IN_TOTALS]
            wv = [r for r in ok if r["medicare_volume_2024"]]
            total_rows.append(dict(figure=label, rates=which, codes=len(ok), codes_weighted=len(wv),
                                   equal_weight=nearest_rank([r["middle"] for r in ok], 50), medicare_use_weighted=_weighted(wv),
                                   units=sum(r["units"] for r in ok)))
            for name, views in (("Doctor and clinician fees (all RBCS categories)", {"professional"}),
                                ("Hospital outpatient facility fees", {"outpatient_hospital"}),
                                ("Hospital stays (inpatient)", {"inpatient"}),
                                ("Hospitals: inpatient + outpatient", {"inpatient", "outpatient_hospital"})):
                sub = [r for r in wv if r["view"] in views]
                total_rows.append(dict(figure=label, rates=which, codes=len([r for r in ok if r["view"] in views]), codes_weighted=len(sub),
                                       equal_weight=nearest_rank([r["middle"] for r in ok if r["view"] in views], 50),
                                       medicare_use_weighted=_weighted(sub), units=sum(r["units"] for r in sub), subtotal=name))
    seg_rows = []
    for which, wcol in WHICH:   # by market segment, as far as the file's own network name says (insurer files, in-network)
        figs = code_figures(con, pg, cg, wcol, state, by_segment=True)
        by = {}
        for k, f in figs.items():
            src, status, program, view, bucket, code, segment = k
            if src == "insurer" and status == "in-network" and f.get("enough_providers"):
                by.setdefault((segment, bucket), []).append((view, f["p50"]))
                if view not in NOT_IN_TOTALS:
                    by.setdefault((segment, "(all kinds of care: equal weight)"), []).append((view, f["p50"]))
        for (segment, bucket), vs in sorted(by.items()):
            seg_rows.append(dict(rates=which, segment=segment, bucket=bucket, codes_with_figure=len(vs),
                                 middle_of_code_middles=_r(nearest_rank([v for _, v in vs], 50))))
    _write_csv(out / "buckets_by_segment.csv", seg_rows)
    providers = _providers(con, ng, state)
    coverage = _coverage(con, pg, state)
    _write_csv(out / "codes.csv", code_rows)
    _write_csv(out / "buckets.csv", bucket_rows)
    _write_csv(out / "totals.csv", total_rows)
    _write_csv(out / "coverage.csv", coverage)
    _write_csv(out / "providers.csv", providers)
    _write_csv(out / "no_benchmark_codes.csv", _no_bench(con, pg, state))
    srcs = json.loads((Path(bench) / "sources.json").read_text())
    _write_csv(out / "medicare_sources.csv", [dict(key=k, what=v.get("what"), year=v.get("year"), url=v.get("url"), sha256=v.get("sha256", ""))
                                               for k, v in srcs.items() if not k.startswith("_")])
    from report import write_md
    write_md(out, state, code_rows, bucket_rows, total_rows, coverage, providers, seg_rows)
    return dict(codes=len(code_rows), buckets=len(bucket_rows), totals=len(total_rows))


def _r(x):
    return None if x is None else round(x, 3)


def _weighted(rows):
    num = sum(r["medicare_volume_2024"] * r["middle_private_amount"] for r in rows)
    den = sum(r["medicare_volume_2024"] * r["middle_medicare_amount"] for r in rows)
    return round(num / den, 3) if den else None


def _providers(con, ng, state):
    q = f"""select source, status, program, bucket, count(distinct npi) filter (where in_ratio) providers,
                   count(distinct npi) filter (where in_ratio and any_keep) providers_keep
            from read_parquet('{ng}', union_by_name=true) where state = '{state}' group by all
            union all
            select source, status, program, '(all buckets in the totals)', count(distinct npi) filter (where in_ratio),
                   count(distinct npi) filter (where in_ratio and any_keep)
            from read_parquet('{ng}', union_by_name=true) where state = '{state}' and view not in ('facility_unmatched', 'none') group by all
            order by all"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _coverage(con, pg, state):
    """Every unit, by source/status/program and why it is or isn't in a ratio. Nothing is dropped silently."""
    q = f"""select source, status, program,
              case when rate_kind <> 'dollar' then 'kept out of the ratio: ' || rate_kind
                   when view = 'none' then 'kept out: no Medicare benchmark'
                   when view = 'facility_unmatched' then 'in its own figure, not in the totals: facility not matched'
                   else 'in the ratio' end as what,
              count(distinct code) codes, sum(units) units, sum(units_keep) units_keep, sum(units_far) far_from_medicare,
              sum(units_many) one_amount_many_codes, sum(units_spec) specialty_mismatch
            from read_parquet('{pg}', union_by_name=true) where state = '{state}' group by all order by all"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _no_bench(con, pg, state):
    q = f"""select source, status, code_type, code, any_value(reason) reason, sum(units) units
            from read_parquet('{pg}', union_by_name=true) where state = '{state}' and view = 'none' and rate_kind = 'dollar'
            group by all order by units desc"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _write_csv(path, rows):
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, keys or ["empty"])
        w.writeheader()
        w.writerows(rows)


def built_on():
    return date.today().isoformat()
