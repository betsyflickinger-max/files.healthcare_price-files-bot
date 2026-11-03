# Care items: one master list of procedures, their bills, and the codes that price each bill

Started Nov 2, 2026 (Betsy: "is there a way to standardize all this?"). Draft; nothing on the site reads it yet.

## The problem
One procedure is priced under different code systems depending on **who bills** and **where**:

| Bill | Same-day care | Overnight hospital stay |
|---|---|---|
| Surgeon or doctor | CPT (professional) | CPT (professional) |
| Hospital or surgery center | CPT (institutional) | MS-DRG (per stay; some contracts pay per day) |
| Anesthesia | anesthesia CPT, base units + time | same |
| Pathology, imaging reads | their own CPT codes, only sometimes | same |

Insurer and hospital files price each bill on its own and never say which bills go together.

## The standard
- **`care_items.csv`**: one row per care item, in plain English (`knee-replacement`), with its main CPT code, usual
  hospital-stay DRG, usual setting, whether it's shoppable, and status.
- **`care_item_bills.csv`**: one row per bill x setting: which code system and code(s) price it, related codes
  (other DRGs with complications, the code family), how it's priced, when it applies, **how sure we are**, and the
  **source**.
- Confidence, strongest first: `in use on the site` / `standard rule` (e.g. a surgeon always bills the procedure's
  CPT) / `Medicare-backed` (CMS TEAM or BPCI Advanced puts the codes in one episode) / `hand-matched (needs a check)` /
  `missing`.
- Rules: bills are shown side by side, **never added into one price**; per-day hospital rates are never compared with
  per-stay prices; anesthesia is shown as its rate per unit plus base units, never a total; emergencies are marked not
  shoppable.

## What's in it (Nov 2)
- **111 care items, 277 bills**: the 5 same-day packages, 36 surgeries from the Oct crosswalk, and the rest of the 89
  featured procedures (labs, imaging, office visits, therapy, procedures, births, 2 hospital stays) by billing rule.
- Hospital-stay links: 16 of 40 Medicare-backed. Anesthesia: hand-matched for the surgeries; 19 procedures still
  "not paired yet".
- **DRG 460** (a featured hospital stay) is listed as deleted by AAPC: CMS split spinal fusion into 402, 426-430 and
  447-451 in FY2024. Marked "check: retired code"; insurer files may still use it.
- Copyright: 210 of the 257 coded bills use CPT codes (170 CPT + 40 anesthesia CPT), owned by the AMA; 40 MS-DRG and 7
  HCPCS Level II bills use free federal codes. This list uses our own plain-English names, never AMA descriptors
  (`source_crosswalk_oct.csv` had CMS's CPT short descriptors; removed Nov 2).

## crosswalk.csv and crosswalk_codes.csv: one code per cell (Nov 2; split fully Nov 3)
Every cell holds one code. Lists are numbered columns (`doctor_cpt_related_1`, `_2`, ...; `drg_other_1` + `drg_other_1_when`, ...), ranges are expanded (461-462 -> 461, 462), notes sit in their own `_when` column, and each anesthesia code has its own `_base_units` column. `crosswalk_codes.csv` has the same 441 codes one row per code (item, role, code system, code, when, base units). `care_item_bills.csv` has `code_1` / `code_2` per bill.

Earlier column list (before numbering):
One row per care item. Columns, by kind of code:
- `doctor_cpt`, `doctor_cpt_related` (other CPT codes for the same procedure, e.g. colonoscopy with biopsy)
- `facility_or_lab_cpt` (what the hospital, surgery center, imaging center or lab bills for same-day care)
- `facility_fee_hcpcs` (G0463: the facility fee hospital-owned clinics add to office visits)
- `drg_usual` (no complications), `drg_with_cc` (with complications), `drg_with_mcc` (with major complications),
  `drg_other` (other DRGs in a named situation, "code (when)")
- `icd10pcs_example` (how the hospital codes the procedure itself for an inpatient stay)
- `anesthesia_cpt`, `anesthesia_cpt_alternate`, `anesthesia_base_units`, `anesthesia_cpt_related`
- `pathology_cpt`, `other_related_cpt` (e.g. 36415 blood draw), `split_billing_modifiers` (TC / 26)
- `drg_confidence`, `anesthesia_confidence`, `notes`
`care_item_bills.csv` splits its related codes the same way (`related_cpt`, `drg_with_cc`, `drg_with_mcc`,
`drg_other`, `anesthesia_base_units`). Both are rebuilt by `build_care_items.py` (which runs `build_crosswalk.py`).

## APR-DRG (added Nov 3)
Some insurers price hospital stays with **APR-DRG** (All Patient Refined DRGs, owned by 3M/Solventum) instead of
Medicare's MS-DRG. In our insurer files (Oct-Nov census): about 12.3 million APR-DRG rows in 54 tables, mostly the
NY/CA/VA/DC/FL/WI, upper-Midwest and western areas, 138,703 in Texas; MS-DRG has about 528 million. Also seen, much
smaller: EAPG (2.2M rows, outpatient), APC (4.0M), AP-DRG (0.3M).
- `apr_drg_map.csv`: each hospital-stay item's usual APR-DRG and other situations, **matched by name** (38 of 40;
  AFib ablation and kidney-stone ureteroscopy not matched; neck fusion, TAVR, knee revision and ectopic pregnancy need
  a grouper check). Only a licensed APR-DRG grouper gives certainty.
