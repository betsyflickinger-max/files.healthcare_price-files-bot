"""Market segment of each insurer rate table, from the insurers' own tables of contents (Nov 10, 2026).

Replaces guessing from network names. Each insurer's table of contents (TOC) lists every plan that uses a file, with the
plan's `plan_market_type` ("group" or "individual"), its ID type and ID. insurers/plan_network_xwalk.py (PR #414) turns the
monthly TOC catalogs into one row per plan x network x TOC month (R2 bot/xwalk/plan_network/<insurer>/<month>.parquet).
Here, per network (the catalog's network key, which is part of the rate table's file name, the same match
insurers/catalog.py uses), every plan is classified, first rule that applies:

  1. table of contents plan_market_type   "individual" -> individual (marketplace); "group" -> group (employer)
  2. HIOS plan ID                         a marketplace plan ID (plan_id_type "hios", or the HIOS shape 12345TX0010001)
                                          -> individual (marketplace)
  3. Form 5500 EIN                        plan_id_type "ein" and the EIN files a Form 5500 health plan
                                          (bot/employers/f5500/health_plans.parquet, insurers/employers.py) -> group (employer)

and the network gets: group (employer) | individual (marketplace) | group and individual (both kinds of plan use it) |
not stated in file, with the method(s) that decided it. Tables whose network isn't in any catalog (insurers without a
catalog, or hospital files) keep the old guess from the network's name, labeled "network name (fallback)".
"""
import re

GROUP, INDIVIDUAL, BOTH, UNKNOWN = "group (employer)", "individual (marketplace)", "group and individual", "not stated in file"
TOC, HIOS, F5500, NAME, NONE = ("table of contents plan_market_type", "HIOS plan ID", "Form 5500 EIN", "network name (fallback)",
                                "not stated anywhere")
HIOS_RE = r"^[0-9]{5}[A-Z]{2}[0-9]{3}[0-9]{4}([0-9]{2})?$"
XWALK_COLS = ("network_key", "plan_id", "plan_id_type", "plan_market_type")


def network_segments(con, xwalk, f5500=None):
    """xwalk: table expression with the XWALK_COLS columns (plan x network rows, newest TOC month per insurer).
    f5500: table expression with an `ein` column (Form 5500 health plan sponsors), or None.
    Returns {network_key (lower case): dict(segment, method, plans_group, plans_individual, plans_unknown)}."""
    ein = (f"left join (select distinct lpad(regexp_replace(cast(ein as varchar), '[^0-9]', '', 'g'), 9, '0') ein from {f5500}) f "
           f"on f.ein = lpad(regexp_replace(x.plan_id, '[^0-9]', '', 'g'), 9, '0') and x.idt = 'ein'") if f5500 else ""
    has5500 = "f.ein is not null" if f5500 else "false"
    q = f"""
      with x as (select lower(cast(network_key as varchar)) nk, upper(trim(coalesce(cast(plan_id as varchar), ''))) plan_id,
                        lower(trim(coalesce(cast(plan_id_type as varchar), ''))) idt, lower(trim(coalesce(cast(plan_market_type as varchar), ''))) mkt
                 from {xwalk} where coalesce(network_key, '') <> ''),
      c as (select distinct x.nk, x.plan_id, x.idt,
              case when x.mkt = 'individual' then 'I' when x.mkt = 'group' then 'G'
                   when x.idt = 'hios' or regexp_matches(x.plan_id, '{HIOS_RE}') then 'I'
                   when {has5500} then 'G' else '' end seg,
              case when x.mkt in ('individual', 'group') then '{TOC}'
                   when x.idt = 'hios' or regexp_matches(x.plan_id, '{HIOS_RE}') then '{HIOS}'
                   when {has5500} then '{F5500}' else '' end how
            from x {ein})
      select nk, count(*) filter (where seg = 'G'), count(*) filter (where seg = 'I'), count(*) filter (where seg = ''),
             list(distinct how) filter (where how <> '')
      from c group by nk"""
    out = {}
    for nk, g, i, u, hows in con.execute(q).fetchall():
        seg = BOTH if g and i else GROUP if g else INDIVIDUAL if i else UNKNOWN
        hows = [h for h in (TOC, HIOS, F5500) if h in (hows or [])]
        out[nk] = dict(segment=seg, method=" + ".join(hows) if hows else NONE, plans_group=g, plans_individual=i, plans_unknown=u)
    return out


