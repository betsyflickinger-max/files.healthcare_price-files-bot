# Card #3 preview: Care Compare ratings on the Illinois Price Finder

Built 2026-10-31 by site/care_compare.py preview. Nothing deployed. Ratings file: reference/site/quality/il.json.

| Kind | Rated | Not rated (CMS gives no rating) | Not rated (no single Medicare match) |
|---|---|---|---|
| Hospitals | 120 | 32 | 498 |
| Surgery centers | 0 | 2 | 192 |
| Clinicians | 15,908 | 98,291 | 0 |

## Check against the DFW ratings built by hand in October (reference/site/quality_dfw_by_npi.json)

- NPI -> CCN: 787 NPIs in both; 786 give the same CCN, 1 differ (first: [('1255412789', '450462', '45S462')])
- Hospital overall star: 104 hospitals in both; 65 the same (differences can be a newer CMS release)
- Clinician MIPS score: 30,293 clinicians in both; 22,839 the same
