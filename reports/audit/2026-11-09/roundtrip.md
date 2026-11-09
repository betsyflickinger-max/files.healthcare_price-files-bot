# Data accuracy audit, Layer 2 (independent round trip): 2026-11-09

audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.

## Insurer lines: 1272 sampled, 139 traced, 139 matched (100.0%)

| Verdict | Lines |
|---|---|
| not checked (time budget used up) | 1133 |
| match | 137 |
| match, but not the lowest plain rate | 2 |

## Hospital-file lines: 423 sampled, 422 traced, 381 matched (90.3%)

| Verdict | Lines |
|---|---|
| match | 381 |
| amount not on cited line | 23 |
| not found in source | 9 |
| found on another line | 5 |
| code not on cited line | 4 |
| source file not found | 1 |

Insurer name check: 0 sampled lines where the file's own insurer name doesn't match the insurer shown.

Matched lines whose source row carries a caveat: modifier 19, arrangement 1, expired 1

Every sampled line with its verdict: roundtrip.csv.
Seed 20261109; rerun with the same seed to get the same sample.
