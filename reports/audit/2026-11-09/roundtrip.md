# Data accuracy audit, Layer 2 (independent round trip): 2026-11-09

audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.

## Insurer lines: 106 sampled, 0 traced, 0 matched (0.0%)

| Verdict | Lines |
|---|---|
| not checked (time budget used up) | 106 |

## Hospital-file lines: 422 sampled, 421 traced, 415 matched (98.6%)

| Verdict | Lines |
|---|---|
| match | 415 |
| not found in source | 4 |
| code not on cited line | 2 |
| source file not found | 1 |

Insurer name check: 0 sampled lines where the file's own insurer name doesn't match the insurer shown.

Every sampled line with its verdict: roundtrip.csv.
Seed 20261109; rerun with the same seed to get the same sample.
