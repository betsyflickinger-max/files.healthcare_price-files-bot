# Hospital file vs insurer file: DFW pilot (Oct 24, 2026)

Live DFW build `2026-10-12`: 83 hospital files, 95 insurer tables. The 89 core procedures, facility fees only.
Bands (set before looking): match = within $1 or 0.5%; close = within 5%; otherwise files disagree. The closest pair of
amounts decides; nothing is averaged. Hospital rows for Medicare Advantage / Medicaid plans are left out. File dates more than 60 days apart are flagged.

**Where both files give a dollar amount: 1,710** (hospital file + insurer + procedure + setting)

- Match: 653 (38%)
- Close: 66 (4%)
- Files disagree: 991 (58%)
- Not comparable (percent of charges, per diem, formula, professional fee only...): 307
- Only the hospital file has it: 45,740 · only the insurer file has it: 390
- File dates more than 60 days apart: 1,057

Note (Oct 24, 2026): UnitedHealthcare Core / Core EPO / Select Plus / Navigate and Aetna's four national networks are being added to DFW this week;
their prices reach this comparison at the next DFW build, so UnitedHealthcare and Aetna results may shift. Re-run: push a change to
site/match_pilot.py or run the "Match pilot" workflow by hand (it also runs on the 10th of each month).

## By insurer

| Insurer | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| UnitedHealthcare | 1,710 | 653 | 66 | 991 | 307 | 2,931 | 390 |
| Aetna | 0 | 0 | 0 | 0 | 0 | 4,558 | 0 |
| Ambetter | 0 | 0 | 0 | 0 | 0 | 4,865 | 0 |
| BCBSTX | 0 | 0 | 0 | 0 | 0 | 5,501 | 0 |
| Cigna | 0 | 0 | 0 | 0 | 0 | 5,012 | 0 |
| Humana | 0 | 0 | 0 | 0 | 0 | 4,404 | 0 |
| Molina | 0 | 0 | 0 | 0 | 0 | 3,938 | 0 |
| Rental PPO networks | 0 | 0 | 0 | 0 | 0 | 3,192 | 0 |

## Biggest hospitals (most procedures both files price)

| Hospital | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| AMH Cath Labs LLC | 33 | 0 | 0 | 33 | 3 | 665 | 0 |
| Flower Mound Hospital Partners LLC | 33 | 0 | 0 | 33 | 3 | 673 | 0 |
| Physicians Medical Center LLC | 33 | 0 | 0 | 33 | 3 | 644 | 0 |
| Rockwall Regional Hospital LLC | 33 | 0 | 0 | 33 | 3 | 656 | 0 |
| Southlake Specialty Hospital LLC | 33 | 0 | 0 | 33 | 3 | 653 | 0 |
| Texas Health Arlington Memorial Hospital | 33 | 0 | 0 | 33 | 3 | 686 | 0 |
| Texas Health Harris Methodist Hospital Alliance | 33 | 0 | 0 | 33 | 3 | 674 | 0 |
| Texas Health Harris Methodist Hospital Azle | 33 | 0 | 0 | 33 | 3 | 664 | 0 |
| Texas Health Harris Methodist Hospital Cleburne | 33 | 0 | 0 | 33 | 3 | 673 | 0 |
| Texas Health Harris Methodist Hospital Fort Worth | 33 | 0 | 0 | 33 | 52 | 644 | 0 |
| Texas Health Harris Methodist Hospital HurstEulessBedford | 33 | 0 | 0 | 33 | 3 | 678 | 0 |
| Texas Health Harris Methodist Hospital Southwest Fort Worth | 33 | 0 | 0 | 33 | 3 | 676 | 0 |
| Texas Health Hospital Frisco | 33 | 0 | 0 | 33 | 3 | 664 | 0 |
| Texas Health Hospital Mansfield | 33 | 0 | 0 | 33 | 0 | 237 | 3 |
| Texas Health Huguley Hospital Fort Worth South | 33 | 0 | 0 | 33 | 0 | 239 | 3 |

