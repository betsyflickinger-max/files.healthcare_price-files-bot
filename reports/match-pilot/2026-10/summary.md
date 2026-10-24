# Hospital file vs insurer file: DFW pilot (Oct 24, 2026)

Live DFW build `2026-10-12`: 83 hospital files, 95 insurer tables. The 89 core procedures, facility fees only.
Bands (set before looking): match = within $1 or 0.5%; close = within 5%; otherwise files disagree. The closest pair of
amounts decides; nothing is averaged. Hospital rows for Medicare Advantage / Medicaid plans are left out. File dates more than 60 days apart are flagged.

**Where both files give a dollar amount: 9,652** (hospital file + insurer + procedure + setting)

- Match: 4,033 (42%)
- Close: 1,603 (17%)
- Files disagree: 4,016 (42%)
- Not comparable (percent of charges, per diem, formula, professional fee only...): 3,742
- Only the hospital file has it: 34,363 · only the insurer file has it: 3,823
- File dates more than 60 days apart: 5,085
- Compared at an NPI that more than one hospital file lists (can't tell which campus the insurer rate is for): 3143

Rules added after the first run (Oct 24, data-type rules, not the bands): a hospital-stay (MS-DRG) amount under $100 is a DRG weight,
not a dollar price (not comparable); a hospital row for a marketplace plan is compared only with marketplace networks, and an
employer-plan row only with the others. If the build's insurer table list isn't recorded, every saved insurer table is read and
each network keeps only its newest file.

Note (Oct 24, 2026): UnitedHealthcare Core / Core EPO / Select Plus / Navigate and Aetna's four national networks are being added to DFW this week;
their prices reach this comparison at the next DFW build, so UnitedHealthcare and Aetna results may shift. Re-run: push a change to
site/match_pilot.py or run the "Match pilot" workflow by hand (it also runs on the 10th of each month).

## By insurer

| Insurer | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| BCBSTX | 4,259 | 2,050 | 1,175 | 1,034 | 830 | 412 | 1,327 |
| Aetna | 1,987 | 754 | 135 | 1,098 | 1,683 | 888 | 1,209 |
| UnitedHealthcare | 1,703 | 653 | 66 | 984 | 314 | 2,931 | 390 |
| Cigna | 634 | 329 | 119 | 186 | 465 | 3,913 | 152 |
| Oscar | 547 | 247 | 0 | 300 | 39 | 722 | 465 |
| Curative | 522 | 0 | 108 | 414 | 324 | 969 | 204 |
| Ambetter | 0 | 0 | 0 | 0 | 41 | 4,824 | 24 |
| Humana | 0 | 0 | 0 | 0 | 0 | 4,404 | 0 |

## Biggest hospitals (most procedures both files price)

| Hospital | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| Methodist Hospitals of Dallas | 295 | 112 | 17 | 166 | 67 | 1,242 | 1,019 |
| MEDICAL CITY ALLIANCE | 226 | 135 | 11 | 80 | 25 | 570 | 41 |
| MEDICAL CITY ARLINGTON | 226 | 134 | 8 | 84 | 27 | 623 | 41 |
| MEDICAL CITY FORT WORTH | 226 | 135 | 7 | 84 | 27 | 620 | 38 |
| MEDICAL CITY LEWISVILLE | 226 | 133 | 13 | 80 | 27 | 629 | 40 |
| MEDICAL CITY SURGERY CITY ALLIANCE | 226 | 135 | 11 | 80 | 25 | 570 | 41 |
| MED CITY HEART HOSPITAL | 225 | 133 | 8 | 84 | 30 | 621 | 41 |
| MED CITY SPINE HOSPITAL | 225 | 133 | 8 | 84 | 30 | 621 | 41 |
| MEDICAL CITY DALLAS | 225 | 133 | 8 | 84 | 30 | 627 | 41 |
| MEDICAL CITY DECATUR | 225 | 134 | 8 | 83 | 33 | 436 | 32 |
| MEDICAL CITY DENTON | 225 | 134 | 8 | 83 | 31 | 647 | 34 |
| MEDICAL CITY FRISCO | 225 | 134 | 7 | 84 | 41 | 460 | 48 |
| MEDICAL CITY MCKINNEY | 225 | 133 | 8 | 84 | 32 | 582 | 38 |
| MEDICAL CITY PLANO | 225 | 134 | 7 | 84 | 41 | 591 | 48 |
| MEDICAL CITY SACHSE | 225 | 134 | 7 | 84 | 29 | 328 | 60 |

## Biggest disagreements (big insurers)

| Hospital | Insurer | Procedure | Hospital file says | Insurer file says | Dates (hospital / insurer) |
|---|---|---|---:|---:|---|
| Methodist Hospitals of Dallas | Aetna (Open Access Select) | 216  (inpatient) | $123,128.72 (AETNA [3000] · MHS HB AETNA CVS MCMC; row 340850) | $230,678.00 | 2026-03-21 / 2026-10-05 ⚑ |
| Methodist Hospitals of Dallas | Aetna (Texas HMO - Open Access Health Network Only) | 216  (inpatient) | $128,234.26 (AETNA [3000] · MHS HB AETNA CVS MRMC; row 62337) | $230,678.00 | 2026-03-21 / 2026-09-05 ⚑ (NPI shared by 2 files) |
| Dallas Medical Center | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $3,310.00 (United HealthCare · UHC Commercial All Payor; row 101) | $92,887.69 | 2026-09-01 / 2026-10-01 |
| Texas Health Huguley Hospital Fort Worth South | BCBSTX (Blue Choice PPO) | 460  (inpatient) | $142,157.70 (BCBS · PPO; row 19722) | $59,450.08 | 2026-04-01 / 2026-09-15 ⚑ |
| USMD Hospital at Arlington LLC | BCBSTX (Blue Choice PPO) | 460  (inpatient) | $119,060.99 (Blue Cross · Blue Cross HMO; row 3226) | $39,153.31 | 7/13/2026 / 2026-09-15 ⚑ |
| MED CITY HEART HOSPITAL | Aetna (Open Access Elect Choice) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 42527) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY HEART HOSPITAL | Aetna (Texas HMO - Open Access Health Network Option) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 23588) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY SPINE HOSPITAL | Aetna (Open Access Elect Choice) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 44185) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY SPINE HOSPITAL | Aetna (PPO) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 22928) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY DALLAS | Aetna (Open Access Elect Choice) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 184799) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY DALLAS | Aetna (Texas HMO - Open Access Health Network Option) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 255912) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY FORT WORTH | Aetna (Open Access Elect Choice) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 76377) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY FORT WORTH | Aetna (Texas HMO - Open Access Health Network Option) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 95601) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY ARLINGTON | Aetna (Open Access Elect Choice) | 27130  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 90410) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY ARLINGTON | Aetna (Texas HMO - Open Access Health Network Option) | 27447  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 42369) | $3,682.00 | 2026-09-01 / 2026-09-05 |

## Why rows were not comparable (most common)

- hospital file: percent of billed charges: 1,642
- hospital file: Medicare Advantage plan rows: 636
- hospital file: Medicaid plan rows: 447
- hospital file: formula only: 316
- different settings: 191
- insurer file: row has a modifier: 143
- insurer file: professional fee only: 119
- insurer file: percent of billed charges: 104

## Data notes

- Hospital files without saved rows: 6 (Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas, Methodist Hospitals of Dallas)
- Hospital files with no NPI found (can't be matched to insurer files): 6
- Insurer tables of the build not found in the stage-A cache: 0
- Full list: pairs.csv (one row per hospital file + insurer + procedure; both amounts with their sources).
