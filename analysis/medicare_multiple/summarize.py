"""Turn the per-table parts (rates.py) into the report: per code, per bucket, two totals, coverage, sanity check.

Rules (Betsy, Nov 10, 2026):
  - Percentiles are nearest-rank: the actual listed amount at that rank (a unit's amount / its own Medicare amount).
    Nothing is averaged. A code gets figures only with at least MIN_PROVIDERS different providers.
  - Per bucket: the middle of its codes' middles.
  - Total (a), Medicare-use weighted: sum(volume x middle private amount) / sum(volume x middle Medicare amount), over
    codes with a figure and a Medicare volume in the state. Label: "weighted by Medicare's mix of care, which skews older".
  - Total (b), equal weight: the middle of all codes' middles.
  - Every figure three ways (Nov 10, 2026, Betsy): all rates; rates at providers with evidence they do this service
    (the main "clean" view: billed Medicare for it, or the hospital's own file lists it / counts paid claims for it); and
    the 0.5x-8x Medicare range check (rates labeled "may never be used" left out, docs/rate-labels.md) as a secondary view.
    Rates under 0.5x and over 8x Medicare are listed in their own table (tails.csv): high prices are never dropped.
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
ALL, EVIDENCE, RANGE = "all rates", "providers with evidence they do this service", "range check: 0.5×–8× Medicare"
WHICH = ((ALL, "all"), (EVIDENCE, "evidence"), (RANGE, "range"))
# weight of a part row in each view. Evidence: (a) Medicare billing (units_ev, decided per rate in rates.py), else (b) the
# hospital's own file lists the code (insurer and allowed-amount rates at a hospital), or (c) its 2026 count of allowed amounts
# for the code is above zero (the hospital file's own rates: listing is what the file is, so (b) would be true of every row)
HOSP_EV = "(p.ccn is not null and ((p.source = 'hospital' and hl.counted) or (p.source <> 'hospital' and hl.ccn is not null)))"
WEIGHT = {"all": "p.units", "range": "p.units_keep",
          "evidence": f"coalesce(p.units_ev, 0) + case when {HOSP_EV} then p.units - coalesce(p.units_ev, 0) else 0 end"}
# views kept out of both totals (still reported per code and per bucket): no like-for-like Medicare amount
NOT_IN_TOTALS = {"facility_unmatched": "Medicare amount is the national outpatient rate; the place isn't matched to a Medicare record",
                 "none": "no Medicare benchmark"}
NOT_IN_WEIGHTED = {"asc": "no Medicare surgery-center volume file was in scope (only physician, outpatient hospital and inpatient files)"}
# anesthesia is compared per unit (conversion factor), so its weight is Medicare's allowed DOLLARS for the code in the state
# (services x average allowed, Physician & Other Practitioners by Geography and Service), not a service count
DOLLAR_WEIGHTED = {"anesthesia"}
# Medicare volume used for each view (kinds in volumes.csv)
VOLUME_KINDS = {"professional": ("professional",), "anesthesia": ("professional",), "lab": ("professional", "outpatient"), "drug": ("professional", "outpatient"),
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


def hospital_lists(con, hcodes_glob):
    """hl: (ccn, code, counted) for every code a hospital file of this run lists (rates.py .hcodes.parquet)."""
    import glob as g
    if g.glob(hcodes_glob):
        con.execute(f"""create or replace temp table hl as select ccn, code, bool_or(counted) counted
                        from read_parquet('{hcodes_glob}', union_by_name=true) where ccn is not null group by all""")
    else:
        con.execute("create or replace temp table hl as select null::varchar ccn, null::varchar code, null::boolean counted where false")


def parts_with_lists(parts_glob):
    return f"read_parquet('{parts_glob}', union_by_name=true) p left join hl on hl.ccn = p.ccn and hl.code = p.code"


def code_figures(con, parts_glob, codes_glob, kind, state, by_segment=False):
    """Per (source, status, program, view, bucket, code[, segment]): units, nearest-rank p10/p50/p90 of the ratio, middle
    private amount and middle Medicare amount, providers (exact up to the 5-provider rule). kind: all | evidence | range."""
    seg = ", p.segment" if by_segment else ""
    wexpr = WEIGHT[kind]
    con.execute(f"""create or replace temp table d as
      select p.source, p.status, p.program, p.view, p.bucket, p.code{seg}, p.rate / p.medicare_amount r, p.rate, p.medicare_amount m,
             p.rate / p.medicare_facility rf, p.rate / p.medicare_office ro, sum({wexpr}) w
      from {parts_with_lists(parts_glob)}
      where p.state = '{state}' and p.rate_kind = 'dollar' and p.rate is not null and p.medicare_amount > 0
      group by all having sum({wexpr}) > 0""")
    key = "source, status, program, view, bucket, code" + (", segment" if by_segment else "")
    nkey = 7 if by_segment else 6
    q = f"""
      with t as (select {key}, sum(w) tot from d group by all),
      cr as (select d.*, sum(w) over (partition by {key} order by r, rate rows unbounded preceding) cum from d),
      cp as (select d.*, sum(w) over (partition by {key} order by rate rows unbounded preceding) cum from d),
      cm as (select d.*, sum(w) over (partition by {key} order by m rows unbounded preceding) cum from d),
      a as (select {key}, {", ".join(f"min(r) filter (where cum >= ceil({p / 100} * tot)) p{p}" for p in PCTS)}
            from cr join t using ({key}) group by all),
      b as (select {key}, min(rate) filter (where cum >= ceil(0.5 * tot)) mid_private from cp join t using ({key}) group by all),
      c as (select {key}, min(m) filter (where cum >= ceil(0.5 * tot)) mid_medicare from cm join t using ({key}) group by all),
      -- doctor fees: the same middle if every rate were compared with Medicare's facility rate, or with its office rate
      ff as (select {key}, rf, sum(w) over (partition by {key} order by rf rows unbounded preceding) cum,
                    sum(w) over (partition by {key}) tt from d where rf is not null),
      fo as (select {key}, ro, sum(w) over (partition by {key} order by ro rows unbounded preceding) cum,
                    sum(w) over (partition by {key}) tt from d where ro is not null),
      f as (select {key}, min(rf) filter (where cum >= ceil(0.5 * tt)) mid_fac from ff group by all),
      o as (select {key}, min(ro) filter (where cum >= ceil(0.5 * tt)) mid_off from fo group by all)
      select t.*, a.p10, a.p50, a.p90, b.mid_private, c.mid_medicare, f.mid_fac, o.mid_off
      from t join a using ({key}) join b using ({key}) join c using ({key}) left join f using ({key}) left join o using ({key})"""
    figs = {tuple(r[:nkey]): dict(zip(["units", "p10", "p50", "p90", "mid_private", "mid_medicare", "mid_fac", "mid_off"], r[nkey:]))
            for r in con.execute(q).fetchall()}
    sg = ", segment" if by_segment else ""
    if kind == "evidence":
        # providers with evidence (a), plus providers at a hospital whose own file lists the code (b) or counts claims for it (c)
        inner = f"""with c as (select *, row_number() over () rid from read_parquet('{codes_glob}', union_by_name=true)
                               where in_ratio and state = '{state}'),
            e as (select rid, source, code, unnest(ccn_npi_noev) cn from c where ccn_npi_noev is not null),
            x as (select e.rid, list(distinct split_part(e.cn, '|', 2)) xs from e
                  join hl on hl.ccn = split_part(e.cn, '|', 1) and hl.code = e.code and (e.source <> 'hospital' or hl.counted)
                  group by e.rid)
            select source, table_name, status, program, view, bucket, code{sg}, sum(coalesce(n_npi_ev, 0) + coalesce(len(xs), 0)) n,
                   list_distinct(flatten(list(list_concat(coalesce(first5_ev, []), coalesce(xs[1:5], []))))) f5
            from c left join x using (rid) group by all"""
    else:
        nk, fk = ("n_npi_keep", "first5_keep") if kind == "range" else ("n_npi", "first5")
        inner = f"""select source, table_name, status, program, view, bucket, code{sg}, sum({nk}) n, list_distinct(flatten(list({fk}))) f5
                    from read_parquet('{codes_glob}', union_by_name=true) where in_ratio and state = '{state}' group by all"""
    # a big table is read in passes that split its providers: add the passes up per table, then take the largest table
    for r in con.execute(f"""select source, status, program, view, bucket, code{sg}, max(n), list_distinct(flatten(list(f5)))
                             from ({inner}) group by all""").fetchall():
        f = figs.get(tuple(r[:nkey]))
        if f is not None:
            f["providers_at_least"] = max(int(r[nkey] or 0), len(r[nkey + 1] or []))
            f["enough_providers"] = len(r[nkey + 1] or []) >= MIN_PROVIDERS
    return figs


def load_volumes(bench, state):
    """{(kind, code): services} and, under ("$" + kind, code), Medicare allowed dollars where the file gives them."""
    v = {}
    for r in csv.DictReader(open(Path(bench) / "volumes.csv")):
        if r["state"] != state:
            continue
        v[(r["kind"], r["code"])] = v.get((r["kind"], r["code"]), 0) + float(r["volume"])
        if r.get("allowed"):
            v[("$" + r["kind"], r["code"])] = v.get(("$" + r["kind"], r["code"]), 0) + float(r["allowed"])
    return v


def volume_for(vols, view, code):
    kinds = VOLUME_KINDS.get(view)
    if not kinds or view in NOT_IN_WEIGHTED or view in DOLLAR_WEIGHTED:
        return None
    t = sum(vols.get((k, code), 0) for k in kinds)
    return t or None


def dollars_for(vols, view, code):
    if view not in DOLLAR_WEIGHTED:
        return None
    return vols.get(("$professional", code)) or None


def summarize(con, parts_dir, bench, out, state):
    parts_dir, out = Path(parts_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pg, cg, ng = str(parts_dir / "*.part.parquet"), str(parts_dir / "*.codes.parquet"), str(parts_dir / "*.npis.parquet")
    hospital_lists(con, str(parts_dir / "*.hcodes.parquet"))
    vols = load_volumes(bench, state)
    code_rows, bucket_rows, total_rows = [], [], []
    for which, kind in WHICH:
        figs = code_figures(con, pg, cg, kind, state)
        for k, f in figs.items():
            src, status, program, view, bucket, code = k
            ok = f.get("enough_providers", False)
            vol = volume_for(vols, view, code)
            dol = dollars_for(vols, view, code)
            code_rows.append(dict(rates=which, source=src, status=status, program=program, view=view, bucket=bucket, code=code,
                                  units=int(f["units"]), providers_at_least=f.get("providers_at_least", 0),
                                  figure="yes" if ok else f"no: fewer than {MIN_PROVIDERS} providers",
                                  p10=_r(f["p10"]) if ok else None, middle=_r(f["p50"]) if ok else None, p90=_r(f["p90"]) if ok else None,
                                  middle_private_amount=f["mid_private"] if ok else None, middle_medicare_amount=f["mid_medicare"] if ok else None,
                                  middle_vs_facility_rate=_r(f["mid_fac"]) if ok else None, middle_vs_office_rate=_r(f["mid_off"]) if ok else None,
                                  medicare_volume_2024=vol, medicare_dollars_2024=dol))
    # buckets and totals, per figure
    for label, src, status, program in FIGURES:
        for which, _ in WHICH:
            rs = [r for r in code_rows if r["rates"] == which and r["source"] == src and r["status"] == status and r["program"] == program]
            if not rs:
                continue
            for b in sorted({r["bucket"] for r in rs}):
                br = [r for r in rs if r["bucket"] == b]
                ok = [r for r in br if r["figure"] == "yes"]
                wv = [r for r in ok if r["medicare_volume_2024"] or r.get("medicare_dollars_2024")]
                bucket_rows.append(dict(figure=label, rates=which, bucket=b, codes_with_figure=len(ok), codes_too_few_providers=len(br) - len(ok),
                                        units=sum(r["units"] for r in ok), middle_of_code_middles=nearest_rank([r["middle"] for r in ok], 50),
                                        medicare_use_weighted=_weighted(wv), codes_with_volume=len(wv)))
            ok = [r for r in rs if r["figure"] == "yes" and r["view"] not in NOT_IN_TOTALS]
            wv = [r for r in ok if r["medicare_volume_2024"] or r.get("medicare_dollars_2024")]
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
    for which, kind in WHICH:   # by market segment (insurer files, in-network)
        figs = code_figures(con, pg, cg, kind, state, by_segment=True)
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
    tails = _tails(con, pg, state)
    _write_csv(out / "tails.csv", tails)
    methods = _methods(con, pg, state)
    _write_csv(out / "methods.csv", methods)
    anes = _anesthesia_cases(con, pg, state)
    _write_csv(out / "anesthesia_per_case.csv", anes)
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
    write_md(out, state, code_rows, bucket_rows, total_rows, coverage, providers, seg_rows, tails, methods, anes)
    return dict(codes=len(code_rows), buckets=len(bucket_rows), totals=len(total_rows))


def _r(x):
    return None if x is None else round(x, 3)


def _weighted(rows):
    """sum(volume x middle private amount) / sum(volume x middle Medicare amount). A dollar-weighted code (anesthesia, per
    unit) adds Medicare's dollars D for it: D x (middle private / middle Medicare) above, D below."""
    num = den = 0.0
    for r in rows:
        if r.get("medicare_dollars_2024"):
            num += r["medicare_dollars_2024"] * r["middle_private_amount"] / r["middle_medicare_amount"]
            den += r["medicare_dollars_2024"]
        elif r.get("medicare_volume_2024"):
            num += r["medicare_volume_2024"] * r["middle_private_amount"]
            den += r["medicare_volume_2024"] * r["middle_medicare_amount"]
    return round(num / den, 3) if den else None


