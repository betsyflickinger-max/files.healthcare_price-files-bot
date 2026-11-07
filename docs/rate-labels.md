# Labels for rates that may never be used

Added Nov 7, 2026. Code: `insurers/pipeline/rate_labels.py`. Tests: `tests/test_rate_labels.py`.

Insurer files list a rate for many provider-and-service pairs that will never be billed. A 2025 study of 61 insurers'
files found 91.8% of listed rates were for providers unlikely to perform the service (Muhlestein, *Health Affairs
Scholar*, Nov 2025, https://pmc.ncbi.nlm.nih.gov/articles/PMC12631121/). The bot now puts **labels** on rates that show
the usual signs. A label never removes, re-ranks or hides a rate. Price lists stay in plain price order, and the
"10 highest" list is unchanged.

Words to use anywhere a label shows: "may never be used" or "unverified". Never "ghost", and never as a finding about an insurer.

| Label | Rule | Why this threshold |
|---|---|---|
| Far from Medicare | Dollar rate below 50% or above 800% of Medicare's rate for the same code and kind of fee (hospital outpatient or lab for facility fees; Dallas doctor fee for professional fees) | The range the research brief asked for. Rates with no Medicare figure (for example hospital stays by DRG) get no label, never a guess. |
| Repeated amount | Same dollar amount listed more than once for the same service (code, modifier, billing class, setting, rate type) at the same provider (NPI + TIN) in one file | Exact copies only. Both rows stay; counts collapse them into one. |
| One amount, many codes | One identical dollar amount at the same provider and billing class for **10 or more different codes in 3 or more code families** (first three characters) | Catches the Aetna pattern ($3,682.00 for 20 codes at 12 Medical City NPIs) but not real flat fees for a few related codes (one price for 99213 and 99214). Stricter than the site's existing "flat case rate" flag (5+ codes), which is unchanged. |

$0 rates and percent-of-charges rates get none of these labels ($0 is already counted separately).

## Where the counts show

- **Monthly census report** (`reports/census/<month>.md`, section "Rates that may never be used"). The counting runs inside
  each insurer-file census on the rented machines, so it is **off until Betsy switches it on**
  (`IN_CENSUS` in `rate_labels.py`, or `RATE_LABELS=1`). On the biggest files it adds machine time.
- **Spread report** (`reports/spread/`), which shows every figure with and without the labeled rates.
