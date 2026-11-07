# Data accuracy audit, Layer 1: 2026-11-06

Read-only rule checks on the deployed site (site/audit_rules.py). 98 areas, the 89 featured procedures; 460,031,057 insurer lines, 12,155,680 hospital-file lines, 427,291 cash lines checked in 70 min.

**Critical findings: 164,752.** Launch gate not met.

| Rule | Level | What | Findings | Areas |
|---|---|---|---|---|
| A1 | Critical | provider's practice ZIP is in another state than the page | 34,355 | 19 |
| A3 | Critical | hospital price file belongs to another hospital or another state | 3 | 3 |
| A4 | Major | quarantined hospital file still has rows in the page data | 2,974 | 2 |
| A9 | Critical | page's state guessed (slug not in the state list) | 0 | 0 |
| B1 | Critical | insurer's rows link to another insurer's file host | 1 | 1 |
| B2 | Major | network shows a code its own file doesn't list | 0 | 0 |
| C1 | Critical | NPI fails the check digit | 0 | 0 |
| C4 | Major | facility fee filed under an individual clinician | 1,827,843 | 25 |
| D1 | Critical | $0, negative or filler-looking amount not flagged | 129,416 | 65 |
| D2 | Major | same amount on 5+ procedures for one place and network, not labeled flat | 392 | 9 |
| D3 | Critical | hospital stay rate under $100 (looks like a weight) | 977 | 25 |
| D6 | Major | percent of charges above 100% | 53,628 | 66 |
| E1 | Major | file date missing or unreadable | 76,228 | 38 |
| E1s | Info | file date older than 183 days (page flags it) | 2,907,016 | 93 |
| E2 | Critical | source link missing | 0 | 0 |
| E4 | Major | source link dead | 449 | 0 |
| F1 | Review | price moved more than 3x since the last audit | 0 | 0 |
| F2 | Review | insurer's lines fell more than 25% since the last audit | 0 | 0 |
| F3 | Review | page lost more than 10% of its providers since the last audit | 0 | 0 |

Source links checked: 8,772 distinct; ok 7,156, blocked to robots 1,082, dead 449, other errors 85 (links.csv).

Change since last audit: first snapshot, nothing to compare yet.

History snapshot: storage history/published/2026-11-06/<area>/insurer.parquet and hospital.parquet (kept permanently).
Full list: storage audit/2026-11-06/failures.csv.gz. Examples (up to 25 per rule and area): examples.csv. Per area: counts.csv.
