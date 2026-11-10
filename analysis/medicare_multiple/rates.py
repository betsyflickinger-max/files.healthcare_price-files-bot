"""Private rates -> "listed rate units" with the matching Medicare amount, one table at a time (Nov 10, 2026).

Three sources, one output shape (a "part" Parquet per source table, see PART_COLS):
  insurer   an insurer in-network table (R2 data/<scope>/rates/<file>.parquet, written by 06f_full_extract.py)
  hospital  a hospital price file's parsed rows (R2 data/hosp_every/rows/<sha16>.parquet, written by site/hosp_every.py)
  allowed   an insurer's out-of-network allowed-amount files (R2 raw/allowed/<yyyy-mm>/<insurer>.tar, plans/allowed_amounts.py)

A UNIT is one listed dollar amount for one provider and one service in one file: insurer side (NPI + TIN, code, modifier,
billing class, setting, rate type, amount), hospital side (hospital + payer + plan, code, modifier, setting, billing class,
amount). Exact copies of a unit count once ("repeated amount", docs/rate-labels.md). Two different amounts for the same
provider and service are two units: nothing is averaged.

Each unit gets the Medicare amount for THAT provider's place and setting (views below). Units are then counted by
(code, view, Medicare amount, listed amount), so a part is small and exact: every percentile later is an actual listed
amount divided by an actual Medicare amount.

Views (which Medicare schedule applies), first match wins:
  inpatient            MS-DRG, facility fee, at a hospital Medicare pays under IPPS: FY2027 weight x that hospital's rate
  drug                 code on the Part B drug file (ASP + 6%, per billing unit), any fee kind
  lab                  code on the lab fee schedule, any fee kind
  ambulance            ambulance code (A0xxx) on the ambulance fee schedule, provider's locality, urban/rural by ZIP
  dme                  code on the DMEPOS fee schedule (state, rural by ZIP); modifier must match when the file gives one
  anesthesia           anesthesia code 00100-01999, doctor fee: the locality's anesthesia conversion factor, per unit. The
                       files have no "per unit" rate type, so each dollar rate is sorted (ANES_* below): the rate's own note
                       ("per unit" / "per case", "case rate") first, then its size. Up to $200 = a per-unit conversion
                       factor (about 10x Texas Medicare's $20-21; commercial factors are well under that) -> compared
                       with Medicare's factor. $400 and up = a per-case amount -> counted, its middle shown in dollars, no
                       ratio (no public CMS source gives typical anesthesia time per code). In between -> "unclear",
                       counted, no ratio.
  outpatient_hospital  facility fee at a hospital (NPI matched to a CMS hospital record, site/med_local.py): OPPS national
                       x (0.60 x FY2026 wage index + 0.40) for wage-adjusted status indicators
  asc                  facility fee at a surgery center (matched): ASC national x (0.50 x wage index + 0.50)
  facility_unmatched   facility fee where the NPI isn't matched to a Medicare hospital or surgery center: OPPS national,
                       no wage adjustment (reported on its own, never in the hospital outpatient figures)
  professional         doctor fee: Physician Fee Schedule for the provider's locality. Place of service (Nov 10, 2026): the
                       rate's own TiC service_code (CMS place-of-service codes): every code on CMS's facility list ->
                       facility rate; none on it -> office (non-facility) rate; both kinds, or no service_code -> a blend,
                       share_facility x facility + (1 - share) x office, with Medicare's own place-of-service mix for that
                       code in the state (Physician & Other Practitioners by Geography and Service; national mix when the
                       state has none; office rate when neither has the code). Each rate's method is in `pos`, and the
                       facility and office amounts are both kept (medicare_facility, medicare_office) for the low-high range.
                       Modifier 26 -> the professional-component row, TC -> technical component; other modifiers: none
  none                 no Medicare benchmark (dental, codes Medicare doesn't pay, packaged codes, unmatched hospitals, ...)

Kept out of the ratio and counted separately (never dropped): percent-of-charges rates, per-day rates (per diem, by type or
by the insurer's own note), $0 rates, capitation and bundle arrangements, rates with no Medicare amount.

Evidence that the provider does the service (Nov 10, 2026; the main "clean" view, docs/medicare-multiple.md):
  (a) the provider billed Medicare for the code in 2024: doctor fees by NPI, or by another NPI under the same TIN (practice)
      (Physician & Other Practitioners by Provider and Service); hospital outpatient facility fees by CCN and the code's APC
      (Outpatient Hospitals by Provider and Service has APCs, not codes); hospital stays by CCN and MS-DRG (Inpatient).
  (b) the hospital lists the code in its own price file, and (c) the hospital file's 2026 count of allowed amounts for the
      code is above zero: these need every hospital file of the run, so each part keeps the hospital's CCN (rates at an NPI
      matched to a hospital) and summarize.py adds them from the hospital files' code lists (.hcodes.parquet).
  units_ev counts the units with evidence (a); summarize adds (b)/(c).

In-network vs out-of-network (never mixed): insurer in-network tables are in-network, except a network whose name says
"Traditional" (e.g. "BCBS Traditional": an indemnity plan with no network) -> "unclear"; allowed-amount files ->
out-of-network. Hospital files: payer/plan names saying out-of-network / non-par -> out-of-network, "Traditional" -> unclear.
"""
import re

