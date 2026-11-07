"""Labels for insurer rates that may never be used (Nov 7, 2026). Labels only: nothing is removed, re-ranked or hidden.

Insurers' in-network files list a rate for many provider-and-service pairs that will never be billed (an eye doctor with
a knee-replacement rate). Research: Muhlestein, Health Affairs Scholar, Nov 2025, found 91.8% of listed rates in 61
insurers' files were for providers unlikely to perform the service. This module marks rates that show the usual signs,
so reports can show figures with and without them. Wording on any page or report: "may never be used" or "unverified".
Never call a labeled rate fake, and never treat a label as a finding about an insurer.

Three labels (each row can carry any of them):

  a  far_from_medicare   a dollar rate below 50% or above 800% of Medicare's rate for the same code and kind of fee
                         (LOW, HIGH). Only when the bot has a Medicare figure for that code and kind of fee; otherwise the
                         row is "no Medicare figure" and gets no label. High rates stay visible: this is a label.
  b  repeated_amount     the same dollar amount listed more than once for the same service (code + modifier + billing
                         class + setting + rate type) at the same provider (NPI + TIN) in one file. Every copy is kept;
                         counts collapse the copies into one ("listed N times, counted once").
  c  one_amount_many_codes  one identical dollar amount at the same provider (NPI + TIN) and billing class for at least
                         MANY_CODES different billing codes that span at least MANY_FAMILIES code families (first three
                         characters of the code, e.g. 293xx vs 450xx). Example that set the threshold: Aetna listed
                         $3,682.00 for 20 different codes at 12 Medical City NPIs. Ten codes across three families keeps
                         real flat fees for a few related codes (e.g. one price for 99213 and 99214) out of this label.
                         This is stricter than the site's existing "flat case rate" flag (same amount for 5+ codes), which
                         is unchanged.

Not labeled: $0 rates (the census already counts them), percentage-of-charges rates (no dollar amount to compare).

Use:
  labeled_sql(t, bench)   SQL for the table expression t with three label columns added (+ medicare_amount, medicare_basis,
                          times_medicare, repeat_count). bench: a DuckDB table expression with columns
                          billing_code, fee ('facility' | 'professional'), medicare_amount, medicare_basis; or None.
  counts(con, t, bench)   counts of each label for one table (for the monthly census report)
  bench_rows(med)         Medicare figures from the site's benchmark file (R2 reference/site/med_all.json, built by
                          site/build_med_all.py) -> rows for `bench`
"""
import json
import os

LOW, HIGH = 0.5, 8.0
MANY_CODES, MANY_FAMILIES = 10, 3
# Count the labels in every new insurer-file census (06f, on the rented machines)? Off until Betsy switches it on:
# on the biggest files (UHC Choice Plus, 18 billion rows) the extra counting adds machine time. The census runs in its
# own process, so a problem here can never cost the price tables. Switch on: set True here, or RATE_LABELS=1.
IN_CENSUS = False or os.environ.get("RATE_LABELS") == "1"
LABELS = {
    "far_from_medicare": "Below half or above 8 times Medicare's rate for the same code (may never be used; unverified)",
    "repeated_amount": "Same amount listed more than once for the same service at the same provider (copies counted once)",
    "one_amount_many_codes": f"One identical amount for {MANY_CODES}+ unrelated codes at the same provider (may never be used; unverified)",
}


def _columns(con, t):
    return {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}


def _c(have, name):
    return f"coalesce(cast({name} as varchar), '')" if name in have else "''"


def labeled_sql(t, bench=None, have=None):
    """SELECT for table expression t with label columns added. `have` = the columns t has (from _columns)."""
    have = have or {"npi", "tin", "billing_code", "billing_code_modifier", "billing_class", "setting", "negotiated_type", "negotiated_rate"}
    mod, cls, sett, typ = _c(have, "billing_code_modifier"), _c(have, "billing_class"), _c(have, "setting"), _c(have, "negotiated_type")
    dollar = "(v > 0 and _typ not ilike 'percent%')"          # inside the CTEs (one table in scope)
    xdollar = "(x.v > 0 and x._typ not ilike 'percent%')"     # in the final select
    fee = f"case when lower({cls}) = 'professional' then 'professional' else 'facility' end"
    med = (f"left join {bench} m on m.billing_code = x.billing_code and m.fee = x.fee_kind" if bench
           else "left join (select null::varchar billing_code, null::varchar fee, null::double medicare_amount, null::varchar medicare_basis) m on false")
    return f"""
with x as (
  select *, try_cast(negotiated_rate as double) v, {mod} _mod, {cls} _cls, {sett} _set, {typ} _typ, {fee} fee_kind
  from {t}),
rep as (
  select npi, tin, billing_code, _mod, _cls, _set, _typ, v, count(*) repeat_count
  from x where {dollar} group by all having count(*) > 1),
many as (
  select npi, tin, _cls, _typ, v from x where {dollar}
  group by all having count(distinct billing_code) >= {MANY_CODES} and count(distinct left(billing_code, 3)) >= {MANY_FAMILIES})
select x.* exclude (_mod, _cls, _set, _typ),
       {xdollar} dollar_rate,
       m.medicare_amount, m.medicare_basis,
       case when {xdollar} and m.medicare_amount > 0 then round(x.v / m.medicare_amount, 3) end times_medicare,
       coalesce({xdollar} and m.medicare_amount > 0 and (x.v < {LOW} * m.medicare_amount or x.v > {HIGH} * m.medicare_amount), false) far_from_medicare,
       coalesce(r.repeat_count, 1) repeat_count,
       r.repeat_count is not null repeated_amount,
       mm.v is not null one_amount_many_codes
from x
{med}
left join rep r on r.npi = x.npi and r.tin = x.tin and r.billing_code = x.billing_code and r._mod = x._mod and r._cls = x._cls
                and r._set = x._set and r._typ = x._typ and r.v = x.v
left join many mm on mm.npi = x.npi and mm.tin = x.tin and mm._cls = x._cls and mm._typ = x._typ and mm.v = x.v"""


