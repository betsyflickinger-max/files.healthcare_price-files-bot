# Proof a provider does the procedure: every state we cover, data year 2024

Built 2026-10-31 by utilization/build_evidence.py (card #2). Counts only; used to confirm, never to exclude or rank by size.
Originals reused from storage (raw/utilization/, no new download).

## Files used (originals saved in storage, raw/utilization/)

| Source | Version | Size | Link |
|---|---|---|---|
| medicare_physician | 2024-12-01 | 3,250 MB | https://data.cms.gov/sites/default/files/2026-05/b5ebab5a-f490-418a-9bce-4b9f31419356/PHY_R26_P05_V10_D24_Prov_Svc.csv |
| medicare_outpatient | 2024-01-01 | 28 MB | https://data.cms.gov/sites/default/files/2026-06/794975f5-e335-4cbf-8e87-982c834a9639/MUP_OUT_RY26_P04_V10_DY24_Prov_Svc.csv |
| medicare_inpatient | 2024-01-01 | 38 MB | https://data.cms.gov/sites/default/files/2026-04/828defb5-c9e6-4442-8c1b-f27bc0799daf/MUP_INP_RY26_P03_V10_DY24_PrvSvc.CSV |
| hospital_enrollments | 2026-10-01 | 3 MB | https://data.cms.gov/sites/default/files/2026-10/961708ac-2136-43cb-9587-ac64af23b6ab/Hospital_Enrollments_2026.09.29.csv |
| medicaid_professional | 2026-02-09 | 3,073 MB | https://stopendataprod.blob.core.windows.net/datasets/medicaid-provider-spending/2026-02-09/dataset/medicaid-provider-spending.parquet |

Medicaid years kept: 2023, 2024 (2024 is preliminary). Medicaid rows are placed by the NPI's practice state.
HCPCS -> APC for 7,359 codes from reference/site/med_all.json (CMS OPPS Addendum B, July 2026; 2024 volume matched to 2026 groups).

States covered (51): AK, AL, AR, AZ, CA, CO, CT, DC, DE, FL, GA, HI, IA, ID, IL, IN, KS, KY, LA, MA, MD, ME, MI, MN, MO, MS, MT, NC, ND, NE, NH, NJ, NM, NV, NY, OH, OK, OR, PA, RI, SC, SD, TN, TX, UT, VA, VT, WA, WI, WV, WY

## Texas check (should match the Oct 30 Texas-only build: 666,881 / 9,614 / 9,955 / 442,625 rows)

| Source | Rows | Providers | Total count |
|---|---|---|---|
| medicaid_professional | 442,625 | 61,799 | 443,648,573 |
| medicare_inpatient | 9,955 | 241 | 334,970 |
| medicare_outpatient | 9,614 | 308 | 352,245 |
| medicare_physician | 666,881 | 80,776 | 214,352,245 |

## Rows by state

| State | Medicare clinician | Medicare hospital outpatient | Medicare hospital stay | Medicaid | Providers |
|---|---|---|---|---|---|
| AK | 22,227 | 265 | 335 | 18,512 | 5,621 |
| AL | 153,404 | 2,248 | 2,214 | 98,979 | 23,336 |
| AR | 99,938 | 1,434 | 1,678 | 78,248 | 22,244 |
| AZ | 214,725 | 2,204 | 3,071 | 155,105 | 37,773 |
| CA | 799,680 | 10,246 | 13,302 | 939,862 | 166,435 |
| CO | 150,660 | 2,146 | 1,581 | 145,275 | 35,759 |
| CT | 114,286 | 1,215 | 1,502 | 115,689 | 26,649 |
| DC | 25,167 | 288 | 506 | 23,486 | 8,035 |
| DE | 38,405 | 307 | 609 | 17,944 | 6,242 |
| FL | 685,288 | 7,165 | 12,045 | 378,919 | 111,786 |
| GA | 275,340 | 3,670 | 4,059 | 191,219 | 47,338 |
| HI | 25,247 | 491 | 375 | 26,526 | 6,221 |
| IA | 100,372 | 1,295 | 1,418 | 74,054 | 17,758 |
| ID | 44,183 | 675 | 616 | 34,827 | 9,989 |
| IL | 381,231 | 4,779 | 6,384 | 192,737 | 61,535 |
| IN | 191,256 | 3,117 | 3,321 | 199,119 | 35,944 |
| KS | 99,241 | 1,530 | 1,537 | 47,592 | 16,202 |
| KY | 130,210 | 2,174 | 2,186 | 171,746 | 28,561 |
| LA | 127,249 | 2,571 | 1,926 | 202,436 | 28,684 |
| MA | 271,302 | 2,469 | 4,537 | 174,703 | 49,927 |
| MD | 218,562 | 0 | 3,531 | 126,124 | 37,671 |
| ME | 38,606 | 674 | 512 | 36,130 | 10,555 |
| MI | 267,371 | 3,667 | 4,095 | 159,285 | 51,076 |
| MN | 194,955 | 1,892 | 2,319 | 138,831 | 42,188 |
| MO | 178,371 | 2,805 | 3,310 | 125,763 | 35,828 |
| MS | 97,426 | 1,537 | 1,628 | 80,455 | 15,152 |
| MT | 33,480 | 532 | 570 | 23,892 | 7,363 |
| NC | 332,411 | 3,433 | 4,459 | 284,219 | 64,362 |
| ND | 26,324 | 337 | 507 | 14,856 | 5,864 |
| NE | 72,639 | 1,013 | 1,058 | 43,268 | 12,501 |
| NH | 51,312 | 623 | 866 | 21,600 | 9,268 |
| NJ | 310,361 | 2,727 | 4,793 | 187,626 | 48,646 |
| NM | 43,543 | 748 | 637 | 62,932 | 13,034 |
| NV | 73,583 | 851 | 1,338 | 75,388 | 14,482 |
| NY | 600,415 | 5,348 | 8,310 | 478,906 | 118,523 |
| OH | 332,022 | 5,076 | 5,545 | 365,723 | 92,611 |
| OK | 111,790 | 2,065 | 2,093 | 93,251 | 25,107 |
| OR | 103,571 | 1,334 | 1,324 | 127,681 | 29,208 |
| PA | 422,323 | 5,431 | 6,904 | 256,412 | 77,776 |
| RI | 33,370 | 368 | 468 | 27,782 | 7,923 |
| SC | 180,948 | 2,026 | 2,754 | 98,520 | 26,520 |
| SD | 33,373 | 611 | 625 | 12,333 | 5,957 |
| TN | 251,800 | 2,711 | 3,434 | 214,522 | 39,148 |
| TX | 666,881 | 9,614 | 9,955 | 442,625 | 115,360 |
| UT | 74,035 | 1,248 | 801 | 29,884 | 13,167 |
| VA | 267,620 | 2,813 | 4,303 | 180,106 | 45,136 |
| VT | 17,901 | 240 | 295 | 13,666 | 4,522 |
| WA | 185,360 | 2,091 | 2,700 | 163,954 | 45,392 |
| WI | 162,369 | 2,747 | 2,178 | 118,052 | 36,175 |
| WV | 47,628 | 972 | 1,149 | 59,694 | 11,413 |
| WY | 18,230 | 359 | 216 | 7,841 | 3,387 |

Hospitals with a Medicare record but no NPI in CMS Hospital Enrollments (matched by CCN only), top 10 states: TX 13, AL 12, PA 11, CA 8, MN 7, NY 7, IL 5, ME 5, IN 5, MA 5
