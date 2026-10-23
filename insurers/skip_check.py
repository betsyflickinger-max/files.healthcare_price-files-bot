"""Skipped-network check (Oct 21, 2026; Betsy: "yes" to testing what the pick lists leave out).

The pick lists keep each insurer's most-used medical networks and leave the rest out (machine-rules.md rule 3). This
measures what that costs: read a sample of the networks that were left out, for one area that already has the kept
networks read, and compare their prices with the kept ones.

  pick     choose the sample from the newest insurer catalogs and write it as a network list (networks_skip<area>.csv).
           Half the sample is the most-used networks that were left out; the other half is spread evenly through the
           rest of the left-out list, so the long tail is tested too. Prints each network's employers and GB for
           Betsy's OK before anything is read (rule 3).
  compare  after the sample is read (insurer bot, scope skip<area>): for the site's 89 procedures, sort every price row
           in each sampled network into
             same       the kept networks have this provider + tax ID + code + price type/class/setting/modifier at the same price (within 1 cent)
             different  the kept networks have that row, but not at this price (with the median gap to the closest kept price)
             new        the kept networks have no such row at all (a provider or code we would not show for this insurer)
           plus how many providers appear only in the sampled network.

Run:  python insurers/skip_check.py pick --area il --insurers uhc,aetna --n 10 [--min-employers 10] [--max-gb 20] > insurers/networks_skipil.csv
      python insurers/skip_check.py compare --area il
Output (compare): R2 bot/skipcheck/<area>/<YYYY-MM-DD>/{summary.md, networks.csv}; also the GitHub step summary.
"""
import argparse
import csv
import io
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import catalog  # noqa: E402

