"""Employer plans: who they are and which price files they use (Oct 16, 2026).

Two public sources, joined by the employer's tax ID (EIN):
  1. The insurer catalogs (insurers/catalog.py): every employer plan an insurer lists in its index, with the networks
     (price files) it uses. R2 bot/catalog/<insurer>/<month>/employers.csv.gz + network_sets.csv.gz.
  2. Form 5500 (U.S. Department of Labor, EFAST2 "Latest" datasets): each health plan's sponsor name and address,
     industry code, participant count, how it is funded, and the insurers on its Schedule A (insured coverage or
     stop-loss). Only plans that must file appear: most plans with 100+ participants. Smaller plans mostly don't file.

Nothing is estimated. "How funded" is what the filing says, written as evidence:
  insured        a Schedule A lists health coverage (health, HMO, PPO or indemnity) from an insurer
  self-funded    no Schedule A health coverage, and the plan says it pays benefits from general assets or a trust
                 (with "stop-loss on file" when a Schedule A lists stop-loss coverage)
  mixed          both of the above (for example an insured HMO next to a self-funded PPO)
  not stated     neither

Usage (employers.yml):
  python insurers/employers.py f5500 [--years 2024,2025]   build bot/employers/f5500/health_plans.parquet
  python insurers/employers.py join                         build bot/employers/<date>/ (needs the f5500 step)
Output of join: employer_plans.parquet (one row per insurer x EIN), employers.parquet (one row per EIN),
dfw_employers.csv (sponsors whose Form 5500 mailing ZIP starts 750-753 or 760-762), report.md.
"""
import argparse, csv, gzip, io, json, os, sys, zipfile
from datetime import date

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from catalog import Store   # same R2 helper as the catalog

DOL = "https://www.askebsa.dol.gov/FOIA%20Files/{y}/Latest/{f}_{y}_Latest.zip"
INSURERS = ["anthem", "uhc", "cigna", "aetna", "hcsc"]
NAMES = {"anthem": "Anthem", "uhc": "UnitedHealthcare", "cigna": "Cigna", "aetna": "Aetna", "hcsc": "BCBS TX/IL/OK/NM/MT (HCSC)"}
# Dallas-Fort Worth = sponsor mailing ZIP 750-753 or 760-762, the same ZIP rule the site uses for the DFW area (site/hosp_area.py)
WORK = os.environ.get("WORK", "/tmp/employers")


def duck():
    import duckdb
    c = duckdb.connect()
    c.sql("SET preserve_insertion_order=false")
    return c


def fetch_zip(url, dest_dir):
    """download a DOL zip and return the path of the CSV inside"""
    os.makedirs(dest_dir, exist_ok=True)
    r = requests.get(url, timeout=900, headers={"User-Agent": "Mozilla/5.0 (price-files-bot)"})
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    z.extract(name, dest_dir)
    print(f"  {url.split('/')[-1].replace('%20', ' ')}: {len(r.content) / 1e6:.1f} MB -> {name}", flush=True)
    return os.path.join(dest_dir, name)


def fetch(st, key, dest):
    """R2 object -> local file (or, without R2, a copy from the local --out folder, for tests)"""
    if st.c:
        st.c.download_file(st.b, key, dest)
    else:
        import shutil
        shutil.copy(os.path.join(st.out or ".", key), dest)


