# Texas ZIP → metro area

`tx_zip_metro.csv` (made by `tx_zip_metro.py`, Oct 12, 2026) places each "rest of Texas" ZIP area (Texas ZIPs outside DFW 750-753/760-762,
Houston 770-775, San Antonio 780-782, Austin 786-787 and El Paso 798-799) in one of 18 metro-area Price Finder pages, or in
`small-towns`. Each Census ZIP area goes to the county that holds most of its land, then to that county's metropolitan area.
Micropolitan areas, counties in no metro area, and provider ZIPs that are not Census ZIP areas (PO boxes) go to `small-towns`.
Read by `site/tx_split.py` and `site/orchestrate_tx.py`.

Sources, downloaded Oct 12, 2026:
- U.S. Census Bureau, 2020 ZCTA-to-county relationship file:
  https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt
- U.S. Census Bureau, CBSA delineation file, list 1, July 2023 (OMB Bulletin 23-01), from
  https://www.census.gov/geographies/reference-files/time-series/demo/metro-micro/delineation-files.html :
  https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx
