# Hospital rows v2: keeping the 2026 "is this price actually used" fields

*Set up Nov 11, 2026. Nothing has run yet. It waits for the move to Backblaze to finish.*

## What this is

Every month the bot reads each hospital's price file and saves its rows (one row per code, payer and plan) in storage.
The Price Finder, the reports and the Private price vs Medicare study all use those saved rows.

Since January 1, 2026, hospitals have to add four new numbers next to each negotiated rate (CMS's 2026 hospital rule,
template version 3):

| Field in the hospital file | Name in our rows | What it means |
|---|---|---|
| median allowed amount | `median_amount` (already kept) | the middle of what the insurer actually paid on real claims |
| 10th percentile | `p10_amount` (new) | the low end of what was actually paid |
| 90th percentile | `p90_amount` (new) | the high end of what was actually paid |
| count of allowed amounts | `allowed_count` (new) | how many paid claims those numbers come from: "0", "1 through 10", or a number of 11 or more |

The bot's daily file checker already reads these (PR #414). The saved rows did not, because they are made by an older copy
of the reader. This change teaches that reader the same fields, word for word, and also saves the file's template version
(`file_version`, for example 2.0.0 or 3.0.0) so anyone can see which rules a file was written under.

## Why it matters

A price file lists every rate in every contract, including rates nobody ever pays. The Private price vs Medicare study
(PR #478) only counts a hospital's own rate as "used" when there is evidence. One kind of evidence is the hospital's own
count of allowed amounts: if the count is above zero, real claims were paid at that rate. Right now that check finds
nothing, because the saved rows don't carry the count. After this rebuild it can.

## What changed

| What | Before | After |
|---|---|---|
| Columns in the live site's rows | 29 columns | **the same 29, unchanged**. The live site keeps reading the rows it reads today until you switch. |
| Columns in the new (v2) rows | (none) | the same 29, then `p10_amount`, `p90_amount`, `allowed_count`, `file_version` at the end |
| Files from before 2026 (template v2) | | the four new columns are **blank, never zero** |
| Where the new rows go | | a new folder: `data/2026-11-11/hosp_every_v2/rows/`. The old folder `data/hosp_every/` is never changed or deleted. |
| Which rows the site and the study read | `data/hosp_every/` | set in one place, `site/hosp_rows.json`. It says `"use": "v1"` (the old rows) until you change it to `"v2"`. |
| Scope | DFW only | `dfw`, `tx` (every Texas hospital in the bot's list), later `all` |
| Storage | its own R2 connection | through `bot/store.py`, so it works on Backblaze after the move |
| Running it | | a new button: **Actions → Hospital rows rebuild (2026 fields)**. By hand only, never on a schedule. |

After you switch to v2, the site and the study take a file's v2 rows when they exist and fall back to the old rows for any
file the rebuild hasn't covered yet (for example other states). No file is parsed again just because of the switch.

## Cost

Estimated Nov 11 from the sizes in the bot's hospital list (`data/hospitals.csv`), with the same machine size the monthly
DFW refresh uses for hospital files (4 cores, 8 GB, about $0.08 an hour) and 4 machines at once. The DigitalOcean credit is
used up (issue #491), so this goes on your card.

| Scope | Files | Size of the original files | Machine-hours | Time with 4 machines | Estimated cost |
|---|---|---|---|---|---|
| DFW | 93 | 56 GB | about 5.5 | about 1.5 hours | about $0.60 |
| Texas | 330 | 100 GB | about 11 | about 3 hours | about $1.15 |
| All states (later) | 2,305 | 499 GB | about 54 | about 14 hours | about $5.75 |

How it was worked out: the parser was timed on made-up files (9 MB a second for CSV, 6 for JSON on one core) and the
estimate plans for half that speed, to allow for "wide" CSV files and slower rented cores. Each file also gets 30 seconds
for download and upload, and each machine 15 minutes to start. Downloads from Backblaze are counted at $0.01 a GB even
though most of that is free. The **estimate** step works it out again from what the bot has in storage at the time, and
**status** shows the real speed once files are finishing, so a slow run is visible early.

Safety limits (same rules as the other big jobs):
- **start** stops if the estimate is over **$25**. To allow more, add `"hosp-v2-tx": {"usd": N, "why": "..."}` to
  `build_approvals.json`.
- It stops if the estimate is more than what is left under this month's card cap (`_card_cap`, now $1,000).
- It only rents machines in free slots: it follows the machine-share rules (insurer files that are waiting come first,
  and it counts as a rebuild, which may use at most a quarter of the machines), and it always leaves 2 slots free.
- It refuses to run while the bot is paused for maintenance.

"All states" has one file of about 37 GB. Check that one on its own before running `all`.

## Run order

1. Wait for the storage move to finish (issue #494 says "Ready to switch: yes" and the switch is done).
2. **Actions → Maintenance → resume.** The rebuild refuses to run while issue #493 is open or the hospital queue is on hold.
3. **Actions → Hospital rows rebuild (2026 fields)**, step **estimate**, scope **tx**. Read the files, GB, hours and dollars.
4. Same workflow, step **start**, scope **tx**, confirm **yes**. Machines start, parse, save to the new folder, and delete
   themselves when done. If they're stopped partway, run **start** again: finished files are skipped.
5. Step **status**, scope **tx**: files done, files left, failures, machines still on, and a sample check. The sample check
   takes 3 finished files and compares their new rows with their old rows: the old 29 columns should match row for row,
   and it shows how many rows have the new counts filled in. A file parsed before an earlier reader fix (for example the
   Nov 9 line-number fix) can differ in the old columns; look at those by hand.
6. When you're happy with the sample, change `"use": "v1"` to `"use": "v2"` in `site/hosp_rows.json` (a one-line change;
   Claude can do it). From then on the site builds and the Medicare study read the new rows.

To go back, set `"use"` to `"v1"` again. Both folders stay.

## For engineers

- Parsing: `site/reader.py` (fields ported from `bot/reader.py`, PR #414; `FIELDS` unchanged, `FIELDS_V2` adds the columns),
  `site/hosp_every.py` (v2 when `ROWS_VERSION=v2` or its folder is the v2 folder; v2 runs stop between files while
  `bot/fleet/hold_hospitals.txt` exists).
- Steps: `site/hosp_rebuild.py` (estimate / start / status; `--offline` estimate needs no keys).
- Setting: `site/hosp_rows.json` and `site/hosp_rows.py`, used by `site/orchestrate.py`, `site/hosp_area.py` and
  `analysis/medicare_multiple/run.py`. (`site/geo_build.py`, `site/match_pilot.py` and `site/match_handcheck.py` still read
  the old rows; the columns they read are identical in both.)
- Tests: `tests/test_hosp_rows_v2.py`. The old reader is frozen in `tests/fixtures/site_reader_nov11.py`; the tests check
  the live site's rows are byte-for-byte what it wrote before, and that the new columns match `bot/reader.py`.
