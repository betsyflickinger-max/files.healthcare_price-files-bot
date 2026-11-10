# Private prices as a multiple of Medicare

Added Nov 10, 2026. Code: `analysis/medicare_multiple/`. Tests: `tests/test_medicare_multiple.py`.
Workflow: **Actions → Private price vs Medicare**. Report: `reports/medicare-multiple/<state>/`.

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
| Anesthesia | anesthesia codes 00100–01999 | the locality's anesthesia conversion factor (per unit) |
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
  (Austin, Beaumont, Brazoria, Dallas, Fort Worth, Galveston, Houston, rest of Texas). The **facility** rate is used when every
  place-of-service code on the insurer's rate is a hospital or facility place; otherwise the **office** rate (the higher one).
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
- Hospitals and surgery centers are matched to their Medicare record by address (`site/med_local.py`, already used by the site).

## Private rates

- **Insurer files** (in-network tables already read for the state; for Texas, `data/tx/` plus the DFW tables for networks and
  files the Texas tables don't have). Dollar amounts only. Kept out of the ratio and counted separately: percent of charges,
  per-day rates (by type or by the insurer's own note), $0, capitation and bundle arrangements.
- **Hospital files** (each hospital's own posted negotiated rates, `data/hosp_every/`), compared with that hospital's own
  Medicare amount, inpatient and outpatient. Commercial plans are the headline; Medicare Advantage, Medicaid and other public
  plans named in the file are reported on their own.
- **Out-of-network:** insurers' allowed-amount files. Their own figure, never pooled with in-network.
- **"Traditional"** (e.g. "BCBS Traditional", an indemnity plan with no network) is labeled **unclear**, never in-network.
- **A listed rate** = one dollar amount for one provider (NPI + TIN) and one service (code, modifier, billing class, setting,
  rate type) in one file. Exact copies count once. Two different amounts for the same provider and service count twice:
  nothing is averaged. High rates are never dropped.

## Rates that may never be used

Every figure is shown twice: with **all rates**, and **without likely-unused rates** — those labeled by
`insurers/pipeline/rate_labels.py` (`docs/rate-labels.md`): far from Medicare (below 0.5× or above 8×), one amount for 10+
unrelated codes at one provider, or a kind of clinician that almost never bills the code. The labeled rates stay in the data.
Because one label is defined by distance from Medicare, the "without" view is narrower by construction: read it as a
range check, not as the answer.

## The figures

- **Per code:** 10th, middle and 90th percentile of (listed rate ÷ that provider's Medicare amount), using the actual value
  at that rank (nearest rank). A code needs **at least 5 different providers** for a figure; codes with fewer are listed with
  their counts and no figure.
- **Per bucket:** the middle of its codes' middles.
- **Total (a), weighted by Medicare's mix of care, which skews older:** Σ(Medicare volume × middle private rate) ÷
  Σ(Medicare volume × middle Medicare amount) over codes with a figure. Volumes are 2024 services in the state from CMS's
  public use files: Physician & Other Practitioners, Outpatient Hospitals, Inpatient Hospitals (DRG discharges), and DME, each
  "by Geography and Service". Anesthesia (cases vs. units) and surgery centers (no volume file in scope) are left out of (a).
- **Total (b), equal weight:** the middle of all codes' middles.
- **Coverage:** codes, providers and listed rates behind every figure, and every code with no benchmark or too few providers.
- **By market segment:** the files have no segment field, so a network counts as individual (marketplace) only when its own
  name says so; everything else is "not stated in file".

## Check against published studies

The report puts its weighted figures next to KFF's 2020 literature review (doctors 1.43×, inpatient 1.89×, outpatient 2.64×)
and RAND Round 5.1 (hospitals 2.54× nationally and 2.59× in Texas, 2022 claims) and explains gaps. Published studies count
**paid claims**; price files list every rate in every contract, used or not, which is why an earlier DFW snapshot that counted
every listed rate once came out near 1.0× for outpatient facility fees and 0.88× for doctor fees. The weighted total and the
"without likely-unused" view are the two corrections; the report shows how far each one moves the numbers.

## Known limits

- Anesthesia amounts are compared per unit; the insurer files don't say whether an amount is per unit or per case.
- DME rates without a modifier are compared with the fee schedule's no-modifier row, else its purchase-new (NU) row.
- Device-intensive surgery-center codes (J8) are wage-adjusted on the whole rate; CMS adjusts only the non-device part.
- Provider counts per code are exact up to the 5-provider rule and "at least" beyond it (a provider in several networks'
  tables is counted once per table).
- Providers whose practice ZIP isn't in CMS's ZIP-to-locality file are outside the state run.
- Hospital files: the newest parsed copy listed in `data/hospitals.csv`.

## How to run it

One command per state, or all states (each area's insurer tables are read once for all its states):

    python analysis/medicare_multiple/run.py estimate --state TX     # cost first: reads only file footers
    python analysis/medicare_multiple/run.py start    --state TX     # if within the limit: Medicare tables, rented machines, ...
    python analysis/medicare_multiple/run.py status   --state TX
    python analysis/medicare_multiple/run.py summarize --state TX    # -> reports/medicare-multiple/tx/

or **Actions → Private price vs Medicare** with step = estimate, start, status, summarize. `start` refuses to read anything
if the estimate is over $40 (or over `build_approvals.json` "mm-tx" / "mm-all"), rents nothing once Betsy's monthly card cap
is reached, and leaves at least two machine slots free. Rented machines delete themselves when done. Nothing is written to
the site and nothing is deleted; everything lands under `analysis/medicare-multiple/<run id>/` in storage.

## Cost

Speed measured Nov 10, 2026 on 20 million made-up rows shaped like an insurer table: 112 seconds on 2 cores for the labels,
the Medicare join and the counts (about 89,000 rows per core-second). Assumed 600,000 rows/second on an 8-core rented machine
and 300,000 on a GitHub machine. Row counts from the insurer-file census (`reports/census/`).

| Run | Rows | Rented machine hours | Rented machines | Storage | Total |
|---|---|---|---|---|---|
| Texas (28 tables over 800 million rows rented, 63 on GitHub) | 96 billion | ~45 | ~$27 at $0.60/hour | $0 on R2; up to ~$4.40 if storage is Backblaze B2 and none of its free download allowance is left | **~$27–31** |
| All states | 1.55 trillion | 625–750 | ~$375–450 | $0 on R2; up to ~$68 on B2 | **~$380–520** |

All states with 10 machines takes about 3 days of rented-machine time; at 4 machines about a week. GitHub's machines are free
for this public repo, but at 4 at a time they would need weeks for all states, so for `--state ALL` set "tables on GitHub's
free machines" to 0.
