# CMS quality history: query-ready tables

Run 2026-11-24. Built from the CMS zips saved in `raw/cms_provider_data/` (list: `bot/cms_provider_data/manifest.csv`). Every CSV is converted as-is, all values kept as CMS's own text. Tables: `reference/cms_provider_data/tables/<topic>/<table>/<release>.parquet`. Full file list: `reference/cms_provider_data/catalog.csv`.

- Files converted this run: 3191
- Zips not started (time limit, re-run to finish): 0
- Files that could not be converted (listed below, nothing partly loaded): 17

| Topic | Releases | Tables | Files converted | Rows | Not converted |
|---|---|---|---|---|---|
| dialysis-facilities | 33 | 107 | 721 | 4,245,257 | 0 |
| doctors-clinicians | 79 | 42 | 444 | 366,957,729 | 16 |
| home-health-services | 33 | 210 | 303 | 19,153,060 | 1 |
| hospice-care | 33 | 180 | 238 | 26,594,021 | 0 |
| hospitals | 35 | 366 | 2,548 | 39,805,807 | 0 |
| inpatient-rehabilitation-facilities | 30 | 93 | 120 | 2,685,878 | 0 |
| long-term-care-hospitals | 29 | 78 | 96 | 720,521 | 0 |
| nursing-homes | 91 | 1201 | 1,677 | 178,862,869 | 0 |
| physician-office-visit-costs | 7 | 170 | 574 | 24,657,695 | 0 |
| supplier-directory | 82 | 4 | 119 | 8,353,970 | 0 |

## Not converted

| Topic | Release | File | Why |
|---|---|---|---|
| home-health-services | 2019-01-31 | HHC_SOCRATA_MSR_DT_RNG.csv | line 2 has 3 cells, the header has 1 |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-GPCA.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-ACOM.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-GPPF.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-ECPI.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._Facility_Affiliation.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-GPIA.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._aco_cahps.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._aco_lvl_info.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-ECIA.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._PhysicianComparePhoneNumberFile.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-ACOC.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-GPPI.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._clinician_apm.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._CCPL-ECPF.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._1brd-cert.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
| doctors-clinicians | 2026-01-28 | __MACOSX/doctors_and_clinicians_01_2026/._aco_mips.csv | 'charmap' codec can't decode byte 0x9d in position 235: character maps to <undefined> |
