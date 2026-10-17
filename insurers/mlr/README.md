# U.S. health insurer master list (CMS MLR, reporting year 2024)

Built 2026-10-16.

## Source
- CMS Medical Loss Ratio public use file, **reporting year 2024** (filed in 2025, released Sept 2025). This is the newest year on the CMS page as of 2026-10-16. No 2025 file is posted yet.
  - Page: https://www.cms.gov/marketplace/resources/data/medical-loss-ratio-data-systems-resources
  - File: https://www.cms.gov/files/zip/mlr-public-use-file-2024.zip (saved in `raw/mlr2024.zip`, unzipped in `raw/mlr2024/`)
- Tables used:
  - `MR_Submission_Template_Header.csv`: one row per filing, giving company name, NAIC company code, HIOS issuer ID, business state, `group_affiliation` (holding company) and `naic_group_code`. The 484 "Grand Total" rows (one per company, all states combined) are excluded.
  - `Part1_2_Summary_Data_Premium_Claims.csv`:
    - row `NUMBER_OF_COVERED_LIVES`, columns `cmm_individual_yearly`, `cmm_small_group_yearly`, `cmm_large_group_yearly`, `uninsured_plans_yearly`. "cmm" means comprehensive major medical, counted as of 12/31/2024.
    - row `TOTAL_DIRECT_PREMIUM_EARNED`, same columns, for premium.
  - `MLR_DataDictionaryPUF.pdf` gives the column meanings.
- Scripts are in `scripts/` (`build_step1.py`, then `build_master.py`, then `finalize.py`; `check_tic.py` checks the links).

## Outputs
- `master_insurers.csv`: **1,710 rows**, one per issuer × state filing. That covers 484 distinct reporting companies in 56 states and territories. 933 of the rows have more than 0 comprehensive lives.
  - Main columns: `parent_group, issuer_name, naic_code, state, individual_lives, small_group_lives, large_group_lives, total_lives, scope`.
  - Extra columns:
    - `hios_issuer_id`, and `parent_state_count` / `parent_states_filed`
    - `uninsured_lives`: self-funded lives that the issuer itself reported. This is partial; see Limits.
    - premium by market
    - the raw MLR group fields
    - `parent_source`: how the parent was assigned
    - `tic_landing_page`
  - CA Knox-Keene plans have no NAIC company code, so use `hios_issuer_id` for them.
- `parents.csv`: **200 parent groups**, ranked by total lives. Columns: states (with lives), states_filed, issuers, lives by market, premium, top 5 states, scope, `tic_landing_page`, `tic_note`.
- `total_lives` = individual + small group + large group comprehensive lives. Mini-med, expat, student health, government programs and "uninsured" lives are left out.

## How the parent group was assigned (`parent_source`)
1. `mlr_group_code` (1,357 rows): the NAIC group code from the filing. Every company with the same code is one parent. This merges, for example, Connecticut General into Cigna, Blue Care Network into BCBS Michigan, and Priority Health into Corewell.
2. `mlr_group_affiliation` (113 rows): a group name with no code. These are joined to the code that has the same name. One alias was added: "Medica" maps to Medica Grp.
3. `company_name_brand_rule` (66 rows): there is no group in the filing, and the company name contains a parent brand. The brands are Oscar, Ambetter, WellCare, Molina, Aetna, UnitedHealthcare/UHC, Cigna, Kaiser and Humana.
4. `manual_known_subsidiary` (4 rows):
   - Absolute Total Care, SilverSummit Healthplan, Western Sky Community Care and Pennsylvania Health & Wellness go to Centene.
   - Blue Cross of California goes to Elevance.
5. Otherwise the company is its own parent. These rows are matched on the normalized company name.
- WellCare Management Group (NAIC group 1199) and the Point32Health pieces (Harvard Pilgrim group 595, Tufts) stay separate because the filings give them separate group codes.

## Scope
- `scope` counts the **states where the parent reported more than 0 comprehensive lives**:
  - 20 or more states = `national`
  - 2 to 19 = `multi_state`
  - 1 = `single_state`
- States where a parent filed but had no comprehensive lives are counted in `parent_states_filed`. For example, Medical Mutual of Ohio files in 29 states but has lives in 2.
- Result: 7 national, 52 multi_state and 141 single_state parents.
- Only 4 large carriers count as national: UnitedHealth, Centene, CVS/Aetna and Cigna. AIG, Tokio Marine and Guardian also count, but each has tiny lives.
- Elevance comes out as multi_state, with lives in 14 states. That is its Blue footprint. Its non-Blue Wellpoint business shows up only where it files.

## tic_landing_page (Transparency in Coverage)
- Checked for the top ~45 parents. **42 parents have a link.** In the top 40, 36 have one.
- Each link was opened on 2026-10-16 (HTTP 200 and a page about TiC or MRFs), unless `tic_note` says otherwise. The exceptions are:
  - Aetna and Humana: taken from the project's `insurer_tic_index.csv`.
  - BCBS MA, Medica, EmblemHealth and BCBS MN: confirmed only by web-search title, because the site blocked the fetch or has a TLS problem.
- **Not found, left blank:**
  - Regence (Cambia)
  - Molina
  - BCBS Arizona
  - BCBS Louisiana
  - Gundersen/Quartz
- Landing pages are not file indexes. Many are JavaScript-only or search portals.

## Limits
- **Fully insured only.** MLR covers insured comprehensive business. Self-funded (ASO) employer lives are **not** included, and that is most large-employer membership. `uninsured_lives` is self-reported, inconsistent and incomplete, so don't treat it as an ASO count. HCSC, the Blues, UHC, Aetna and Cigna look much smaller here than their real commercial footprint.
- **No Medicare Advantage, Medicaid managed care or FEHB**, in the lives totals. MLR files them separately or not at all. This is why Humana shows only 320 lives, and why Molina and Centene look small next to their total membership.
- **Blue plans are separate companies.** Each Blue licensee appears under its own parent unless an NAIC group joins them. Examples of groups that do join them are HCSC (TX/IL/OK/NM/MT), Highmark, Regence/Cambia and Elevance's 14 Anthem states. BlueCard national accounts are counted under the plan that writes the policy.
- **Group names come from the filers.** Holding-company names in the MLR are free text. The clean display names in `parent_group` were added for readability. The original values are in `mlr_group_affiliation_raw`.
- **Point in time.** Covered lives are as of 12/31/2024. Mergers and market exits since then are not reflected. For example, Cigna and Aetna have left some ACA markets.
- Some covered-lives values are fractional in the source, such as Providence at 167,631.66. They are rounded to whole numbers.
