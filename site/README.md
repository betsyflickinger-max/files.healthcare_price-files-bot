# Monthly website refresh

`.github/workflows/site-build.yml` runs `site/orchestrate.py` every 6 hours. Once a month (from the 8th, after the
insurer bot has read the month's new files) it rebuilds the Price Finder and deploys it to the private preview site.

1. **build1** (rented machines): `every_code.py` reads every DFW insurer table (`data/full/rates/`) into one file per
   billing code; `hosp_every.py` reads only the DFW hospital price files that changed since last month.
2. **build2** (one machine): `h2_build.py` turns the hospital lines into one file per code.
3. **publish** (GitHub runner): `merge_page.py` + `apply_names_med.py` update the page, `check_build.py` compares it
   with the live page (networks, codes, providers, rate lines, hospital files must not drop), then R2
   `site/every/CURRENT` is pointed at the new build and the site is deployed with wrangler.
   Any failed check → nothing goes live and an issue opens.
   After a build is live, `cleanup()` deletes only build leftovers (older `site/every/<build>/` beyond the live one and the one before it, and `work/every/<build>/` scratch). It never touches `raw/`, `data/`, `work/retired/`, `site/deploy/` or `site/builds/`.

Needs the `CLOUDFLARE_API_TOKEN` secret to deploy (without it the build stops at "ready" and opens an issue).
The site's files are kept in R2 (`site/deploy/current.tgz`), not in this public repo.
State: R2 `site/builds/<YYYY-MM>/state.json`. Start early: run the workflow by hand with "force".

## Texas city pages

`.github/workflows/city-page.yml` (run by hand; pick a city) runs `city_page.py`. It takes the live DFW page as the layout,
puts in the city's finished insurer build (newest R2 `site/every-tx/<city>/<build>/embed.json`), sets the Medicare doctor
fees to the city's Medicare locality (and first checks that the same formula reproduces every Dallas figure on the DFW page),
and changes the words that name DFW. Hospital price files, posted cash prices, quality ratings and the map are DFW only for
now; the city page says "not on the El Paso page yet" rather than "none found". Any expected wording that is missing stops
the build, so a half-edited page never goes out. The page goes to `/<city>/price-finder/` on the preview site with a small
function that serves the city's per-code files. A copy is kept in R2 `site/deploy/cities/<city>/price-finder.html`.
Each city page gets its own map: `geo_build.py` places the city's providers (cached per build at
`site/every-tx/<city>/<build>/geo.json`; the Census address cache is shared, so only new addresses are looked up) and
`basemap_build.py` draws the background from Census TIGERweb (cached at `site/deploy/cities/<city>/basemap.json`). If either
fails, the page goes out without its Map button.
Each published city is added to `site/cities.json` in the site (the list behind the "Area" picker on every Price Finder page).
After the monthly DFW refresh goes live, `orchestrate.py` rebuilds every city in that list with the new layout and the city's
newest finished build; a city that fails keeps its previous page and opens an issue. 
## Texas city builds (monthly, automatic from November 2026)

`site/orchestrate_tx.py` runs right after `orchestrate.py` in the same workflow. One build per month (`tx-YYYY-MM`, state in
R2 `site/builds/tx-YYYY-MM/state.json`): from the 8th, once the month's DFW refresh is live and no Texas insurer file is still
being read, it splits every new Texas insurer table by metro (`tx_split.py`, up to 4 machines), moves split tables whose insurer
table was retired to `work/retired/<month>/tx_metro/`, rebuilds each metro's provider list from `data/scope/tx_npis_all.parquet`,
then runs `every_code.py` per metro (Houston 5 machines, San Antonio 2, Austin 2, El Paso 1, each metro area 1-3 by size;
8 vCPU / 32 GB) into `site/every-tx/<metro>/<YYYY-MM>/`. When every metro has its `embed.json`, it publishes the pages with
`city_page.py --deploy`. Run the workflow by hand with "force_tx" to start early. October 2026 was built by hand.