- `apr_drg_names.csv`: the names used, from Pennsylvania DHS's APR-DRG v42 weights table (base DRGs up to 385) and
  Ohio Medicaid's APR-DRG v41 descriptions (400 and up).
- APR-DRG adds a severity level 1-4 (minor, moderate, major, extreme) to each base code; insurer files may write
  it as part of the code.
- In crosswalk.csv: `APR-DRG: usual` (+ name), `APR-DRG: other situation N` (+ when), severity, how sure. In
  care_item_bills.csv: an `APR-DRG` column on each hospital-stay row, beside its MS-DRG.

## Codes added Nov 3 (Betsy: "are there any medical codes missing?")
`extra_codes.py`, run inside the crosswalk build:
- **APC + OPPS status indicator + ASC payment indicator** (Medicare's outpatient facility groups; CMS OPPS Addendum B
  and ASC Addendum AA, July 2026, via the site's Medicare file; `medicare_codes.csv`, rebuilt by the "Care items -
  Medicare codes" workflow). 64 items have an APC.
- **Place of service (POS)**, CMS's two-digit setting codes (11 office, 19/22 hospital outpatient, 24 surgery center,
  21 inpatient, 81 independent lab, 10/02 telehealth). Insurer files carry these as `service_code`.
- **Revenue codes**, the hospital's department line on a UB-04 claim (0360 operating room, 0490 surgery center, 0710
  recovery, 0750 GI suite, 0481 cath lab, 0278 implants, 061x MRI, 035x CT, 0402 ultrasound, 040x mammography,
  030x lab, 0310 pathology, 0510 clinic, 0420 PT, 091x psychotherapy, 0720 delivery, 0120 room and board, 0170
  nursery). "Typical": hospitals vary. NUBC (AHA) owns the code set: on the lawyer question with CPT and APR-DRG.
- **Modifiers**: RT / LT / 50 (side), TC / 26 (split billing), 33 and PT (screening colonoscopy), 25 (separate visit).
- **Medicare's own HCPCS Level II versions**: G0121 / G0105 (screening colonoscopy), G0438 / G0439 (annual wellness
  visit, Medicare's stand-in for a routine physical).

## Still left out, on purpose
- **ICD-10-CM diagnosis codes**: they describe the patient, not the service, and change which DRG a stay falls in; a
  "typical diagnosis" per item needs a coder's review.
- **Drug (NDC), dental (CDT), post-acute (HIPPS, CMG) codes**: outside these procedures. In insurer files: CDT ~10.9B
  rows, NDC ~6.4B, HIPPS ~2.0B, CMG ~5.3M.
- **EAPG** (3M's outpatient groups, ~2.2M rows) and **AP-DRG** (an older DRG system, ~0.3M rows): proprietary and
  rare; can be added like APR-DRG if wanted.
- **Insurer-made codes** (CSTM-ALL ~37M rows, LOCAL ~1.8B): each insurer's own; no crosswalk exists.
- **Type of bill, condition and occurrence codes, implant C-codes**: claim-level or device-specific, not tied to one
  procedure.

## Insurer-made codes (added Nov 3; Betsy: "they have to tie back to at least something")
`insurers/insurer_codes.py` (workflow "Insurer-made codes") lists every code an insurer made up or labeled with a
non-standard type (LOCAL, CSTM-ALL, REV, Local, blank, ...) in every insurer table read: **69,099** codes.
`insurer_codes.csv` ties each back, one code per cell (`tied_code_1_type` / `tied_code_1` ... up to 4):
standard codes inside the insurer's code (Aetna "131/REV & 10E0XZZ/ICD10PX", BCBS MA "0360-28300"), the code
itself is a CPT/HCPCS code (with or without an insurer suffix), Medicare payment groups (SNF PDPM, home health
HIPPS), a DRG number, a service category with its usual revenue code, or a care item by name. **5,461 (8%) tie to
nothing**: mostly internal order catalogs from provider-owned plans (Group Health Cooperative of South Central
Wisconsin, Valley Health Plan, Health First, Hometown Health). Codes that tie to a care item also appear in
`crosswalk_codes.csv` (role "insurer-made code") and are counted in crosswalk.csv. Re-tie without reading storage:
`python insurers/insurer_codes.py --retie`.

## Next
2. Free federal groupings to sort items into families: AHRQ HCUP CCS Services and Procedures (CPT/HCPCS) and CCSR for
   ICD-10-PCS procedures.
3. Betsy's calls: a coder's review of the hand-matched rows (or launch Medicare-backed rows first), and the surgery
   page layout.
4. Then point `packages/build_packages.py` and the surgery pages at this list, so every page uses the codes the same way.

Rebuild: `python reference/care_items/build_care_items.py`
