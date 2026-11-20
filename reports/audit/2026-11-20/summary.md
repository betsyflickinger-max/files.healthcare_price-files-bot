# Data accuracy audit, Layer 1: 2026-11-20

Read-only rule checks on the deployed site (site/audit_rules.py). 107 areas, the 89 featured procedures; 498,023,702 insurer lines, 8,629,381 hospital-file lines, 406,941 cash lines checked in 93 min.

**Critical findings: 1.** Launch gate not met.

| Rule | Level | What | Findings | Areas |
|---|---|---|---|---|
| A1 | Major | provider's practice ZIP is in another state than the page (procedure pages leave them out; Price Finder lists them) | 31,116 | 17 |
| A3 | Critical | hospital price file's own address is in another state than the page | 1 | 1 |
| A3r | Review | hospital price file was filed under another hospital (same state; check the name shown) | 5 | 5 |
| A3b | Major | page names a hospital differently than the hospital whose file it is | 2 | 1 |
| A4 | Major | quarantined hospital file still has rows in the page data | 682 | 2 |
| A9 | Critical | page's state guessed (slug not in the state list) | 0 | 0 |
| B1 | Critical | insurer's rows link to another insurer's file host | 0 | 0 |
| B2 | Major | network shows a code its own file doesn't list | 0 | 0 |
| C1 | Critical | NPI fails the check digit | 0 | 0 |
| C4 | Info | facility fee filed under an individual clinician (in the data; the pages' own filters keep it off the price lists) | 5,127,222 | 24 |
| D1 | Info | $0, negative or filler-looking amount not flagged in the data (the pages' own filters keep these out of prices) | 128,975 | 53 |
| D2 | Major | same amount on 5+ procedures for one place and network, not labeled flat | 392 | 9 |
| D3 | Critical | hospital-file stay rate under $100 (a weight, not a price; reaches the pages) | 0 | 0 |
| D3p | Info | hospital-file stay rate under $100 in the data (the page's own filter, /*DRGW, leaves it out) | 90 | 3 |
| D3i | Info | insurer-file stay rate under $100 (the pages' low-rate filter drops these) | 138 | 8 |
| D6 | Major | percent of charges above 100% | 54,276 | 67 |
| E1 | Major | file date missing or unreadable | 312,522 | 47 |
| E1s | Info | file date older than 183 days (page flags it) | 2,907,887 | 103 |
| E2 | Critical | source link missing | 0 | 0 |
| E4 | Major | source link dead | 415 | 0 |
| F1 | Review | price moved more than 3x since the last audit | 0 | 0 |
| F2 | Review | insurer's lines fell more than 25% since the last audit | 0 | 0 |
| F3 | Review | page lost more than 10% of its providers since the last audit | 0 | 0 |

Source links checked: 8,800 distinct; ok 6,717, blocked to robots 1,186, dead 415, other errors 482 (links.csv).

Change since last audit: compared with 2026-11-15.

History snapshot: storage history/published/2026-11-20/<area>/insurer.parquet and hospital.parquet (kept permanently).
Full list: storage audit/2026-11-20/failures.csv.gz. Examples (up to 25 per rule and area): examples.csv. Per area: counts.csv.