def _providers(con, ng, state):
    q = f"""with n as (select *, row_number() over () rid from read_parquet('{ng}', union_by_name=true) where state = '{state}'),
            y as (select rid, source, ccn, unnest(codes_noev) code from n where not coalesce(any_ev, false) and ccn is not null),
            x as (select distinct rid from y join hl on hl.ccn = y.ccn and hl.code = y.code and (y.source <> 'hospital' or hl.counted)),
            m as (select n.*, coalesce(any_ev, false) or x.rid is not null ev from n left join x using (rid))
            select source, status, program, bucket, count(distinct npi) filter (where in_ratio) providers,
                   count(distinct npi) filter (where in_ratio and ev) providers_evidence,
                   count(distinct npi) filter (where in_ratio and any_keep) providers_range_check
            from m group by all
            union all
            select source, status, program, '(all buckets in the totals)', count(distinct npi) filter (where in_ratio),
                   count(distinct npi) filter (where in_ratio and ev), count(distinct npi) filter (where in_ratio and any_keep)
            from m where view not in ('facility_unmatched', 'none') group by all
            order by all"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _coverage(con, pg, state):
    """Every unit, by source/status/program and why it is or isn't in a ratio. Nothing is dropped silently."""
    q = f"""select p.source, p.status, p.program,
              case when p.rate_kind <> 'dollar' then 'kept out of the ratio: ' || p.rate_kind
                   when p.view = 'none' then 'kept out: no Medicare benchmark'
                   when p.view = 'facility_unmatched' then 'in its own figure, not in the totals: facility not matched'
                   else 'in the ratio' end as what,
              count(distinct p.code) codes, sum(p.units) units, sum({WEIGHT['evidence']}) units_with_evidence,
              sum(coalesce(p.units_ev, 0)) evidence_medicare_billing, sum(p.units_keep) units_range_check,
              sum(p.units_far) far_from_medicare, sum(p.units_many) one_amount_many_codes, sum(p.units_spec) specialty_mismatch
            from {parts_with_lists(pg)} where p.state = '{state}' group by all order by all"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _methods(con, pg, state):
    """How many listed rates used each method: place of service for doctor fees (and later: market segment, anesthesia)."""
    q = f"""select 'place of service (doctor fees)' question, source, status, pos method, sum(units) units, count(distinct code) codes
            from read_parquet('{pg}', union_by_name=true)
            where state = '{state}' and view = 'professional' and rate_kind = 'dollar' group by all
            union all
            select 'anesthesia: per unit or per case', source, status,
                   case when rate_kind = 'dollar' then 'per unit (up to $200, or the rate says so): compared with the conversion factor'
                        else rate_kind || ': counted, no ratio' end, sum(units), count(distinct code)
            from read_parquet('{pg}', union_by_name=true)
            where state = '{state}' and view = 'anesthesia' and (rate_kind = 'dollar' or rate_kind like 'anesthesia:%') group by all
            order by all"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _anesthesia_cases(con, pg, state):
    """Anesthesia amounts that look like a whole case: per code, how many and the middle listed amount in dollars. No ratio:
    Medicare pays per unit (base units + time units), and no public CMS source gives typical time per code."""
    q = f"""with d as (select source, status, program, code, rate, sum(units) w from read_parquet('{pg}', union_by_name=true)
                       where state = '{state}' and view = 'anesthesia' and rate_kind like 'anesthesia:%' and rate is not null and units > 0
                       group by all),
            c as (select *, sum(w) over (partition by source, status, program, code order by rate rows unbounded preceding) cum,
                         sum(w) over (partition by source, status, program, code) tot from d)
            select source, status, program, code, max(tot)::bigint listed_rates,
                   min(rate) filter (where cum >= ceil(0.5 * tot)) middle_listed_amount, min(rate) lowest, max(rate) highest
            from c group by all order by listed_rates desc"""
    c = con.execute(q)
    cols = [d[0] for d in c.description]
    return [dict(zip(cols, r)) for r in c.fetchall()]


def _tails(con, pg, state):
    """Rates under 0.5x or over 8x Medicare, in their own table (never dropped): per code, how many, how many at providers with
    evidence they do the service, and the most extreme multiple and listed amount."""
    q = f"""select p.source, p.status, p.program, p.view, p.bucket, p.code,
              case when p.rate < 0.5 * p.medicare_amount then 'under 0.5×' else 'over 8×' end side,
              sum(p.units) units, sum({WEIGHT['evidence']}) units_with_evidence,
              round(max(p.rate / p.medicare_amount), 2) highest_multiple, round(min(p.rate / p.medicare_amount), 3) lowest_multiple,
              max(p.rate) highest_listed_amount, min(p.rate) lowest_listed_amount
            from {parts_with_lists(pg)}
            where p.state = '{state}' and p.rate_kind = 'dollar' and p.medicare_amount > 0 and p.rate is not null
              and (p.rate < 0.5 * p.medicare_amount or p.rate > 8 * p.medicare_amount)
            group by all order by side, units desc"""
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