# CMS place-of-service codes paid at the Physician Fee Schedule's facility rate (Claims Processing Manual ch. 12 sec. 20.4.2;
# 02 = telehealth other than the patient's home, paid at the facility rate since 2017). site/every_code.py has the same list
# without 02.
FAC_POS = ("02", "19", "21", "22", "23", "24", "26", "31", "34", "41", "42", "51", "52", "53", "56", "61")
FAC_LIST = "[" + ", ".join(f"'{p}'" for p in FAC_POS) + "]"
PART_COLS = ["source", "scope", "table_name", "state", "insurer", "network", "status", "segment", "program", "view", "bucket", "code",
             "code_type", "modifier", "pos", "ccn", "medicare_amount", "medicare_facility", "medicare_office", "rate_kind", "rate",
             "units", "units_keep", "units_far", "units_many", "units_spec", "units_ev", "reason"]
# anesthesia amounts: per unit up to ANES_UNIT_MAX dollars, per case from ANES_CASE_MIN (docstring above)
ANES_UNIT_MAX, ANES_CASE_MIN = 200, 400
ANES_CASE = "anesthesia: per case"   # rate_kind values (kept out of ratios, counted)
ANES_UNCLEAR = f"anesthesia: unclear (between ${ANES_UNIT_MAX} and ${ANES_CASE_MIN})"
UNIT_NOTE_SQL = r"""case when regexp_matches({x}, '\bper (time |base )?unit\b|/ ?unit\b|\bper 15 min') then 'unit'
  when regexp_matches({x}, '\bper case\b|\bcase rate\b|\bflat (rate|fee)\b|\bper procedure\b') then 'case' else '' end"""
# a rate's place of service from its TiC service_code list (SQL over a varchar column x)
POS_SQL = """case when {cls} then ''
  when regexp_replace(coalesce({x}, ''), '[\\[\\]" ]', '', 'g') = '' then 'not stated'
  when list_has_all({fac}, string_split(regexp_replace({x}, '[\\[\\]" ]', '', 'g'), ',')) then 'facility'
  when not list_has_any({fac}, string_split(regexp_replace({x}, '[\\[\\]" ]', '', 'g'), ',')) then 'office'
  else 'both kinds of place' end"""

STATUS_SQL = r"""case
  when regexp_matches(lower({x}), '\btraditional\b') then 'unclear'
  when regexp_matches(lower({x}), 'out[ -]of[ -]network|\boon\b|non[ -]?par(ticipating)?\b|\bnon[ -]?network\b') then 'out-of-network'
  else 'in-network' end"""
SEGMENT_SQL = r"""case when regexp_matches(lower({x}), 'marketplace|exchange|individual|\bifp\b|ambetter|oscar|\bconnect\b|on[ -]exchange')
  then 'individual (marketplace)' else 'not stated in file' end"""
PROGRAM_SQL = r"""case
  when regexp_matches(lower({x}), 'medicaid|\bchip\b|\bstar\b|star\+plus|star kids|\bdsnp\b|d-snp|dual') then 'Medicaid / dual'
  when regexp_matches(lower({x}), 'medicare|advantage|\bmapd\b|\bma\b|\bsnp\b|senior|\bpffs\b') then 'Medicare Advantage'
  when regexp_matches(lower({x}), 'workers|work comp|\bwc\b|tricare|champva|\bva\b') then 'other public / workers comp'
  else 'commercial' end"""

BUCKET_SQL = """case view
  when 'inpatient' then 'Hospital stays (inpatient, MS-DRG)'
  when 'outpatient_hospital' then 'Hospital outpatient facility fees'
  when 'asc' then 'Surgery-center facility fees'
  when 'facility_unmatched' then 'Facility fees, place not matched to a Medicare hospital or surgery center'
  when 'anesthesia' then 'Anesthesia (per unit: conversion factor)'
  when 'drug' then 'Part B drugs (ASP)'
  when 'lab' then 'Lab tests (lab fee schedule)'
  when 'dme' then 'Durable medical equipment and supplies'
  when 'ambulance' then 'Ambulance'
  when 'professional' then 'Doctor and clinician fees: ' || coalesce(rb.cat_desc, 'code not in RBCS')
  else 'No Medicare benchmark' end"""


