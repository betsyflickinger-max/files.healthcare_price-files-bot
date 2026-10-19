# Medicare anesthesia figures (CY 2026)

- `anes_cf_2026.csv`: CMS "Locality-Adjusted Anesthesia Conversion Factors as a result of the CY 2026 Final Rule" (updated 11/20/2025),
  column "Non-Qualifying APM National Anes CF (with 2.5% statutory increase) of 20.49754".
  Source: https://www.cms.gov/files/zip/2026-anesthesia-conversion-factors.zip (CMS Anesthesiologists Center, posted 12/29/2025).
- `anes_base_units.csv`: CMS CY 2022 anesthesia base units by CPT code. CMS: "The anesthesia base units are unchanged for CY 2026."
  Source: https://www.cms.gov/files/zip/2022-anesthesia-base-units-cpt-code.zip
- Medicare pays anesthesia as (base units + time units) x the locality's conversion factor; a time unit is 15 minutes.
  The site shows the per-unit rate and the base-unit amount only. It never assumes a case length.
