# Care Compare ratings: build 2026-10-31

Built by site/care_compare.py build (card #3). Nothing deployed.

## CMS files used (originals saved in raw/care_compare/)

| Key | Title | CMS release | Size | Link |
|---|---|---|---|---|
| gen | Hospital General Information | 2026-07-22 | 1 MB | https://data.cms.gov/provider-data/dataset/xubh-q36u |
| hc | Patient survey (HCAHPS) - Hospital | 2026-07-22 | 105 MB | https://data.cms.gov/provider-data/dataset/dgck-syfz |
| asc | Ambulatory Surgical Center Quality Measures - Facility | 2025-12-16 | 2 MB | https://data.cms.gov/provider-data/dataset/4jcv-atw7 |
| oas | Outpatient and Ambulatory Surgery Consumer Assessment of Healthcare Providers and Systems (OAS CAHPS) survey for ambulatory surgical centers - Facility | 2026-07-22 | 1 MB | https://data.cms.gov/provider-data/dataset/48nr-hqxx |
| ndf | National Downloadable File | 2026-10-02 | 900 MB | https://data.cms.gov/provider-data/dataset/mj5m-pzi6 |
| mips | PY 2024 Clinician Public Reporting: Overall MIPS Performance | 2026-08-18 | 41 MB | https://data.cms.gov/provider-data/dataset/a174-a962 |
| aff | Facility Affiliation Data | 2026-10-02 | 134 MB | https://data.cms.gov/provider-data/dataset/27ea-46a8 |

NPI -> CCN matches: 11,217 (address matches + 9,138 Hospital Enrollments pairs; 766 NPIs with more than one CCN get no rating)
Surgery centers with a rating: 5,769. Hospitals: 5,419 (3,174 with a CMS star, 3,183 with a patient-survey star).

## By state

| State | Hospitals | With CMS star | With survey star | NPI->CCN matches | Clinicians | With MIPS score |
|---|---|---|---|---|---|---|
| AK | 25 | 10 | 12 | 31 | 3,982 | 1,281 |
| AL | 99 | 58 | 54 | 255 | 20,917 | 4,792 |
| AR | 90 | 43 | 37 | 164 | 13,346 | 1,559 |
| AZ | 108 | 55 | 65 | 131 | 32,608 | 8,495 |
| CA | 377 | 279 | 276 | 492 | 145,902 | 38,093 |
| CO | 96 | 49 | 56 | 442 | 32,449 | 6,346 |
| CT | 36 | 26 | 26 | 166 | 24,337 | 8,130 |
| DC | 10 | 7 | 6 | 15 | 5,508 | 1,568 |
| DE | 13 | 7 | 7 | 17 | 5,948 | 1,063 |
| FL | 221 | 168 | 165 | 341 | 106,656 | 29,795 |
| GA | 149 | 84 | 93 | 712 | 43,948 | 15,723 |
| HI | 23 | 11 | 13 | 29 | 5,849 | 1,514 |
| IA | 118 | 62 | 48 | 223 | 16,137 | 3,979 |
| ID | 48 | 22 | 24 | 76 | 9,153 | 1,613 |
| IL | 193 | 136 | 118 | 289 | 64,638 | 16,499 |
| IN | 148 | 91 | 89 | 210 | 32,044 | 6,815 |
| KS | 139 | 55 | 52 | 260 | 14,952 | 4,250 |
| KY | 103 | 67 | 60 | 174 | 23,627 | 8,744 |
| LA | 161 | 59 | 59 | 281 | 21,153 | 3,512 |
| MA | 84 | 54 | 54 | 129 | 50,735 | 6,601 |
| MD | 56 | 42 | 42 | 58 | 33,054 | 9,792 |
| ME | 36 | 24 | 25 | 57 | 9,699 | 3,984 |
| MI | 149 | 94 | 100 | 234 | 56,841 | 8,305 |
| MN | 136 | 56 | 70 | 213 | 39,529 | 8,183 |
| MO | 120 | 79 | 74 | 374 | 31,323 | 9,521 |
| MS | 109 | 52 | 38 | 323 | 12,098 | 2,955 |
| MT | 63 | 20 | 20 | 82 | 6,565 | 1,056 |
| NC | 120 | 90 | 93 | 470 | 54,874 | 11,207 |
| ND | 47 | 16 | 11 | 83 | 5,325 | 1,630 |
| NE | 93 | 36 | 36 | 163 | 11,240 | 1,568 |
| NH | 27 | 23 | 21 | 56 | 9,061 | 2,752 |
| NJ | 78 | 61 | 60 | 131 | 47,969 | 12,945 |
| NM | 45 | 23 | 26 | 54 | 9,381 | 2,969 |
| NV | 46 | 25 | 26 | 69 | 11,999 | 3,082 |
| NY | 192 | 136 | 135 | 267 | 113,975 | 36,894 |
| OH | 193 | 128 | 128 | 299 | 63,597 | 15,930 |
| OK | 136 | 62 | 54 | 327 | 16,909 | 4,240 |
| OR | 62 | 44 | 46 | 87 | 22,400 | 4,965 |
| PA | 186 | 131 | 135 | 312 | 75,147 | 21,958 |
| RI | 13 | 11 | 11 | 23 | 7,524 | 985 |
| SC | 66 | 49 | 50 | 119 | 24,344 | 6,994 |
| SD | 61 | 18 | 18 | 95 | 5,584 | 1,427 |
| TN | 121 | 72 | 77 | 434 | 35,205 | 8,366 |
| TX | 467 | 216 | 229 | 1,684 | 108,946 | 26,614 |
| UT | 52 | 29 | 34 | 51 | 14,323 | 2,830 |
| VA | 96 | 76 | 79 | 160 | 40,697 | 11,383 |
| VT | 17 | 12 | 13 | 21 | 4,153 | 282 |
| WA | 100 | 60 | 60 | 136 | 37,661 | 6,973 |
| WI | 140 | 86 | 98 | 207 | 33,840 | 7,130 |
| WV | 55 | 34 | 37 | 82 | 9,332 | 3,734 |
| WY | 31 | 16 | 13 | 38 | 2,890 | 753 |

## Columns read (for checking)

- gen: Address, City/Town, Count of Facility MORT Measures, Count of Facility Pt Exp Measures, Count of Facility READM Measures, Count of Facility Safety Measures, Count of Facility TE Measures, Count of MORT Measures Better, Count of MORT Measures No Different, Count of MORT Measures Worse, Count of READM Measures Better, Count of READM Measures No Different, Count of READM Measures Worse, Count of Safety Measures Better, Count of Safety Measures No Different, Count of Safety Measures Worse, County/Parish, Emergency Services, Facility ID, Facility Name, Hospital Ownership, Hospital Type, Hospital overall rating, Hospital overall rating footnote, MORT Group Footnote, MORT Group Measure Count, Meets criteria for birthing friendly designation, Pt Exp Group Footnote, Pt Exp Group Measure Count, READM Group Footnote, READM Group Measure Count, Safety Group Footnote, Safety Group Measure Count, State, TE Group Footnote, TE Group Measure Count, Telephone Number, ZIP Code
- hc: Address, City/Town, County/Parish, End Date, Facility ID, Facility Name, HCAHPS Answer Description, HCAHPS Answer Percent, HCAHPS Answer Percent Footnote, HCAHPS Linear Mean Value, HCAHPS Measure ID, HCAHPS Question, Number of Completed Surveys, Number of Completed Surveys Footnote, Patient Survey Star Rating, Patient Survey Star Rating Footnote, Start Date, State, Survey Response Rate Percent, Survey Response Rate Percent Footnote, Telephone Number, ZIP Code
- asc: ASC-1 Footnote, ASC-1 Rate*, ASC-11 Footnote, ASC-11 Rate*, ASC-12 Footnote, ASC-12 Interval Lower Limit, ASC-12 Interval Upper Limit, ASC-12 Performance Category, ASC-12 RSHV Rate, ASC-12 Total Cases, ASC-13 Footnote, ASC-13 Rate*, ASC-14 Footnote, ASC-14 Rate*, ASC-17 Footnote, ASC-17 Interval Lower Limit, ASC-17 Interval Upper Limit, ASC-17 Performance Category, ASC-17 RSHV Rate, ASC-17 Total Cases, ASC-18 Footnote, ASC-18 Interval Lower Limit, ASC-18 Interval Upper Limit, ASC-18 Performance Category, ASC-18 RSHV Rate, ASC-18 Total Cases, ASC-19 Footnote, ASC-19 Interval Lower Limit, ASC-19 Interval Upper Limit, ASC-19 Performance Category, ASC-19 RSHV Rate, ASC-19 Total Cases, ASC-2 Footnote, ASC-2 Rate*, ASC-3 Footnote, ASC-3 Rate*, ASC-4 Footnote, ASC-4 Rate*, ASC-9 Footnote, ASC-9 Rate*
- oas: Address, City/Town, Communication about your procedure linear mean score, County/Parish, End Date, Facilities and staff linear mean score, Facility ID, Facility Name, Footnote, Number of Completed Surveys, Number of Sampled Patients, Patients recommending the facility linear mean score, Patients who gave the facility a rating of 0 to 6 on a scale from 0 (lowest) to 10 (highest), Patients who gave the facility a rating of 7 or 8 on a scale from 0 (lowest) to 10 (highest), Patients who gave the facility a rating of 9 or 10 on a scale from 0 (lowest) to 10 (highest), Patients who reported NO, they would not recommend the facility to family or friends, Patients who reported PROBABLY YES they would recommend the facility to family or friends, Patients who reported YES they would DEFINITELY recommend the facility to family or friends, Patients who reported that staff definitely communicated about what to expect during and after the procedure, Patients who reported that staff definitely gave care in a professional way and the facility was clean, Patients who reported that staff did not communicate about what to expect during and after the procedure, Patients who reported that staff did not give care in a professional way or the facility was not clean, Patients who reported that staff somewhat communicated about what to expect during and after the procedure, Patients who reported that staff somewhat gave care in a professional way or the facility was somewhat clean, Patients' rating of the facility linear mean score, Start Date, State, Survey Response Rate Percent, Telephone Number, ZIP Code
- ndf: City/Town, Cred, Facility Name, Grd_yr, Ind_PAC_ID, Ind_enrl_ID, Med_sch, NPI, Provider First Name, Provider Last Name, Provider Middle Name, State, Telehlth, Telephone Number, ZIP Code, adr_ln_1, adr_ln_2, adrs_id, gndr, grp_assgn, ind_assgn, ln_2_sprs, num_org_mem, org_pac_id, pri_spec, sec_spec_1, sec_spec_2, sec_spec_3, sec_spec_4, sec_spec_all, suff
- mips: Cost_category_score, Facility Name, Facility-based scoring Certification number, IA_category_score, NPI, Org_PAC_ID, PI_category_score, Provider First Name, Provider Last Name, Quality_category_score, final_MIPS_score, final_MIPS_score_without_CPB, source
- aff: Facility Affiliations Certification Number, Facility Type Certification Number, Ind_PAC_ID, NPI, Provider First Name, Provider Last Name, Provider Middle Name, facility_type, suff
