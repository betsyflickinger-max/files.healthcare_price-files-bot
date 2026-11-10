# Data accuracy audit, Layer 2 (independent round trip): 2026-11-09

audit/roundtrip.py, which shares no code with the bot. Random price lines as the pages carry them, traced back to the source.

## Insurer lines: 1272 sampled, 153 traced, 153 matched (100.0%)

| Verdict | Lines |
|---|---|
| not checked (time budget used up) | 1119 |
| match | 151 |
| match, but not the lowest plain rate | 2 |

## Hospital-file lines: 419 sampled, 418 traced, 417 matched (99.8%)

| Verdict | Lines |
|---|---|
| match | 417 |
| source file not found | 1 |
| found on another line | 1 |

Insurer name check: 0 sampled lines where the file's own insurer name doesn't match the insurer shown.

Matched lines whose source row carries a caveat: modifier 22, arrangement 1, expired 1

Every sampled line with its verdict: roundtrip.csv.
Seed 20261109; rerun with the same seed to get the same sample.
