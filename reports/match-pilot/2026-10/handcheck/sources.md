# Match pilot hand-check: original rows (Oct 24, 2026)

## Case 1: Texas Health Arlington Memorial Hospital × UnitedHealthcare · 27447 

Pilot: hospital $19,497.00 vs insurer $21,154.00 (files disagree)

- Hospital row 5754304: payer `United Healthcare` · plan `All Payer` · CPT 27447 · setting `outpatient` · class `facility` · methodology `case rate` · $ `19497.00` · % `None` · algorithm `` · modifiers `None` · description `TOTAL KNEE ARTHROPLASTY` · notes `Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are comp` / `Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are comp` · file date 2026-04-21
- Same code + insurer in the hospital file: 4 rows: PPO outpatient case rate $24806.00; Medicare Advantage PPO outpatient case rate $14339.46; All Payer outpatient case rate $19497.00; Medicare Advantage HMO outpatient case rate $14597.83
- Raw line 5754304: `TOTAL KNEE ARTHROPLASTY,27447,CPT,0360,RC,,,,,,outpatient,,,,,United Healthcare,All Payer,19497.00,,,,,,,case rate,14351.00,99442.33,"Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are compensated. Rev Codes 274,275,276,278,343,344,636 and 891 are reimbursed in addition to case rate. ","Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are compensated. Rev Codes 274,275,276,278,343,344,636 and 891 are reimbursed in addition to case rate. ",facility`
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `outpatient` · CPT 27447 · rate $21154 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1174533343 TIN 750972805 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet

## Case 2: Texas Health Hospital Mansfield × UnitedHealthcare · 216 

Pilot: hospital $242,041.68 vs insurer $264,820.40 (files disagree)

- Hospital row 23455: payer `Aetna` · plan `HMO/POS/PPO` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `210571.73` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `` · file date 2026-04-01
- Hospital row 23455: payer `BCBS` · plan `Medicare Managed Care Plan` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `77262.79` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `MSDRG Base Rate` · file date 2026-04-01
- Hospital row 23455: payer `BCBS` · plan `PPO` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `249195.5` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `` · file date 2026-04-01
- Same code + insurer in the hospital file: 5 rows: All Commercial Plans inpatient fee schedule $242041.68; Medicare Managed Care Plan inpatient fee schedule $77262.79; All Commercial Plans inpatient other $None; Medicaid Managed Care Plan inpatient other $None; Medicare Managed Care Plan inpatient other $None
- Raw: None
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 0216 · rate $264820.4 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1356960132 TIN 831869297 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet

## Case 3: Texas Health Harris Methodist Hospital Fort Worth × UnitedHealthcare · 19120 

Pilot: hospital $5,023.00 vs insurer $5,473.00 (files disagree)

- Hospital row 3004377: payer `United Healthcare` · plan `All Payer` · CPT 19120 · setting `outpatient` · class `facility` · methodology `case rate` · $ `5023.00` · % `None` · algorithm `` · modifiers `None` · description `REMOVAL OF BREAST LESION` · notes `Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are comp` / `Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are comp` · file date 2026-04-21
- Same code + insurer in the hospital file: 5 rows: All Payer outpatient case rate $5023.00; Managed Medicaid outpatient fee schedule $963.66; Medicare Advantage HMO outpatient case rate $4444.60; Medicare Advantage PPO outpatient case rate $4365.94; PPO outpatient case rate $6494.00
- Raw line 3004377: `REMOVAL OF BREAST LESION,19120,CPT,0360,RC,,,,,,outpatient,,,,,United Healthcare,All Payer,5023.00,,,,,,,case rate,3808.14,25314.92,"Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are compensated. Rev Codes 274,275,276,278,343,344,636 and 891 are reimbursed in addition to case rate. ","Multiple procedures highest paid case rate will be reimbursed 100%, second highest 50%, no additional surgeries are compensated. Rev Codes 274,275,276,278,343,344,636 and 891 are reimbursed in addition to case rate. ",facility`
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `outpatient` · CPT 19120 · rate $5473 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1336172105 TIN 752678857 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `professional` · setting `outpatient` · CPT 19120 · rate $573.16 · service codes `CSTM-00` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1336172105 TIN 756001743 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `outpatient` · CPT 19120 · rate $5473 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1336172105 TIN 756001743 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet

## Case 4: MEDICAL CITY DALLAS × Aetna · 27447 

Pilot: hospital $60,934.00 vs insurer $3,682.00 (files disagree)

