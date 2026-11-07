# Data accuracy audit, Layer 2 (independent round trip): 2026-11-07

audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.

## Insurer lines: 1165 sampled, 112 traced, 112 matched (100.0%)

| Verdict | Lines |
|---|---|
| not checked (time budget used up) | 1052 |
| match | 112 |
| source table not found | 1 |

## Hospital-file lines: 483 sampled, 467 traced, 386 matched (82.7%)

| Verdict | Lines |
|---|---|
| match | 386 |
| not found in source | 31 |
| code not on cited line | 31 |
| amount not on cited line | 19 |
| not checked (read error) | 16 |

Insurer name check: 0 sampled lines where the file's own insurer name doesn't match the insurer shown.

Matched lines whose source row carries a caveat: expired 6, modifier 12

Every sampled line with its verdict: roundtrip.csv.
Seed 20261107; rerun with the same seed to get the same sample.
