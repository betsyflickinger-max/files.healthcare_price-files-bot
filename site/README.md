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
Each published city is added to `site/cities.json` in the site (the list behind the "Area" picker on every Price Finder page).
After the monthly DFW refresh goes live, `orchestrate.py` rebuilds every city in that list with the new layout and the city's
newest finished build; a city that fails keeps its previous page and opens an issue. New Texas city builds themselves
(insurer files split by metro, then built on rented machines) are still started by hand.
Offline test: `python site/city_page.py el-paso --template PAGE --embed EMBED --rvu RVU_ZIP --med-all MED --t5 T5 [--quality Q]`.

Names: `plain_names_cpt.tsv` (plain-English names written for the most common codes), HCPCS Level II official
descriptions and MS-DRG titles (public CMS files), Medicare 2026 benchmarks (`build_med_all.py`, CMS fee schedules).