- Hospital row 255912: payer `Aetna` · plan `COMM` · CPT 27447 · setting `outpatient` · class `None` · methodology `case rate` · $ `65100.0` · % `None` · algorithm `` · modifiers `None` · description `Arthroplasty, knee, condyle and plateau; medial AND lateral compartments with or without p` · notes `` / `` · file date 2026-09-01
- Hospital row 255912: payer `Aetna` · plan `Meritain` · CPT 27447 · setting `outpatient` · class `None` · methodology `case rate` · $ `65100.0` · % `None` · algorithm `` · modifiers `None` · description `Arthroplasty, knee, condyle and plateau; medial AND lateral compartments with or without p` · notes `` / `` · file date 2026-09-01
- Hospital row 255912: payer `Aetna` · plan `NewBusiness` · CPT 27447 · setting `outpatient` · class `None` · methodology `case rate` · $ `60934.0` · % `None` · algorithm `` · modifiers `None` · description `Arthroplasty, knee, condyle and plateau; medial AND lateral compartments with or without p` · notes `` / `` · file date 2026-09-01
- Same code + insurer in the hospital file: 4 rows: COMM outpatient case rate $65100.0; Meritain outpatient case rate $65100.0; NewBusiness outpatient case rate $60934.0; OON outpatient case rate $77013.0
- Raw: JSON file: the fields above are the parsed entry
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `both` · CPT 27447 · rate $3682 · service codes `01,06,08,12,19,20,22,23,24,25,26,27,41,42,50,52,53,57,58,60,` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1689628984 TIN 621682198 (ein) · table 2026-09-05_pl-22z-hr23_Aetna-Health-Inc.---Texas.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `both` · CPT 27447 · rate $3682 · service codes `01,06,08,12,19,20,22,23,25,26,27,41,42,50,52,53,57,58,60,62,` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1689628984 TIN 621682198 (ein) · table 2026-09-05_pl-22z-hr23_Aetna-Health-Inc.---Texas.parquet

## Case 5: Methodist Hospitals of Dallas × Aetna · 216 

Pilot: hospital $123,128.72 vs insurer $230,678.00 (files disagree)

- Hospital row 340850: payer `AETNA [3000]` · plan `MHS HB AETNA CVS MCMC` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `other` · $ `123128.72` · % `None` · algorithm `Case rate ($76,005.38). If operating cost, defined as billed amount less exclusions * an operating cost-to-charge ratio ` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH ` · notes `Re-evaluated: HLB.61062461; Using new claim; Scope: All Financial Classes; Cases: 18; Inpatient DRG; FSC: XR MC DRG WEIG` / `` · file date 2026-03-21
- Same code + insurer in the hospital file: 3 rows: MHS HB AETNA GOLDEN MCMC inpatient other $76005.38; MHS HB AETNA EXCHANGE MCMC inpatient other $123128.72; MHS HB AETNA CVS MCMC inpatient other $123128.72
- Raw: None
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `both` · MS-DRG 216 · rate $230678 · service codes `21,31,32,33,34,51,54,55,56,61` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1275592131 TIN 750800661 (ein) · table 2026-10-05_pl-4xo-tr25_Aetna-Life-Insurance-Company.parquet

## Case 6: Dallas Medical Center × UnitedHealthcare · 216 

Pilot: hospital $3,310.00 vs insurer $92,887.69 (files disagree)

- Hospital row 101: payer `TRIWEST (BCBS)` · plan `Triwest BCBS` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `case rate` · $ `72188.2` · % `None` · algorithm `` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH ` · notes `` / `100.00% of Medicare Rates` · file date 2026-09-01
- Hospital row 101: payer `United HealthCare` · plan `UHC Commercial All Payor` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `case rate` · $ `3310` · % `None` · algorithm `` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH ` · notes `` / `` · file date 2026-09-01
- Hospital row 101: payer `United HealthCare` · plan `UHC Medicare Advantage` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `case rate` · $ `72188.2` · % `None` · algorithm `` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH ` · notes `` / `100.00% of Medicare Rates` · file date 2026-09-01
- Same code + insurer in the hospital file: 2 rows: UHC Commercial All Payor inpatient case rate $3310; UHC Medicare Advantage inpatient case rate $72188.2
- Raw: JSON file: the fields above are the parsed entry
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 0216 · rate $92887.69 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1861690364 TIN 271459658 (ein) · table 2026-09-01_UHIC_Insurer_Choice-Plus_C2_in-network-rates.parquet

## Case 7: Texas Health Huguley Hospital Fort Worth South × BCBSTX · 460 

Pilot: hospital $142,157.70 vs insurer $59,450.08 (files disagree)

