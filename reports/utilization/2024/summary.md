# Proof a provider does the procedure: Texas, data year 2024

Built 2026-10-31 by utilization/build_evidence.py (card #2). Counts only; used to confirm, never to exclude or rank by size.

## Files used (originals saved in storage, raw/utilization/)

| Source | Version | Size | Link |
|---|---|---|---|
| medicare_physician | 2024-12-01 | 3,250 MB | https://data.cms.gov/sites/default/files/2026-05/b5ebab5a-f490-418a-9bce-4b9f31419356/PHY_R26_P05_V10_D24_Prov_Svc.csv |
| medicare_outpatient | 2024-01-01 | 28 MB | https://data.cms.gov/sites/default/files/2026-06/794975f5-e335-4cbf-8e87-982c834a9639/MUP_OUT_RY26_P04_V10_DY24_Prov_Svc.csv |
| medicare_inpatient | 2024-01-01 | 38 MB | https://data.cms.gov/sites/default/files/2026-04/828defb5-c9e6-4442-8c1b-f27bc0799daf/MUP_INP_RY26_P03_V10_DY24_PrvSvc.CSV |
| hospital_enrollments | 2026-10-01 | 3 MB | https://data.cms.gov/sites/default/files/2026-10/961708ac-2136-43cb-9587-ac64af23b6ab/Hospital_Enrollments_2026.09.29.csv |
| medicaid_professional | 2026-02-09 | 3,073 MB | https://stopendataprod.blob.core.windows.net/datasets/medicaid-provider-spending/2026-02-09/dataset/medicaid-provider-spending.parquet |

Medicaid years kept: 2023, 2024 (2024 is preliminary).
HCPCS -> APC for 7,359 codes from reference/site/med_all.json (CMS OPPS Addendum B, July 2026; 2024 volume matched to 2026 groups).

## Texas rows

| Source | Rows | Providers | Total count |
|---|---|---|---|
| medicaid_professional | 442,625 | 61,799 | 443,648,573 |
| medicare_inpatient | 9,955 | 241 | 334,970 |
| medicare_outpatient | 9,614 | 308 | 352,245 |
| medicare_physician | 666,881 | 80,776 | 214,352,245 |

Hospitals with a Medicare record but no NPI in CMS Hospital Enrollments (matched by CCN only): medicare_inpatient 8, medicare_outpatient 13

Texas clinicians with delivery codes (59400-59515), by source: medicaid_professional 501

## Packaged procedures: Texas hospitals with Medicare outpatient volume in the code's procedure group

| Code | Group (APC) | Group name | Hospitals | Services |
|---|---|---|---|---|
| 29881 | 5113 | Level 3 Musculoskeletal Procedures | 247 | 9,030 |
| 47562 | 5361 | Level 1 Laparoscopy and Related Services | 244 | 11,911 |
| 64721 | 5431 | Level 1 Nerve Procedures | 221 | 10,336 |
| 66984 | 5491 | Level 1 Intraocular Procedures | 80 | 14,253 |

Codes missing from this table have no hospital outpatient volume record (not a comprehensive procedure group).
