# Hospital file vs insurer file: DFW pilot (Nov 10, 2026)

Live DFW build `2026-11`: 83 hospital files, 97 insurer tables. The 89 core procedures, facility fees only.
Bands (set before looking): match = within $1 or 0.5%; close = within 5%; otherwise files disagree. The closest pair of
amounts decides; nothing is averaged. Hospital rows for Medicare Advantage / Medicaid plans are left out. Hospital rows labelled out-of-network are listed as their own category and never compared with in-network rates. File dates more than 60 days apart are flagged.

**Where both files give a dollar amount: 10,096** (hospital file + insurer + procedure + setting)

- Match: 4,294 (43%)
- Close: 1,605 (16%)
- Files disagree: 4,197 (42%)
- Not comparable (percent of charges, per diem, formula, professional fee only...): 4,023
- Only the hospital file has it: 36,749 · only the insurer file has it: 11,346
- Out-of-network amounts listed in hospital files (shown separately, not compared): 5,300
- File dates more than 60 days apart: 5,466
- Compared at an NPI that more than one hospital file lists (can't tell which campus the insurer rate is for): 3313

Rules added after the first run (Oct 24, data-type rules, not the bands): a hospital-stay (MS-DRG) amount under $100 is a DRG weight,
not a dollar price (not comparable); a hospital row for a marketplace plan is compared only with marketplace networks, and an
employer-plan row only with the others. If the build's insurer table list isn't recorded, every saved insurer table is read and
each network keeps only its newest file.
Added Oct 24 after the hand-check (reports/match-pilot/2026-10/handcheck/): a hospital row whose methodology is "other" and that gives a
formula is an estimate, not a set price (not comparable): e.g. Methodist's "Case rate ($76,005.38). If operating cost ... ".

Note (Oct 24, 2026): UnitedHealthcare Core / Core EPO / Select Plus / Navigate and Aetna's four national networks are being added to DFW this week;
their prices reach this comparison at the next DFW build, so UnitedHealthcare and Aetna results may shift. Re-run: push a change to
site/match_pilot.py or run the "Match pilot" workflow by hand (it also runs on the 10th of each month).

## By insurer

| Insurer | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| BCBSTX | 4,444 | 2,247 | 1,143 | 1,054 | 922 | 412 | 1,226 |
| Aetna | 2,148 | 815 | 164 | 1,169 | 1,794 | 898 | 1,085 |
| UnitedHealthcare | 1,706 | 656 | 65 | 985 | 330 | 3,189 | 384 |
| Cigna | 728 | 329 | 125 | 274 | 527 | 4,014 | 54 |
| Oscar | 547 | 247 | 0 | 300 | 39 | 980 | 465 |
| Curative | 522 | 0 | 108 | 414 | 324 | 969 | 204 |
| BSW Health Plan | 1 | 0 | 0 | 1 | 46 | 1,322 | 54 |
| Ambetter | 0 | 0 | 0 | 0 | 41 | 5,097 | 24 |

## Biggest hospitals (most procedures both files price)

| Hospital | Both give a $ | Match | Close | Files disagree | Not comparable | Hospital file only | Insurer file only |
|---|---:|---:|---:|---:|---:|---:|---:|
| Methodist Hospitals of Dallas | 674 | 305 | 44 | 325 | 412 | 3,629 | 1,386 |
| MED CITY HEART HOSPITAL | 229 | 136 | 9 | 84 | 26 | 621 | 156 |
| MED CITY SPINE HOSPITAL | 229 | 136 | 9 | 84 | 26 | 621 | 156 |
| MEDICAL CITY DALLAS | 229 | 136 | 9 | 84 | 26 | 627 | 156 |
| MEDICAL CITY FORT WORTH | 229 | 135 | 9 | 85 | 24 | 620 | 153 |
| MEDICAL CITY FRISCO | 229 | 136 | 7 | 86 | 37 | 460 | 163 |
| MEDICAL CITY LEWISVILLE | 229 | 135 | 13 | 81 | 24 | 629 | 155 |
| MEDICAL CITY PLANO | 229 | 136 | 7 | 86 | 37 | 591 | 163 |
| MEDICAL CITY SACHSE | 229 | 136 | 7 | 86 | 25 | 328 | 175 |
| MEDICAL CITY ALLIANCE | 228 | 135 | 11 | 82 | 23 | 570 | 156 |
| MEDICAL CITY DECATUR | 228 | 136 | 8 | 84 | 30 | 436 | 147 |
| MEDICAL CITY DENTON | 228 | 136 | 8 | 84 | 28 | 647 | 149 |
| MEDICAL CITY LAS COLINAS | 228 | 134 | 13 | 81 | 23 | 626 | 156 |
| MEDICAL CITY MCKINNEY | 228 | 134 | 9 | 85 | 29 | 582 | 153 |
| MEDICAL CITY SURGERY CITY ALLIANCE | 228 | 135 | 11 | 82 | 23 | 570 | 156 |

## Biggest disagreements (big insurers)

| Hospital | Insurer | Procedure | Hospital file says | Insurer file says | Dates (hospital / insurer) |
|---|---|---|---:|---:|---|
| Dallas Medical Center | UnitedHealthcare (Choice Plus) | 216  (inpatient) | $3,310.00 (United HealthCare · UHC Commercial All Payor; row 101) | $92,887.69 | 2026-09-01 / 2026-10-01 |
| Texas Health Huguley Hospital Fort Worth South | BCBSTX (Blue Choice PPO) | 460  (inpatient) | $142,157.70 (BCBS · PPO; row 19722) | $59,450.08 | 2026-04-01 / 2026-10-15 ⚑ |
| USMD Hospital at Arlington LLC | BCBSTX (Blue Choice PPO) | 460  (inpatient) | $119,060.99 (Blue Cross · Blue Cross HMO; row 3226) | $39,153.31 | 7/13/2026 / 2026-10-15 ⚑ |
| MED CITY HEART HOSPITAL | Aetna (PPO) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 42527) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY HEART HOSPITAL | Aetna (Open Access Elect Choice) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 23588) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY SPINE HOSPITAL | Aetna (PPO) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 44185) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MED CITY SPINE HOSPITAL | Aetna (Texas HMO - Open Access Health Network Only) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 22928) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY DALLAS | Aetna (PPO) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 184799) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY DALLAS | Aetna (Open Access Elect Choice) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 255912) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 3 files) |
| MEDICAL CITY FORT WORTH | Aetna (PPO) | 27130  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 76377) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY FORT WORTH | Aetna (Texas HMO - Open Access Health Network Only) | 27447  (outpatient) | $60,934.00 (Aetna · NewBusiness; row 95601) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY ARLINGTON | Aetna (Texas HMO - Open Access Health Network Only) | 27130  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 90410) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY ARLINGTON | Aetna (Texas HMO - Open Access Health Network Only) | 27447  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 42369) | $3,682.00 | 2026-09-01 / 2026-09-05 |
| MEDICAL CITY DECATUR | Aetna (Texas HMO - Open Access Health Network Option) | 27130  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 24874) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 4 files) |
| MEDICAL CITY DECATUR | Aetna (PPO) | 27447  (outpatient) | $58,032.00 (Aetna · NewBusiness; row 157705) | $3,682.00 | 2026-09-01 / 2026-09-05 (NPI shared by 4 files) |

## Why rows were not comparable (most common)

- hospital file: percent of billed charges: 1,448
- hospital file: Medicare Advantage plan rows: 1,039
- hospital file: Medicaid plan rows: 456
- hospital file: formula only: 302
- different settings: 191
- hospital file: estimate from a formula: 113
- insurer file: professional fee only: 107
- insurer file: percent of billed charges: 106

## Data notes

- Hospital files without saved rows: 0
- Hospital files with no NPI found (can't be matched to insurer files): 4
- Insurer tables of the build not found in the stage-A cache: 47 (innetwork-G-GMZCT24818.parquet, innetwork-G-GMZCT27929.parquet, innetwork-G-GMZCT28161.parquet, innetwork-G-GMZCT31852.parquet, innetwork-G-MPTCT00001.parquet, innetwork-G-MPTCT00002.parquet)
- Full list: pairs.csv (one row per hospital file + insurer + procedure; both amounts with their sources).