- Hospital row 19722: payer `BCBS` · plan `PPO` · MS-DRG 460 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `142157.7` · % `None` · algorithm `` · modifiers `None` · description `Spinal Fusion Except Cervical Without Mcc` · notes `` / `` · file date 2026-04-01
- Hospital row 19722: payer `Cigna` · plan `HMO` · MS-DRG 460 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `96934.35` · % `None` · algorithm `` · modifiers `None` · description `Spinal Fusion Except Cervical Without Mcc` · notes `` / `` · file date 2026-04-01
- Hospital row 19722: payer `Aetna` · plan `Better Health Medicaid Managed Care Plan` · MS-DRG 460 · setting `inpatient` · class `facility` · methodology `other` · $ `None` · % `None` · algorithm `[Inpatient Services: Payer leverages state specific Medicaid payment methodology. Available, referenceable algorithm log` · modifiers `None` · description `Spinal Fusion Except Cervical Without Mcc` · notes `` / `No services performed during 15-month lookback period.` · file date 2026-04-01
- Same code + insurer in the hospital file: 4 rows: PPO inpatient fee schedule $142157.7; Medicaid Managed Care Plan inpatient other $None; Medicare Managed Care Plan inpatient other $None; PPO inpatient other $None
- Raw: None
- Insurer row: type `per diem` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 460 · rate $1487 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1033120423 TIN 452694620 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 460 · rate $59450.08 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1033120423 TIN 452694620 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet

## Case 8: USMD Hospital at Arlington LLC × BCBSTX · 460 

Pilot: hospital $119,060.99 vs insurer $39,153.31 (files disagree)

- Hospital row 3226: payer `Blue Cross` · plan `Blue Cross HMO` · MS-DRG 460 · setting `inpatient` · class `None` · methodology `case rate` · $ `119060.99` · % `None` · algorithm `` · modifiers `None` · description `SPINAL FUSION EXCEPT CERVICAL WITHOUT MCC` · notes `DRG Not Used in Last Year` / `` · file date 7/13/2026
- Same code + insurer in the hospital file: 2 rows: Blue Cross HMO inpatient case rate $119060.99; Blue Cross PPO inpatient case rate $132291.61
- Raw line 3226: `SPINAL FUSION EXCEPT CERVICAL WITHOUT MCC,460,MS-DRG,inpatient,,,,,Blue Cross,Blue Cross HMO,,119060.99,,,,,,0,79815.38,132291.61,case rate,DRG Not Used in Last Year`
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 460 · rate $39153.31 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1659352987 TIN 731662763 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet
- Insurer row: type `per diem` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 460 · rate $1250 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1659352987 TIN 731662763 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet

## Case 9: MEDICAL CITY LEWISVILLE × Aetna · 216 

Pilot: hospital $135,158.00 vs insurer $81,187.00 (files disagree)