def register_bench(con, bench_dir, prov=None, states=None):
    """Load the benchmark CSVs (cms.py build) as DuckDB tables b_<name>. prov: a table expression with columns
    npi, zip5, kind ('H' | 'A' | NULL), wage_index, ccn (site/med_local.py) -> table prov with state, locality and rural.
    Only providers whose practice ZIP is in `states` (default: every state in the benchmark) are in prov: a rate at a
    provider outside the run's states belongs to that state's run, not this one."""
    for n in ("pfs", "opps", "asc", "clfs", "asp", "dme", "amb", "anes", "drg", "ipps", "zip", "rbcs", "wi2026", "hosp_zip"):
        con.execute(f"create or replace table b_{n} as select * from read_csv('{bench_dir}/{n}.csv', header=true, all_varchar=true)")
    # evidence that a provider does a service (who billed Medicare for what, 2024). Missing file -> empty table (no evidence).
    import os
    for n, cols in (("ev_prof", ("npi", "code")), ("ev_out", ("ccn", "apc")), ("ev_inp", ("ccn", "drg")),
                    ("posmix", ("state", "code", "share_facility"))):
        f = f"{bench_dir}/{n}.csv"
        src = (f"select distinct {', '.join(cols)} from read_csv('{f}', header=true, all_varchar=true)" if os.path.exists(f)
               else "select " + ", ".join(f"null::varchar {c}" for c in cols) + " where false")
        con.execute(f"create or replace table b_{n} as {src}")
    for t, cols in (("pfs", ["nonfacility", "facility"]), ("opps", ["rate"]), ("asc", ["rate"]), ("clfs", ["rate"]),
                    ("asp", ["rate"]), ("dme", ["nonrural", "rural"]), ("amb", ["urban", "rural", "super_rural"]),
                    ("anes", ["cf"]), ("drg", ["weight"]), ("ipps", ["wage_index", "op_per_weight", "cap_per_weight", "ucp_per_claim"]),
                    ("wi2026", ["wage_index"])):
        rep = ", ".join(f"try_cast({c} as double) as {c}" for c in cols)
        con.execute(f"create or replace table b_{t} as select * replace ({rep}) from b_{t}")
    con.execute("create or replace table b_posmix as select * replace (try_cast(share_facility as double) as share_facility) from b_posmix")
    # empty text cells read as NULL: modifiers and the rural flag must be '' to match
    for t, c in (("pfs", "mod"), ("dme", "mod"), ("zip", "rural")):
        con.execute(f"create or replace table b_{t} as select * replace (coalesce({c}, '') as {c}) from b_{t}")
    # DME rows without a modifier in the insurer file: the fee schedule's no-modifier row, else the purchase-new (NU) row
    con.execute("""create or replace table b_dme_def as select code, min(mod) filter (where mod = '') m0,
                     min(mod) filter (where mod = 'NU') m1 from b_dme group by code""")
    con.execute("create or replace table b_dme_def as select code, coalesce(m0, m1) as mod from b_dme_def where coalesce(m0, m1) is not null")
    con.execute("create or replace table b_opps as select * replace (wage_adj = 'True' as wage_adj) from b_opps")
    con.execute("create or replace table b_asc as select * replace (wage_adj = 'True' as wage_adj) from b_asc")
    build_code_bench(con)
    if prov is not None:
        sf = "" if not states else "and z.state in (" + ", ".join(f"'{x}'" for x in states) + ")"
        con.execute(f"""create or replace table prov as
          select distinct on (cast(p.npi as varchar)) cast(p.npi as varchar) npi, left(cast(p.zip5 as varchar), 5) zip5, p.kind,
                 try_cast(p.wage_index as double) wage_index, cast(p.ccn as varchar) ccn, z.state, z.locality, coalesce(z.rural, '') rural
          from {prov} p join b_zip z on z.zip5 = left(cast(p.zip5 as varchar), 5) {sf}""")


def build_code_bench(con):
    """One row per code with every code-level Medicare fact (so each rate needs one join on code, plus the place-dependent
    joins: doctor fee schedule by locality, ambulance by locality, anesthesia CF by locality, DME by state, IPPS by hospital)."""
    con.execute("""create or replace table b_code as
      with codes as (select code from b_asp union select code from b_clfs union select code from b_opps union select code from b_asc
                     union select code from b_amb union select code from b_dme union select code from b_pfs union select code from b_rbcs)
      select c.code, sp.rate asp_rate, cl.rate clfs_rate, op.si opps_si, op.rate opps_rate, op.wage_adj opps_wage_adj,
             case when coalesce(op.apc, '') <> '' then lpad(ltrim(op.apc, '0'), 4, '0') end opps_apc,
             ac.rate asc_rate, ac.wage_adj asc_wage_adj, c.code in (select code from b_amb) is_amb,
             c.code in (select code from b_dme) is_dme, dd.mod dme_default_mod, rb.cat_desc,
             regexp_matches(c.code, '^0[01][0-9]{3}$') and c.code between '00100' and '01999' is_anes
      from codes c left join b_asp sp using (code) left join b_clfs cl using (code) left join b_opps op using (code)
           left join b_asc ac using (code) left join b_dme_def dd using (code) left join b_rbcs rb using (code)""")