def table_segment(table_stem, segs):
    """The segment of one rate table: the network whose key is in the table's file name (longest key wins), else None."""
    t = (table_stem or "").lower().replace("-", "_")
    hits = [k for k in segs if k and k.replace("-", "_") in t]
    if not hits:
        return None
    return segs[max(hits, key=len)]


CACHE_KEY = "bot/xwalk/plan_network_segments.json"


def from_storage(con, s3c, bucket, prefix="bot/xwalk/plan_network/", f5500_key="bot/employers/f5500/health_plans.parquet",
                 work=None):
    """network_segments() over the newest crosswalk month of every insurer in storage.
    Returns ({} , note) when the crosswalk hasn't been built yet.

    Nov 12, 2026: the Anthem crosswalk alone is 42 million rows. Querying it in place over HTTP took 2.5 hours of ranged
    reads and used up the storage account's daily download cap (Backblaze answers 403 "cap exceeded"). Now: the result
    (one small row per network) is saved to CACHE_KEY with the ETags of the files it came from and reused while they are
    unchanged; when it has to be rebuilt, each file is downloaded once to local disk and queried there."""
    import json
    import os
    import tempfile
    newest = {}
    for pg in s3c.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for o in pg.get("Contents", []):
            m = re.match(re.escape(prefix) + r"([^/]+)/(\d{4}-\d{2})\.parquet$", o["Key"])
            if m and m.group(2) > newest.get(m.group(1), ("",))[0]:
                newest[m.group(1)] = (m.group(2), o["Key"], o.get("ETag", ""))
    if not newest:
        return {}, "plan-network crosswalk not built yet (Actions -> Plan to network crosswalk): every table falls back to its network name"
    try:
        f5_tag = s3c.head_object(Bucket=bucket, Key=f5500_key).get("ETag", "")
    except Exception:
        f5_tag = None
    fp = sorted([k, t] for _, k, t in newest.values()) + [[f5500_key, f5_tag]]
    note = (f"crosswalk months: {', '.join(f'{i} {m}' for i, (m, _, _) in sorted(newest.items()))}; "
            f"Form 5500 EINs: {'yes' if f5_tag is not None else 'not built'}")
    try:
        cached = json.loads(s3c.get_object(Bucket=bucket, Key=CACHE_KEY)["Body"].read())
        if cached.get("fingerprint") == fp:
            return cached["segments"], note + " (saved result reused)"
    except Exception:
        pass
    d = tempfile.mkdtemp(prefix="xwalk_", dir=work)
    local = []
    for ins, (_, k, _) in sorted(newest.items()):
        dst = os.path.join(d, f"{ins}.parquet")
        s3c.download_file(bucket, k, dst)
        local.append(dst)
    files = ", ".join(f"'{x}'" for x in local)
    xw = f"(select {', '.join(XWALK_COLS)} from read_parquet([{files}], union_by_name=true))"
    f5 = None
    if f5_tag is not None:
        dst = os.path.join(d, "f5500.parquet")
        s3c.download_file(bucket, f5500_key, dst)
        f5 = f"read_parquet('{dst}')"
    segs = network_segments(con, xw, f5)
    for x in local + ([os.path.join(d, "f5500.parquet")] if f5 else []):
        try:
            os.remove(x)
        except OSError:
            pass
    try:
        s3c.put_object(Bucket=bucket, Key=CACHE_KEY, Body=json.dumps(dict(fingerprint=fp, segments=segs)).encode())
    except Exception:
        pass
    return segs, note
