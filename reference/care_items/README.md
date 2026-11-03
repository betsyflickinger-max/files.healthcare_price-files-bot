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

## Next
2. Free federal groupings to sort items into families: AHRQ HCUP CCS Services and Procedures (CPT/HCPCS) and CCSR for
   ICD-10-PCS procedures.
3. Betsy's calls: a coder's review of the hand-matched rows (or launch Medicare-backed rows first), and the surgery
   page layout.
4. Then point `packages/build_packages.py` and the surgery pages at this list, so every page uses the codes the same way.

Rebuild: `python reference/care_items/build_care_items.py`