def medicare_sql(u):
    """SQL fragments (view, medicare_amount, reason, joins) for a relation alias u with columns code, code_type, fee
    ('facility' | 'professional'), modifier, pos ('facility' | 'office' | 'both kinds of place' | 'not stated' | ''), and
    provider columns p_kind, p_wi, p_ccn, p_loc, p_rural, p_state (any may be NULL). All joins are plain equality joins on
    small tables."""
    is_drg = f"{u}.code_type = 'MS-DRG'"
    share = "coalesce(pm.share_facility, pmn.share_facility)"
    pfs_amt = f"""case when {u}.pos in ('facility', 'hospital-based') then coalesce(pf.facility, pf.nonfacility)
      when {u}.pos = 'office' then coalesce(pf.nonfacility, pf.facility)
      when pf.facility is not null and pf.nonfacility is not null and {share} is not null
        then round({share} * pf.facility + (1 - {share}) * pf.nonfacility, 2)
      else coalesce(pf.nonfacility, pf.facility) end"""
    opps_ok = f"{u}.modifier = '' and bc.opps_rate is not null and bc.opps_si <> 'N'"
    view = f"""case
      when {is_drg} then case when {u}.fee = 'facility' and ip.ccn is not null and dr.weight is not null then 'inpatient' else 'none' end
      when bc.asp_rate is not null then 'drug'
      when bc.clfs_rate is not null then 'lab'
      when am.code is not null then 'ambulance'
      when dm.code is not null then 'dme'
      when bc.is_anes and {u}.fee = 'professional' and an.cf is not null then 'anesthesia'
      when {u}.fee = 'facility' and {u}.p_kind = 'H' and {opps_ok} then 'outpatient_hospital'
      when {u}.fee = 'facility' and {u}.p_kind = 'A' and {u}.modifier = '' and bc.asc_rate is not null then 'asc'
      when {u}.fee = 'facility' and {opps_ok} then 'facility_unmatched'
      when {u}.fee = 'professional' and pf.code is not null and ({pfs_amt}) > 0 then 'professional'
      else 'none' end"""
    amount = f"""case
      when {is_drg} then round(dr.weight * (ip.op_per_weight + ip.cap_per_weight) + ip.ucp_per_claim, 2)
      when bc.asp_rate is not null then bc.asp_rate
      when bc.clfs_rate is not null then bc.clfs_rate
      when am.code is not null then case when {u}.p_rural = 'B' then am.super_rural when {u}.p_rural = 'R' then am.rural else am.urban end
      when dm.code is not null then case when {u}.p_rural in ('R', 'B') then coalesce(dm.rural, dm.nonrural) else coalesce(dm.nonrural, dm.rural) end
      when bc.is_anes and {u}.fee = 'professional' then an.cf
      when {u}.fee = 'facility' and {u}.p_kind = 'H' and {opps_ok}
        then round(bc.opps_rate * case when bc.opps_wage_adj then {OPPS_LABOR} * {u}.p_wi + {1 - OPPS_LABOR} else 1 end, 2)
      when {u}.fee = 'facility' and {u}.p_kind = 'A' and {u}.modifier = '' and bc.asc_rate is not null
        then round(bc.asc_rate * case when bc.asc_wage_adj then {ASC_LABOR} * {u}.p_wi + {1 - ASC_LABOR} else 1 end, 2)
      when {u}.fee = 'facility' and {opps_ok} then bc.opps_rate
      when {u}.fee = 'professional' then {pfs_amt}
      end"""
    reason = f"""case
      when {is_drg} and {u}.fee <> 'facility' then 'DRG listed as a doctor fee'
      when {is_drg} and dr.weight is null then 'not an FY2027 MS-DRG'
      when {is_drg} then 'hospital not paid under the inpatient PPS or not matched to a CMS hospital record'
      when {u}.code_type not in ('CPT', 'HCPCS') then 'code type ' || {u}.code_type || ' (no Medicare fee schedule)'
      when {u}.fee = 'professional' and {u}.p_loc is null then 'provider ZIP not in this state''s Medicare locality file'
      when {u}.modifier not in ('', '26', 'TC') then 'modifier ' || {u}.modifier || ' not priced'
      when bc.opps_si = 'N' then 'packaged into another service under OPPS (no separate Medicare payment)'
      else 'code not on a Medicare fee schedule for this kind of fee' end"""
    joins = f"""
      left join b_code bc on bc.code = {u}.code
      left join b_drg dr on dr.drg = {u}.code_drg
      left join b_ipps ip on ip.ccn = {u}.p_ccn_drg
      left join b_amb am on am.code = {u}.code and am.locality = {u}.p_loc
      left join b_dme dm on dm.code = {u}.code and dm.state = {u}.p_state and dm.mod = coalesce(nullif({u}.modifier, ''), bc.dme_default_mod)
      left join b_anes an on an.locality = {u}.p_loc
      left join b_pfs pf on pf.code = {u}.code and pf.mod = {u}.modifier and pf.locality = {u}.p_loc
      left join b_posmix pm on pm.code = {u}.code and pm.state = {u}.p_state
      left join b_posmix pmn on pmn.code = {u}.code and pmn.state = 'US'
      left join b_ev_prof ep on ep.npi = {u}.npi and ep.code = {u}.code
      left join b_ev_inp ei on ei.ccn = {u}.p_ccn_drg and ei.drg = {u}.code_drg
      left join b_ev_out eo on eo.ccn = {u}.p_ccn and eo.apc = bc.opps_apc and {u}.fee = 'facility'"""
    return view, amount, reason, joins