## Biggest disagreements (big insurers)

| Hospital | Insurer | Procedure | Hospital file says | Insurer file says | Dates (hospital / insurer) |
|---|---|---|---:|---:|---|
| Dallas Medical Center | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $3,310.00 (United HealthCare · UHC Commercial All Payor; row 101) | $92,887.69 | 2026-09-01 / 2026-10-01 |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $14.97 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MRMC; row 360440) | $88,657.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $14.97 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MCMC; row 636604) | $88,657.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $14.97 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MSMC; row 703314) | $81,779.00 | 2026-03-23 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 470  (inpatient) | $2.95 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MRMC; row 360614) | $24,134.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 470  (inpatient) | $2.95 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MCMC; row 636774) | $24,134.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Texas Health Hospital Mansfield | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $242,041.68 (UnitedHealthCare · All Commercial Plans; row 23455) | $264,820.40 | 2026-04-01 / 2026-10-01 ⚑ |
| Texas Health Huguley Hospital Fort Worth South | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $242,041.68 (UnitedHealthCare · All Commercial Plans; row 19559) | $264,820.40 | 2026-04-01 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 473  (inpatient) | $3.74 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MRMC; row 360617) | $20,447.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Methodist Hospitals of Dallas | UnitedHealthcare (Choice Plus) | 473  (inpatient) | $3.74 (UNITED HEALTHCARE MANAGED CARE [3021] · MHS HB UHC EXCHANGE MCMC; row 636777) | $20,447.00 | 2026-03-21 / 2026-10-01 ⚑ |
| Dallas Medical Center | UnitedHealthcare (Choice Plus) | 473  (inpatient) | $3,310.00 (United HealthCare · UHC Commercial All Payor; row 138) | $23,180.14 | 2026-09-01 / 2026-10-01 |
| USMD Hospital at Arlington LLC | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $245,362.41 (United Healthcare · United Healthcare HMO; row 1399) | $264,820.40 | 7/13/2026 / 2026-10-01 ⚑ |
| AMH Cath Labs LLC | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $247,108.14 (United Healthcare · All Payer; row 6699148) | $264,820.40 | 2026-04-21 / 2026-10-01 ⚑ |
| Flower Mound Hospital Partners LLC | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $247,108.14 (United Healthcare · All Payer; row 6877205) | $264,820.40 | 2026-04-21 / 2026-10-01 ⚑ |
| Physicians Medical Center LLC | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $247,108.14 (United Healthcare · All Payer; row 2853970) | $264,820.40 | 2026-04-21 / 2026-10-01 ⚑ |

## Why rows were not comparable (most common)

- hospital file: percent of billed charges: 121
- hospital file: Medicare Advantage plan rows: 82
- insurer file: professional fee only: 60
- hospital and insurer files give it for different settings: 26
- hospital file: row has a modifier: 10
- hospital file: Medicaid plan rows: 4
- hospital file: professional fee only: 3
- hospital file: per diem: 1

## Data notes

- Hospital files without saved rows: 6 (Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas)
- Hospital files with no NPI found (can't be matched to insurer files): 6
- Insurer tables of the build not found in the stage-A cache: 91 (2026-09-05_pl-22z-hr23_Aetna-Health-Inc.---Texas.parquet, 2026-09-05_pl-2ua-hr23_Aetna-Life-Insurance-Company.parquet, 2026-09-05_pl-3ei-hr23_Aetna-Life-Insurance-Company.parquet, 2026-09-05_pl-4wr-hr23_Aetna-Health-Inc.---Texas.parquet, 2026-09-05_pl-5it-hr23_Aetna-Life-Insurance-Company.parquet, 2026-09-28_centene-management-company-llc_ambetter-tx_in-network.parquet)
- Full list: pairs.csv (one row per hospital file + insurer + procedure; both amounts with their sources).
