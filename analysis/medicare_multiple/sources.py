"""Every public CMS file the Medicare-multiple analysis reads: what it is, which year, where it comes from.

Nothing here needs a password. `cms.py fetch` downloads each file once into a cache folder and records its SHA-256, so
every benchmark in the report can be traced to the exact file it came from. To move to a newer CMS release, change the URL
and the year here; nothing else in the code names a file.

Year rule (Betsy, Nov 10, 2026): calendar-2026 rates for everything paid by the calendar year, federal fiscal year 2027
(Oct 1, 2026 - Sept 30, 2027) for hospital stays. Medicare-use volumes are the newest public year (2024 services).
"""

CMS = {
    # ---------- buckets
    "rbcs": dict(
        what="Restructured BETOS Classification System (RBCS): every HCPCS/CPT code -> category, subcategory, family",
        year="RBCS release RY2026 (taxonomy final, July 31, 2026; 2025 code assignments)",
        url="https://data.cms.gov/sites/default/files/2026-09/c35bb6b7-501d-4c27-ae29-514386dc8919/RBCS_Taxonomy_Final_RY26_20260731.csv"),
    # ---------- Medicare rates
    "pfs": dict(
        what="Physician Fee Schedule relative value units (RVU26D, October 2026 update), GPCIs by locality, conversion factor",
        year="CY2026 (non-qualifying-APM conversion factor $33.4009)",
        url="https://www.cms.gov/files/zip/rvu26d-updated-08-26-2026.zip"),
    "zip_locality": dict(
        what="ZIP code to Medicare carrier and pricing locality (also urban/rural/super-rural flag)",
        year="CY2026, October 2026 file",
        url="https://www.cms.gov/files/zip/zip-code-carrier-locality-file-updated-08-13-2026.zip"),
    "anes": dict(
        what="Anesthesia conversion factors by locality",
        year="CY2026 final rule (Nov 20, 2025)",
        url="https://www.cms.gov/files/zip/2026-anesthesia-conversion-factors.zip"),
    "opps": dict(
        what="Hospital outpatient (OPPS) Addendum B: payment rate and status indicator by HCPCS",
        year="CY2026, October 2026 update",
        url="https://www.cms.gov/files/zip/october-2026-opps-addendum-b.zip"),
    "asc": dict(
        what="Ambulatory surgical center (ASC) Addendum AA: payment rate and payment indicator by HCPCS",
        year="CY2026, October 2026 update",
        url="https://www.cms.gov/files/zip/october-2026-asc-approved-hcpcs-code-payment-rates.zip"),
    "clfs": dict(
        what="Clinical Laboratory Fee Schedule (national limitation amounts)",
        year="CY2026, quarter 4",
        url="https://www.cms.gov/files/zip/26clabq4.zip"),
    "asp": dict(
        what="Medicare Part B drug payment limits (ASP + 6%), per HCPCS billing unit",
        year="October 2026 quarter (from 2Q26 ASP data)",
        url="https://www.cms.gov/files/zip/october-2026-medicare-part-b-payment-limit-files-final.zip"),
    "dme": dict(
        what="DMEPOS fee schedule by state, non-rural and rural",
        year="CY2026, October 2026 (DME26-D)",
        url="https://www.cms.gov/files/zip/dme26-d.zip"),
    "ambulance": dict(
        what="Ambulance fee schedule public use file: base rates and mileage by locality, urban/rural/super-rural",
        year="CY2026",
        url="https://www.cms.gov/files/zip/cy-2026-file.zip"),
    "ipps_weights": dict(
        what="IPPS Table 5: MS-DRG relative weights (10% cap applied)",
        year="FY2027 final rule and correction notice (CMS-1849)",
        url="https://www.cms.gov/files/zip/fy2027-ipps-fr-table-5.zip"),
    "ipps_rates": dict(
        what="IPPS Tables 1A-1E: operating standardized amounts (66%/62% labor share) and capital federal rate",
        year="FY2027 final rule and correction notice (CMS-1849)",
        url="https://www.cms.gov/files/zip/fy2027-ipps-fr-table-1a-1e.zip"),
    "ipps_impact": dict(
        what="IPPS impact file: each hospital's wage index, GAF, teaching (IME) and DSH factors, uncompensated-care amount, "
             "value-based purchasing and readmission factors",
        year="FY2027 final rule and correction notice (September 2026)",
        url="https://www.cms.gov/files/zip/fy2027-ipps-fr-impact-file.zip"),
    "ipps_impact_2026": dict(
        what="IPPS impact file, FY2026: the wage index the CY2026 outpatient (OPPS) rates use (\"including all reclassifications\")",
        year="FY2026 final rule",
        url="https://www.cms.gov/files/zip/fy2026-ipps-fr-impact-file.zip"),
    "hgi": dict(
        what="Hospital General Information (CMS number -> ZIP code), for hospital-file doctor fees",
        year="July 22, 2026",
        url="https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1785189955/Hospital_General_Information.csv"),
    # ---------- Medicare use (weights for total (a))
    "vol_physician": dict(
        what="Medicare Physician & Other Practitioners - by Geography and Service (state rows: services by HCPCS, office vs facility)",
        year="2024 services (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-05/e534c74b-79b8-4892-8a95-5a17e2dfec9f/MUP_PHY_R26_P05_V10_D24_Geo.csv"),
    "vol_outpatient": dict(
        what="Medicare Outpatient Hospitals - by Geography and Service (state rows: services by APC and HCPCS)",
        year="2024 services (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-06/32491150-3e8f-4feb-95e4-3f66a355951a/MUP_OUT_RY26_P04_V10_DY24_Geo.csv"),
    "vol_inpatient": dict(
        what="Medicare Inpatient Hospitals - by Geography and Service (state rows: discharges by MS-DRG)",
        year="2024 discharges (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-04/4517a6a1-adeb-4345-9f3d-a95391a470db/MUP_INP_RY26_P03_V10_DY24_Geo.CSV"),
    "vol_dme": dict(
        what="Medicare Durable Medical Equipment, Devices & Supplies - by Geography and Service (state rows, by referring provider's state)",
        year="2024 services (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-07/d264f6fd-f327-4e54-9ab7-9132f1395b6b/mup_dme_ry26_p05_v10_dy24_geor.csv"),
    # ---------- evidence that a provider does a service (the "may be used" view): who billed Medicare for what
    "ev_physician": dict(
        what="Medicare Physician & Other Practitioners - by Provider and Service: which NPI billed Medicare for which HCPCS code "
             "(only the run's states, read page by page through CMS's data API; cells under 11 beneficiaries are left out by CMS)",
        year="2024 services (release RY2026)",
        url="https://data.cms.gov/data-api/v1/dataset/92396110-2aed-4d63-a6a2-5d6207d46a29/data",
        api=dict(state_field="Rndrng_Prvdr_State_Abrvtn", columns="Rndrng_NPI,Rndrng_Prvdr_State_Abrvtn,HCPCS_Cd,Place_Of_Srvc,Tot_Srvcs")),
    "ev_outpatient": dict(
        what="Medicare Outpatient Hospitals - by Provider and Service: which hospital (CCN) billed Medicare for which APC (payment group; "
             "the file has no HCPCS column, so a code counts when the hospital billed the APC CMS pays it in)",
        year="2024 services (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-06/794975f5-e335-4cbf-8e87-982c834a9639/MUP_OUT_RY26_P04_V10_DY24_Prov_Svc.csv"),
    "ev_inpatient": dict(
        what="Medicare Inpatient Hospitals - by Provider and Service: which hospital (CCN) billed Medicare for which MS-DRG",
        year="2024 discharges (release RY2026)",
        url="https://data.cms.gov/sites/default/files/2026-04/828defb5-c9e6-4442-8c1b-f27bc0799daf/MUP_INP_RY26_P03_V10_DY24_PrvSvc.CSV"),
}