def f5500(a):
    st = Store()
    c = duck()
    years = [y.strip() for y in a.years.split(",") if y.strip()]
    for y in years:
        main = fetch_zip(DOL.format(y=y, f="F_5500"), f"{WORK}/{y}")
        scha = fetch_zip(DOL.format(y=y, f="F_SCH_A"), f"{WORK}/{y}")
        c.sql(f"CREATE OR REPLACE VIEW m{y} AS SELECT *, '{y}' AS data_year FROM read_csv('{main}', all_varchar=true, header=true)")
        c.sql(f"CREATE OR REPLACE VIEW a{y} AS SELECT *, '{y}' AS data_year FROM read_csv('{scha}', all_varchar=true, header=true)")
    c.sql("CREATE OR REPLACE VIEW m AS " + " UNION ALL BY NAME ".join(f"SELECT * FROM m{y}" for y in years))
    c.sql("CREATE OR REPLACE VIEW a AS " + " UNION ALL BY NAME ".join(f"SELECT * FROM a{y}" for y in years))
    # health plans (welfare benefit code 4A = health), newest filing per plan (EIN + plan number)
    c.sql("""
      CREATE TABLE hp AS
      SELECT * EXCLUDE (rn) FROM (
        SELECT ACK_ID, data_year, FORM_PLAN_YEAR_BEGIN_DATE AS plan_year_begin, PLAN_NAME AS plan_name,
               SPONS_DFE_PN AS plan_num, lpad(regexp_replace(SPONS_DFE_EIN, '[^0-9]', '', 'g'), 9, '0') AS ein,
               SPONSOR_DFE_NAME AS sponsor_name, SPONS_DFE_DBA_NAME AS sponsor_dba,
               SPONS_DFE_MAIL_US_CITY AS city, SPONS_DFE_MAIL_US_STATE AS state, left(SPONS_DFE_MAIL_US_ZIP, 5) AS zip5,
               SPONS_DFE_LOC_US_CITY AS loc_city, SPONS_DFE_LOC_US_STATE AS loc_state, left(SPONS_DFE_LOC_US_ZIP, 5) AS loc_zip5,
               BUSINESS_CODE AS naics, ADMIN_NAME AS admin_name,
               TRY_CAST(TOT_ACTIVE_PARTCP_CNT AS BIGINT) AS active_participants,
               TRY_CAST(TOT_PARTCP_BOY_CNT AS BIGINT) AS participants_boy,
               TYPE_WELFARE_BNFT_CODE AS welfare_codes,
               coalesce(FUNDING_INSURANCE_IND, '') = '1' AS fund_insurance, coalesce(FUNDING_TRUST_IND, '') = '1' AS fund_trust,
               coalesce(FUNDING_GEN_ASSET_IND, '') = '1' AS fund_general_assets,
               coalesce(BENEFIT_INSURANCE_IND, '') = '1' AS bnft_insurance, coalesce(BENEFIT_TRUST_IND, '') = '1' AS bnft_trust,
               coalesce(BENEFIT_GEN_ASSET_IND, '') = '1' AS bnft_general_assets,
               DATE_RECEIVED AS date_received,
               row_number() OVER (PARTITION BY SPONS_DFE_EIN, SPONS_DFE_PN ORDER BY FORM_PLAN_YEAR_BEGIN_DATE DESC, DATE_RECEIVED DESC) AS rn
        FROM m WHERE TYPE_WELFARE_BNFT_CODE LIKE '%4A%' AND coalesce(SPONS_DFE_EIN, '') <> ''
      ) WHERE rn = 1""")
    # Schedule A lines of those filings: health coverage vs stop-loss, with the insurer
    c.sql("""
      CREATE TABLE sa AS
      SELECT a.ACK_ID, INS_CARRIER_NAME AS carrier, INS_CARRIER_EIN AS carrier_ein, INS_CARRIER_NAIC_CODE AS naic,
             TRY_CAST(INS_PRSN_COVERED_EOY_CNT AS BIGINT) AS persons_covered,
             (coalesce(WLFR_BNFT_HEALTH_IND,'')='1' OR coalesce(WLFR_BNFT_HMO_IND,'')='1' OR coalesce(WLFR_BNFT_PPO_IND,'')='1'
              OR coalesce(WLFR_BNFT_INDEMNITY_IND,'')='1') AS health,
             coalesce(WLFR_BNFT_STOP_LOSS_IND,'')='1' AS stop_loss,
             TRY_CAST(WLFR_TOT_EARNED_PREM_AMT AS DOUBLE) AS earned_premium
      FROM a JOIN hp USING (ACK_ID)""")
    c.sql("""
      CREATE TABLE plans AS
      SELECT hp.*,
             coalesce(s.health_carriers, '') AS health_carriers, coalesce(s.stop_loss_carriers, '') AS stop_loss_carriers,
             coalesce(s.health_lines, 0) AS health_lines, coalesce(s.stop_loss_lines, 0) AS stop_loss_lines,
             s.insured_persons,
             CASE WHEN coalesce(s.health_lines, 0) > 0 AND (fund_general_assets OR fund_trust) AND NOT fund_insurance THEN 'mixed'
                  WHEN coalesce(s.health_lines, 0) > 0 AND (bnft_general_assets OR bnft_trust) THEN 'mixed'
                  WHEN coalesce(s.health_lines, 0) > 0 THEN 'insured'
                  WHEN (fund_general_assets OR fund_trust OR bnft_general_assets OR bnft_trust) THEN 'self-funded'
                  ELSE 'not stated' END AS funding,
             coalesce(s.stop_loss_lines, 0) > 0 AS stop_loss_on_file
      FROM hp LEFT JOIN (
        SELECT ACK_ID,
               string_agg(DISTINCT carrier, '; ') FILTER (WHERE health) AS health_carriers,
               string_agg(DISTINCT carrier, '; ') FILTER (WHERE stop_loss) AS stop_loss_carriers,
               count(*) FILTER (WHERE health) AS health_lines, count(*) FILTER (WHERE stop_loss) AS stop_loss_lines,
               sum(persons_covered) FILTER (WHERE health) AS insured_persons
        FROM sa GROUP BY ACK_ID) s USING (ACK_ID)""")
    out = f"{WORK}/health_plans.parquet"
    c.sql(f"COPY plans TO '{out}' (FORMAT parquet, COMPRESSION zstd)")
    c.sql("SELECT data_year, count(*) AS health_plans, count(DISTINCT ein) AS employers, "
          "count(*) FILTER (WHERE funding='self-funded') AS self_funded, count(*) FILTER (WHERE funding='insured') AS insured, "
          "count(*) FILTER (WHERE funding='mixed') AS mixed, count(*) FILTER (WHERE funding='not stated') AS not_stated, "
          "count(*) FILTER (WHERE stop_loss_on_file) AS stop_loss, count(*) FILTER (WHERE state='TX') AS texas "
          "FROM plans GROUP BY 1 ORDER BY 1").show()
    if st.c:
        st.c.upload_file(out, st.b, "bot/employers/f5500/health_plans.parquet")
        st.put("bot/employers/f5500/meta.json", dict(years=years, built=date.today().isoformat(),
                                                     source="U.S. Department of Labor, Form 5500 Latest datasets (EFAST2)",
                                                     urls=[DOL.format(y=y, f=f) for y in years for f in ("F_5500", "F_SCH_A")]))
        print("uploaded bot/employers/f5500/health_plans.parquet")