OPPS_LABOR, ASC_LABOR = 0.60, 0.50


def _units_to_part(con, units_sql, const):
    """units_sql: one row per listed rate with columns insurer, network, status, segment, program, code, code_type, fee,
    modifier, pos, rate_kind, rate (double), w (1 / number of exact copies, so copies add up to one unit), p_kind, p_wi,
    p_ccn, p_loc, p_rural, p_state, npi, tin, counted, labeled_many, labeled_spec. Returns the SQL of the outputs."""
    view, amount, reason, joins = medicare_sql("u")
    con.execute(f"""create or replace temp view units as
      select *, case when code_type = 'MS-DRG' then code end code_drg, case when code_type = 'MS-DRG' then p_ccn end p_ccn_drg
      from ({units_sql})""")
    con.execute(f"""create or replace temp table uv as
      with j as (select u.p_state, u.insurer, u.network, u.status, u.segment, u.program, u.code, u.code_type, u.modifier, u.pos,
                        case when u.rate_kind = 'dollar' and bc.is_anes and u.fee = 'professional' and an.cf is not null then
                               case when u.unit_note = 'unit' then 'dollar' when u.unit_note = 'case' then '{ANES_CASE}'
                                    when u.rate <= {ANES_UNIT_MAX} then 'dollar' when u.rate >= {ANES_CASE_MIN} then '{ANES_CASE}'
                                    else '{ANES_UNCLEAR}' end
                             else u.rate_kind end rate_kind,
                        u.rate, u.w, u.npi, u.tin, u.labeled_many, u.labeled_spec, bc.cat_desc,
                        case when u.p_kind = 'H' then u.p_ccn end ccn,
                        ep.npi is not null ev_npi, (ei.ccn is not null or eo.ccn is not null) ev_fac,
                        pf.facility pf_fac, pf.nonfacility pf_off, pm.share_facility sh_state, pmn.share_facility sh_us,
                        {view} as view, {amount} as medicare_amount, {reason} as reason0
                 from units u {joins})
      select * exclude (reason0, cat_desc, pos, pf_fac, pf_off, sh_state, sh_us), case when view = 'none' then reason0 end reason,
             case when view <> 'professional' then ''
                  when pos in ('facility', 'office') then 'service code: ' || pos
                  when pos = 'hospital-based' then 'hospital file: facility rate'
                  when pf_fac is null or pf_off is null then pos || ': the only Medicare rate for this code'
                  when sh_state is not null then pos || ': blended by Medicare''s state site mix'
                  when sh_us is not null then pos || ': blended by Medicare''s national site mix'
                  else pos || ': office rate (no Medicare site mix)' end pos,
             case when view = 'professional' then pf_fac end medicare_facility,
             case when view = 'professional' then pf_off end medicare_office,
             {BUCKET_SQL.replace('rb.cat_desc', 'cat_desc')} bucket,
             rate_kind = 'dollar' and view <> 'none' and medicare_amount > 0
               and (rate < 0.5 * medicare_amount or rate > 8 * medicare_amount) far
      from j""")
    # evidence (a) at the practice: another NPI under the same TIN billed Medicare for the code
    con.execute("""create or replace temp table te as select distinct tin, code from uv where ev_npi and coalesce(tin, '') <> ''""")
    con.execute("""create or replace temp view uve as
      select uv.*, (uv.ev_npi or uv.ev_fac or te.tin is not null) ev from uv left join te on te.tin = uv.tin and te.code = uv.code""")
    c = ", ".join(f"'{v}' as {k}" for k, v in const.items())
    # insurer, status, segment and program follow from the network; bucket and code type from the code: carried, not grouped
    part = f"""select {c}, p_state state, any_value(insurer) insurer, network, any_value(status) status, any_value(segment) segment,
        any_value(program) program, view, any_value(bucket) bucket, code, any_value(code_type) code_type, modifier, pos, ccn,
        case when rate_kind = 'dollar' and view <> 'none' then medicare_amount end medicare_amount,
        case when rate_kind = 'dollar' then medicare_facility end medicare_facility,
        case when rate_kind = 'dollar' then medicare_office end medicare_office, rate_kind,
        case when (rate_kind = 'dollar' or rate_kind like 'anesthesia:%') and view <> 'none' then rate end rate,
        round(sum(w))::bigint units, round(coalesce(sum(w) filter (where not (far or labeled_many or labeled_spec)), 0))::bigint units_keep,
        round(coalesce(sum(w) filter (where far), 0))::bigint units_far, round(coalesce(sum(w) filter (where labeled_many), 0))::bigint units_many,
        round(coalesce(sum(w) filter (where labeled_spec), 0))::bigint units_spec,
        round(coalesce(sum(w) filter (where ev), 0))::bigint units_ev, any_value(reason) reason
      from uve group by p_state, network, view, code, modifier, pos, ccn, rate_kind,
        case when rate_kind = 'dollar' and view <> 'none' then medicare_amount end,
        case when rate_kind = 'dollar' then medicare_facility end, case when rate_kind = 'dollar' then medicare_office end,
        case when (rate_kind = 'dollar' or rate_kind like 'anesthesia:%') and view <> 'none' then rate end"""
    # providers: per code, how many (and the first five, so "at least 5 providers" can be checked exactly across tables);
    # per bucket, every provider (to count providers behind a bucket or a total without double counting). A provider at a
    # hospital without evidence (a) keeps its hospital's CCN, so summarize can add evidence (b)/(c) from the hospital files.
    con.execute("""create or replace temp table pn as
      select p_state state, status, segment, program, view, bucket, code, npi, rate_kind = 'dollar' and view <> 'none' as in_ratio,
             bool_or(not (far or labeled_many or labeled_spec)) any_keep, bool_or(ev) any_ev, any_value(ccn) ccn
      from uve group by all""")
    codes = f"""select {c}, state, status, segment, program, view, bucket, code, in_ratio, count(*) n_npi,
        count(*) filter (where any_keep) n_npi_keep, count(*) filter (where any_ev) n_npi_ev, list(npi order by npi)[1:5] first5,
        list(npi order by npi) filter (where any_keep)[1:5] first5_keep, list(npi order by npi) filter (where any_ev)[1:5] first5_ev,
        list(ccn || '|' || npi) filter (where not any_ev and ccn is not null) ccn_npi_noev
      from pn group by all"""
    buckets = f"""select {c}, state, status, segment, program, view, bucket, npi, in_ratio, bool_or(any_keep) any_keep,
        bool_or(any_ev) any_ev, any_value(ccn) ccn, list(code) filter (where not any_ev and ccn is not null) codes_noev
      from pn group by all"""
    # the codes a hospital's own file lists, and whether its 2026 count of allowed amounts is above zero (hospital files only)
    hcodes = f"""select {c}, p_ccn ccn, code, bool_or(counted) counted from units where p_ccn is not null group by all"""
    return part, codes, buckets, hcodes


