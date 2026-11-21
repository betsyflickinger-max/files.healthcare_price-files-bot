# Data accuracy audit, Layer 2 (independent round trip): 2026-11-21

audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.

## Insurer lines: 1272 sampled, 142 traced, 142 matched (100.0%)

| Verdict | Lines |
|---|---|
| not checked (table too big for this run) | 1005 |
| match | 139 |
| not checked (read error) | 124 |
| match, but not the lowest plain rate | 3 |
| source table not found | 1 |

## Hospital-file lines: 420 sampled, 419 traced, 416 matched (99.3%)

| Verdict | Lines |
|---|---|
| match | 416 |
| code not on cited line | 3 |
| source file not found | 1 |

Insurer name check: 0 sampled lines where the file's own insurer name doesn't match the insurer shown.

Matched lines whose source row carries a caveat: modifier 12, arrangement 2, expired 4

Every sampled line with its verdict: roundtrip.csv.
Seed 20261121; rerun with the same seed to get the same sample.