def join(a):
    st = Store(a.out)
    c = duck()
    os.makedirs(WORK, exist_ok=True)
    fetch(st, "bot/employers/f5500/health_plans.parquet", f"{WORK}/health_plans.parquet")
    c.sql(f"CREATE VIEW f AS SELECT * FROM '{WORK}/health_plans.parquet'")
    parts, months = [], {}
    for ins in INSURERS:
        m = (st.get(f"bot/catalog/{ins}/latest.json") or {}).get("month")
        if not m:
            print(f"{ins}: no catalog yet, skipped"); continue
        base = f"bot/catalog/{ins}/{m}/"
        e, s = f"{WORK}/{ins}_employers.csv.gz", f"{WORK}/{ins}_network_sets.csv.gz"
        try:
            fetch(st, base + "employers.csv.gz", e)
            fetch(st, base + "network_sets.csv.gz", s)
        except Exception as ex:
            print(f"{ins}: employer list missing in {base} ({ex}), skipped"); continue
        months[ins] = m
        cat = st.get(base + "catalog.json") or {}
        nd = {n["network"]: (n.get("description") or "", n.get("state") or "") for n in cat.get("networks", [])}
        with open(f"{WORK}/{ins}_nets.csv", "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["network", "description", "state"])
            for k, (d, s_) in nd.items(): w.writerow([k, d, s_])
        c.sql(f"""CREATE TABLE e_{ins} AS SELECT '{ins}' AS insurer, * FROM read_csv('{e}', all_varchar=true, header=true)""")
        cols = [r[0] for r in c.sql(f"DESCRIBE e_{ins}").fetchall()]
        print(f"{ins} ({m}): {c.sql(f'SELECT count(*) FROM e_{ins}').fetchone()[0]:,} plan rows; columns {cols}", flush=True)
        c.sql(f"CREATE TABLE s_{ins} AS SELECT * FROM read_csv('{s}', all_varchar=true, header=true)")
        c.sql(f"CREATE TABLE n_{ins} AS SELECT * FROM read_csv('{WORK}/{ins}_nets.csv', all_varchar=true, header=true)")
        parts.append(ins)
    if not parts:
        raise SystemExit("no insurer catalogs with employer lists")
    # employers.csv.gz columns (catalog.py): plan_sponsor_name, plan_id, plan_id_type, plan_name, plan_market_type,
    # issuer_name, network_set. Employer plans are listed by EIN.
    c.sql("CREATE TABLE ep_raw AS " + " UNION ALL ".join(f"""
        SELECT insurer, lpad(regexp_replace(e.plan_id, '[^0-9]', '', 'g'), 9, '0') AS ein, e.plan_sponsor_name AS sponsor_listed,
               e.plan_name, e.plan_market_type AS market, e.issuer_name, e.network_set
        FROM e_{i} e WHERE lower(e.plan_id_type) = 'ein' AND length(regexp_replace(e.plan_id, '[^0-9]', '', 'g')) BETWEEN 8 AND 9"""
        for i in parts))
    c.sql("CREATE TABLE nets AS " + " UNION ALL ".join(
        f"SELECT '{i}' AS insurer, network_set, trim(unnest(string_split(networks, '|'))) AS network FROM s_{i}" for i in parts))
    c.sql("CREATE TABLE netd AS " + " UNION ALL ".join(f"SELECT '{i}' AS insurer, network, description, state FROM n_{i}" for i in parts))
    c.sql("""
      CREATE TABLE employer_plans AS
      WITH g AS (
        SELECT insurer, ein, any_value(sponsor_listed) AS sponsor_listed, count(*) AS plans_listed,
               string_agg(DISTINCT market, '; ') AS markets, string_agg(DISTINCT issuer_name, '; ') AS issuers,
               list(DISTINCT plan_name)[1:5] AS plan_names_sample, list(DISTINCT network_set) AS sets
        FROM ep_raw GROUP BY 1, 2),
      gs AS (SELECT insurer, ein, unnest(sets) AS network_set FROM g),
      n AS (
        SELECT gs.insurer, gs.ein, list(DISTINCT nets.network ORDER BY nets.network) AS networks
        FROM gs JOIN nets ON nets.insurer = gs.insurer AND nets.network_set = gs.network_set
        GROUP BY 1, 2)
      SELECT g.* EXCLUDE (sets), n.networks, len(n.networks) AS network_count
      FROM g LEFT JOIN n USING (insurer, ein)""")
    # one row per EIN: Form 5500 facts (largest health plan of that EIN) + which insurers list it
    c.sql("""
      CREATE TABLE employers AS
      WITH ff AS (
        SELECT * EXCLUDE (rk) FROM (SELECT *, row_number() OVER (PARTITION BY ein ORDER BY regexp_matches(upper(plan_name), 'ASSISTANCE PROGRAM|\bEAP\b|DENTAL|VISION|DISABILITY|LIFE INS|SEVERANCE|CAFETERIA|FLEXIBLE SPENDING') , coalesce(active_participants, participants_boy, 0) DESC) rk FROM f) WHERE rk = 1),
      fe AS (SELECT ein, count(*) AS health_plans_filed, string_agg(DISTINCT funding, '; ') AS funding_all FROM f GROUP BY 1),
      li AS (SELECT ein, string_agg(DISTINCT insurer, ', ' ORDER BY insurer) AS listed_by, any_value(sponsor_listed) AS sponsor_listed,
                    sum(network_count) AS networks FROM employer_plans GROUP BY 1)
      SELECT li.ein, coalesce(ff.sponsor_name, li.sponsor_listed) AS employer, ff.sponsor_dba, li.listed_by, li.networks,
             ff.city, ff.state, ff.zip5,
             coalesce(ff.state = 'TX' AND (left(ff.zip5, 3) BETWEEN '750' AND '753' OR left(ff.zip5, 3) BETWEEN '760' AND '762'), false) AS dfw,
             ff.naics, ff.active_participants, ff.participants_boy, ff.plan_name AS f5500_plan_name, ff.plan_year_begin,
             ff.data_year AS f5500_year, ff.funding, fe.funding_all, ff.stop_loss_on_file, ff.health_carriers, ff.stop_loss_carriers,
             fe.health_plans_filed, ff.ACK_ID AS f5500_ack_id, ff.ein IS NOT NULL AS has_f5500
      FROM li LEFT JOIN ff USING (ein) LEFT JOIN fe USING (ein)""")
    stamp = date.today().isoformat()
    base = f"bot/employers/{stamp}/"
    c.sql(f"COPY employer_plans TO '{WORK}/employer_plans.parquet' (FORMAT parquet, COMPRESSION zstd)")
    c.sql(f"COPY employers TO '{WORK}/employers.parquet' (FORMAT parquet, COMPRESSION zstd)")
    c.sql(f"""COPY (SELECT e.*, (SELECT string_agg(p.insurer || ': ' || array_to_string(p.networks[1:8], ' | '), ' || ')
                                 FROM employer_plans p WHERE p.ein = e.ein) AS networks_by_insurer
                    FROM employers e WHERE dfw ORDER BY coalesce(active_participants, participants_boy, 0) DESC)
              TO '{WORK}/dfw_employers.csv' (HEADER, DELIMITER ',')""")
    # site data for the Employer Plans page: every Texas employer the catalogs list, with the networks each insurer's
    # index ties it to (network names as the insurer's index describes them, file-part wording dropped)
    rows = c.sql("""
      SELECT e.ein, e.employer, e.city, e.zip5, e.dfw, e.naics, e.active_participants, e.participants_boy, e.f5500_year,
             e.plan_year_begin, e.funding, e.stop_loss_on_file, e.health_carriers, e.stop_loss_carriers, e.f5500_ack_id, e.f5500_plan_name,
             list(struct_pack(i := p.insurer, n := p.networks, c := p.plans_listed)) AS ins
      FROM employers e JOIN employer_plans p USING (ein)
      WHERE e.state = 'TX'
      GROUP BY ALL ORDER BY coalesce(any_value(e.active_participants), any_value(e.participants_boy), 0) DESC""").fetchall()
    desc = {(i, n): d for i, n, d, s_ in c.sql("SELECT insurer, network, description, state FROM netd").fetchall()}
    import re as _re
    def nname(i, n):
        d = _re.sub(r"\s*in-network file.*$", "", desc.get((i, n)) or "", flags=_re.I).strip()
        return d or n
    site = []
    for r in rows:
        ins = {}
        for x in r[16]:
            names = sorted({nname(x["i"], n) for n in (x["n"] or [])})
            ins[NAMES[x["i"]]] = names[:40] + ([f"and {len(names) - 40} more"] if len(names) > 40 else [])
        site.append(dict(ein=r[0], name=r[1], city=r[2], dfw=bool(r[4]), naics=r[5], active=r[6], boy=r[7], year=r[8],
                         pyb=r[9], funding=r[10], stop_loss=bool(r[11]), carriers=r[12] or "", sl_carriers=r[13] or "",
                         ack=r[14], plan=r[15], ins=ins))
    meta = dict(built=stamp, catalogs={NAMES[i]: m for i, m in months.items()},
                f5500=(st.get("bot/employers/f5500/meta.json") or {}).get("years", []),
                counts=dict(zip(["employers", "with_5500", "texas", "dfw", "dfw_self"], c.sql(
                    """SELECT count(*), count(*) FILTER (WHERE has_f5500), count(*) FILTER (WHERE state='TX'), count(*) FILTER (WHERE dfw),
                              count(*) FILTER (WHERE dfw AND funding='self-funded') FROM employers""").fetchone())),
                by_insurer={NAMES[i]: n for i, n in c.sql("SELECT insurer, count(*) FROM employer_plans GROUP BY 1").fetchall()})
    json.dump(dict(meta=meta, employers=site), open(f"{WORK}/site_employers.json", "w"), separators=(",", ":"), default=str)
    print(f"site_employers.json: {len(site):,} Texas employers")
    # report
    L = [f"# Employer plans: insurer catalogs joined to Form 5500 ({stamp})", "",
         "Catalog months: " + ", ".join(f"{NAMES[i]} {m}" for i, m in months.items()), ""]
    def tbl(sql, head):
        rows = c.sql(sql).fetchall()
        L.append("| " + " | ".join(head) + " |"); L.append("|" + "---|" * len(head))
        for r in rows: L.append("| " + " | ".join("" if v is None else (f"{v:,}" if isinstance(v, int) else str(v)) for v in r) + " |")
        L.append("")
    L.append("## Employers listed by each insurer (by EIN)")
    tbl("""SELECT p.insurer, count(*) employers, count(*) FILTER (WHERE e.has_f5500) with_form_5500,
                  count(*) FILTER (WHERE e.funding='self-funded') self_funded, count(*) FILTER (WHERE e.funding='insured') insured,
                  count(*) FILTER (WHERE e.funding='mixed') mixed, count(*) FILTER (WHERE e.dfw) dfw
           FROM employer_plans p JOIN employers e USING (ein) GROUP BY 1 ORDER BY 2 DESC""",
        ["insurer", "employers", "with Form 5500", "self-funded", "insured", "mixed", "DFW"])
    L.append("## All employers (one row per EIN)")
    tbl("""SELECT count(*) employers, count(*) FILTER (WHERE has_f5500) with_form_5500, count(*) FILTER (WHERE state='TX') texas,
                  count(*) FILTER (WHERE dfw) dfw, count(*) FILTER (WHERE dfw AND funding='self-funded') dfw_self_funded FROM employers""",
        ["employers", "with Form 5500", "Texas", "DFW", "DFW self-funded"])
    L.append("## Largest Dallas-Fort Worth employers in the catalogs (by active participants on the Form 5500)")
    tbl("""SELECT employer, city, listed_by, funding || CASE WHEN stop_loss_on_file THEN ' (stop-loss on file)' ELSE '' END,
                  active_participants, f5500_year FROM employers WHERE dfw
           ORDER BY coalesce(active_participants, participants_boy, 0) DESC LIMIT 40""",
        ["employer", "city", "listed by", "funding (Form 5500)", "active participants", "5500 data year"])
    rep = "\n".join(L)
    open(f"{WORK}/report.md", "w").write(rep)
    print(rep)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(rep + "\n")
    if st.c:
        for n in ("employer_plans.parquet", "employers.parquet", "dfw_employers.csv", "report.md", "site_employers.json"):
            st.c.upload_file(f"{WORK}/{n}", st.b, base + n)
        st.put("bot/employers/latest.json", dict(date=stamp, catalogs=months))
        print("uploaded", base)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["f5500", "join"])
    p.add_argument("--years", default="2024,2025")
    p.add_argument("--out", default=None, help="local folder instead of R2 (tests)")
    a = p.parse_args()
    {"f5500": f5500, "join": join}[a.cmd](a)
