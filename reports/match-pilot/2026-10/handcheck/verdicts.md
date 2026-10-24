# Match pilot hand-check: 12 disagreements checked against the original files (Oct 24, 2026)

Betsy OK'd Oct 24, 3:38am ET: hand-check the pilot's top disagreements before anything goes on the Price File Watch.
Cases: the 5 named (case 1 checked with 3 examples) plus the 5 next-largest dollar gaps among the biggest hospitals and
insurers, skipping repeats of the same hospital + insurer + flat amount. 12 rows checked in all.

How: workflow "Match pilot hand-check" (site/match_handcheck.py, run 40082994920) pulled, for each case, every field of the
hospital row the pilot cited (data/hosp_every/rows/, the parsed copy of the hospital's own file; the original CSV line too
where the file is a CSV of a size that could be streamed) plus every other row in that file for the same code and insurer,
and every row in the insurer's own table for that NPI and code (every field the reader keeps). Full rows:
reports/match-pilot/2026-10/handcheck/case_01.json … case_12.json and sources.md. Every insurer NPI was looked up in the
NPI Registry and is the named hospital's own (organization) NPI; the insurer row's TIN matches the EIN in the hospital
file's name where the file name carries one.

Verdicts: real disagreement (the files conflict on the same thing) / not the same thing / pilot error / placeholder-looking.

| # | Case | Hospital file says | Insurer file says | Verdict |
|---|---|---:|---:|---|
| 1a | Texas Health Arlington Memorial × UnitedHealthcare, knee replacement 27447, outpatient | $19,497 case rate, "All Payer" (Apr 21, 2026) | $21,154, Choice Plus (Sept 1 file, updated Oct 1) | Real disagreement |
| 1b | Texas Health Mansfield × UnitedHealthcare, heart valve DRG 216 | $242,041.68, "All Commercial Plans" (Apr 1) | $264,820.40, Choice Plus (Oct 1) | Real disagreement |
| 1c | Texas Health Harris Methodist Fort Worth × UnitedHealthcare, breast lesion removal 19120 | $5,023 case rate, "All Payer" (Apr 21) | $5,473, Choice Plus (Oct 1) | Real disagreement |
| 2 | Medical City Dallas × Aetna, knee replacement 27447 | $60,934 (NewBusiness), $65,100 (COMM), case rate (Sept 1) | $3,682, Aetna HMO / Open Access (Sept 5) | Placeholder-looking (insurer side) |
| 3 | Methodist (Charlton) × Aetna, heart valve DRG 216 | $123,128.72, methodology "other" (Mar 21) | $230,678, Aetna Choice POS II (Oct 5) | Pilot error (fixed) |
| 4 | Dallas Medical Center × UnitedHealthcare, heart valve DRG 216 | $3,310 "case rate" (Sept 1) | $92,887.69, Choice Plus (Oct 1) | Placeholder-looking (hospital side) |
| 5 | Texas Health Huguley × BCBSTX, spinal fusion DRG 460 | $142,157.70, BCBS PPO, fee schedule (Apr 1) | $59,450.08, Blue Choice PPO (Sept 15) | Real disagreement |
| 6 | USMD Hospital at Arlington × BCBSTX, spinal fusion DRG 460 | $132,291.61 Blue Cross PPO / $119,060.99 HMO, case rate (July 13) | $39,153.31, Blue Choice PPO (Sept 15) | Real disagreement |
| 7 | Medical City Lewisville × Aetna, heart valve DRG 216 | $135,158 (NewBusiness) to $144,400 (COMM), case rate (Sept 1) | $81,187, Aetna HMO / Open Access (Sept 5) | Real disagreement |
| 8 | Texas Health Mansfield × BCBSTX, heart valve DRG 216 | $249,195.50, BCBS PPO, fee schedule (Apr 1) | $301,259.09, Blue Choice PPO (Sept 15) | Real disagreement |
| 9 | UT Southwestern × BCBSTX, heart valve DRG 216 | $296,925.74 PPO / $328,928.79 Traditional, case rate (Mar 10) | $359,281.50, Blue Choice PPO (Sept 15) | Real disagreement |
| 10 | UT Southwestern × Cigna, neck fusion DRG 473 | $47,939.85, Cigna "HMO-PPO", case rate (Mar 10) | $77,909.21, Cigna PathWell OAP (Oct 1) | Not the same thing (plan) |

## Why, case by case

**1a–1c, Texas Health × UnitedHealthcare: real disagreement.** Same hospital (NPI and TIN match), same code, facility fee, same setting, both fixed dollar amounts with no modifier. The hospital rows are case rates for UHC "All Payer" or "All Commercial Plans". UHC's rows are plain negotiated fee-for-service amounts for Choice Plus with no extra notes, and they don't expire (9999-12-31). The hospital files are about 5½ months older (April 2026) than UHC's (Sept 1 file, updated Oct 1). The gap is a steady ~8% on almost every procedure (495 comparisons, middle ratio 0.92), so the likeliest cause is a contract increase the hospital's April file doesn't show yet. The hospital rows also say a second procedure in the same visit is paid at 50% and some supply/drug revenue codes are paid on top; that changes a bill, not the base amount for one procedure. Original lines: Arlington row 5754304 and Fort Worth row 3004377 (quoted in sources.md). Fort Worth's UHC file lists the $5,473 under two TINs (752678857, 756001743); the hospital file's name carries 756001743.