def counts(con, t, bench=None):
    """Counts of each label in one table. Rows are never dropped; 'collapsed' counts each repeated amount once."""
    have = _columns(con, t)
    need = {"npi", "tin", "billing_code", "negotiated_rate"}
    if not need <= have:
        return {"rate_labels_skipped": f"table lacks {sorted(need - have)}"}
    r = con.execute(f"""select count(*), count_if(dollar_rate),
                               count_if(medicare_amount > 0 and dollar_rate), count_if(far_from_medicare),
                               count_if(far_from_medicare and v < medicare_amount), count_if(far_from_medicare and v > medicare_amount),
                               count_if(repeated_amount), count_if(repeated_amount) - sum(case when repeated_amount then 1.0 / repeat_count else 0 end),
                               count_if(one_amount_many_codes), count_if(far_from_medicare or repeated_amount or one_amount_many_codes)
                        from ({labeled_sql(t, bench, have)})""").fetchone()
    keys = ["rows", "dollar_rows", "with_medicare_figure", "far_from_medicare", "below_half_medicare", "above_8x_medicare",
            "repeated_amount_rows", "repeated_amount_extra_copies", "one_amount_many_codes", "any_label"]
    out = {k: int(round(v or 0)) for k, v in zip(keys, r)}
    out["thresholds"] = dict(low=LOW, high=HIGH, many_codes=MANY_CODES, many_families=MANY_FAMILIES)
    out["medicare_figures_used"] = bool(bench)
    return out


def bench_rows(med):
    """Site benchmark file -> [(billing_code, fee, medicare_amount, medicare_basis)].
    facility: Medicare hospital outpatient (OPPS, national); else lab fee schedule.
    professional: Medicare doctor fee, Dallas locality, facility rate (the lower one; doctors' fees for work done in a
    hospital or surgery center), else lab fee schedule. Hospital stays (MS-DRG) have no figure in this file, so DRG
    rates are never labeled 'far from Medicare' by this function."""
    med = med.get("med", med)
    out = []
    for code, m in med.items():
        lab = m.get("lab")
        opps = (m.get("opps") or [None])[0]
        if opps:
            out.append((code, "facility", float(opps), "Medicare hospital outpatient rate (national), CY2026"))
        elif lab:
            out.append((code, "facility", float(lab), "Medicare lab fee schedule, 2026"))
        pfs = (m.get("pfs") or {}).get("dal") or [None, None]
        doc = pfs[1] if pfs[1] else pfs[0]
        if doc:
            out.append((code, "professional", float(doc), "Medicare doctor fee, Dallas, 2026"))
        elif lab:
            out.append((code, "professional", float(lab), "Medicare lab fee schedule, 2026"))
    return out


def load_bench(con, med, name="medicare_bench"):
    """Register bench_rows(med) as a DuckDB table and return its name (for labeled_sql / counts)."""
    rows = bench_rows(med)
    con.execute(f"create or replace temp table {name} (billing_code varchar, fee varchar, medicare_amount double, medicare_basis varchar)")
    if rows:
        con.executemany(f"insert into {name} values (?, ?, ?, ?)", rows)
    return name


def bench_from_storage(con, cache):
    """Medicare figures for label a on a rented machine: the site's benchmark file (a few MB, R2
    reference/site/med_all.json), read once per machine and kept at `cache`. None if it can't be read (label a is
    then skipped and the census says so)."""
    try:
        if not os.path.exists(cache):
            import boto3
            g = lambda k: "".join(os.environ.get(k, "").split())
            s3 = boto3.client("s3", endpoint_url=os.environ.get("STORAGE_ENDPOINT") or f"https://{g('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
                              aws_access_key_id=g("R2_ACCESS_KEY_ID"), aws_secret_access_key=g("R2_SECRET_ACCESS_KEY"),
                              region_name=os.environ.get("STORAGE_REGION") or "auto")
            s3.download_file(g("R2_BUCKET"), "reference/site/med_all.json", cache)
        return load_bench(con, json.load(open(cache)))
    except Exception:
        return None