def insurer_units(t, have, membership=None, spec=None, part_k=0, parts=1):
    """Units SQL for one insurer in-network table expression t (columns `have`). Labels from rate_labels.labeled_sql
    (repeated amounts collapse to one unit; one-amount-many-codes and specialty mismatch carried as flags).
    parts > 1: only providers with hash(NPI) % parts = part_k. Every label looks at one provider (NPI + TIN) at a time,
    so splitting a big table by provider gives exactly the same labels while each pass needs a fraction of the memory."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "insurers", "pipeline"))
    import rate_labels
    q = lambda n: f"coalesce(cast({n} as varchar), '')" if n in have else "''"
    proj = (f"(select {q('reporting_entity_name')} reporting_entity_name, {q('file_label')} file_label, "
            f"upper({q('billing_code_type')}) billing_code_type, upper(trim({q('billing_code')})) billing_code, "
            f"{q('npi')} npi, {q('tin')} tin, lower({q('negotiated_type')}) negotiated_type, "
            f"try_cast(negotiated_rate as double) negotiated_rate, lower({q('billing_class')}) billing_class, lower({q('setting')}) setting, "
            f"upper({q('billing_code_modifier')}) billing_code_modifier, {q('service_code')} service_code, "
            f"lower({q('negotiation_arrangement')}) arrangement, lower({q('additional_information')}) addl from {t}"
            + (f" where hash({q('npi')}) % {int(parts)} = {int(part_k)}" if parts > 1 else "") + ")")
    lab_cols = {"npi", "tin", "billing_code", "billing_code_modifier", "billing_class", "setting", "negotiated_type",
                "negotiated_rate", "reporting_entity_name", "file_label", "billing_code_type", "service_code", "arrangement", "addl"}
    lab = rate_labels.labeled_sql(proj, None, lab_cols, spec)
    net = "coalesce(nullif(m.network_name, ''), l.file_label)" if membership else "l.file_label"
    mj = (f"left join (select cast(npi as varchar) npi, cast(tin as varchar) tin, string_agg(distinct cast(network_name as varchar), '|') network_name "
          f"from {membership} group by all) m on m.npi = l.npi and m.tin = l.tin") if membership else ""
    kind = r"""case when l.arrangement in ('capitation', 'bundle') then l.arrangement
      when l.negotiated_type like 'percent%' then 'percent of charges'
      when l.negotiated_type like '%per diem%' or (l.addl <> '' and regexp_matches(l.addl, '\bper[ -]?(diem|day)\b|/ ?day\b|\bdaily rate')) then 'per day'
      when l.v is null then 'not a number'
      when l.v = 0 then 'zero'
      when l.negotiated_type in ('negotiated', 'fee schedule', 'derived') then 'dollar'
      else 'other rate type: ' || l.negotiated_type end"""
    return f"""select 1.0 / coalesce(l.repeat_count, 1) w, l.reporting_entity_name insurer, {net} network,
        {STATUS_SQL.format(x=net)} status, {SEGMENT_SQL.format(x=net)} segment, 'commercial' program,
        case when l.billing_code_type in ('MS-DRG', 'DRG') then ltrim(l.billing_code, '0') else l.billing_code end code,
        case when l.billing_code_type in ('MS-DRG', 'DRG') then 'MS-DRG' when l.billing_code_type like 'CPT%' then 'CPT'
             when l.billing_code_type like 'HCPCS%' then 'HCPCS' else l.billing_code_type end code_type,
        case when l.billing_class like 'inst%' then 'facility' else 'professional' end fee,
        l.billing_code_modifier modifier,
        {POS_SQL.format(cls="l.billing_class like 'inst%'", x="l.service_code", fac=FAC_LIST)} pos,
        {kind} rate_kind, l.v rate, l.npi, l.tin, false counted, {UNIT_NOTE_SQL.format(x="l.addl")} unit_note,
        p.kind p_kind, coalesce(p.wage_index, 1.0) p_wi, p.ccn p_ccn, p.locality p_loc, p.rural p_rural, p.state p_state,
        l.one_amount_many_codes labeled_many, l.specialty_mismatch labeled_spec
      from ({lab}) l join prov p on p.npi = l.npi {mj}"""


def hospital_units(t, have):
    """Units SQL for one hospital file's parsed rows (site/hosp_every.py). Provider = the hospital: a one-row table `hosp`
    (ccn, state) must exist (the CMS number and state of the file's hospital, from data/hospitals.csv)."""
    q = lambda n: f"coalesce(cast({n} as varchar), '')" if n in have else "''"
    payer = f"({q('payer_name')} || ' ' || {q('plan_name')})"
    kind = rf"""case when lower({q('methodology')}) like '%per diem%' then 'per day'
      when try_cast(replace(replace({q('negotiated_dollar')}, '$', ''), ',', '') as double) > 0 then 'dollar'
      when try_cast(replace(replace({q('negotiated_dollar')}, '$', ''), ',', '') as double) = 0 then 'zero'
      when {q('negotiated_percentage')} <> '' then 'percent of charges'
      when {q('negotiated_algorithm')} <> '' then 'formula only'
      else 'no negotiated amount' end"""
    return f"""select distinct 1.0 w, {q('hospital_name')} insurer, {q('payer_name')} || ' | ' || {q('plan_name')} network,
        {STATUS_SQL.format(x=payer)} status, {SEGMENT_SQL.format(x=payer)} segment, {PROGRAM_SQL.format(x=payer)} program,
        case when upper({q('code_type')}) in ('MS-DRG', 'MSDRG') then ltrim({q('code')}, '0') else upper({q('code')}) end code,
        case when upper({q('code_type')}) in ('MS-DRG', 'MSDRG') then 'MS-DRG' else upper({q('code_type')}) end code_type,
        case when lower({q('billing_class')}) = 'professional' then 'professional' else 'facility' end fee,
        upper(split_part(replace({q('modifiers')}, ' ', ''), '|', 1)) modifier,
        case when lower({q('billing_class')}) = 'professional' then 'hospital-based' else '' end pos,
        {kind} rate_kind, try_cast(replace(replace({q('negotiated_dollar')}, '$', ''), ',', '') as double) rate,
        h.ccn npi, '' tin, lower({q('setting')}) setting,
        {q('allowed_count')} not in ('', '0') counted,
        {UNIT_NOTE_SQL.format(x="lower(" + q('methodology') + " || ' ' || " + q('notes') + ")")} unit_note,
        'H' p_kind, coalesce(w.wage_index, 1.0) p_wi, h.ccn p_ccn, z.locality p_loc, coalesce(z.rural, '') p_rural,
        coalesce(hz.state, h.state) p_state, false labeled_many, false labeled_spec
      from {t} r cross join hosp h left join b_wi2026 w on w.ccn = h.ccn
      left join b_hosp_zip hz on hz.ccn = h.ccn left join b_zip z on z.zip5 = hz.zip5"""


def allowed_units(t):
    """Units SQL for out-of-network allowed amounts already flattened to rows (insurer, plan, code_type, code, tin, npi,
    billing_class, modifier, service_code, allowed_amount) by allowed_rows()."""
    return f"""select distinct 1.0 w, r.insurer, r.plan network, 'out-of-network' status, {SEGMENT_SQL.format(x='r.plan')} segment,
        'commercial' program,
        case when upper(r.code_type) in ('MS-DRG', 'DRG') then ltrim(r.code, '0') else upper(r.code) end code,
        case when upper(r.code_type) in ('MS-DRG', 'DRG') then 'MS-DRG' else upper(r.code_type) end code_type,
        case when lower(r.billing_class) like 'inst%' then 'facility' else 'professional' end fee,
        upper(coalesce(r.modifier, '')) modifier,
        {POS_SQL.format(cls="lower(r.billing_class) like 'inst%'", x="r.service_code", fac=FAC_LIST)} pos,
        case when r.allowed_amount > 0 then 'dollar' when r.allowed_amount = 0 then 'zero' else 'not a number' end rate_kind,
        r.allowed_amount rate, cast(r.npi as varchar) npi, cast(r.tin as varchar) tin, '' setting, false counted, '' unit_note,
        p.kind p_kind, coalesce(p.wage_index, 1.0) p_wi, p.ccn p_ccn, p.locality p_loc, p.rural p_rural, p.state p_state,
        false labeled_many, false labeled_spec
      from {t} r join prov p on p.npi = cast(r.npi as varchar)"""


def allowed_rows(doc, insurer):
    """One TiC allowed-amount file (parsed JSON) -> flat rows. Every payment amount for every NPI it lists."""
    plan = doc.get("plan_name") or doc.get("reporting_entity_name") or ""
    for item in doc.get("out_of_network") or []:
        ct, code = item.get("billing_code_type") or "", str(item.get("billing_code") or "")
        for aa in item.get("allowed_amounts") or []:
            tin = (aa.get("tin") or {}).get("value") or ""
            sc = ",".join(aa.get("service_code") or [])
            for pay in aa.get("payments") or []:
                amt = pay.get("allowed_amount")
                mod = ",".join(pay.get("billing_code_modifier") or [])
                for pr in pay.get("providers") or []:
                    for npi in pr.get("npi") or []:
                        yield dict(insurer=insurer, plan=plan, code_type=ct, code=code, tin=str(tin), npi=str(npi),
                                   billing_class=aa.get("billing_class") or "", modifier=mod, service_code=sc,
                                   allowed_amount=float(amt) if amt is not None else None)


OUT_SUFFIXES = (".part.parquet", ".codes.parquet", ".npis.parquet", ".hcodes.parquet")


def reduce_table(con, units_sql, const, out_prefix):
    """Write <out_prefix>.part.parquet (amount counts), .codes.parquet (providers per code), .npis.parquet (providers
    per bucket) and, for a hospital file, .hcodes.parquet (the codes it lists). Returns the number of part rows."""
    part, codes, buckets, hcodes = _units_to_part(con, units_sql, const)
    con.execute(f"copy ({part}) to '{out_prefix}.part.parquet' (format parquet, compression zstd)")
    con.execute(f"copy ({codes}) to '{out_prefix}.codes.parquet' (format parquet, compression zstd)")
    con.execute(f"copy ({buckets}) to '{out_prefix}.npis.parquet' (format parquet, compression zstd)")
    if const.get("source") == "hospital":
        con.execute(f"copy ({hcodes}) to '{out_prefix}.hcodes.parquet' (format parquet, compression zstd)")
    n = con.execute(f"select count(*) from '{out_prefix}.part.parquet'").fetchone()[0]
    con.execute("drop view if exists uve; drop table if exists te; drop table if exists uv; drop table if exists pn")
    return n


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)[:150]
