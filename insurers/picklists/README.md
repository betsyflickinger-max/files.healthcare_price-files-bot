# Pick lists (proposed insurer networks per state, waiting for Betsy's OK)

2026-10/: the 33 states not yet started (Oct 21, 2026). One JSON per state (rows: insurer, network_label, index_url,
sample_file_url, parts, gb, plan_ids, status, note); OH/IN/KY are the regional insurers only (`*-locals.json`), with
Anthem and HCSC rows in catalog_anthem_hcsc.json (from insurers/catalog.py); multistate.json has Centene, Oscar,
Molina and Kaiser rows with a state field. Write-ups: claude/pick-lists-oct21.md and claude/pick-lists/*.md (project).
After an OK, turn a state's "Works" rows into insurers/networks_<area>.csv. insurers/toc_summary.py is the index reader
used to build these (streams any TiC index, groups files into networks, checks every part).