**2, Medical City Dallas × Aetna: placeholder-looking (insurer side).** Aetna's HMO / Open Access file lists the same $3,682 for this hospital on 20 different procedures, from colonoscopy (45378) to knee and hip replacement and neck fusion. The setting is "both" and the place-of-service list is broad. Medical City's own file lists Aetna in-network case rates of $60,934 (NewBusiness) and $65,100 (COMM, Meritain) for a knee replacement, and $77,013 out of network. One flat amount covering a colonoscopy and a joint replacement isn't a usable price for either. Hold, and look at Aetna's other DFW files for the same hospital before calling it anything.

**3, Methodist × Aetna: pilot error, fixed.** The hospital's $123,128.72 is not a set price. The row's methodology is "other", and its formula reads "Case rate ($76,005.38). If operating cost, defined as billed amount less exclusions × an operating cost-to-charge ratio …": the dollar figure is the hospital's estimate from a formula. The rule is now in site/match_pilot.py: a hospital row with methodology "other" that gives a formula is "not comparable". Also, the hospital row is for "AETNA CVS" plans and the insurer row for Aetna Choice POS II, so the plans may differ too.

**4, Dallas Medical Center × UnitedHealthcare: placeholder-looking (hospital side).** The hospital file lists one "case rate" of $3,310 for UHC commercial plans on heart valve surgery (DRG 216), joint replacement (DRG 470) and neck fusion (DRG 473). Its UHC Medicare Advantage row for the same DRG 216 is $72,188.20. A single amount for three very different hospital stays looks like a per-day or placeholder figure under the wrong label. UHC's file lists $92,887.69 for DRG 216. Not a Price File Watch entry as a disagreement; it could be one later as a labeling problem in Dallas Medical Center's file.

**5, Texas Health Huguley × BCBSTX: real disagreement.** Same hospital (NPI 1033120423, Texas Health Huguley), same DRG, inpatient, facility. Hospital: BCBS PPO, fee schedule, $142,157.70 (Apr 1). Blue Cross: Blue Choice PPO, negotiated $59,450.08, plus a separate per-day amount of $1,487 for the same DRG (Sept 15). A 2.4× gap. The per-day row suggests Blue Cross's contract may pay per day in some cases, but neither file says which applies when.

**6, USMD Arlington × BCBSTX: real disagreement.** Hospital (July 13): Blue Cross PPO case rate $132,291.61, Blue Cross HMO $119,060.99, note "DRG Not Used in Last Year". Blue Cross (Sept 15): Blue Choice PPO negotiated $39,153.31, plus a $1,250 per-day amount. PPO to PPO, the hospital's figure is 3.4 times Blue Cross's. (The pilot paired the HMO row because it was closest; the PPO row is the better pair and the gap is larger.)

**7, Medical City Lewisville × Aetna: real disagreement, with a plan caveat.** Hospital (Sept 1): Aetna commercial case rates $144,400 (COMM, Meritain) and $135,158 (NewBusiness), with a stop-loss clause above $800,000 in charges, plus a COMM per-day rate of $2,555; its Aetna Medicare row is $73,093.74. Aetna (Sept 5): HMO / Open Access network, $81,187. Both files are from the same week. The hospital file has no HMO-labeled row, so its "COMM" may or may not include Aetna's HMO.

**8, Texas Health Mansfield × BCBSTX: real disagreement.** Same hospital (NPI 1356960132), same DRG. Hospital: BCBS PPO, fee schedule, $249,195.50 (Apr 1). Blue Cross: Blue Choice PPO $301,259.09 plus a $3,181 per-day amount (Sept 15). Here the insurer's figure is the higher one (hospital at 83%). Huguley's file (case 5) lists the same $249,195.50 for DRG 216; the two hospitals' files share their rates.

**9, UT Southwestern × BCBSTX: real disagreement.** Hospital (Mar 10): Blue Cross PPO case rate $296,925.74 (Traditional $328,928.79, HMO $267,229.31, MyBlueHealth $174,501.54), with a stop-loss above $270,399 in charges (48.22% of the excess). Blue Cross (Sept 15): Blue Choice PPO $359,281.50, plus a $4,536 per-day amount. PPO to PPO the hospital's figure is 83% of Blue Cross's. The files are six months apart.

**10, UT Southwestern × Cigna: not the same thing (plan).** Cigna's row is from its PathWell OAP network file, a separate network product. The hospital file has one Cigna row, "HMO-PPO", $47,939.85. Nothing shows the two describe the same contract. Not drafted.

## Pilot fix and counts
Rule added (commit 626a4cb): a hospital row with methodology "other" that gives a formula is an estimate, so "not comparable".
Re-run (run 40083743301, report commit fa6b48a):

| | Before | After |
|---|---:|---:|
| Both files give a $ | 9,652 | 9,597 |
| Match | 4,033 | 4,033 |
| Close | 1,603 | 1,603 |
| Files disagree | 4,016 | 3,961 |
| Not comparable | 3,742 | 3,797 |

Not changed (judged not systematic): flat amounts repeated across many codes are common and often legitimate (Curative's $11,500 bundle; Texas Health's tiered case rates), so they stay compared, case by case. The closest-pair rule can pair an HMO row with a PPO network (case 6); it understates gaps, it doesn't create them.