# Third total (c): how privately insured people under 65 spend on care. Shares computed once from this public use file by
# meps.py and committed (meps_2024_under65_private.csv, with this file's SHA-256), so a run downloads nothing from AHRQ.
MEPS = dict(
    what="AHRQ Medical Expenditure Panel Survey, Household Component: 2024 Full Year Consolidated Data File (HC-256); "
         "total expenditures by event type, people under 65 with any private insurance (MEPS-HC summary table measure)",
    year="2024 (newest year in the MEPS-HC summary tables, Nov 2026)",
    url="https://meps.ahrq.gov/data_files/pufs/h256/h256dta.zip",
    sha256="653891861ec18574b07f576915e6f9e423263fc947610dc34e1bd176feff7b40")

# Published benchmarks for the sanity check (report only; never used in a calculation)
PUBLISHED = [
    dict(name="KFF literature review (2020): physician services", multiple=1.43, kind="professional",
         url="https://www.kff.org/health-costs/report/how-much-more-than-medicare-do-private-insurers-pay-a-review-of-the-literature/"),
    dict(name="KFF literature review (2020): hospital inpatient", multiple=1.89, kind="inpatient",
         url="https://www.kff.org/health-costs/report/how-much-more-than-medicare-do-private-insurers-pay-a-review-of-the-literature/"),
    dict(name="KFF literature review (2020): hospital outpatient", multiple=2.64, kind="outpatient",
         url="https://www.kff.org/health-costs/report/how-much-more-than-medicare-do-private-insurers-pay-a-review-of-the-literature/"),
    dict(name="RAND Round 5.1 (2024 report, 2022 claims): hospitals, national", multiple=2.54, kind="hospital",
         url="https://www.rand.org/pubs/research_reports/RRA1144-2-v2.html"),
    dict(name="RAND Round 5.1, Texas (2022 claims; as reported by the Texas Employers for Affordable Healthcare)", multiple=2.59,
         kind="hospital", url="https://txeahc.org/texas-employers-paid-hospitals-259-of-what-medicare-would-pay-per-rand-price-transparency-study/"),
]