Rest of Texas (Oct 12, 2026): instead of one "rest" build, every Texas ZIP outside the five big areas goes to one of 18
Census metro areas (McAllen, Killeen–Temple, Brownsville–Harlingen, Corpus Christi, Beaumont–Port Arthur, Lubbock, Waco,
Longview, College Station–Bryan, Amarillo, Tyler, Abilene, Midland, Odessa, Wichita Falls, Texarkana, San Angelo, Victoria)
or to `small-towns`, by `reference/geo/tx_zip_metro.csv` (Census ZIP → county → metro; sources in `reference/geo/README.md`).
Each is its own page, built like the cities. `tx_split.py SRC=rest` re-splits the October `data/tx/metro/rest/` tables once.
In October 2026, "force_tx" builds only these 19 pages (build `tx-2026-10-metros`).
Offline test: `python site/city_page.py el-paso --template PAGE --embed EMBED --rvu RVU_ZIP --med-all MED --t5 T5 [--quality Q]`.

Names: `plain_names_cpt.tsv` (plain-English names written for the most common codes), HCPCS Level II official
descriptions and MS-DRG titles (public CMS files), Medicare 2026 benchmarks (`build_med_all.py`, CMS fee schedules).

## Procedure pages (/costs/)

`.github/workflows/procedure-pages.yml` (daily, or by hand with "force") runs `procedure_pages.py deploy`. For every area in
`site/cities.json` and every featured procedure in `codes89.csv` it writes a static page at `/costs/<area>/<procedure>/`
(DFW's area slug is `dallas-fort-worth`), plus `/costs/<area>/` (every procedure in that area), `/costs/<procedure>/` (one
procedure across every area), `/costs/` and `/costs/sitemap.xml`. It also writes the national front-page section of the
homepage (between `<!-- NATIONAL:START -->` and `<!-- NATIONAL:END -->`; the receipts, chargemaster and house-rules views are
left alone). Figures come from the same data as each area's Price Finder: the page's embedded data and its per-code `pf/t`
and `pf/h` files in R2 (prefixes read from the area's own Pages Functions). Lowest and highest are real published figures,
each linked to its file; $0 lines, percent-of-charges rates and rates flagged as unusually low or unusually high (over 20x the median, likely placeholders) are counted, not used.
It rebuilds only areas whose Price Finder page changed since the last run (fingerprints and summaries in R2
`site/deploy/costs_state.json`), and everything on the first run of each month. URLs never change once made:
`site/procedure_slugs.csv`. Pages follow the homepage's robots setting (noindex while the site is a private preview).
Offline test: `python site/procedure_pages.py build DIR --offline DEV --codes 45378,73721` with DEV/<area>/{t,h}/<code>.txt.
Search: titles follow how people search ("Colonoscopy Cost in Houston: $427 to $11,500 (2026)") using the everyday names in
`SEARCH_NAMES`; each page has a "What stands out" list and a Q&A section written from its own figures (FAQPage data), a byline
and /about/ page (`AUTHOR`), a CSV of every figure behind the page (`prices.csv`, lists up to 5,000 lines), and Dataset data.
Pages with fewer than 5 providers and fewer than 3 cash prices carry noindex and stay out of the sitemap until they have more.
Each page also lists the 10 highest rates and the biggest gap inside one network ("same procedure, same network: $4,157 at A,
$232 at B"). Ghost rates (contract rates listed for places that don't do the service) are kept out of the figures by kind of
place plus a name test that can only exclude (rehab, psychiatric, nursing; single-specialty names like an eye center for a
colonoscopy; scans and labs count clinics only when the name says imaging or lab); the Price Finder still lists everything.
Placeholder-looking rates (over 20x the median) are listed by insurer network, with example lines and file links, in the
Price File Watch private notes (functions/api/watch-notes.js, between PLACEHOLDERS markers), rebuilt each run, for review
before anything is made public.