- Hospital row 220848: payer `Aetna` · plan `COMM` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `case rate` · $ `144400.0` · % `None` · algorithm `Stop-loss provision: If billable gross charges exceed threshold of $800000.00, reimbursement will be 27% of billable gro` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZA ` · notes `` / ` Zero instances of this service in the last 15 months prior to posting. Allowed amount values are derived from 835 data ` · file date 2026-09-01
- Hospital row 220848: payer `Aetna` · plan `MCR` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `fee schedule` · $ `73093.74` · % `None` · algorithm `` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZA ` · notes `` / `` · file date 2026-09-01
- Hospital row 220848: payer `Aetna` · plan `Meritain` · MS-DRG 216 · setting `inpatient` · class `None` · methodology `case rate` · $ `144400.0` · % `None` · algorithm `Stop-loss provision: If billable gross charges exceed threshold of $800000.00, reimbursement will be 27% of billable gro` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZA ` · notes `` / ` Zero instances of this service in the last 15 months prior to posting. Allowed amount values are derived from 835 data ` · file date 2026-09-01
- Same code + insurer in the hospital file: 7 rows: COMM inpatient case rate $144400.0; MCR inpatient fee schedule $73093.74; Meritain inpatient case rate $144400.0; NewBusiness inpatient case rate $135158.0; OON inpatient case rate $170825.0; WCOMP inpatient percent of total billed charges $None %50.0; COMM inpatient per diem $2555.0
- Raw: JSON file: the fields above are the parsed entry
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `both` · MS-DRG 216 · rate $81187 · service codes `21,31,32,33,34,51,54,55,56,61` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1255384533 TIN 621682210 (ein) · table 2026-09-05_pl-22z-hr23_Aetna-Health-Inc.---Texas.parquet

## Case 10: Texas Health Hospital Mansfield × BCBSTX · 216 

Pilot: hospital $249,195.50 vs insurer $301,259.09 (files disagree)

- Hospital row 23455: payer `Aetna` · plan `HMO/POS/PPO` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `210571.73` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `` · file date 2026-04-01
- Hospital row 23455: payer `BCBS` · plan `Medicare Managed Care Plan` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `77262.79` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `MSDRG Base Rate` · file date 2026-04-01
- Hospital row 23455: payer `BCBS` · plan `PPO` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `fee schedule` · $ `249195.5` · % `None` · algorithm `` · modifiers `None` · description `Cardiac Valve And Other Major Cardiothoracic Procedures With Cardiac Catheterization With ` · notes `` / `` · file date 2026-04-01
- Same code + insurer in the hospital file: 5 rows: Medicare Managed Care Plan inpatient fee schedule $77262.79; PPO inpatient fee schedule $249195.5; Medicaid Managed Care Plan inpatient other $None; Medicare Managed Care Plan inpatient other $None; PPO inpatient other $None
- Raw: None
- Insurer row: type `per diem` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 216 · rate $3181 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1356960132 TIN 831869297 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 216 · rate $301259.09 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1356960132 TIN 831869297 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet

## Case 11: The University of Texas Southwestern Medical Center at Dallas × BCBSTX · 216 

Pilot: hospital $328,928.79 vs insurer $359,281.50 (files disagree)

- Hospital row 2187213: payer `Blue Cross Blue Shield` · plan `Traditional` · MS-DRG 216 · setting `inpatient` · class `facility` · methodology `case rate` · $ `328928.79` · % `None` · algorithm `` · modifiers `None` · description `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH ` · notes `Accounts receive 48.22% of billed charges in excess of stop loss threshold of $270,399` / `Accounts receive 48.22% of billed charges in excess of stop loss threshold of $270,399` · file date 2026-03-10
- Same code + insurer in the hospital file: 5 rows: MyBlueHealth inpatient case rate $174501.54; Traditional inpatient case rate $328928.79; PPO inpatient case rate $296925.74; HMO inpatient case rate $267229.31; Medicare Advantage inpatient case rate $78897.66
- Raw line 2187213: `CARDIAC VALVE AND OTHER MAJOR CARDIOTHORACIC PROCEDURES WITH CARDIAC CATHETERIZATION WITH MCC,216,MS-DRG,,,,,,,,inpatient,,,,,Blue Cross Blue Shield,Traditional,328928.79,,,,,,,case rate,23784.00,328928.79,"Accounts receive 48.22% of billed charges in excess of stop loss threshold of $270,399","Accounts receive 48.22% of billed charges in excess of stop loss threshold of $270,399",facility`
- Insurer row: type `per diem` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 216 · rate $4536 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1285798918 TIN 753175630 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet
- Insurer row: type `negotiated` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 216 · rate $359281.5 · service codes `` · modifier `` · additional info `` · expires 2999-12-31 · NPI 1285798918 TIN 753175630 (ein) · table 2026-09-15_Blue-Cross-and-Blue-Shield-of-Texas_Blue-Choice-PPO_in-network-rates.parquet

## Case 12: The University of Texas Southwestern Medical Center at Dallas × Cigna · 473 

Pilot: hospital $47,939.85 vs insurer $77,909.21 (files disagree)

- Hospital row 2202036: payer `Cigna` · plan `HMO-PPO` · MS-DRG 473 · setting `inpatient` · class `facility` · methodology `case rate` · $ `47939.85` · % `None` · algorithm `` · modifiers `None` · description `CERVICAL SPINAL FUSION WITHOUT CC/MCC` · notes `Accounts receive 63.93% of total billed charges when stop loss threshold of $208,159 is exceeded` / `Accounts receive 63.93% of total billed charges when stop loss threshold of $208,159 is exceeded` · file date 2026-03-10
- Same code + insurer in the hospital file: 1 rows: HMO-PPO inpatient case rate $47939.85
- Raw line 2202036: `CERVICAL SPINAL FUSION WITHOUT CC/MCC,473,MS-DRG,,,,,,,,inpatient,,,,,Cigna,HMO-PPO,47939.85,,,,,,,case rate,20070.83,79324.87,"Accounts receive 63.93% of total billed charges when stop loss threshold of $208,159 is exceeded","Accounts receive 63.93% of total billed charges when stop loss threshold of $208,159 is exceeded",facility`
- Insurer row: type `fee schedule` · arrangement `ffs` · class `institutional` · setting `inpatient` · MS-DRG 473 · rate $77909.21 · service codes `` · modifier `` · additional info `` · expires 9999-12-31 · NPI 1285798918 TIN 753175630 (ein) · table 2026-10-01_cigna-health-life-insurance-company_pathwell-oap_in-network-rates.parquet

