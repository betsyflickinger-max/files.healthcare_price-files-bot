# Private prices as a multiple of Medicare

Added Nov 10, 2026; caveats fixed the same day (table below). Code: `analysis/medicare_multiple/`. Tests:
`tests/test_medicare_multiple.py`. Workflow: **Actions → Private price vs Medicare**. Report: `reports/medicare-multiple/<state>/`.

## Caveats and how we handle them

| Caveat | What we do now |
|---|---|
| Price files list every rate in every contract, used or not | Main "clean" view: **providers with evidence they do this service** (billed Medicare for it, or the hospital's own file lists it or counts paid claims for it). The 0.5×–8× Medicare range check stays as a second view. Nothing is dropped. |
| A range check hides real overcharges | Rates under 0.5× and over 8× Medicare get their own table (`tails.csv`), with how many have evidence of use. High prices stay in the main view. |
| Medicare data barely covers children and pregnancy | Said in the report. A hospital's own file (it lists the code, or counts paid claims for it) counts as evidence, so children's and maternity hospitals aren't judged on Medicare billing alone. |
| Doctors are paid differently in an office and in a hospital | Each rate uses its own place-of-service codes. Where the file doesn't say, a blend in Medicare's own office/facility mix for that code in the state. Every code also shows its facility-rate and office-rate figure (the range). |
| Anesthesia can be per unit or per case | Sorted by the rate's own note, then its size (up to $200 = per unit, $400 and up = per case). Per unit is compared with Medicare's conversion factor and counts in the weighted total; per case is counted in dollars, with no multiple. |
| Market segment was guessed from network names | Taken from each insurer's table of contents (group or individual, per plan), plus marketplace plan IDs and employer EINs. The name guess is a labeled fallback. |
| Hospital files were matched to Medicare records from a fixed list | Matched every run from what each file says about itself (its NPIs, CMS number, license, EIN). The fixed list is a labeled fallback. |
| Medicare's mix of care skews older | A third total weights kinds of care by how privately insured people under 65 spend (federal MEPS survey, 2024). |
| A run failed when the rented-machine slots were busy | It waits, or queues itself for the nightly run, and always leaves 2 slots for other builds. Optional start time. |

## The question

For every billing code and every kind of care: how much do private insurers' negotiated rates come to, compared with what
Medicare pays for the same service, at the same kind of place, in the same part of the state? Grouped by kind of care, with
a total. Texas first; the same command runs any state, or all of them.

A figure of **1.50×** means the private rate is one and a half times Medicare's.

## Kinds of care (buckets)

Every code is put in one bucket by which Medicare fee schedule pays it and, for doctors' fees, by CMS's own grouping:

| Bucket | Which rates | Medicare amount |
|---|---|---|
| Hospital stays | MS-DRG, facility fee, at a hospital Medicare pays per stay | FY2027 DRG weight × **that hospital's own** rate (see below) |
| Hospital outpatient facility fees | facility fee at an NPI matched to a Medicare hospital | 2026 outpatient (OPPS) rate, adjusted by that hospital's wage index |
| Surgery-center facility fees | facility fee at an NPI matched to a Medicare surgery center | 2026 ASC rate, adjusted by the local wage index |
| Doctor and clinician fees, by RBCS category | doctor fees (evaluation and management, procedures, imaging, tests, treatments, other) | 2026 Physician Fee Schedule for the provider's locality, office or facility rate |
| Anesthesia | anesthesia codes 00100–01999, per-unit amounts | the locality's anesthesia conversion factor (per unit); whole-case amounts counted in dollars, no multiple (see "Anesthesia") |
| Part B drugs | codes on CMS's drug payment file (J-codes and others) | October 2026 payment limit (average sales price + 6%), per billing unit |
| Lab tests | codes on the lab fee schedule | 2026 lab fee schedule |
| Durable medical equipment and supplies | codes on the DMEPOS fee schedule | 2026 state fee schedule, rural or not by ZIP |
| Ambulance | ambulance codes | 2026 ambulance fee schedule, urban / rural / super-rural by ZIP |
| Facility fees, place not matched | facility fee where the NPI isn't matched to a Medicare hospital or surgery center | national outpatient rate; **reported on its own, never in the totals** |
| No Medicare benchmark | dental (CDT), revenue codes, APR-DRGs, codes Medicare doesn't pay or packages into another service, modifiers Medicare doesn't price | none: **counted and listed with the reason** in `no_benchmark_codes.csv`, never dropped |

RBCS is CMS's Restructured BETOS Classification System (every HCPCS/CPT code → category, subcategory, family).

## Medicare amounts: same place, same setting

All from CMS's public files, each recorded with its year and SHA-256 in `medicare_sources.csv`
(list in `analysis/medicare_multiple/sources.py`):

- **Doctor fees:** (work RVU × work GPCI + practice-expense RVU × PE GPCI + malpractice RVU × MP GPCI) × $33.4009, for the
  provider's Medicare locality (from the ZIP of the provider's practice address in the NPI registry). Texas has 8 localities
  (Austin, Beaumont, Brazoria, Dallas, Fort Worth, Galveston, Houston, rest of Texas).
  **Office or facility rate:** each insurer rate carries CMS place-of-service codes (`service_code`). All on CMS's facility
  list (hospital, surgery center, nursing facility, telehealth outside the home and the others in CMS's list) → Medicare's
  **facility** rate; none on it → the **office** rate; both kinds, or no codes at all → a **blend**: share × facility rate +
  (1 − share) × office rate, where the share is how much of that code Medicare itself sees in facilities in the state
  (*Physician & Other Practitioners — by Geography and Service*, 2024; the national share when the state has none; the office
  rate when neither does). `codes.csv` also shows each code's middle multiple **against the facility rate** and **against the
  office rate**, so the low–high range is visible. `methods.csv` counts how many rates used each method.
  Modifier 26 uses Medicare's professional-component row, TC the technical-component row.
- **Hospital outpatient:** national OPPS rate × (0.60 × the hospital's FY2026 wage index + 0.40) for the status indicators CMS
  wage-adjusts (drugs, devices on pass-through and labs are not). Packaged codes (status N) have no separate Medicare payment.
- **Surgery centers:** national ASC rate × (0.50 × wage index + 0.50).
- **Hospital stays:** DRG weight × (operating + capital amount for that hospital) + its uncompensated-care amount per stay.
  Operating = (labor share × wage index × cost-of-living + non-labor share) × (value-based-purchasing × readmissions factor
  + teaching (IME) + DSH); labor share 66% when the wage index is above 1, else 62% (FY2027 Tables 1A/1B, hospitals that
  report quality data). Capital = $539.95 × GAF × (1 + capital IME + capital DSH). All factors per hospital from CMS's FY2027
  impact file. Outlier payments are left out. Sole-community and Medicare-dependent hospitals can be paid on their own
  hospital-specific rate instead; we always use the federal rate. Critical access, children's and cancer hospitals aren't paid
  this way: their stays are "no Medicare benchmark".
- Hospitals and surgery centers are matched to their Medicare record by address (`site/med_local.py`, already used by the site),
  plus the NPIs each hospital's own price file lists for itself (see "Hospital files").

## Anesthesia

Medicare pays anesthesia as (base units + time units) × a conversion factor (about $20–21 in Texas). Insurer files have no
"per unit" rate type, so each dollar amount is sorted:

1. The rate's own note: "per unit" (or "per 15 minutes") → per unit; "per case", "case rate", "flat rate", "per procedure" → per case.
2. Otherwise its size: **up to $200 = per unit** (about 10× Texas Medicare's factor; commercial factors are well below that),
   **$400 and up = per case**, in between = "unclear".

Per-unit amounts are compared with the locality's Medicare conversion factor, and they count in the Medicare-use weighted
total, weighted by Medicare's **allowed dollars** for each anesthesia code in the state (from the same CMS geography file),
because a per-unit multiple can't be weighted by a count of cases. Per-case and unclear amounts are counted, with their
middle dollar amount per code (`anesthesia_per_case.csv`), and left out of every multiple: comparing them would need the
typical anesthesia time per code, and no public CMS file gives it. (CMS's geography file does give Medicare's average allowed
amount per anesthesia service, but cases where an anesthesiologist directs a nurse anesthetist are split into two half-paid
services, so it can't stand in for typical time.)

## Private rates

- **Insurer files** (in-network tables already read for the state; for Texas, `data/tx/` plus the DFW tables for networks and
  files the Texas tables don't have). Dollar amounts only. Kept out of the ratio and counted separately: percent of charges,
  per-day rates (by type or by the insurer's own note), $0, capitation and bundle arrangements.
- **Hospital files** (each hospital's own posted negotiated rates, `data/hosp_every/`), compared with that hospital's own
  Medicare amount, inpatient and outpatient. Commercial plans are the headline; Medicare Advantage, Medicaid and other public
  plans named in the file are reported on their own.
- **Which hospital a file belongs to** is worked out again on every run from what the file says about itself
  (`hospital_match.py`): first its **type 2 NPIs** (looked up in CMS's Hospital Enrollments file), then a **CMS number written
  in the file**, then its **state license number** or its **EIN** (from CMS's file-name rule, `<EIN>_<name>_standardcharges`).
  No public list ties a license or an EIN to a CMS number, so those two count only when another file in the same run, already
  matched by NPI or CMS number, has the same license or EIN, and only when that points to one hospital. Last comes the bot's
  own hospital list (`data/hospitals.csv`), labeled as the fallback. A file covering several hospitals says so. Files that
  can't be matched are listed, never silently skipped. `hospital_matches.csv` shows every file's match, and whether it agrees
  with the bot's list.
- **Out-of-network:** insurers' allowed-amount files. Their own figure, never pooled with in-network.
- **"Traditional"** (e.g. "BCBS Traditional", an indemnity plan with no network) is labeled **unclear**, never in-network.
- **A listed rate** = one dollar amount for one provider (NPI + TIN) and one service (code, modifier, billing class, setting,
  rate type) in one file. Exact copies count once. Two different amounts for the same provider and service count twice:
  nothing is averaged. High rates are never dropped.

## Three views of every figure

1. **All rates.**
2. **Providers with evidence they do this service** (the main view). A rate counts when any of these is true:
   - (a) **The provider billed Medicare for that code in 2024.** Doctor fees: the rate's NPI, or another NPI under the same
     tax ID (the same practice), appears for that code in CMS's *Medicare Physician & Other Practitioners — by Provider and
     Service*. Hospital outpatient facility fees: the hospital (CMS number) billed the payment group (APC) that code is paid in,
     in *Medicare Outpatient Hospitals — by Provider and Service* (that file lists payment groups, not codes). Hospital stays:
     the hospital billed that MS-DRG in *Medicare Inpatient Hospitals — by Provider and Service*.
   - (b) **The hospital lists the code in its own price file** (for insurer and out-of-network rates at that hospital).
   - (c) **The hospital file's 2026 "count of allowed amounts" for that code is above zero** (for the hospital file's own
     rates: every row of a hospital file "lists" its code, so (b) would prove nothing there).

   High prices stay in this view. CMS leaves out of its files any provider-code pair with fewer than 11 Medicare patients,
   so small practices and rare codes can look "without evidence" when they do the service.
   **Medicare data under-represents children's and pregnancy care.** That is why (b) and (c) count too.
   Surgery centers, equipment suppliers and other places with no CMS by-provider file can only show evidence through (a) when
   their NPI is in the physician file; the report says how many rates in each kind of care had evidence.
3. **Range check: 0.5×–8× Medicare** (secondary). Leaves out rates labeled by `insurers/pipeline/rate_labels.py`
   (`docs/rate-labels.md`): far from Medicare (below 0.5× or above 8×), one amount for 10+ unrelated codes at one provider, or
   a kind of clinician that almost never bills the code. Narrower by construction: read it as a range check, not as the answer.

**Rates under 0.5× and over 8× Medicare** are listed in their own table, `tails.csv` (per code: how many, how many have
evidence of use, the highest multiple and the highest listed amount), and summarized in the report.

## The figures

- **Per code:** 10th, middle and 90th percentile of (listed rate ÷ that provider's Medicare amount), using the actual value
  at that rank (nearest rank). A code needs **at least 5 different providers** for a figure; codes with fewer are listed with
  their counts and no figure.
- **Every figure three ways:** all rates, evidence of use, range check (see "Three views").
- **Per bucket:** the middle of its codes' middles.
- **Total (a), weighted by Medicare's mix of care, which skews older:** Σ(Medicare volume × middle private rate) ÷
  Σ(Medicare volume × middle Medicare amount) over codes with a figure. Volumes are 2024 services in the state from CMS's
  public use files: Physician & Other Practitioners, Outpatient Hospitals, Inpatient Hospitals (DRG discharges), and DME, each
  "by Geography and Service". Anesthesia counts per unit, weighted by Medicare's allowed dollars (see "Anesthesia"). Surgery
  centers (no volume file in scope) are left out of (a) and (c).
- **Total (b), equal weight:** the middle of all codes' middles.
- **Total (c), weighted to how privately insured people under 65 use care (MEPS):** each kind of care weighted by its share
  of 2024 spending for people under 65 with any private insurance, from AHRQ's Medical Expenditure Panel Survey (Household
  Component, 2024 Full Year Consolidated file HC-256, the newest year in the MEPS summary tables; the measure is the summary
  table "total expenditures by event type"). Inside each kind, codes keep Medicare-volume weights as in (a). MEPS event types →
  our kinds of care: office visits and the doctor part of outpatient, ER and hospital stays → doctor and clinician fees
  (with anesthesia, lab tests and Part B drugs); outpatient and ER facility → hospital outpatient facility fees; inpatient
  facility → hospital stays; other medical equipment and services → equipment, supplies and ambulance. Prescriptions (23%),
  dental (7%), home health (3%) and glasses (1%) are not in these files: their shares are shown and left out, so (c) covers
  66% of that spending. The shares were computed once from the public file and committed
  (`analysis/medicare_multiple/meps_2024_under65_private.csv`, with the file's SHA-256), so a run downloads nothing from AHRQ.
- **Coverage:** codes, providers and listed rates behind every figure, and every code with no benchmark or too few providers.
- **By market segment:** each insurer's **table of contents** lists every plan that uses a network, with the plan's market
  ("group" or "individual"). The plan-to-network crosswalk (`insurers/plan_network_xwalk.py`) turns that into one row per plan
  and network. A plan with no market stated counts as individual when its ID is a marketplace (HIOS) plan ID, and as group
  when its ID is an employer EIN that files a Form 5500 health plan. A network is "group", "individual", "group and
  individual" or "not stated" by the plans that use it (`segments.py`). Out-of-network allowed-amount files state their own
  market. Only networks no table of contents covers (insurers without a catalog, hospital files) fall back to the old guess
  from the network's name, labeled "network name (fallback)". `methods.csv` counts rates and tables per method.

## Check against published studies

The report puts its weighted figures next to KFF's 2020 literature review (doctors 1.43×, inpatient 1.89×, outpatient 2.64×)
and RAND Round 5.1 (hospitals 2.54× nationally and 2.59× in Texas, 2022 claims) and explains gaps. Published studies count
**paid claims**; price files list every rate in every contract, used or not, which is why an earlier DFW snapshot that counted
every listed rate once came out near 1.0× for outpatient facility fees and 0.88× for doctor fees. The weighted totals and the
evidence-of-use view are the corrections; the report shows how far each one moves the numbers.

## Known limits

- Evidence of use (a) comes from 2024 Medicare billing; CMS leaves out pairs with fewer than 11 patients.
- Outpatient evidence is by payment group (APC), not by code: CMS's by-hospital outpatient file has no code column.
- Evidence (c) needs the 2026 "count of allowed amounts" in the parsed hospital rows. The bot's hospital reader keeps it since
  PR #414, but the shared parsed-row cache (`site/hosp_every.py`, built with `site/reader.py`) doesn't keep that column yet, so
  until that cache is rebuilt with the newer reader, (c) finds nothing and hospital files' own rates show evidence only through (a).
- Anesthesia whole-case amounts have no multiple (no public typical-time source).
- DME rates without a modifier are compared with the fee schedule's no-modifier row, else its purchase-new (NU) row.
- Device-intensive surgery-center codes (J8) are wage-adjusted on the whole rate; CMS adjusts only the non-device part.
- Provider counts per code are exact up to the 5-provider rule and "at least" beyond it.
- Providers whose practice ZIP isn't in CMS's ZIP-to-locality file are outside the state run.
- Market segment needs the plan-to-network crosswalk to have been built (Actions → Plan to network crosswalk). Without it,
  every table falls back to its network name, and the report says so.

## How to run it

**Actions → Private price vs Medicare → Run workflow**, with step:

1. **estimate** (state TX): lists the tables and prints the cost. Reads only file footers. Rents nothing.
2. **start**: estimates again and stops if it is over $40 (or over `build_approvals.json` "mm-tx" / "mm-all"); otherwise
   builds the Medicare tables from CMS's public files, starts the free GitHub machines, and rents up to 4 machines for the
   biggest tables. If no machine slot is free (2 are always kept for other builds), it checks every 10 minutes for up to
   **wait_minutes** (240), then leaves the run **queued**; the **nightly run** (2:17 am Central, step "resume", by itself)
   starts it when slots are free, after the same $40 check. Optional **start_after** = "HH:MM" Central: the run waits for
   that time, or queues itself for the nightly run if it is more than wait_minutes away.
3. **status**: how many tables are done.
4. **summarize**: when status shows 0 left, writes the report and commits it to this branch.

Rented machines delete themselves when done. Nothing is written to the site and nothing is deleted; everything lands under
`analysis/medicare-multiple/<run id>/` in storage. The same steps from a terminal:

    python analysis/medicare_multiple/run.py estimate --state TX
    python analysis/medicare_multiple/run.py start    --state TX [--start-after 22:00] [--wait-minutes 240]
    python analysis/medicare_multiple/run.py resume                 # what the nightly run does
    python analysis/medicare_multiple/run.py status   --state TX
    python analysis/medicare_multiple/run.py summarize --state TX   # -> reports/medicare-multiple/tx/

## Cost

Speed measured Nov 10, 2026 on 20 million made-up rows shaped like an insurer table: 112 seconds on 2 cores for the labels,
the Medicare join and the counts. The evidence, place-of-service and anesthesia steps added later the same day made the same
work 1.23× slower (8 million made-up rows, two runs each: 44.9 s instead of 36.5 s), so the speeds the estimate assumes were
cut by a quarter: 480,000 rows/second on an 8-core rented machine and 240,000 on a GitHub machine. Row counts come from the
insurer-file census (`reports/census/`). The new inputs are small (CMS by-provider files for the state's rows only, read in
pages through CMS's data API; one small file per hospital file for its NPIs), so the cost change is the slower speed.

| Run | Rows | Rented machine hours | Rented machines | Storage | Total |
|---|---|---|---|---|---|
| Texas (28 tables over 800 million rows rented, 63 on GitHub) | 96 billion | ~56 (was ~45) | ~$33 at $0.60/hour | $0 on R2; up to ~$4.40 if storage is Backblaze B2 and none of its free download allowance is left | **~$33–38** (was ~$27–31): under the $40 limit |
| All states | 1.55 trillion | 780–940 (was 625–750) | ~$470–560 | $0 on R2; up to ~$68 on B2 | **~$470–630** (was ~$380–520) |

These are the Nov 10 estimate scaled by the measured slow-down; **estimate** prints the real figure from the live table list
and machine price, and **start** refuses anything over the limit. All states with 10 machines takes about 4 days of
rented-machine time; at 4 machines about 10 days. For `--state ALL` set "tables on GitHub's free machines" to 0.
