# Following a plan's rates across the 2027 file change

Added Nov 7, 2026. Code: `insurers/plan_network_xwalk.py`. Test: `tests/test_plan_network_xwalk.py`.

## The change

The Transparency in Coverage final rule (CMS-9882-F, Oct 2026) changes insurer files about five months after it was
published, so about **March 2027**:

- **Today:** one in-network rate file per plan (or per group of plans). The table of contents (TOC) lists every plan and
  the files it uses. Files are updated **monthly**.
- **After:** one in-network rate file **per provider network**, updated **quarterly**, and the file names its network
  (name and identifier). Out-of-network files are combined by market.

So a plan's rates will move from "the files this plan's TOC entry points to" to "the file for the network this plan
uses". To follow one plan across that change, the bot needs, from every TOC it reads before and after, which networks
each plan uses, keyed by the TOC's own date.

## What the bot already had

| Piece | What it covers | Gap for the change |
|---|---|---|
| `insurers/catalog.py` (monthly, 5 insurers: Anthem, Cigna, UnitedHealthcare, Aetna, HCSC/BCBSTX) | For each TOC month (the folder is the TOC's own `last_updated_on`): every plan (sponsor, plan ID, ID type, market, issuer) and the set of networks (file keys without dates) it uses | Stored as one month's files per insurer, not one table you can follow a plan through. No place for a network identifier. |
| `plans/employer_plans.py` (Cigna, UHC) | One row per plan with its in-network file names | Same as above. |
| `dashboard/build_xwalk_us.py` | Network vs. network: providers two networks share | No plans at all. |

## What was added

`insurers/plan_network_xwalk.py build` turns each catalog month into one long table, **one row per plan × network ×
TOC date**, at R2 `bot/xwalk/plan_network/<insurer>/<toc month>.parquet`:

`insurer, toc_month, toc_last_updated_on, plan_id, plan_id_type, plan_market_type, plan_name, plan_sponsor_name,
issuer_name, network_key, network_description, network_state, network_id, network_name_in_file, source_key`

- A month already written is never overwritten (only with `--force`). Nothing is deleted.
- `network_id` and `network_name_in_file` are blank today. They fill in from the catalog as soon as the catalog records
  them from the new files.
- `follow --plan-id <id>` prints a plan's networks month by month, so the last per-plan file before the change and the
  first per-network file after it sit side by side under the same plan ID.

## Still to do when the new files appear (Betsy)

1. When CMS publishes the new TOC/in-network schema, teach `insurers/catalog.py` to keep the network identifier and name
   on each network row (`network_id`, `network_name`). The crosswalk already reads those two names.
2. The insurer-file census (06f) already keeps every top-level field of each in-network file in its `header`, so a
   network name or ID written at the top of the new files will show up there without code changes.
3. Plan IDs: employer plans use the EIN, marketplace plans the HIOS ID. Both stay the join key.
4. Run the crosswalk after each monthly catalog: **Actions → Plan to network crosswalk → Run workflow** (reads the
   catalog's employer files from R2; Anthem's is the largest). It is not chained to the catalog yet.
5. The spread report marks March 2027 as a series break for the same reason.
