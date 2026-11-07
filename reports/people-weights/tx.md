# People covered in Texas, by insurer (for weighting research figures only)

Built 2026-11-07 by `insurers/people_weights.py`. Each count is labeled with its source and year. Nothing is estimated or scaled: self-funded plans that don't file a Form 5500 (most with under 100 participants) are missing, and a plan listed by more than one insurer is not split. The site's headline figures are never weighted.

Insured: CMS MLR public use file, reporting year 2024 (lives on Dec 31, 2024), https://www.cms.gov/files/zip/mlr-public-use-file-2024.zip.

| Insurer | MLR parent group | Individual | Small group | Large group | Insured total | Self-funded employers (5500) | Self-funded participants (5500) | 5500 years | Total listed |
|---|---|---|---|---|---|---|---|---|---|
| BCBSTX | Health Care Service Corp (HCSC) | 1,445,546 | 542,592 | 1,519,799 | 3,507,937 | — | — | — | — |
| UnitedHealthcare | UnitedHealth Group | 730,972 | 42,148 | 713,537 | 1,486,657 | — | — | — | — |
| Aetna | CVS Health (Aetna) | 245,819 | 873 | 123,716 | 370,408 | — | — | — | — |
| Cigna | Cigna Group | 100,167 | 0 | 136,724 | 236,891 | — | — | — | — |
| Anthem | — | — | — | — | — | — | — | — | — |
| Wellpoint | Elevance Health (Anthem) | — | — | — | — | — | — | — | — |
| Ambetter | Centene (Ambetter) | 521,891 | 0 | 0 | 521,891 | — | — | — | — |
| Oscar | Oscar Health | 141,000 | 0 | 0 | 141,000 | — | — | — | — |
| Molina | Molina Healthcare | 18,942 | 0 | 0 | 18,942 | — | — | — | — |
| BSW Health Plan | Baylor Scott & White Health Plan | 230,684 | 15,851 | 17,023 | 263,558 | — | — | — | — |
| Community Health Choice | Community Health Choice, Inc. | 110,756 | 0 | 0 | 110,756 | — | — | — | — |
| CHRISTUS Health Plan | CHRISTUS HEALTH PLAN | 49,341 | 0 | 0 | 49,341 | — | — | — | — |
| Curative | Curative Inc Grp | 0 | 0 | 45,697 | 45,697 | — | — | — | — |
| Moda | Oregon Dental Grp | 4,486 | 0 | 0 | 4,486 | — | — | — | — |

Self-funded side: Form 5500 side not loaded in this run.
Form 5500 participants are employees on the filing, not family members, so they undercount people covered.

Notes:
- Anthem: no Texas comprehensive lives under Elevance in the 2024 MLR file; counted only through employer plans that list Anthem networks
- Wellpoint: Elevance brand; no Texas comprehensive lives under Elevance in the 2024 MLR file
- Moda: Moda Health Plan, Inc. files under the Oregon Dental group in the MLR file
