# CMS quality history: query-ready tables

Run 2026-11-24. Built from the CMS zips saved in `raw/cms_provider_data/` (list: `bot/cms_provider_data/manifest.csv`). Every CSV is converted as-is, all values kept as CMS's own text. Tables: `reference/cms_provider_data/tables/<topic>/<table>/<release>.parquet`. Full file list: `reference/cms_provider_data/catalog.csv`.

- Files converted this run: 0
- Zips not started (time limit, re-run to finish): 0
- Files that could not be converted (listed below, nothing partly loaded): 1

| Topic | Releases | Tables | Files converted | Rows | Not converted |
|---|---|---|---|---|---|
| home-health-services | 33 | 210 | 303 | 19,153,060 | 1 |
| hospice-care | 4 | 6 | 24 | 2,131,492 | 0 |
| hospitals | 35 | 366 | 2,548 | 39,805,807 | 0 |
| inpatient-rehabilitation-facilities | 30 | 93 | 120 | 2,685,878 | 0 |
| long-term-care-hospitals | 29 | 78 | 96 | 720,521 | 0 |
| physician-office-visit-costs | 7 | 170 | 574 | 24,657,695 | 0 |

## Not converted

| Topic | Release | File | Why |
|---|---|---|---|
| home-health-services | 2019-01-31 | HHC_SOCRATA_MSR_DT_RNG.csv | line 2 has 3 cells, the header has 1 |