# Left out on purpose, like the pick lists: ancillary and special-purpose networks (chiropractic, acupuncture, speech,
# behavioral, therapy, transplant, pharmacy, vision, dental, hearing, lab, equipment).
ANCILLARY = re.compile(r"chiro|acupunct|speech|behavior|optum|ohph|therap|transplant|pharm|vision|dental|hearing|\blab\b|\bdme\b|\beap\b", re.I)
NAMES = {"uhc": "UnitedHealthcare", "aetna": "Aetna", "cigna": "Cigna", "anthem": "Anthem", "hcsc": "HCSC"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def kept_networks(area):
    """The area's network list: catalog network keys the bot already reads, per insurer, plus each row's table name."""
    rows = list(csv.DictReader(open(os.path.join(HERE, f"networks_{area}.csv"))))
    keys, tables = {}, []
    for r in rows:
        fa = (r.get("finder_arg") or "").split("|")
        if r.get("finder") == "catalog" and len(fa) >= 2:
            keys.setdefault(fa[0], set()).add(fa[1])
        tables.append(norm(r.get("current_table")))
    return rows, keys, tables


def pick(a):
    st = catalog.Store()
    _, keys, tables = kept_networks(a.area)
    want = {s.strip().lower() for s in a.states.split(",")} | {a.area.lower()}
    cols = ["slot", "insurer", "network_label", "url_template", "current_url", "current_table", "last_updated_on",
            "machine_group", "enabled", "finder", "finder_arg"]
    w = csv.DictWriter(sys.stdout, fieldnames=cols)
    w.writeheader()
    md = [f"## Skipped-network sample for {a.area.upper()} ({date.today().isoformat()})", ""]
    total_gb = 0.0
    for ins in [x.strip() for x in a.insurers.split(",") if x.strip()]:
        m = (st.get(f"bot/catalog/{ins}/latest.json") or {}).get("month")
        cat = st.get(f"bot/catalog/{ins}/{m}/catalog.json") if m else None
        if not cat:
            md.append(f"- {ins}: no catalog found"); continue
        kept, cand = [], []
        for r in cat["networks"]:
            k = r["network"]
            is_kept = k in keys.get(ins, set()) or any(norm(k) and norm(k) in t for t in tables)
            if is_kept:
                kept.append(r); continue
            if (r.get("state") or "").lower() not in want or r.get("coverage", "medical") != "medical":
                continue
            if ANCILLARY.search(f"{k} {r.get('description', '')}"):
                continue
            if r["problems"] or not r["files"] or (r.get("gb") or 0) > a.max_gb:
                continue
            if (r.get("employers") or 0) < a.min_employers:
                continue
            cand.append(r)
        cand.sort(key=lambda r: (-(r.get("employers") or 0), -(r.get("plans") or 0), r["network"]))
        top = cand[: a.n // 2]
        rest = cand[a.n // 2:]
        k = a.n - len(top)
        spread = [rest[round(i * (len(rest) - 1) / max(k - 1, 1))] for i in range(k)] if rest and k > 0 else []
        sample = top + [r for i, r in enumerate(spread) if r not in spread[:i]]
        gb = sum(r.get("gb") or 0 for r in sample)
        total_gb += gb
        md += [f"### {NAMES.get(ins, ins)} (catalog {m})", "",
               f"Kept (already read for {a.area.upper()}): " + ", ".join(f"{r['network']} ({(r.get('employers') or 0):,})" for r in kept), "",
               f"Left out, medical, used by {a.min_employers}+ employers, no file problems: **{len(cand)} networks, "
               f"{sum(r.get('gb') or 0 for r in cand):,.0f} GB**. Sample: {len(sample)} networks, {gb:,.1f} GB.", "",
               "| # | why picked | network | name | employers | GB | parts |", "|---:|---|---|---|---:|---:|---:|"]
        for i, r in enumerate(sample, 1):
            name = (r.get("description") or r.get("reporting_entity") or "").replace("|", "/")[:60]
            why = "most-used left out" if r in top else f"spread (rank {cand.index(r) + 1} of {len(cand)})"
            md.append(f"| {i} | {why} | {r['network']} | {name} | {(r.get('employers') or 0):,} | {r.get('gb')} | {r['parts']} |")
            label = r["description"] if r["description"] and "In-Network Negotiated" not in r["description"] else (r["reporting_entity"] or r["network"])
            for f in r["files"]:
                grp = "bcbstx" if (f.get("bytes") or 0) > 5e9 else "bcbs" if (f.get("bytes") or 0) > 1e9 else "small"
                slot = re.sub(r"[^a-z0-9]+", "-", f"skip-{ins}-{r['network']}-part-{f['part']}".lower()).strip("-")
                w.writerow(dict(slot=slot, insurer=NAMES.get(ins, ins), network_label=f"{label} ({r['network']})",
                                url_template="", current_url=f["url"], current_table=re.sub(r"\.json(\.gz)?$", "", f["fname"]),
                                last_updated_on=r["file_date"], machine_group=grp, enabled="yes", finder="catalog",
                                finder_arg=f"{ins}|{r['network']}|{f['part']}"))
        md.append("")
    md.append(f"**Total to read: {total_gb:,.1f} GB.**")
    out = "\n".join(md)
    print(out, file=sys.stderr)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(out + "\n")


def manifest(st, area):
    try:
        body = st.c.get_object(Bucket=st.b, Key=f"bot/insurers/{area}/manifest.csv")["Body"].read().decode()
    except Exception:
        return {}
    return {r["slot"]: r for r in csv.DictReader(io.StringIO(body))}


def compare(a):
    import duckdb
    st = catalog.Store()
    skip = f"skip{a.area}"
    rows_k, _, _ = kept_networks(a.area)
    rows_s = list(csv.DictReader(open(os.path.join(HERE, f"networks_{skip}.csv"))))
    man_k, man_s = manifest(st, a.area), manifest(st, skip)
    codes = [r["code"].strip() for r in csv.DictReader(open(os.path.join(HERE, "..", "site", "codes89.csv"))) if r["code"].strip()]
    lst = ",".join(f"'{c}'" for c in codes)
    E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
    con = duckdb.connect('/tmp/skipcheck.duckdb')   # on disk: Aetna's kept rows don't fit in memory
    # Oct 22, 2026: the first run lost its runner (out of memory) holding every kept Illinois row with all its text
    # columns. Each row is now one 64-bit key (provider + tax ID + code + price type/class/setting/modifier) plus its
    # price, with a memory cap so DuckDB spills to disk instead of starving the runner.
    con.execute("set temp_directory='/tmp/duck'; set preserve_insertion_order=false; set memory_limit='9GB'; set threads=8")
    con.execute(f"create secret r2 (type r2, key_id '{E['R2_ACCESS_KEY_ID']}', secret '{E['R2_SECRET_ACCESS_KEY']}', account_id '{E['R2_ACCOUNT_ID']}')")
    out_k, out_s = f"data/{a.area}/", f"data/{skip}/"
    con.execute("set http_retries=8; set http_retry_wait_ms=2000; set http_retry_backoff=2")

    def run(sql):   # Oct 22, 2026: R2 answered one read with 502 Bad Gateway and the whole run stopped; try again
        import time as _t
        for i in range(4):
            try:
                return con.execute(sql)
            except duckdb.HTTPException as e:
                if i == 3:
                    raise
                print(f"  R2 read failed ({str(e)[:120]}); retrying in {30 * (i + 1)}s", flush=True)
                _t.sleep(30 * (i + 1))

    def select(key):
        return (f"select hash(npi, coalesce(tin,''), lower(coalesce(billing_code_type,'')), billing_code, "
                f"lower(coalesce(negotiated_type,'')), lower(coalesce(billing_class,'')), lower(coalesce(setting,'')), "
                f"coalesce(cast(billing_code_modifier as varchar),'')) k, npi, round(try_cast(negotiated_rate as double), 2) rate "
                f"from read_parquet('r2://{E['R2_BUCKET']}/{key}') where billing_code in ({lst}) and try_cast(negotiated_rate as double) > 0")

    def table_of(row, man):
        m = man.get(row["slot"]) or {}
        return (m.get("table") or row.get("current_table")) if m.get("status") == "processed" else None

    by_ins = {}
    for r in rows_s:
        by_ins.setdefault(r["insurer"], []).append(r)
    report, md = [], [f"## Skipped-network check, {a.area.upper()}, {date.today().isoformat()}", "",
                      f"Prices compared: the site's {len(codes)} procedures. \"Same\" = the kept networks have that provider, tax ID, code and price type "
                      f"at the same price; \"different\" = same row, other price; \"new\" = no such row in the kept networks.", ""]
    for ins, srows in by_ins.items():
        if a.insurer and not ins.lower().startswith(a.insurer.lower()):
            continue
        kt = [table_of(r, man_k) for r in rows_k if r["insurer"].split(" ")[0] == ins.split(" ")[0]]
        kt = [t for t in kt if t]
        if not kt:
            md.append(f"- {ins}: no kept tables read for {a.area.upper()} yet"); continue
        print(f"{ins}: reading {len(kt)} kept tables", flush=True)
        run("create or replace table kept as " + " union all ".join(select(f"{out_k}rates/{t}.parquet") for t in kt))
        con.execute("create or replace table kept_rates as select distinct k, rate from kept")
        con.execute("create or replace table kept_npi as select distinct npi from kept")
        print(f"{ins}: kept rows loaded", con.execute("select count(*) from kept").fetchone()[0], flush=True)
        con.execute("drop table kept")
        md += [f"### {ins} (kept: {len(kt)} tables)", "",
               "| network | price rows | same | different (median gap) | new | providers only here |",
               "|---|---:|---:|---:|---:|---:|"]
        nets = {}
        for r in srows:
            nets.setdefault(r["network_label"], []).append(r)
        tot = dict(rows=0, same=0, diff=0, new=0)
        for label, parts in nets.items():
            tabs = [table_of(p, man_s) for p in parts]
            if not all(tabs):
                md.append(f"| {label} | not read yet ({sum(1 for t in tabs if t)} of {len(tabs)} parts) | | | | |"); continue
            print(f"  reading {label} ({len(tabs)} tables)", flush=True)
            run("create or replace table s as select distinct * from (" + " union all ".join(select(f"{out_s}rates/{t}.parquet") for t in tabs) + ")")
            res = con.execute("""
                with j as (
                  select s.k, s.npi, s.rate, min(abs(k.rate - s.rate) / nullif(k.rate, 0)) gap, count(k.rate) nk
                  from s left join kept_rates k using (k)
                  group by all)
                select count(*), count(*) filter (where nk > 0 and gap < 0.0001),
                       count(*) filter (where nk > 0 and gap >= 0.0001), count(*) filter (where nk = 0),
                       median(gap) filter (where nk > 0 and gap >= 0.0001),
                       (select count(distinct npi) from s where npi not in (select npi from kept_npi))
                from j""").fetchone()
            n, same, diff, new, med, only = res
            print(f"  {label}: {n:,} rows", flush=True)
            print("RESULT", ins, label, n, same, diff, new, med, only, flush=True)
            tot.update(rows=tot["rows"] + n, same=tot["same"] + same, diff=tot["diff"] + diff, new=tot["new"] + new)
            pct = (lambda x: f"{100 * x / n:.1f}%") if n else (lambda x: "-")
            md.append(f"| {label} | {n:,} | {pct(same)} | {pct(diff)}" + (f" ({100 * med:.0f}%)" if med is not None else "") +
                      f" | {pct(new)} | {only:,} |")
            report.append(dict(area=a.area, insurer=ins, network=label, parts=len(parts), price_rows=n, same=same, different=diff,
                               new=new, median_gap=round(med, 4) if med is not None else "", providers_only_here=only))
        if tot["rows"]:
            md += ["", f"All sampled {ins} networks together: {tot['rows']:,} price rows, {100 * tot['same'] / tot['rows']:.1f}% same, "
                       f"{100 * tot['diff'] / tot['rows']:.1f}% different, {100 * tot['new'] / tot['rows']:.1f}% new.", ""]
    text = "\n".join(md)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")
    buf = io.StringIO()
    if report:
        cw = csv.DictWriter(buf, fieldnames=list(report[0])); cw.writeheader(); cw.writerows(report)
    base = f"bot/skipcheck/{a.area}/{date.today().isoformat()}/" + (f"{a.insurer.lower()}_" if a.insurer else "")
    st.put(base + "summary.md", text, "text/markdown")
    st.put(base + "networks.csv", buf.getvalue(), "text/csv")
    os.makedirs("out", exist_ok=True)
    sfx = f"_{a.insurer.lower()}" if a.insurer else ""
    open(f"out/summary{sfx}.md", "w").write(text)
    open(f"out/networks{sfx}.csv", "w").write(buf.getvalue())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    p.add_argument("--area", default="il")
    p.add_argument("--insurers", default="uhc,aetna")
    p.add_argument("--states", default="national", help="catalog states to sample from besides the area itself")
    p.add_argument("--n", type=int, default=10, help="networks per insurer")
    p.add_argument("--min-employers", type=int, default=10)
    p.add_argument("--max-gb", type=float, default=20)
    c = sub.add_parser("compare")
    c.add_argument("--area", default="il")
    c.add_argument("--insurer", default="", help="only this insurer (e.g. UnitedHealthcare, Aetna)")
    a = ap.parse_args()
    pick(a) if a.cmd == "pick" else compare(a)
