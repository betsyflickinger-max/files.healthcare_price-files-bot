"""Per-file inventory ("census") and contract end dates for one insurer rates table.

Used by 06f after every new read, and by insurers/backfill_inventory.py over tables already in R2.
Works on old tables too: it only counts the columns a table actually has.
Research only: counts of what insurers put in their files, never prices shown on the site.

contract_ends(): one row per provider (NPI + TIN) x contract end date x billing class, with how many prices
and codes end then. Insurers write placeholder dates such as 9999-12-31 or 2999-12-31 for "no set end";
those rows are kept as written and counted separately in the census, never re-interpreted.
"""
from datetime import date

GROUPED = ["billing_code_type", "billing_code_type_version", "negotiation_arrangement", "negotiated_type", "billing_class",
           "setting", "expiration_date", "additional_information"]
FILLED = ["additional_information", "bundled_codes", "covered_services", "billing_code_modifier",
          "service_code", "expiration_date", "setting", "billing_code_type_version"]
NO_END = "left(expiration_date, 4) >= '2900'"  # 9999-12-31, 2999-12-31: the insurer's "no set end date"


def columns(con, t):
    return {r[0] for r in con.execute(f"describe select * from {t}").fetchall()}


def census(con, t, base):
    """t = a DuckDB table expression (e.g. read_parquet('...')). base = dict of file facts to include."""
    have = columns(con, t)
    out = dict(base)
    n = con.execute(f"select count(*) from {t}").fetchone()[0]
    out["rows"] = n
    if not n:
        return out
    filled = [c for c in FILLED if c in have]
    d = con.execute(f"select approx_count_distinct(billing_code), approx_count_distinct(npi), approx_count_distinct(tin), "
                    + "".join(f"count_if({c} <> ''), " for c in filled)
                    + f"count_if(negotiated_type ilike 'percent%') from {t}").fetchone()
    out["distinct_approx"] = dict(zip(["billing_codes", "npis", "tins"], d[:3]))
    out["rows_with_value"] = dict(zip(filled, d[3:-1]))
    out["percent_of_charges_rows"] = d[-1]
    out["fields_not_in_table"] = [c for c in FILLED if c not in have]  # tables read before Oct 13, 2026
    grouped = [c for c in GROUPED if c in have]
    rows = con.execute(f"select {', '.join(grouped)}, " + ", ".join(f"grouping({c})" for c in grouped)
                       + f", count(*) from {t} group by grouping sets ({', '.join(f'({c})' for c in grouped)})").fetchall()
    k = len(grouped)
    tops = {c: [] for c in grouped}
    for r in rows:
        i = r[k:2 * k].index(0)
        tops[grouped[i]].append((r[i], r[-1]))
    out["values"] = {c: {"distinct": len(v), "top": [{"value": x, "rows": m} for x, m in sorted(v, key=lambda z: -z[1])[:25]]}
                     for c, v in tops.items()}
    if "expiration_date" in have:  # contract end dates by month, as written in the file
        e = con.execute(f"""select case when expiration_date = '' then 'blank' when {NO_END} then 'no set end'
                                        else left(expiration_date, 7) end m, count(*) prices,
                                   count(distinct npi || '|' || tin) providers
                            from {t} group by 1 order by 1""").fetchall()
        out["contract_ends_by_month"] = [{"month": m, "prices": p, "providers": q} for m, p, q in e]
        today = date.today().isoformat()
        out["prices_already_past_end_date"] = sum(p for m, p, _ in e if m not in ("blank", "no set end") and m < today[:7])
    return out


def contract_ends(con, t, dest):
    """Write the per-provider contract end dates for one table to dest (a local path or r2:// key)."""
    if "expiration_date" not in columns(con, t):
        return 0
    cls = "billing_class" if "billing_class" in columns(con, t) else "''"
    con.execute(f"""copy (select npi, tin, expiration_date, {cls} billing_class, count(*) prices,
                                 count(distinct billing_code) codes, any_value(file_label) network,
                                 any_value(reporting_entity_name) insurer, any_value(source_url) source_url,
                                 any_value(last_updated_on) file_date
                          from {t} where expiration_date <> '' group by npi, tin, expiration_date, 4)
                    to '{dest}' (format parquet, compression zstd)""")
    return 1
