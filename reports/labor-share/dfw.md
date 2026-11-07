# Labor share of hospital operating costs: Dallas-Fort Worth

Built 2026-11-07 by `costreports/labor_share.py` from CMS Medicare cost reports (HCRIS, form 2552-10), files for federal fiscal years 2022, 2023, 2024, 2025. Labor share = (salaries + employee benefits + direct patient care contract labor) ÷ total operating expenses, all from the same report. Every number is copied from the report; a blank stays blank.

Where each number comes from: salaries, Worksheet A line 200 column 1; benefits and contract labor, Worksheet S-3 Part V line 1 columns 2 and 1; total operating expenses, Worksheet G-3 line 4. Contract labor here is direct patient care only (management contracts are not in Part V).

**What this is not.** A cost report is the hospital's own accounting for Medicare. It shows how its costs split, not what any patient or insurer paid. Hospital systems can book shared costs (like a central office) in different ways.

The newest fiscal-year file keeps filling in as hospitals file (reports are due five months after a period ends).

Latest report for each period shown; every report (including earlier versions) is in `reports/labor-share/dfw.csv`.

"Salaries only" is shown for hospitals whose report has no Part V (benefits and contract labor); it is not a labor share.

| Hospital | CCN | Type | Period | Salaries | Benefits | Contract labor | Operating costs | Labor share | Salaries only | Report status |
|---|---|---|---|---|---|---|---|---|---|---|
| ACCEL REHABILITATION HOSPITAL PLANO | 673055 | rehabilitation | 01/01/2022–12/31/2022 | $4.3M | — | — | $13.3M | — | 32.2% | settled without audit |
| ACCEL REHABILITATION HOSPITAL PLANO | 673055 | rehabilitation | 01/01/2023–12/31/2023 | $4.5M | — | — | $13.0M | — | 34.3% | settled without audit |
| ACCEL REHABILITATION HOSPITAL PLANO | 673055 | rehabilitation | 01/01/2024–12/31/2024 | $4.5M | — | — | $13.1M | — | 33.9% | as submitted |
| ACCEL REHABILITATION HOSPITAL PLANO | 673055 | rehabilitation | 01/01/2025–12/31/2025 | $4.4M | — | — | $13.1M | — | 33.5% | as submitted |
| ADHC | 670321 | short-term acute | 01/01/2024–12/31/2024 | $7.7M | — | — | $25.3M | — | 30.3% | settled without audit |
| ADHC | 670321 | short-term acute | 01/01/2025–12/31/2025 | $10.4M | — | — | $26.5M | — | 39.1% | settled without audit |
| ADHC | 670321 | short-term acute | 07/18/2023–12/31/2023 | $3.5M | — | — | $18.0M | — | 19.4% | settled without audit |
| ATRIUM MEDICAL CENTER | 452111 | long-term care | 12/01/2021–11/30/2022 | $9.2M | — | — | $51.9M | — | 17.8% | as submitted |
| ATRIUM MEDICAL CENTER | 452111 | long-term care | 12/01/2022–11/30/2023 | $8.9M | — | — | $49.9M | — | 17.9% | settled without audit |
| ATRIUM MEDICAL CENTER | 452111 | long-term care | 12/01/2023–10/31/2024 | $5.1M | — | — | $27.6M | — | 18.7% | as submitted |
| BAYLOR EMERGENCY MEDICAL CENTER | 670062 | short-term acute | 01/01/2022–12/31/2022 | $9.9M | $1.8M | $2.7M | $41.1M | 35.3% |  | settled without audit |
| BAYLOR EMERGENCY MEDICAL CENTER | 670062 | short-term acute | 01/01/2023–12/31/2023 | $11.7M | $2.3M | $1.2M | $45.1M | 33.8% |  | settled without audit |
| BAYLOR EMERGENCY MEDICAL CENTER | 670062 | short-term acute | 01/01/2024–12/31/2024 | $12.2M | $2.6M | $0.3M | $45.6M | 33.2% |  | settled without audit |
| BAYLOR EMERGENCY MEDICAL CENTER | 670062 | short-term acute | 01/01/2025–12/31/2025 | $12.9M | $2.6M | $0.3M | $55.0M | 28.7% |  | settled without audit |
| BAYLOR HEART AND VASCULAR HOSPITAL | 450851 | short-term acute | 07/01/2022–06/30/2023 | $48.4M | $10.9M | $0.9M | $178.4M | 33.8% |  | settled without audit |
| BAYLOR HEART AND VASCULAR HOSPITAL | 450851 | short-term acute | 07/01/2023–06/30/2024 | $52.3M | $11.3M | $1.6M | $197.1M | 33.0% |  | settled without audit |
| BAYLOR HEART AND VASCULAR HOSPITAL | 450851 | short-term acute | 07/01/2024–01/31/2025 | $32.8M | $7.0M | $1.0M | $127.2M | 32.0% |  | as submitted |
| BAYLOR INSTITUTE FOR REHABILITATION | 453036 | rehabilitation | 07/01/2022–06/30/2023 | $68.5M | — | — | $170.1M | — | 40.3% | reopened |
| BAYLOR INSTITUTE FOR REHABILITATION | 673046 | rehabilitation | 07/01/2022–06/30/2023 | $18.3M | — | — | $30.4M | — | 60.3% | settled without audit |
| BAYLOR INSTITUTE FOR REHABILITATION | 673046 | rehabilitation | 07/01/2023–06/30/2024 | $18.5M | — | — | $32.7M | — | 56.5% | settled without audit |
| BAYLOR INSTITUTE FOR REHABILITATION | 453036 | rehabilitation | 07/01/2023–06/30/2024 | $69.4M | — | — | $187.8M | — | 37.0% | reopened |
| BAYLOR INSTITUTE FOR REHABILITATION | 453036 | rehabilitation | 07/01/2024–06/30/2025 | $70.4M | — | — | $200.1M | — | 35.2% | amended |
| BAYLOR INSTITUTE FOR REHABILITATION | 673046 | rehabilitation | 07/01/2024–06/30/2025 | $18.9M | — | — | $33.5M | — | 56.6% | as submitted |
| BAYLOR MEDICAL CENTER AT FRISCO | 450853 | short-term acute | 01/01/2022–12/31/2022 | $42.1M | $9.9M | $1.0M | $143.7M | 36.9% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT FRISCO | 450853 | short-term acute | 01/01/2023–12/31/2023 | $42.8M | $9.6M | $0.7M | $147.4M | 36.0% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT FRISCO | 450853 | short-term acute | 01/01/2024–12/31/2024 | $44.1M | $9.4M | $0.0M | $140.7M | 38.0% |  | as submitted |
| BAYLOR MEDICAL CENTER AT FRISCO | 450853 | short-term acute | 01/01/2025–12/31/2025 | $45.2M | $10.2M | $0.2M | $143.8M | 38.6% |  | as submitted |
| BAYLOR MEDICAL CENTER AT TROPHY CLUB | 450883 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $13.6M | $3.2M | $0.4M | $61.4M | 28.0% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT TROPHY CLUB | 450883 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $12.8M | $2.9M | $0.8M | $56.2M | 29.3% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT TROPHY CLUB | 450883 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $13.4M | $2.8M | $0.5M | $58.5M | 28.6% |  | as submitted |
| BAYLOR MEDICAL CENTER AT TROPHY CLUB | 450883 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $13.6M | $2.9M | $1.0M | $62.7M | 27.8% |  | as submitted |
| BAYLOR MEDICAL CENTER AT UPTOWN | 450422 | short-term acute | 01/01/2022–12/31/2022 | $14.5M | $3.1M | $1.2M | $59.8M | 31.5% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT UPTOWN | 450422 | short-term acute | 01/01/2023–12/31/2023 | $14.3M | $3.0M | $0.2M | $61.8M | 28.2% |  | settled without audit |
| BAYLOR MEDICAL CENTER AT UPTOWN | 450422 | short-term acute | 01/01/2024–12/31/2024 | $14.1M | $2.9M | $0.3M | $62.5M | 27.6% |  | as submitted |
| BAYLOR MEDICAL CENTER AT UPTOWN | 450422 | short-term acute | 01/01/2025–12/31/2025 | $14.6M | $3.0M | $1.6M | $67.1M | 28.6% |  | as submitted |
| BAYLOR MEDICAL CENTER-GRAPEVINE | 450563 | short-term acute | 07/01/2022–06/30/2023 | $103.5M | $22.5M | $7.9M | $298.4M | 44.9% |  | as submitted |
| BAYLOR MEDICAL CENTER-GRAPEVINE | 450563 | short-term acute | 07/01/2023–06/30/2024 | $108.0M | $23.4M | $5.1M | $312.4M | 43.7% |  | as submitted |
| BAYLOR MEDICAL CENTER-GRAPEVINE | 450563 | short-term acute | 07/01/2024–06/30/2025 | $111.8M | $23.0M | $4.5M | $329.0M | 42.3% |  | as submitted |
| BAYLOR ORTHOPEDIC AND SPINE HOSPITAL | 670067 | short-term acute | 01/01/2022–12/31/2022 | $15.9M | $3.6M | $0.0M | $80.5M | 24.2% |  | settled without audit |
| BAYLOR ORTHOPEDIC AND SPINE HOSPITAL | 670067 | short-term acute | 01/01/2023–12/31/2023 | $16.4M | $3.5M | $0.4M | $80.4M | 25.3% |  | settled without audit |
| BAYLOR ORTHOPEDIC AND SPINE HOSPITAL | 670067 | short-term acute | 01/01/2024–12/31/2024 | $18.0M | $3.8M | $0.3M | $84.2M | 26.3% |  | as submitted |
| BAYLOR ORTHOPEDIC AND SPINE HOSPITAL | 670067 | short-term acute | 01/01/2025–12/31/2025 | $17.7M | $4.0M | $0.4M | $88.8M | 24.9% |  | as submitted |
| BAYLOR S&W ALL SAINTS MEDICAL CENTER | 450137 | short-term acute | 10/01/2021–09/30/2022 | $170.3M | $36.8M | $16.3M | $497.9M | 44.9% |  | amended |
| BAYLOR S&W ALL SAINTS MEDICAL CENTER | 450137 | short-term acute | 10/01/2022–09/30/2023 | $177.4M | $40.4M | $2.4M | $522.4M | 42.2% |  | as submitted |
| BAYLOR S&W ALL SAINTS MEDICAL CENTER | 450137 | short-term acute | 10/01/2023–09/30/2024 | $182.2M | $41.6M | $0.7M | $547.2M | 41.0% |  | as submitted |
| BAYLOR S&W ALL SAINTS MEDICAL CENTER | 450137 | short-term acute | 10/01/2024–09/30/2025 | $194.9M | $40.7M | $1.1M | $569.6M | 41.6% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - IRVING | 450079 | short-term acute | 07/01/2022–06/30/2023 | $87.2M | $19.1M | $13.3M | $276.1M | 43.3% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - IRVING | 450079 | short-term acute | 07/01/2023–06/30/2024 | $97.0M | $21.0M | $6.8M | $298.2M | 41.8% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - IRVING | 450079 | short-term acute | 07/01/2024–06/30/2025 | $100.7M | $20.8M | $7.1M | $309.0M | 41.6% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - PLANO | 450890 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $70.8M | $15.1M | $6.3M | $232.8M | 39.6% |  | amended |
| BAYLOR S&W MEDICAL CENTER - PLANO | 450890 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $73.4M | $16.5M | $0.9M | $247.7M | 36.6% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - PLANO | 450890 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $77.0M | $16.2M | $3.2M | $263.4M | 36.6% |  | as submitted |
| BAYLOR S&W MEDICAL CENTER - PLANO | 450890 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $81.2M | $16.3M | $4.0M | $281.1M | 36.1% |  | as submitted |
| BAYLOR SCOTT & WHITE MC- LAKE POINTE | 450742 | short-term acute | 06/01/2022–05/31/2023 | $76.5M | $15.3M | $6.2M | $220.1M | 44.5% |  | as submitted |
| BAYLOR SCOTT & WHITE MC- LAKE POINTE | 450742 | short-term acute | 06/01/2023–05/31/2024 | $84.3M | $16.8M | $1.6M | $237.8M | 43.2% |  | as submitted |
| BAYLOR SCOTT & WHITE MC- LAKE POINTE | 450742 | short-term acute | 06/01/2024–05/31/2025 | $88.5M | $17.0M | $1.4M | $243.1M | 44.0% |  | as submitted |
| BAYLOR SCOTT & WHITE MEDICAL CENTER | 670346 | short-term acute | 08/25/2025–03/31/2026 | $20.4M | $3.4M | $0.5M | $79.0M | 30.7% |  | as submitted |
| BAYLOR SCOTT & WHITE THE HEART HOSPI | 670347 | short-term acute | 12/01/2024–11/30/2025 | $3.5M | $0.7M | $0.0M* | $10.6M | 39.0% |  | settled without audit |
| BAYLOR SCOTT AND WHITE MC AT SUNNYVA | 670060 | short-term acute | 01/01/2022–12/31/2022 | $24.3M | $6.1M | $8.2M | $90.9M | 42.5% |  | settled without audit |
| BAYLOR SCOTT AND WHITE MC AT SUNNYVA | 670060 | short-term acute | 01/01/2023–12/31/2023 | $24.3M | $5.8M | $4.8M | $86.2M | 40.6% |  | settled without audit |
| BAYLOR SCOTT AND WHITE MC AT SUNNYVA | 670060 | short-term acute | 01/01/2024–12/31/2024 | $29.3M | $6.8M | $3.8M | $97.6M | 40.9% |  | as submitted |
| BAYLOR SCOTT AND WHITE MC AT SUNNYVA | 670060 | short-term acute | 01/01/2025–12/31/2025 | $30.5M | $7.2M | $4.3M | $103.6M | 40.6% |  | as submitted |
| BAYLOR SURGICAL HOSPITAL AT FORT WOR | 450880 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $23.1M | $5.2M | $0.1M | $115.9M | 24.5% |  | settled without audit |
| BAYLOR SURGICAL HOSPITAL AT FORT WOR | 450880 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $21.1M | $4.3M | $0.0M* | $100.7M | 25.2% |  | settled without audit |
| BAYLOR SURGICAL HOSPITAL AT FORT WOR | 450880 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $20.5M | $4.2M | $0.0M* | $97.7M | 25.3% |  | as submitted |
| BAYLOR SURGICAL HOSPITAL AT FORT WOR | 450880 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $19.4M | $4.2M | $0.5M | $95.9M | 25.2% |  | as submitted |
| BAYLOR SURGICAL HOSPITAL LAS COLINAS | 450874 | short-term acute | 01/01/2022–12/31/2022 | $11.8M | $2.6M | $0.5M | $53.3M | 28.1% |  | settled without audit |
| BAYLOR SURGICAL HOSPITAL LAS COLINAS | 450874 | short-term acute | 01/01/2023–12/31/2023 | $11.9M | $2.3M | $1.4M | $53.4M | 29.3% |  | settled without audit |
| BAYLOR SURGICAL HOSPITAL LAS COLINAS | 450874 | short-term acute | 01/01/2024–12/31/2024 | $12.1M | $2.4M | $0.2M | $49.0M | 30.1% |  | as submitted |
| BAYLOR SURGICAL HOSPITAL LAS COLINAS | 450874 | short-term acute | 01/01/2025–12/31/2025 | $12.1M | $2.4M | $0.3M | $49.9M | 29.8% |  | as submitted |
| BAYLOR SW MEDICAL CENTER- WAXAHACHIE | 450372 | short-term acute | 07/01/2022–06/30/2023 | $68.6M | $15.8M | $1.3M | $230.0M | 37.3% |  | as submitted |
| BAYLOR SW MEDICAL CENTER- WAXAHACHIE | 450372 | short-term acute | 07/01/2023–06/30/2024 | $74.1M | $16.8M | $2.4M | $254.8M | 36.6% |  | as submitted |
| BAYLOR SW MEDICAL CENTER- WAXAHACHIE | 450372 | short-term acute | 07/01/2024–06/30/2025 | $80.1M | $17.0M | $2.7M | $271.3M | 36.8% |  | as submitted |
| BAYLOR UNIVERSITY MEDICAL CTR | 450021 | short-term acute | 07/01/2022–06/30/2023 | $381.9M | $89.6M | $19.6M | $1,253.7M | 39.2% |  | as submitted |
| BAYLOR UNIVERSITY MEDICAL CTR | 450021 | short-term acute | 07/01/2023–06/30/2024 | $418.1M | $96.3M | $10.7M | $1,349.3M | 38.9% |  | as submitted |
| BAYLOR UNIVERSITY MEDICAL CTR | 450021 | short-term acute | 07/01/2024–06/30/2025 | $440.4M | $95.4M | $11.6M | $1,422.7M | 38.5% |  | as submitted |
| BEMC BURLESON | 670107 | short-term acute | 01/01/2022–12/31/2022 | $6.7M | $1.3M | $2.4M | $31.2M | 33.4% |  | settled without audit |
| BEMC BURLESON | 670107 | short-term acute | 01/01/2023–12/31/2023 | $7.7M | $1.5M | $1.3M | $31.5M | 33.3% |  | settled without audit |
| BEMC BURLESON | 670107 | short-term acute | 01/01/2024–12/31/2024 | $8.3M | $1.8M | $0.8M | $34.2M | 31.6% |  | settled without audit |
| BEMC BURLESON | 670107 | short-term acute | 01/01/2025–12/31/2025 | $8.7M | $1.8M | $0.6M | $36.7M | 30.5% |  | settled without audit |
| BIR AT FORT WORTH | 673035 | rehabilitation | 01/01/2022–12/31/2022 | $11.6M | — | — | $19.9M | — | 58.5% | settled without audit |
| BIR AT FORT WORTH | 673035 | rehabilitation | 01/01/2023–12/31/2023 | $12.7M | — | — | $23.0M | — | 55.2% | settled without audit |
| BIR AT FORT WORTH | 673035 | rehabilitation | 01/01/2024–12/31/2024 | $13.5M | — | — | $23.8M | — | 56.8% | as submitted |
| BIR AT FORT WORTH | 673035 | rehabilitation | 01/01/2025–12/31/2025 | $13.8M | — | — | $25.4M | — | 54.1% | as submitted |
| CARROLLTON REGIONAL MEDICAL CENTER | 450730 | short-term acute | 01/01/2022–12/31/2022 | $29.5M | $6.5M | $4.9M | $83.2M | 49.2% |  | settled without audit |
| CARROLLTON REGIONAL MEDICAL CENTER | 450730 | short-term acute | 01/01/2023–12/31/2023 | $30.8M | — | — | $86.6M | — | 35.6% | settled without audit |
| CARROLLTON REGIONAL MEDICAL CENTER | 450730 | short-term acute | 01/01/2024–12/31/2024 | $32.9M | — | — | $87.8M | — | 37.5% | as submitted |
| CARROLLTON REGIONAL MEDICAL CENTER | 450730 | short-term acute | 01/01/2025–12/31/2025 | $34.4M | $7.8M | $0.3M | $90.0M | 47.3% |  | amended |
| CARROLLTON SPRINGS | 454119 | psychiatric | 01/01/2022–12/31/2022 | $15.2M | — | — | $31.6M | — | 48.1% | settled without audit |
| CARROLLTON SPRINGS | 454119 | psychiatric | 01/01/2023–12/31/2023 | $14.3M | — | — | $28.6M | — | 50.0% | settled without audit |
| CARROLLTON SPRINGS | 454119 | psychiatric | 01/01/2024–06/30/2024 | $8.4M | — | — | $17.7M | — | 47.3% | settled without audit |
| CARROLLTON SPRINGS | 454119 | psychiatric | 07/01/2024–06/30/2025 | $24.5M | — | — | $47.0M | — | 52.3% | settled without audit |
| CENTENNIAL MEDICAL CENTER | 450885 | other (CCN 08xx range) | 04/01/2022–03/31/2023 | $39.8M | $8.1M | $1.7M | $115.0M | 43.2% |  | settled without audit |
| CENTENNIAL MEDICAL CENTER | 450885 | other (CCN 08xx range) | 04/01/2023–03/31/2024 | $43.7M | $9.3M | $0.8M | $124.2M | 43.3% |  | settled without audit |
| CENTENNIAL MEDICAL CENTER | 450885 | other (CCN 08xx range) | 04/01/2024–03/31/2025 | $47.5M | $9.1M | $1.3M | $135.3M | 42.8% |  | as submitted |
| CENTENNIAL MEDICAL CENTER | 450885 | other (CCN 08xx range) | 04/01/2025–03/31/2026 | $46.2M | $8.9M | $1.3M | $133.9M | 42.1% |  | as submitted |
| CHILDRENS MEDICAL CENTER OF DALLAS | 453302 | children's | 01/01/2022–12/31/2022 | $415.1M | — | — | $1,398.1M | — | 29.7% | as submitted |
| CHILDRENS MEDICAL CENTER OF DALLAS | 453302 | children's | 01/01/2023–12/31/2023 | $485.7M | — | — | $1,689.2M | — | 28.8% | as submitted |
| CHILDRENS MEDICAL CENTER OF DALLAS | 453302 | children's | 01/01/2024–12/31/2024 | $543.7M | — | — | $1,846.4M | — | 29.4% | as submitted |
| CHILDRENS MEDICAL CENTER OF DALLAS | 453302 | children's | 01/01/2025–12/31/2025 | $577.5M | — | — | $1,918.6M | — | 30.1% | as submitted |
| CHILDRENS MEDICAL CENTER OF PLANO | 453316 | children's | 01/01/2022–12/31/2022 | $78.0M | — | — | $266.2M | — | 29.3% | settled without audit |
| CHILDRENS MEDICAL CENTER OF PLANO | 453316 | children's | 01/01/2023–12/31/2023 | $102.5M | — | — | $326.3M | — | 31.4% | settled without audit |
| CHILDRENS MEDICAL CENTER OF PLANO | 453316 | children's | 01/01/2024–12/31/2024 | $121.7M | — | — | $397.0M | — | 30.7% | as submitted |
| CHILDRENS MEDICAL CENTER OF PLANO | 453316 | children's | 01/01/2025–12/31/2025 | $145.4M | — | — | $472.0M | — | 30.8% | as submitted |
| CLEARSKY REHABILITIATION HOSPITAL OF | 673088 | rehabilitation | 04/01/2024–03/31/2025 | $10.3M | — | — | $27.4M | — | 37.5% | as submitted |
| CLEARSKY REHABILITIATION HOSPITAL OF | 673088 | rehabilitation | 04/01/2025–03/31/2026 | $12.5M | — | — | $30.0M | — | 41.5% | as submitted |
| CLEARSKY REHABILITIATION HOSPITAL OF | 673088 | rehabilitation | 07/26/2023–03/31/2024 | $5.8M | — | — | $16.1M | — | 35.7% | settled without audit |
| COOK CHILDREN CARE | 453317 | children's | 02/28/2023–09/30/2023 | — | — | — | — | — |  | settled without audit |
| COOK CHILDRENS MEDICAL CENTER | 453300 | children's | 10/01/2021–09/30/2022 | $371.7M | — | — | $1,258.1M | — | 29.5% | reopened |
| COOK CHILDRENS MEDICAL CENTER | 453300 | children's | 10/01/2022–09/30/2023 | $404.2M | — | — | $1,449.8M | — | 27.9% | settled with audit |
| COOK CHILDRENS MEDICAL CENTER | 453300 | children's | 10/01/2023–09/30/2024 | $415.1M | — | — | $1,645.0M | — | 25.2% | settled without audit |
| COOK CHILDRENS MEDICAL CENTER | 453300 | children's | 10/01/2024–09/30/2025 | $437.8M | — | — | $1,746.1M | — | 25.1% | as submitted |
| COOK CHILDRENS MEDICAL CENTER PROSPE | 453317 | children's | 10/01/2023–09/30/2024 | $39.5M | — | — | $129.4M | — | 30.5% | settled without audit |
| COOK CHILDRENS MEDICAL CENTER PROSPE | 453317 | children's | 10/01/2024–09/30/2025 | $49.7M | — | — | $165.9M | — | 30.0% | as submitted |
| CRESCENT MEDICAL CENTER LANCASTER | 670090 | short-term acute | 01/01/2022–12/31/2022 | $14.0M | $2.7M | $0.0M* | $44.4M | 37.7% |  | settled without audit |
| CRESCENT MEDICAL CENTER LANCASTER | 670090 | short-term acute | 01/01/2023–12/31/2023 | $15.5M | $3.2M | $0.0M* | $42.2M | 44.3% |  | settled without audit |
| CRESCENT MEDICAL CENTER LANCASTER | 670090 | short-term acute | 01/01/2024–12/31/2024 | $14.8M | $2.7M | $0.0M* | $48.3M | 36.2% |  | amended |
| CRESCENT MEDICAL CENTER LANCASTER | 670090 | short-term acute | 01/01/2025–12/31/2025 | $14.7M | $2.6M | $0.0M* | $59.8M | 29.1% |  | as submitted |
| DALLAS BEHAVIORAL HEALTHCARE | 454126 | psychiatric | 01/01/2022–12/31/2022 | $12.0M | — | — | $23.3M | — | 51.4% | settled without audit |
| DALLAS BEHAVIORAL HEALTHCARE | 454126 | psychiatric | 01/01/2023–12/31/2023 | $13.7M | — | — | $25.9M | — | 52.7% | settled without audit |
| DALLAS BEHAVIORAL HEALTHCARE | 454126 | psychiatric | 01/01/2024–12/31/2024 | $15.4M | — | — | $27.2M | — | 56.7% | settled without audit |
| DALLAS BEHAVIORAL HEALTHCARE | 454126 | psychiatric | 01/01/2025–12/31/2025 | $15.9M | — | — | $27.6M | — | 57.7% | settled without audit |
| DALLAS CO. HOSP. DIST. | 450015 | short-term acute | 10/01/2021–09/30/2022 | $1,014.4M | $247.0M | $105.1M | $2,388.5M | 57.2% |  | amended |
| DALLAS CO. HOSP. DIST. | 450015 | short-term acute | 10/01/2022–09/30/2023 | $1,123.5M | $280.1M | $99.9M | $2,700.6M | 55.7% |  | amended |
| DALLAS CO. HOSP. DIST. | 450015 | short-term acute | 10/01/2023–09/30/2024 | $1,227.9M | $302.3M | $29.9M | $2,815.2M | 55.4% |  | amended |
| DALLAS CO. HOSP. DIST. | 450015 | short-term acute | 10/01/2024–09/30/2025 | $1,294.9M | $383.2M | $0.6M | $3,041.0M | 55.2% |  | as submitted |
| DALLAS MEDICAL CENTER | 450379 | short-term acute | 01/01/2022–12/31/2022 | $16.6M | $4.2M | $2.5M | $53.0M | 44.0% |  | settled without audit |
| DALLAS MEDICAL CENTER | 450379 | short-term acute | 01/01/2023–12/31/2023 | $17.9M | $4.6M | $1.2M | $61.3M | 38.7% |  | settled without audit |
| DALLAS MEDICAL CENTER | 450379 | short-term acute | 01/01/2024–12/31/2024 | $18.0M | $4.0M | $0.7M | $67.0M | 34.0% |  | as submitted |
| DALLAS MEDICAL CENTER | 450379 | short-term acute | 01/01/2025–12/31/2025 | $16.1M | $3.6M | $0.6M | $59.5M | 33.9% |  | as submitted |
| DALLAS REGIONAL MEDICAL CENTER | 450688 | short-term acute | 01/01/2022–12/31/2022 | $38.5M | $10.2M | $8.8M | $104.3M | 55.2% |  | settled without audit |
| DALLAS REGIONAL MEDICAL CENTER | 450688 | short-term acute | 01/01/2023–12/31/2023 | $38.8M | $10.2M | $3.8M | $104.5M | 50.5% |  | as submitted |
| DALLAS REGIONAL MEDICAL CENTER | 450688 | short-term acute | 01/01/2024–12/31/2024 | $41.8M | $10.7M | $3.9M | $114.5M | 49.3% |  | as submitted |
| DALLAS REGIONAL MEDICAL CENTER | 450688 | short-term acute | 01/01/2025–12/31/2025 | $46.8M | $10.3M | $3.9M | $130.3M | 46.8% |  | as submitted |
| DECATUR COMMUNITY HOSPITAL | 450271 | short-term acute | 01/01/2022–12/31/2022 | $96.5M | $14.6M | $0.6M | $417.0M | 26.8% |  | settled without audit |
| DECATUR COMMUNITY HOSPITAL | 450271 | short-term acute | 01/01/2023–11/30/2023 | $78.6M | $12.0M | $0.8M | $356.7M | 25.6% |  | as submitted |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453040 | rehabilitation | 01/01/2022–07/31/2022 | $8.8M | $1.5M | $0.3M | $18.0M | 58.5% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673029 | rehabilitation | 01/01/2022–12/31/2022 | $12.6M | $3.2M | $0.3M | $24.8M | 64.8% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453047 | rehabilitation | 01/01/2022–08/31/2022 | $10.3M | $3.8M | $0.4M | $20.3M | 70.9% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453042 | rehabilitation | 01/01/2022–07/31/2022 | $8.2M | $1.5M | $0.6M | $17.5M | 59.0% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673029 | rehabilitation | 01/01/2023–12/31/2023 | $13.0M | $3.4M | $0.3M | $26.1M | 64.2% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673029 | rehabilitation | 01/01/2024–12/31/2024 | $12.7M | $2.5M | $0.2M | $26.0M | 59.1% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673096 | rehabilitation | 01/01/2025–12/31/2025 | $12.1M | $2.3M | $0.2M | $24.8M | 58.5% |  | as submitted |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673029 | rehabilitation | 01/01/2025–12/31/2025 | $12.3M | $3.5M | $0.2M | $26.8M | 60.0% |  | as submitted |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673043 | rehabilitation | 07/01/2022–06/30/2023 | $14.2M | $3.6M | $0.6M | $32.2M | 57.2% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673044 | rehabilitation | 07/01/2022–06/30/2023 | $13.3M | $2.4M | $0.4M | $29.1M | 55.5% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673043 | rehabilitation | 07/01/2023–06/30/2024 | $14.3M | $3.0M | $0.2M | $31.7M | 55.3% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673044 | rehabilitation | 07/01/2023–06/30/2024 | $15.2M | $3.3M | $0.3M | $31.7M | 59.5% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673044 | rehabilitation | 07/01/2024–06/30/2025 | $16.8M | $3.4M | $0.3M | $33.8M | 60.8% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673043 | rehabilitation | 07/01/2024–06/30/2025 | $14.5M | $3.4M | $0.2M | $31.8M | 56.7% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453040 | rehabilitation | 08/01/2022–07/31/2023 | $16.4M | $3.3M | $0.3M | $33.4M | 59.9% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453042 | rehabilitation | 08/01/2022–07/31/2023 | $14.8M | $2.8M | $0.7M | $32.2M | 56.7% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453042 | rehabilitation | 08/01/2023–07/31/2024 | $15.7M | $3.3M | $0.3M | $35.1M | 55.2% |  | settled without audit |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453040 | rehabilitation | 08/01/2023–07/31/2024 | $15.4M | $3.5M | $0.3M | $33.7M | 56.8% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453040 | rehabilitation | 08/01/2024–07/31/2025 | $15.5M | $3.6M | $0.3M | $34.0M | 57.2% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453042 | rehabilitation | 08/01/2024–07/31/2025 | $16.6M | $3.2M | $0.3M | $38.2M | 52.5% |  | amended |
| ENCOMPASS HEALTH REHABILITATION HOSP | 453047 | rehabilitation | 09/01/2024–08/31/2025 | $13.8M | $2.5M | $0.4M | $30.6M | 54.5% |  | as submitted |
| ENCOMPASS HEALTH REHABILITATION HOSP | 673096 | rehabilitation | 12/04/2023–12/31/2024 | $11.8M | $2.5M | $0.2M | $21.4M | 67.6% |  | as submitted |
| ENCOMPASS REHABILITATION HOSP | 453047 | rehabilitation | 09/01/2022–08/31/2023 | $15.2M | $4.4M | $0.5M | $31.0M | 64.9% |  | settled without audit |
| ENCOMPASS REHABILITATION HOSP | 453047 | rehabilitation | 09/01/2023–08/31/2024 | $15.8M | $2.8M | $0.4M | $32.8M | 57.8% |  | settled without audit |
| ENNIS REGIONAL MEDICAL CENTER | 450833 | short-term acute | 05/01/2022–04/30/2023 | $8.0M | $1.8M | $1.3M | $21.6M | 51.1% |  | settled without audit |
| ENNIS REGIONAL MEDICAL CENTER | 450833 | short-term acute | 05/01/2023–04/30/2024 | $8.0M | $1.4M | $0.3M | $25.9M | 37.5% |  | settled without audit |
| ENNIS REGIONAL MEDICAL CENTER | 450833 | short-term acute | 05/01/2024–04/30/2025 | $8.4M | $1.4M | $0.5M | $24.2M | 42.4% |  | as submitted |
| GLEN OAKS HOSPITAL | 454050 | psychiatric | 01/01/2022–12/31/2022 | $7.2M | — | — | $12.6M | — | 57.1% | settled without audit |
| GLEN OAKS HOSPITAL | 454050 | psychiatric | 01/01/2023–12/31/2023 | $7.6M | — | — | $13.3M | — | 57.1% | settled without audit |
| GLEN OAKS HOSPITAL | 454050 | psychiatric | 01/01/2024–12/31/2024 | $8.1M | — | — | $14.2M | — | 57.1% | settled without audit |
| GLEN OAKS HOSPITAL | 454050 | psychiatric | 01/01/2025–12/31/2025 | $8.4M | — | — | $14.5M | — | 57.9% | as submitted |
| HAVEN BEHAVIORAL HOSPITAL OF FRISCO | 454134 | psychiatric | 01/01/2022–12/31/2022 | $7.6M | — | — | $16.7M | — | 45.7% | settled without audit |
| HAVEN BEHAVIORAL HOSPITAL OF FRISCO | 454134 | psychiatric | 01/01/2023–12/31/2023 | $8.5M | — | — | $18.5M | — | 45.6% | settled without audit |
| HAVEN BEHAVIORAL HOSPITAL OF FRISCO | 454134 | psychiatric | 01/01/2024–02/29/2024 | $1.4M | — | — | $3.2M | — | 44.4% | settled without audit |
| HICKORY TRAIL HOSPITAL | 454065 | psychiatric | 08/01/2022–07/31/2023 | $12.3M | — | — | $19.3M | — | 63.4% | settled without audit |
| HICKORY TRAIL HOSPITAL | 454065 | psychiatric | 08/01/2023–07/31/2024 | $12.6M | — | — | $20.2M | — | 62.4% | settled without audit |
| HICKORY TRAIL HOSPITAL | 454065 | psychiatric | 08/01/2024–07/31/2025 | $13.1M | — | — | $22.7M | — | 57.4% | settled without audit |
| HORIZON MEDICAL CENTER MCKINNEY | 743031 | rehabilitation | 12/10/2024–12/31/2025 | $5.2M | — | — | $13.4M | — | 38.8% | as submitted |
| HUNT REGIONAL MEDICAL CENTER | 450352 | short-term acute | 10/01/2021–09/30/2022 | $76.8M | $15.5M | $14.8M | $193.2M | 55.4% |  | settled without audit |
| HUNT REGIONAL MEDICAL CENTER | 450352 | short-term acute | 10/01/2022–09/30/2023 | $100.9M | $19.2M | $4.6M | $234.0M | 53.3% |  | settled without audit |
| HUNT REGIONAL MEDICAL CENTER | 450352 | short-term acute | 10/01/2023–09/30/2024 | $119.4M | $15.2M | $14.8M | $261.7M | 57.1% |  | as submitted |
| HUNT REGIONAL MEDICAL CENTER | 450352 | short-term acute | 10/01/2024–09/30/2025 | $126.8M | $28.9M | $28.0M | $275.1M | 66.8% |  | as submitted |
| KINDRED HOSPITAL DALLAS CENTRAL | 452108 | long-term care | 09/01/2022–08/31/2023 | $13.1M | — | — | $31.7M | — | 41.4% | settled without audit |
| KINDRED HOSPITAL DALLAS CENTRAL | 452108 | long-term care | 09/01/2023–08/31/2024 | $12.2M | — | — | $30.2M | — | 40.6% | settled without audit |
| KINDRED HOSPITAL DALLAS CENTRAL | 452108 | long-term care | 09/01/2024–08/31/2025 | $11.2M | — | — | $30.4M | — | 36.9% | amended |
| KINDRED HOSPITAL TARRANT COUNTY | 452028 | long-term care | 09/01/2022–08/31/2023 | $25.9M | — | — | $62.8M | — | 41.2% | settled without audit |
| KINDRED HOSPITAL TARRANT COUNTY | 452028 | long-term care | 09/01/2023–08/31/2024 | $24.7M | — | — | $60.7M | — | 40.7% | settled without audit |
| KINDRED HOSPITAL TARRANT COUNTY | 452028 | long-term care | 09/01/2024–08/31/2025 | $22.3M | — | — | $57.2M | — | 39.1% | as submitted |
| KPC PROMISE HOSPITAL OF DALLAS | 452067 | long-term care | 09/01/2022–08/31/2023 | $4.0M | — | — | $8.5M | — | 46.4% | settled without audit |
| KPC PROMISE HOSPITAL OF DALLAS | 452067 | long-term care | 09/01/2023–05/31/2024 | $2.0M | — | — | $4.8M | — | 42.1% | settled without audit |
| LEGENT ORTHOPEDIC HOSPITAL CARROLLTO | 670265 | short-term acute | 09/01/2022–08/31/2023 | $10.2M | $1.7M | $0.0M* | $43.8M | 27.1% |  | settled without audit |
| LEGENT ORTHOPEDIC HOSPITAL CARROLLTO | 670265 | short-term acute | 09/01/2023–08/31/2024 | $9.2M | $1.3M | $0.0M* | $45.4M | 23.1% |  | settled without audit |
| LEGENT ORTHOPEDIC HOSPITAL CARROLLTO | 670265 | short-term acute | 09/01/2024–08/31/2025 | $13.6M | $2.0M | $0.6M | $66.4M | 24.3% |  | as submitted |
| LEGENT SURGICAL HOSPITAL PLANO | 670322 | short-term acute | 06/08/2023–08/31/2023 | — | — | — | — | — |  | settled without audit |
| LEGENT SURGICAL HOSPITAL PLANO | 670322 | short-term acute | 09/01/2023–08/31/2024 | $5.1M | $0.6M | $0.0M* | $25.5M | 22.2% |  | settled without audit |
| LEGENT SURGICAL HOSPITAL PLANO | 670322 | short-term acute | 09/01/2024–08/31/2025 | $5.3M | $0.6M | $0.4M | $51.0M | 12.5% |  | as submitted |
| LIFECARE SPEC HOSP OF NORTH TEXAS | 452044 | long-term care | 09/01/2022–08/31/2023 | $28.0M | — | — | $77.9M | — | 36.0% | settled without audit |
| LIFECARE SPEC HOSP OF NORTH TEXAS | 452044 | long-term care | 09/01/2023–08/31/2024 | $19.3M | — | — | $49.7M | — | 38.8% | settled without audit |
| LIFECARE SPEC HOSP OF NORTH TEXAS | 452044 | long-term care | 09/01/2024–08/31/2025 | $10.1M | — | — | $23.1M | — | 43.8% | as submitted |
| MAYHILL HOSPITAL | 670010 | short-term acute | 01/01/2022–12/31/2022 | $8.0M | $1.0M | $0.0M* | $14.7M | 60.7% |  | settled without audit |
| MAYHILL HOSPITAL | 670010 | short-term acute | 01/01/2023–12/31/2023 | $8.5M | $1.0M | $0.0M* | $15.8M | 59.7% |  | settled without audit |
| MAYHILL HOSPITAL | 670010 | short-term acute | 01/01/2024–12/31/2024 | $8.8M | — | — | $16.8M | — | 52.7% | as submitted |
| MAYHILL HOSPITAL | 670010 | short-term acute | 01/01/2025–08/31/2025 | $5.5M | — | — | $12.6M | — | 43.8% | as submitted |
| MC MENTAL HEALTH WELLNESS FRISCO | 454161 | psychiatric | 04/24/2024–10/31/2024 | $6.0M | — | — | $15.8M | — | 37.8% | settled without audit |
| MC MENTAL HEALTH WELLNESS FRISCO | 454161 | psychiatric | 11/01/2024–10/31/2025 | $8.8M | — | — | $23.3M | — | 37.5% | settled without audit |
| MEDICAL CITY ALLIANCE | 670103 | short-term acute | 02/01/2022–01/31/2023 | $36.4M | $8.7M | $0.3M | $111.5M | 40.6% |  | settled without audit |
| MEDICAL CITY ALLIANCE | 670103 | short-term acute | 02/01/2023–01/31/2024 | $43.4M | $9.0M | $0.3M | $130.0M | 40.5% |  | settled without audit |
| MEDICAL CITY ALLIANCE | 670103 | short-term acute | 02/01/2024–01/31/2025 | $49.7M | $11.0M | $1.9M | $163.6M | 38.3% |  | amended |
| MEDICAL CITY ALLIANCE | 670103 | short-term acute | 02/01/2025–01/31/2026 | $53.7M | $12.5M | $0.6M | $171.8M | 38.9% |  | as submitted |
| MEDICAL CITY ARLINGTON | 450675 | short-term acute | 06/01/2022–05/31/2023 | $104.8M | $1.4M | $0.2M | $318.1M | 33.5% |  | amended |
| MEDICAL CITY ARLINGTON | 450675 | short-term acute | 06/01/2023–05/31/2024 | $113.2M | $1.0M | $0.1M | $359.8M | 31.8% |  | amended |
| MEDICAL CITY ARLINGTON | 450675 | short-term acute | 06/01/2024–05/31/2025 | $113.9M | $1.5M | $0.1M | $363.1M | 31.8% |  | amended |
| MEDICAL CITY DALLAS | 450647 | short-term acute | 06/01/2022–05/31/2023 | $248.8M | $53.2M | $4.6M | $667.0M | 46.0% |  | amended |
| MEDICAL CITY DALLAS | 450647 | short-term acute | 06/01/2023–05/31/2024 | $262.1M | $1.4M | $0.2M | $654.8M | 40.3% |  | amended |
| MEDICAL CITY DALLAS | 450647 | short-term acute | 06/01/2024–05/31/2025 | $266.2M | $1.5M | $4.9M | $666.6M | 40.9% |  | amended |
| MEDICAL CITY DECATUR | 450271 | short-term acute | 12/01/2023–05/31/2024 | $24.7M | $4.6M | $0.0M | $96.3M | 30.5% |  | amended |
| MEDICAL CITY DENTON | 450634 | short-term acute | 01/01/2022–12/31/2022 | $68.0M | $14.7M | $2.0M | $194.4M | 43.6% |  | amended |
| MEDICAL CITY DENTON | 450634 | short-term acute | 01/01/2023–12/31/2023 | $73.3M | $17.1M | $2.5M | $217.2M | 42.7% |  | amended |
| MEDICAL CITY DENTON | 450634 | short-term acute | 01/01/2024–12/31/2024 | $107.7M | $24.7M | $0.9M | $365.4M | 36.5% |  | amended |
| MEDICAL CITY DENTON | 450634 | short-term acute | 01/01/2025–12/31/2025 | $126.3M | $28.8M | $1.8M | $413.6M | 37.9% |  | as submitted |
| MEDICAL CITY FORT WORTH | 450672 | short-term acute | 02/01/2022–01/31/2023 | $84.4M | $20.0M | $5.3M | $289.8M | 37.8% |  | amended |
| MEDICAL CITY FORT WORTH | 450672 | short-term acute | 02/01/2023–01/31/2024 | $88.8M | $18.7M | $4.6M | $325.5M | 34.4% |  | amended |
| MEDICAL CITY FORT WORTH | 450672 | short-term acute | 02/01/2024–01/31/2025 | $95.0M | $23.2M | $3.5M | $351.6M | 34.6% |  | amended |
| MEDICAL CITY FORT WORTH | 450672 | short-term acute | 02/01/2025–01/31/2026 | $104.4M | $25.2M | $4.3M | $359.9M | 37.2% |  | as submitted |
| MEDICAL CITY GREEN OAKS HOSPITAL | 454094 | psychiatric | 09/01/2022–08/31/2023 | $18.5M | — | — | $42.9M | — | 43.0% | settled without audit |
| MEDICAL CITY GREEN OAKS HOSPITAL | 454094 | psychiatric | 09/01/2023–08/31/2024 | $17.8M | — | — | $43.4M | — | 40.9% | settled without audit |
| MEDICAL CITY GREEN OAKS HOSPITAL | 454094 | psychiatric | 09/01/2024–08/31/2025 | $18.1M | — | — | $44.8M | — | 40.3% | as submitted |
| MEDICAL CITY LAS COLINAS | 450822 | short-term acute | 01/01/2022–12/31/2022 | $30.6M | $7.1M | $0.6M | $100.1M | 38.2% |  | settled without audit |
| MEDICAL CITY LAS COLINAS | 450822 | short-term acute | 01/01/2023–12/31/2023 | $30.7M | $6.6M | $0.0M* | $102.6M | 36.3% |  | settled without audit |
| MEDICAL CITY LAS COLINAS | 450822 | short-term acute | 01/01/2024–12/31/2024 | $33.3M | $6.9M | $0.0M | $105.1M | 38.2% |  | amended |
| MEDICAL CITY LAS COLINAS | 450822 | short-term acute | 01/01/2025–12/31/2025 | $33.3M | $6.7M | $0.1M | $111.1M | 36.1% |  | as submitted |
| MEDICAL CITY LEWISVILLE | 450669 | short-term acute | 06/01/2022–05/31/2023 | $53.5M | $10.8M | $1.3M | $157.7M | 41.7% |  | settled without audit |
| MEDICAL CITY LEWISVILLE | 450669 | short-term acute | 06/01/2023–05/31/2024 | $56.2M | $11.8M | $2.0M | $170.8M | 41.0% |  | settled without audit |
| MEDICAL CITY LEWISVILLE | 450669 | short-term acute | 06/01/2024–05/31/2025 | $58.7M | $13.6M | $1.2M | $182.2M | 40.3% |  | amended |
| MEDICAL CITY MCKINNEY | 450403 | short-term acute | 09/01/2022–08/31/2023 | $87.1M | $23.7M | $1.3M | $303.8M | 36.9% |  | settled without audit |
| MEDICAL CITY MCKINNEY | 450403 | short-term acute | 09/01/2023–08/31/2024 | $92.1M | $21.2M | $0.9M | $327.1M | 34.9% |  | settled without audit |
| MEDICAL CITY MCKINNEY | 450403 | short-term acute | 09/01/2024–08/31/2025 | $93.8M | $25.9M | $1.1M | $343.4M | 35.2% |  | amended |
| MEDICAL CITY MENTAL HEALTH AND WELLN | 454079 | psychiatric | 11/01/2024–10/31/2025 | $4.9M | — | — | $16.6M | — | 29.2% | settled without audit |
| MEDICAL CITY NORTH HILLS | 450087 | short-term acute | 06/01/2022–05/31/2023 | $46.2M | $9.4M | $0.0M* | $125.6M | 44.3% |  | settled without audit |
| MEDICAL CITY NORTH HILLS | 450087 | short-term acute | 06/01/2023–05/31/2024 | $47.1M | $9.4M | $0.0M* | $134.7M | 42.0% |  | settled without audit |
| MEDICAL CITY NORTH HILLS | 450087 | short-term acute | 06/01/2024–05/31/2025 | $47.5M | $9.5M | $0.0M* | $134.9M | 42.3% |  | amended |
| MEDICAL CITY PLANO | 450651 | short-term acute | 04/01/2022–03/31/2023 | $189.1M | $43.0M | $3.7M | $559.1M | 42.2% |  | amended |
| MEDICAL CITY PLANO | 450651 | short-term acute | 04/01/2023–03/31/2024 | $197.4M | $42.3M | $6.0M | $572.1M | 42.9% |  | amended |
| MEDICAL CITY PLANO | 450651 | short-term acute | 04/01/2024–03/31/2025 | $209.8M | $45.7M | $4.5M | $613.4M | 42.4% |  | amended |
| MEDICAL CITY PLANO | 450651 | short-term acute | 04/01/2025–03/31/2026 | $217.8M | $49.9M | $3.8M | $635.8M | 42.7% |  | as submitted |
| MEDICAL CITY WEATHERFORD | 450203 | short-term acute | 10/01/2021–09/30/2022 | $29.6M | $6.6M | $1.3M | $104.9M | 35.7% |  | settled with audit |
| MEDICAL CITY WEATHERFORD | 450203 | short-term acute | 10/01/2022–09/30/2023 | $34.9M | $7.8M | $0.1M | $116.6M | 36.7% |  | amended |
| MEDICAL CITY WEATHERFORD | 450203 | short-term acute | 10/01/2023–09/30/2024 | $38.6M | $8.6M | $0.0M | $128.7M | 36.7% |  | amended |
| MEDICAL CITY WEATHERFORD | 450203 | short-term acute | 10/01/2024–09/30/2025 | $38.2M | $10.0M | $0.0M* | $128.3M | 37.6% |  | as submitted |
| MESA SPRINGS | 454124 | psychiatric | 01/01/2022–12/31/2022 | $14.3M | — | — | $30.4M | — | 47.1% | settled without audit |
| MESA SPRINGS | 454124 | psychiatric | 01/01/2023–12/31/2023 | $13.7M | — | — | $29.1M | — | 47.2% | settled without audit |
| MESA SPRINGS | 454124 | psychiatric | 01/01/2024–06/30/2024 | $6.9M | — | — | $14.3M | — | 48.4% | settled without audit |
| MESA SPRINGS | 454124 | psychiatric | 07/01/2024–06/30/2025 | $14.2M | — | — | $28.4M | — | 49.9% | settled without audit |
| MESQUITE REHABILITATION INSTITUTE | 673045 | rehabilitation | 01/01/2022–12/31/2022 | $7.1M | — | — | $13.1M | — | 54.1% | settled without audit |
| MESQUITE REHABILITATION INSTITUTE | 673045 | rehabilitation | 01/01/2023–12/31/2023 | $8.1M | — | — | $13.8M | — | 58.7% | settled without audit |
| MESQUITE REHABILITATION INSTITUTE | 673045 | rehabilitation | 01/01/2024–12/31/2024 | $8.3M | — | — | $14.2M | — | 58.8% | as submitted |
| MESQUITE REHABILITATION INSTITUTE | 673045 | rehabilitation | 01/01/2025–12/31/2025 | $8.6M | — | — | $14.9M | — | 57.6% | as submitted |
| MESQUITE SPECIALTY HOSPITAL | 452100 | long-term care | 06/01/2022–05/31/2023 | $7.3M | — | — | $16.4M | — | 44.4% | settled without audit |
| MESQUITE SPECIALTY HOSPITAL | 452100 | long-term care | 06/01/2023–05/31/2024 | $8.0M | — | — | $16.7M | — | 48.2% | reopened |
| MESQUITE SPECIALTY HOSPITAL | 452100 | long-term care | 06/01/2024–05/31/2025 | $8.2M | — | — | $18.3M | — | 44.7% | as submitted |
| METHODIST CELINA MEDICAL CENTER | 670340 | short-term acute | 04/10/2025–01/31/2026 | $15.1M | $2.3M | $0.3M | $47.6M | 37.2% |  | as submitted |
| METHODIST CHARLTON MEDICAL CENTER | 450723 | short-term acute | 07/01/2022–06/30/2023 | $109.4M | $21.9M | $36.4M | $324.9M | 51.6% |  | settled without audit |
| METHODIST CHARLTON MEDICAL CENTER | 450723 | short-term acute | 07/01/2023–06/30/2024 | $127.3M | $24.3M | $19.5M | $349.8M | 48.9% |  | settled without audit |
| METHODIST CHARLTON MEDICAL CENTER | 450723 | short-term acute | 07/01/2024–06/30/2025 | $140.3M | $32.3M | $7.2M | $366.3M | 49.1% |  | amended |
| METHODIST DALLAS MEDICAL CENTER | 450051 | short-term acute | 07/01/2022–06/30/2023 | $172.2M | $31.0M | $12.9M | $585.6M | 36.9% |  | amended |
| METHODIST DALLAS MEDICAL CENTER | 450051 | short-term acute | 07/01/2023–06/30/2024 | $186.1M | $32.9M | $8.6M | $632.8M | 36.0% |  | as submitted |
| METHODIST DALLAS MEDICAL CENTER | 450051 | short-term acute | 07/01/2024–06/30/2025 | $205.1M | $40.7M | $6.7M | $710.6M | 35.5% |  | as submitted |
| METHODIST HOSPITAL FOR SURGERY | 670073 | short-term acute | 01/01/2022–12/31/2022 | $18.5M | $6.2M | $2.6M | $137.7M | 19.9% |  | settled without audit |
| METHODIST HOSPITAL FOR SURGERY | 670073 | short-term acute | 01/01/2023–12/31/2023 | $20.2M | $7.2M | $4.1M | $142.1M | 22.1% |  | settled without audit |
| METHODIST HOSPITAL FOR SURGERY | 670073 | short-term acute | 01/01/2024–12/31/2024 | $20.6M | $5.6M | $3.9M | $138.6M | 21.7% |  | as submitted |
| METHODIST HOSPITAL FOR SURGERY | 670073 | short-term acute | 01/01/2025–12/31/2025 | $22.0M | $6.2M | $3.3M | $138.6M | 22.7% |  | as submitted |
| METHODIST MANSFIELD MEDICAL CENTER | 670023 | short-term acute | 07/01/2022–06/30/2023 | $104.9M | $17.1M | $11.7M | $284.3M | 47.0% |  | settled without audit |
| METHODIST MANSFIELD MEDICAL CENTER | 670023 | short-term acute | 07/01/2023–06/30/2024 | $118.6M | $18.8M | $2.8M | $313.8M | 44.7% |  | settled without audit |
| METHODIST MANSFIELD MEDICAL CENTER | 670023 | short-term acute | 07/01/2024–06/30/2025 | $123.1M | $32.0M | $0.8M | $336.7M | 46.3% |  | as submitted |
| METHODIST MCKINNEY HOSPITAL | 670069 | short-term acute | 01/01/2022–12/31/2022 | $13.8M | $4.3M | $0.8M | $68.0M | 27.8% |  | settled without audit |
| METHODIST MCKINNEY HOSPITAL | 670069 | short-term acute | 01/01/2023–12/31/2023 | $15.8M | $4.0M | $0.4M | $73.7M | 27.4% |  | settled without audit |
| METHODIST MCKINNEY HOSPITAL | 670069 | short-term acute | 01/01/2024–12/31/2024 | $16.5M | $3.1M | $0.1M | $75.5M | 26.2% |  | as submitted |
| METHODIST MCKINNEY HOSPITAL | 670069 | short-term acute | 01/01/2025–12/31/2025 | $16.4M | $3.2M | $0.4M | $77.3M | 25.8% |  | as submitted |
| METHODIST MIDLOTHIAN MEDICAL CENTER | 670300 | short-term acute | 07/01/2022–06/30/2023 | $25.8M | $4.8M | $1.8M | $67.4M | 48.0% |  | settled without audit |
| METHODIST MIDLOTHIAN MEDICAL CENTER | 670300 | short-term acute | 07/01/2023–06/30/2024 | $30.1M | $4.4M | $0.7M | $80.4M | 43.8% |  | settled without audit |
| METHODIST MIDLOTHIAN MEDICAL CENTER | 670300 | short-term acute | 07/01/2024–06/30/2025 | $34.3M | $8.5M | $0.1M | $87.9M | 48.7% |  | as submitted |
| METHODIST REHABILITATION HOSPITAL | 673031 | rehabilitation | 01/01/2022–12/31/2022 | $10.3M | $1.3M | $1.0M | $19.6M | 64.5% |  | settled without audit |
| METHODIST REHABILITATION HOSPITAL | 673031 | rehabilitation | 01/01/2023–12/31/2023 | $11.3M | $1.5M | $1.0M | $21.0M | 65.2% |  | settled without audit |
| METHODIST REHABILITATION HOSPITAL | 673031 | rehabilitation | 01/01/2024–12/31/2024 | $11.3M | $1.5M | $0.8M | $23.9M | 56.9% |  | settled without audit |
| METHODIST REHABILITATION HOSPITAL | 673031 | rehabilitation | 01/01/2025–12/31/2025 | $10.8M | — | — | $25.4M | — | 42.4% | as submitted |
| METHODIST RICHARDSON MEDICAL CENTER | 450537 | short-term acute | 07/01/2022–06/30/2023 | $124.4M | $20.4M | $19.8M | $383.4M | 42.9% |  | settled without audit |
| METHODIST RICHARDSON MEDICAL CENTER | 450537 | short-term acute | 07/01/2023–06/30/2024 | $144.4M | $28.7M | $6.3M | $426.0M | 42.1% |  | as submitted |
| METHODIST RICHARDSON MEDICAL CENTER | 450537 | short-term acute | 07/01/2024–06/30/2025 | $152.7M | $36.0M | $2.8M | $454.8M | 42.1% |  | as submitted |
| METHODIST SOUTHLAKE MEDICAL CENTER | 670132 | short-term acute | 10/01/2021–09/30/2022 | $12.1M | $1.8M | $5.3M | $56.9M | 33.7% |  | settled without audit |
| METHODIST SOUTHLAKE MEDICAL CENTER | 670132 | short-term acute | 10/01/2022–09/30/2023 | $15.2M | $2.1M | $2.0M | $63.2M | 30.5% |  | settled without audit |
| METHODIST SOUTHLAKE MEDICAL CENTER | 670132 | short-term acute | 10/01/2023–09/30/2024 | $17.5M | $2.8M | $1.1M | $68.2M | 31.3% |  | as submitted |
| METHODIST SOUTHLAKE MEDICAL CENTER | 670132 | short-term acute | 10/01/2024–09/30/2025 | $19.0M | $4.1M | $0.9M | $71.4M | 33.8% |  | as submitted |
| MILLWOOD HOSPITAL | 454012 | psychiatric | 01/01/2022–12/31/2022 | $16.4M | — | — | $24.0M | — | 68.4% | settled without audit |
| MILLWOOD HOSPITAL | 454012 | psychiatric | 01/01/2023–12/31/2023 | $17.4M | — | — | $25.5M | — | 68.3% | settled without audit |
| MILLWOOD HOSPITAL | 454012 | psychiatric | 01/01/2024–12/31/2024 | $17.7M | — | — | $26.7M | — | 66.2% | settled without audit |
| MILLWOOD HOSPITAL | 454012 | psychiatric | 01/01/2025–12/31/2025 | $19.0M | — | — | $31.7M | — | 59.9% | as submitted |
| NEXUS CHILDRENS HOSPITAL DALLAS | 453318 | children's | 01/01/2025–12/31/2025 | $10.4M | — | — | $24.8M | — | 42.2% | as submitted |
| NEXUS CHILDRENS HOSPITAL DALLAS | 453318 | children's | 02/05/2024–12/31/2024 | $6.8M | — | — | $17.8M | — | 38.5% | as submitted |
| NORTH CENTRAL SURGICAL HOSPITAL | 670049 | short-term acute | 01/01/2022–12/31/2022 | $21.3M | $4.8M | $3.7M | $97.6M | 30.5% |  | settled without audit |
| NORTH CENTRAL SURGICAL HOSPITAL | 670049 | short-term acute | 01/01/2023–12/31/2023 | $20.4M | $4.4M | $2.7M | $99.3M | 27.7% |  | settled without audit |
| NORTH CENTRAL SURGICAL HOSPITAL | 670049 | short-term acute | 01/01/2024–12/31/2024 | $22.3M | $4.7M | $2.1M | $106.1M | 27.4% |  | as submitted |
| NORTH CENTRAL SURGICAL HOSPITAL | 670049 | short-term acute | 01/01/2025–12/31/2025 | $22.3M | $4.9M | $1.8M | $108.3M | 26.8% |  | as submitted |
| OUR CHILDRENS HOUSE | 453308 | children's | 01/01/2022–07/18/2022 | $6.2M | — | — | $19.6M | — | 31.7% | settled without audit |
| PERIMETER BEHAVIORAL HOSPITAL OF DAL | 454149 | psychiatric | 01/01/2022–12/31/2022 | $9.3M | — | — | $16.7M | — | 55.9% | settled without audit |
| PERIMETER BEHAVIORAL HOSPITAL OF DAL | 454149 | psychiatric | 01/01/2023–12/31/2023 | $10.7M | — | — | $17.0M | — | 62.8% | settled without audit |
| PERIMETER BEHAVIORAL HOSPITAL OF DAL | 454149 | psychiatric | 01/01/2024–12/31/2024 | $11.2M | — | — | $18.2M | — | 61.4% | settled without audit |
| PERIMETER BEHAVIORAL HOSPITAL OF DAL | 454149 | psychiatric | 01/01/2025–12/31/2025 | $14.2M | — | — | $23.4M | — | 60.6% | as submitted |
| PERIMETER BEHAVIORIAL HOSPITAL OF AR | 454148 | psychiatric | 01/01/2022–12/31/2022 | — | — | — | — | — |  | settled without audit |
| PERIMETER HOSPITAL OF ARLINGTON | 454148 | psychiatric | 01/01/2023–12/31/2023 | $9.9M | — | — | $17.6M | — | 56.0% | settled without audit |
| PERIMETER HOSPITAL OF ARLINGTON | 454148 | psychiatric | 01/01/2024–12/31/2024 | — | — | — | — | — |  | settled without audit |
| PERIMETER HOSPITAL OF ARLINGTON | 454148 | psychiatric | 01/01/2025–12/31/2025 | $13.2M | — | — | $22.2M | — | 59.7% | as submitted |
| POST ACUTE MEDICAL AT ALLEN | 673025 | rehabilitation | 01/01/2022–12/31/2022 | $12.9M | — | — | $26.8M | — | 48.3% | settled without audit |
| POST ACUTE MEDICAL AT ALLEN | 673025 | rehabilitation | 01/01/2023–12/31/2023 | $12.9M | — | — | $26.4M | — | 48.8% | settled without audit |
| POST ACUTE MEDICAL AT ALLEN | 673025 | rehabilitation | 01/01/2024–12/31/2024 | $14.3M | — | — | $28.2M | — | 50.6% | as submitted |
| POST ACUTE MEDICAL AT ALLEN | 673025 | rehabilitation | 01/01/2025–12/31/2025 | $14.9M | — | — | $30.2M | — | 49.2% | as submitted |
| PRESBYTERIAN HOSP FLOWER MOUND | 670068 | short-term acute | 01/01/2022–12/31/2022 | $49.8M | $11.7M | $2.8M | $154.2M | 41.7% |  | settled without audit |
| PRESBYTERIAN HOSP FLOWER MOUND | 670068 | short-term acute | 01/01/2023–12/31/2023 | $53.9M | $11.1M | $0.8M | $161.4M | 40.8% |  | settled without audit |
| PRESBYTERIAN HOSP FLOWER MOUND | 670068 | short-term acute | 01/01/2024–12/31/2024 | $56.6M | $12.4M | $0.0M | $163.0M | 42.3% |  | amended |
| PRESBYTERIAN HOSP FLOWER MOUND | 670068 | short-term acute | 01/01/2025–12/31/2025 | $58.4M | $13.0M | $0.0M | $170.4M | 41.9% |  | as submitted |
| PRESBYTERIAN HOSPITAL OF ROCKWALL | 670044 | short-term acute | 01/01/2022–12/31/2022 | $40.8M | $9.6M | $4.5M | $126.4M | 43.4% |  | settled without audit |
| PRESBYTERIAN HOSPITAL OF ROCKWALL | 670044 | short-term acute | 01/01/2023–12/31/2023 | $44.2M | $9.5M | $0.5M | $118.3M | 45.9% |  | settled without audit |
| PRESBYTERIAN HOSPITAL OF ROCKWALL | 670044 | short-term acute | 01/01/2024–12/31/2024 | $50.5M | — | — | $148.2M | — | 34.1% | amended |
| PRESBYTERIAN HOSPITAL OF ROCKWALL | 670044 | short-term acute | 01/01/2025–12/31/2025 | $56.6M | — | — | $165.4M | — | 34.2% | as submitted |
| PRESBYTERIAN PLANO CENTER DIAG SRVCS | 450891 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $16.1M | $3.8M | $1.0M | $58.7M | 35.6% |  | settled without audit |
| PRESBYTERIAN PLANO CENTER DIAG SRVCS | 450891 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $16.3M | $3.6M | $1.0M | $66.0M | 31.7% |  | settled without audit |
| PRESBYTERIAN PLANO CENTER DIAG SRVCS | 450891 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $17.8M | $4.0M | $0.4M | $71.3M | 31.2% |  | as submitted |
| PRESBYTERIAN PLANO CENTER DIAG SRVCS | 450891 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $18.8M | $4.3M | $0.2M | $77.9M | 29.8% |  | as submitted |
| REHAB HOSPITAL OF FLOWER MOUND | 673076 | rehabilitation | 01/01/2022–12/31/2022 | $5.7M | — | — | $11.5M | — | 49.9% | settled without audit |
| REHAB HOSPITAL OF FLOWER MOUND | 673076 | rehabilitation | 01/01/2023–12/31/2023 | $5.9M | — | — | $12.1M | — | 49.1% | settled without audit |
| REHAB HOSPITAL OF FLOWER MOUND | 673076 | rehabilitation | 01/01/2024–12/31/2024 | $7.1M | — | — | $12.9M | — | 54.7% | settled without audit |
| REHAB HOSPITAL OF FLOWER MOUND | 673076 | rehabilitation | 01/01/2025–12/31/2025 | $9.0M | — | — | $16.2M | — | 55.6% | as submitted |
| REHABILITATION INSTITUTE OF DENTON | 673036 | rehabilitation | 06/01/2022–05/31/2023 | $11.2M | — | — | $20.0M | — | 55.7% | settled without audit |
| REHABILITATION INSTITUTE OF DENTON | 673036 | rehabilitation | 06/01/2023–05/31/2024 | $12.2M | — | — | $21.7M | — | 56.5% | settled without audit |
| REHABILITATION INSTITUTE OF DENTON | 673036 | rehabilitation | 06/01/2024–05/31/2025 | $12.8M | — | — | $22.4M | — | 57.3% | as submitted |
| REUNION REHABILITATION HOSPITAL ARLI | 673081 | rehabilitation | 04/25/2023–07/31/2023 | $1.8M | — | — | $3.2M | — | 57.2% | settled without audit |
| REUNION REHABILITATION HOSPITAL ARLI | 673081 | rehabilitation | 08/01/2023–07/31/2024 | $7.6M | — | — | $17.7M | — | 43.0% | settled without audit |
| REUNION REHABILITATION HOSPITAL ARLI | 673081 | rehabilitation | 08/01/2024–07/31/2025 | $10.6M | — | — | $21.6M | — | 48.9% | as submitted |
| REUNION REHABILITATION HOSPITAL PLAN | 673080 | rehabilitation | 05/25/2023–07/31/2023 | $1.2M | — | — | $2.1M | — | 58.2% | settled without audit |
| REUNION REHABILITATION HOSPITAL PLAN | 673080 | rehabilitation | 08/01/2023–07/31/2024 | $10.7M | — | — | $20.2M | — | 53.1% | settled without audit |
| REUNION REHABILITATION HOSPITAL PLAN | 673080 | rehabilitation | 08/01/2024–07/31/2025 | $12.5M | — | — | $25.1M | — | 49.7% | as submitted |
| SOUTHLAKE SPECIALITY HOSPITAL | 450888 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $11.6M | — | — | $59.6M | — | 19.4% | settled without audit |
| SOUTHLAKE SPECIALITY HOSPITAL | 450888 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $11.5M | — | — | $64.8M | — | 17.8% | settled without audit |
| SOUTHLAKE SPECIALITY HOSPITAL | 450888 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $13.4M | — | — | $66.3M | — | 20.1% | as submitted |
| SOUTHLAKE SPECIALITY HOSPITAL | 450888 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $13.1M | — | — | $67.3M | — | 19.5% | as submitted |
| SSH - DALLAS  INC. | 452022 | long-term care | 01/01/2022–12/31/2022 | $19.1M | — | — | $39.6M | — | 48.3% | settled without audit |
| SSH - DALLAS  INC. | 452022 | long-term care | 01/01/2023–12/31/2023 | $18.1M | — | — | $38.8M | — | 46.6% | settled without audit |
| SSH - DALLAS  INC. | 452022 | long-term care | 01/01/2024–12/31/2024 | $20.3M | — | — | $42.9M | — | 47.2% | settled without audit |
| SSH - DALLAS  INC. | 452022 | long-term care | 01/01/2025–12/31/2025 | $20.5M | — | — | $41.9M | — | 48.9% | as submitted |
| ST DAVIDS MEDICAL CENTER | 450431 | short-term acute | 01/01/2024–12/31/2024 | $215.2M | $44.7M | $0.6M | $755.7M | 34.5% |  | amended |
| ST DAVIDS MEDICAL CENTER | 450431 | short-term acute | 01/01/2025–12/31/2025 | $224.7M | $49.3M | $0.5M | $794.5M | 34.6% |  | amended |
| TCHD D/B/A JPS HEALTH NETWORK | 450039 | short-term acute | 10/01/2021–09/30/2022 | $522.7M | $119.9M | $39.4M | $1,292.1M | 52.8% |  | settled with audit |
| TCHD D/B/A JPS HEALTH NETWORK | 450039 | short-term acute | 10/01/2022–09/30/2023 | $555.3M | $128.7M | $47.1M | $1,383.9M | 52.8% |  | settled without audit |
| TCHD D/B/A JPS HEALTH NETWORK | 450039 | short-term acute | 10/01/2023–09/30/2024 | $600.2M | $132.8M | $9.6M | $1,471.6M | 50.5% |  | amended |
| TCHD D/B/A JPS HEALTH NETWORK | 450039 | short-term acute | 10/01/2024–09/30/2025 | $643.9M | $150.3M | $3.7M | $1,583.9M | 50.4% |  | amended |
| TERRELL STATE HOSPITAL | 454006 | psychiatric | 09/01/2022–08/31/2023 | $63.8M | — | — | $75.5M | — | 84.5% | settled without audit |
| TERRELL STATE HOSPITAL | 454006 | psychiatric | 09/01/2023–08/31/2024 | $75.0M | — | — | $87.0M | — | 86.2% | settled without audit |
| TERRELL STATE HOSPITAL | 454006 | psychiatric | 09/01/2024–08/31/2025 | $64.5M | — | — | $92.6M | — | 69.7% | as submitted |
| TEXAS HEALTH ALLIANCE | 670085 | short-term acute | 07/01/2022–06/30/2023 | $59.0M | — | $1.5M | $157.5M | — | 37.4% | settled without audit |
| TEXAS HEALTH ALLIANCE | 670085 | short-term acute | 07/01/2023–06/30/2024 | $60.8M | $14.7M | $0.2M | $168.4M | 44.9% |  | amended |
| TEXAS HEALTH ALLIANCE | 670085 | short-term acute | 07/01/2024–06/30/2025 | $63.8M | $15.0M | $0.1M | $177.4M | 44.5% |  | as submitted |
| TEXAS HEALTH ARLINGTON MEMORIAL HOSP | 450064 | short-term acute | 01/01/2022–12/31/2022 | $125.4M | $25.3M | $17.3M | $328.3M | 51.2% |  | settled without audit |
| TEXAS HEALTH ARLINGTON MEMORIAL HOSP | 450064 | short-term acute | 01/01/2023–12/31/2023 | $124.3M | $28.6M | $3.8M | $327.9M | 47.8% |  | settled without audit |
| TEXAS HEALTH ARLINGTON MEMORIAL HOSP | 450064 | short-term acute | 01/01/2024–12/31/2024 | $122.1M | $29.4M | $0.0M | $325.8M | 46.5% |  | amended |
| TEXAS HEALTH ARLINGTON MEMORIAL HOSP | 450064 | short-term acute | 01/01/2025–12/31/2025 | $122.6M | $30.5M | $0.0M* | $335.5M | 45.6% |  | amended |
| TEXAS HEALTH CLEBURNE | 450148 | short-term acute | 10/01/2021–09/30/2022 | $27.8M | $6.8M | $7.8M | $84.9M | 49.9% |  | settled without audit |
| TEXAS HEALTH CLEBURNE | 450148 | short-term acute | 10/01/2022–09/30/2023 | $31.2M | $7.1M | $1.6M | $79.8M | 49.9% |  | settled without audit |
| TEXAS HEALTH CLEBURNE | 450148 | short-term acute | 10/01/2023–09/30/2024 | $32.3M | $7.6M | $0.0M | $83.1M | 48.0% |  | amended |
| TEXAS HEALTH CLEBURNE | 450148 | short-term acute | 10/01/2024–09/30/2025 | $30.9M | $7.6M | $0.0M* | $80.8M | 47.7% |  | as submitted |
| TEXAS HEALTH DALLAS | 450462 | short-term acute | 01/01/2022–12/31/2022 | $243.5M | — | $29.2M | $724.3M | — | 33.6% | settled without audit |
| TEXAS HEALTH DALLAS | 450462 | short-term acute | 01/01/2023–12/31/2023 | $254.6M | $58.9M | $3.3M | $761.5M | 41.6% |  | settled without audit |
| TEXAS HEALTH DALLAS | 450462 | short-term acute | 01/01/2024–12/31/2024 | $258.3M | $61.2M | $1.6M | $753.3M | 42.6% |  | amended |
| TEXAS HEALTH DALLAS | 450462 | short-term acute | 01/01/2025–12/31/2025 | $276.1M | $65.7M | $4.5M | $817.2M | 42.4% |  | as submitted |
| TEXAS HEALTH DENTON | 450743 | short-term acute | 05/01/2022–04/30/2023 | $88.3M | $19.5M | $9.3M | $259.0M | 45.2% |  | settled without audit |
| TEXAS HEALTH DENTON | 450743 | short-term acute | 05/01/2023–04/30/2024 | $92.7M | $20.8M | $0.6M | $269.3M | 42.4% |  | settled without audit |
| TEXAS HEALTH DENTON | 450743 | short-term acute | 05/01/2024–04/30/2025 | $99.9M | $23.3M | $0.3M | $289.8M | 42.6% |  | amended |
| TEXAS HEALTH H-E-B | 450639 | short-term acute | 10/01/2021–09/30/2022 | $104.0M | $8.3M | $11.8M | $287.6M | 43.2% |  | settled without audit |
| TEXAS HEALTH H-E-B | 450639 | short-term acute | 10/01/2022–09/30/2023 | $115.3M | $25.6M | $4.0M | $302.4M | 47.9% |  | settled without audit |
| TEXAS HEALTH H-E-B | 450639 | short-term acute | 10/01/2023–09/30/2024 | $123.4M | — | $0.2M | $325.5M | — | 37.9% | amended |
| TEXAS HEALTH H-E-B | 450639 | short-term acute | 10/01/2024–09/30/2025 | $128.6M | $31.2M | $0.1M | $336.5M | 47.5% |  | as submitted |
| TEXAS HEALTH HEART & VASCULAR HOSP | 670071 | short-term acute | 01/01/2022–12/31/2022 | $0.6M | $3.6M | $3.4M | $51.0M | 15.0% |  | reopened |
| TEXAS HEALTH HEART & VASCULAR HOSP | 670071 | short-term acute | 01/01/2023–12/31/2023 | $12.7M | $3.3M | $1.1M | $60.2M | 28.3% |  | settled without audit |
| TEXAS HEALTH HEART & VASCULAR HOSP | 670071 | short-term acute | 01/01/2024–12/31/2024 | $13.9M | $3.2M | $0.3M | $60.5M | 28.6% |  | as submitted |
| TEXAS HEALTH HEART & VASCULAR HOSP | 670071 | short-term acute | 01/01/2025–12/31/2025 | $13.7M | $3.1M | $0.2M | $57.1M | 29.8% |  | as submitted |
| TEXAS HEALTH HOSPITAL ALLEN | 450840 | short-term acute | 01/01/2022–12/31/2022 | $37.6M | $8.5M | $7.7M | $122.6M | 43.9% |  | settled without audit |
| TEXAS HEALTH HOSPITAL ALLEN | 450840 | short-term acute | 01/01/2023–12/31/2023 | $40.4M | — | $1.3M | $121.8M | — | 33.1% | settled without audit |
| TEXAS HEALTH HOSPITAL ALLEN | 450840 | short-term acute | 01/01/2024–12/31/2024 | $41.7M | — | $0.4M | $122.9M | — | 33.9% | amended |
| TEXAS HEALTH HOSPITAL ALLEN | 450840 | short-term acute | 01/01/2025–12/31/2025 | $46.3M | $10.7M | $0.6M | $137.9M | 41.8% |  | as submitted |
| TEXAS HEALTH HOSPITAL FRISCO | 670260 | short-term acute | 01/01/2022–12/31/2022 | $46.5M | — | — | $138.5M | — | 33.6% | settled without audit |
| TEXAS HEALTH HOSPITAL FRISCO | 670260 | short-term acute | 01/01/2023–12/31/2023 | $47.2M | — | — | $151.3M | — | 31.2% | settled without audit |
| TEXAS HEALTH HOSPITAL FRISCO | 670260 | short-term acute | 01/01/2024–12/31/2024 | $53.6M | $11.6M | $0.1M | $165.5M | 39.5% |  | as submitted |
| TEXAS HEALTH HOSPITAL FRISCO | 670260 | short-term acute | 01/01/2025–12/31/2025 | $59.0M | $13.3M | $0.2M | $172.6M | 42.0% |  | as submitted |
| TEXAS HEALTH HOSPITAL MANSFIELD | 670309 | short-term acute | 01/01/2022–12/31/2022 | $23.6M | — | — | $66.5M | — | 35.5% | settled without audit |
| TEXAS HEALTH HOSPITAL MANSFIELD | 670309 | short-term acute | 01/01/2023–12/31/2023 | $28.5M | $5.6M | $0.3M | $78.0M | 44.1% |  | settled without audit |
| TEXAS HEALTH HOSPITAL MANSFIELD | 670309 | short-term acute | 01/01/2024–12/31/2024 | $29.7M | — | — | $84.4M | — | 35.3% | as submitted |
| TEXAS HEALTH HOSPITAL MANSFIELD | 670309 | short-term acute | 01/01/2025–12/31/2025 | $35.6M | — | — | $102.3M | — | 34.8% | as submitted |
| TEXAS HEALTH HUGULEY | 450677 | short-term acute | 01/01/2022–12/31/2022 | $99.6M | — | — | $239.4M | — | 41.6% | settled without audit |
| TEXAS HEALTH HUGULEY | 450677 | short-term acute | 01/01/2023–12/31/2023 | $112.9M | $22.6M | $0.3M | $260.0M | 52.2% |  | settled without audit |
| TEXAS HEALTH HUGULEY | 450677 | short-term acute | 01/01/2024–12/31/2024 | $118.9M | — | — | $299.8M | — | 39.7% | as submitted |
| TEXAS HEALTH HUGULEY | 450677 | short-term acute | 01/01/2025–12/31/2025 | $134.8M | — | — | $364.5M | — | 37.0% | as submitted |
| TEXAS HEALTH KAUFMAN | 450292 | short-term acute | 01/01/2022–12/31/2022 | $14.7M | — | $0.3M | $39.2M | — | 37.6% | settled without audit |
| TEXAS HEALTH KAUFMAN | 450292 | short-term acute | 01/01/2023–12/31/2023 | $16.1M | — | — | $41.9M | — | 38.4% | settled without audit |
| TEXAS HEALTH KAUFMAN | 450292 | short-term acute | 01/01/2024–12/31/2024 | $17.1M | $4.2M | $0.0M | $44.8M | 47.5% |  | amended |
| TEXAS HEALTH KAUFMAN | 450292 | short-term acute | 01/01/2025–12/31/2025 | $18.4M | $4.4M | $0.2M | $50.0M | 46.1% |  | as submitted |
| TEXAS HEALTH PRESBYTERIAN HOSPITAL P | 450771 | short-term acute | 01/01/2022–12/31/2022 | $147.8M | — | $13.5M | $426.3M | — | 34.7% | settled without audit |
| TEXAS HEALTH PRESBYTERIAN HOSPITAL P | 450771 | short-term acute | 01/01/2023–12/31/2023 | $156.8M | $36.1M | $1.4M | $451.8M | 43.0% |  | settled without audit |
| TEXAS HEALTH PRESBYTERIAN HOSPITAL P | 450771 | short-term acute | 01/01/2024–12/31/2024 | $165.8M | — | $0.8M | $478.9M | — | 34.6% | amended |
| TEXAS HEALTH PRESBYTERIAN HOSPITAL P | 450771 | short-term acute | 01/01/2025–12/31/2025 | $177.3M | $42.6M | $0.7M | $519.8M | 42.4% |  | as submitted |
| TEXAS HEALTH SOUTHWEST | 450779 | short-term acute | 10/01/2021–09/30/2022 | $104.5M | $24.6M | $12.8M | $324.8M | 43.7% |  | settled without audit |
| TEXAS HEALTH SOUTHWEST | 450779 | short-term acute | 10/01/2022–09/30/2023 | $113.7M | $25.3M | $4.0M | $343.3M | 41.7% |  | settled without audit |
| TEXAS HEALTH SOUTHWEST | 450779 | short-term acute | 10/01/2023–09/30/2024 | $119.8M | $27.3M | $0.9M | $352.5M | 42.0% |  | amended |
| TEXAS HEALTH SOUTHWEST | 450779 | short-term acute | 10/01/2024–09/30/2025 | $124.6M | — | — | $370.9M | — | 33.6% | as submitted |
| TEXAS INSTITUTE  FOR SURGERY AT PRES | 450889 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $13.6M | $2.9M | $1.7M | $57.7M | 31.6% |  | settled without audit |
| TEXAS INSTITUTE  FOR SURGERY AT PRES | 450889 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $14.6M | $3.1M | $1.9M | $61.0M | 32.3% |  | settled without audit |
| TEXAS INSTITUTE  FOR SURGERY AT PRES | 450889 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $16.9M | $4.0M | $1.2M | $66.7M | 33.2% |  | as submitted |
| TEXAS INSTITUTE  FOR SURGERY AT PRES | 450889 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $16.1M | $3.8M | $0.6M | $67.8M | 30.2% |  | as submitted |
| TEXAS REHAB HOSPITAL OF ARLINGTON | 673060 | rehabilitation | 01/01/2022–12/31/2022 | $9.1M | $1.2M | $0.0M | $16.4M | 63.2% |  | settled without audit |
| TEXAS REHAB HOSPITAL OF FT. WORTH | 673048 | rehabilitation | 01/01/2022–12/31/2022 | $12.1M | $1.8M | $0.0M* | $23.0M | 60.4% |  | settled without audit |
| TEXAS REHABILITATION HOSPITAL OF ARL | 673060 | rehabilitation | 01/01/2023–12/31/2023 | $8.9M | $1.3M | $0.1M | $16.6M | 61.8% |  | settled without audit |
| TEXAS REHABILITATION HOSPITAL OF ARL | 673060 | rehabilitation | 01/01/2024–12/31/2024 | $8.2M | $1.3M | $0.1M | $17.5M | 54.6% |  | as submitted |
| TEXAS REHABILITATION HOSPITAL OF ARL | 673060 | rehabilitation | 01/01/2025–12/31/2025 | $8.8M | — | — | $19.0M | — | 46.1% | as submitted |
| TEXAS REHABILITATION HOSPITAL OF FT. | 673048 | rehabilitation | 01/01/2023–12/31/2023 | $12.6M | $2.1M | $0.0M* | $25.0M | 58.7% |  | settled without audit |
| TEXAS REHABILITATION HOSPITAL OF FT. | 673048 | rehabilitation | 01/01/2024–12/31/2024 | $12.8M | $2.0M | $0.0M* | $28.4M | 52.3% |  | as submitted |
| TEXAS REHABILITATION HOSPITAL OF FT. | 673048 | rehabilitation | 01/01/2025–12/31/2025 | $13.3M | — | — | $31.0M | — | 42.9% | as submitted |
| TEXAS REHABILITATION HOSPITAL OF KEL | 673077 | rehabilitation | 01/01/2022–12/31/2022 | $5.4M | $0.7M | $0.3M | $11.6M | 54.8% |  | settled without audit |
| TEXAS REHABILITATION HOSPITAL OF KEL | 673077 | rehabilitation | 01/01/2023–12/31/2023 | $6.5M | $0.9M | $0.2M | $13.7M | 55.7% |  | settled without audit |
| TEXAS REHABILITATION HOSPITAL OF KEL | 673077 | rehabilitation | 01/01/2024–12/31/2024 | $7.7M | $1.1M | $0.2M | $15.8M | 56.7% |  | as submitted |
| TEXAS REHABILITATION HOSPITAL OF KEL | 673077 | rehabilitation | 01/01/2025–12/31/2025 | $8.3M | — | — | $17.6M | — | 47.1% | as submitted |
| TEXAS SCOTTISH RITE HOSPITAL FOR CHI | 453314 | children's | 10/01/2021–09/30/2022 | — | — | — | — | — |  | settled without audit |
| TEXAS SCOTTISH RITE HOSPITAL FOR CHI | 453314 | children's | 10/01/2022–09/30/2023 | — | — | — | — | — |  | settled without audit |
| TEXAS SCOTTISH RITE HOSPITAL FOR CRI | 453314 | children's | 10/01/2023–09/30/2024 | — | — | — | — | — |  | settled without audit |
| THE HEART HOSPITAL BAYLOR DENTON | 450893 | other (CCN 08xx range) | 01/01/2022–12/31/2022 | $19.1M | $3.7M | $0.2M | $57.1M | 40.3% |  | settled without audit |
| THE HEART HOSPITAL BAYLOR DENTON | 450893 | other (CCN 08xx range) | 01/01/2023–12/31/2023 | $20.1M | $4.2M | $0.0M* | $61.6M | 39.4% |  | settled without audit |
| THE HEART HOSPITAL BAYLOR DENTON | 450893 | other (CCN 08xx range) | 01/01/2024–12/31/2024 | $22.6M | $4.4M | $0.0M* | $77.5M | 34.8% |  | as submitted |
| THE HEART HOSPITAL BAYLOR DENTON | 450893 | other (CCN 08xx range) | 01/01/2025–12/31/2025 | $23.0M | $4.3M | $0.0M* | $81.9M | 33.4% |  | as submitted |
| THE HEART HOSPITAL BAYLOR PLANO | 670025 | short-term acute | 01/01/2022–12/31/2022 | $106.3M | $22.3M | $1.8M | $345.3M | 37.7% |  | settled without audit |
| THE HEART HOSPITAL BAYLOR PLANO | 670025 | short-term acute | 01/01/2023–12/31/2023 | $111.9M | $24.6M | $0.9M | $386.6M | 35.5% |  | settled without audit |
| THE HEART HOSPITAL BAYLOR PLANO | 670025 | short-term acute | 01/01/2024–12/31/2024 | $117.1M | $24.7M | $0.0M | $427.9M | 33.1% |  | as submitted |
| THE HEART HOSPITAL BAYLOR PLANO | 670025 | short-term acute | 01/01/2025–12/31/2025 | $127.6M | $25.4M | $0.2M | $512.4M | 29.9% |  | as submitted |
| THE HEART HOSPITAL CORINTH | 452111 | long-term care | 11/01/2024–11/30/2024 | — | — | — | — | — |  | settled without audit |
| THE HEART HOSPITAL DALLAS | 450851 | short-term acute | 02/01/2025–06/30/2025 | $24.0M | $5.0M | $0.1M | $93.1M | 31.2% |  | as submitted |
| THE LEAVES | 451990 | other (CCN 19xx range) | 01/01/2022–12/31/2022 | $2.0M | — | — | $3.1M | — | 64.8% | settled without audit |
| THE LEAVES  INC. | 451990 | other (CCN 19xx range) | 01/01/2023–12/31/2023 | $2.3M | — | — | $3.5M | — | 67.1% | settled without audit |
| THE LEAVES  INC. | 451990 | other (CCN 19xx range) | 01/01/2024–12/31/2024 | $2.4M | — | — | $3.7M | — | 65.1% | settled without audit |
| THE LEAVES  INC. | 451990 | other (CCN 19xx range) | 01/01/2025–12/31/2025 | $2.4M | — | — | $3.8M | — | 63.2% | as submitted |
| TRINITY REGIONAL HOSPITAL SACHSE | 670319 | short-term acute | 01/01/2023–01/31/2024 | $9.2M | $1.1M | $0.0M* | $99.5M | 10.4% |  | settled without audit |
| TRINITY REGIONAL HOSPITAL SACHSE | 670319 | short-term acute | 01/31/2022–12/31/2022 | $5.9M | $0.9M | $0.5M | $32.7M | 22.2% |  | settled without audit |
| TX HLTH HARRIS METHODIST AZLE | 450419 | short-term acute | 10/01/2021–09/30/2022 | $18.3M | — | $1.5M | $43.2M | — | 42.3% | settled without audit |
| TX HLTH HARRIS METHODIST AZLE | 450419 | short-term acute | 10/01/2022–09/30/2023 | $19.2M | — | $0.2M | $43.7M | — | 43.8% | settled without audit |
| TX HLTH HARRIS METHODIST AZLE | 450419 | short-term acute | 10/01/2023–09/30/2024 | $20.5M | — | $0.1M | $47.2M | — | 43.5% | amended |
| TX HLTH HARRIS METHODIST AZLE | 450419 | short-term acute | 10/01/2024–09/30/2025 | $21.6M | — | — | $48.6M | — | 44.3% | amended |
| TX HLTH HARRIS METHODIST HOSPITAL | 450135 | short-term acute | 10/01/2021–09/30/2022 | $326.1M | — | $31.4M | $982.9M | — | 33.2% | settled without audit |
| TX HLTH HARRIS METHODIST HOSPITAL | 450135 | short-term acute | 10/01/2022–09/30/2023 | $369.0M | $82.9M | $15.1M | $1,107.2M | 42.2% |  | settled without audit |
| TX HLTH HARRIS METHODIST HOSPITAL | 450135 | short-term acute | 10/01/2023–09/30/2024 | $380.5M | — | $2.9M | $1,159.5M | — | 32.8% | amended |
| TX HLTH HARRIS METHODIST HOSPITAL | 450135 | short-term acute | 10/01/2024–09/30/2025 | $406.4M | — | $1.3M | $1,257.5M | — | 32.3% | amended |
| TX HLTH SPECIALTY HOSP FORT WORTH | 452018 | long-term care | 04/01/2022–03/31/2023 | $3.9M | — | — | $9.4M | — | 41.4% | settled without audit |
| TX HLTH SPECIALTY HOSP FORT WORTH | 452018 | long-term care | 04/01/2023–03/31/2024 | $4.2M | — | — | $10.2M | — | 41.4% | settled without audit |
| TX HLTH SPECIALTY HOSP FORT WORTH | 452018 | long-term care | 04/01/2024–03/31/2025 | $4.4M | — | — | $10.3M | — | 42.9% | settled without audit |
| TX HLTH SPECIALTY HOSP FORT WORTH | 452018 | long-term care | 04/01/2025–03/31/2026 | $4.5M | — | — | $10.5M | — | 43.1% | as submitted |
| TX SCOTTISH RITE HOSPITAL FOR CHILDR | 453314 | children's | 10/01/2024–09/30/2025 | $114.3M | — | — | $250.5M | — | 45.6% | as submitted |
| UBH DENTON HOSPITAL | 454104 | psychiatric | 01/01/2022–12/31/2022 | $11.5M | — | — | $20.6M | — | 55.6% | settled without audit |
| UBH DENTON HOSPITAL | 454104 | psychiatric | 01/01/2023–12/31/2023 | $12.3M | — | — | $21.2M | — | 57.7% | settled without audit |
| UBH DENTON HOSPITAL | 454104 | psychiatric | 01/01/2024–12/31/2024 | $12.0M | — | — | $21.1M | — | 57.0% | settled without audit |
| UBH DENTON HOSPITAL | 454104 | psychiatric | 01/01/2025–12/31/2025 | $13.0M | — | — | $22.7M | — | 57.2% | as submitted |
| USMD HOSPITAL OF ARLINGTON | 450872 | short-term acute | 01/01/2022–12/31/2022 | $19.8M | $5.7M | $2.2M | $67.1M | 41.1% |  | settled without audit |
| USMD HOSPITAL OF ARLINGTON | 450872 | short-term acute | 01/01/2023–12/31/2023 | $19.7M | $6.7M | $1.4M | $71.2M | 39.1% |  | settled without audit |
| USMD HOSPITAL OF ARLINGTON | 450872 | short-term acute | 01/01/2024–12/31/2024 | $22.0M | $6.1M | $1.1M | $83.4M | 35.0% |  | as submitted |
| USMD HOSPITAL OF ARLINGTON | 450872 | short-term acute | 01/01/2025–12/31/2025 | $23.8M | $6.9M | $0.6M | $89.4M | 34.9% |  | as submitted |
| UT SOUTHWESTERN UNIVERSITY HOSP | 450044 | short-term acute | 09/01/2022–08/31/2023 | $696.6M | $169.1M | $58.5M | $2,385.3M | 38.8% |  | amended |
| UT SOUTHWESTERN UNIVERSITY HOSP | 450044 | short-term acute | 09/01/2023–08/31/2024 | $738.8M | $177.1M | $41.6M | $2,674.3M | 35.8% |  | as submitted |
| UT SOUTHWESTERN UNIVERSITY HOSP | 450044 | short-term acute | 09/01/2024–08/31/2025 | $851.7M | $261.0M | $39.2M | $3,135.0M | 36.7% |  | amended |
| VIBRA SPECIALTY HOSP DALLAS | 452097 | long-term care | 08/01/2022–07/31/2023 | $13.1M | — | — | $29.7M | — | 44.0% | settled without audit |
| VIBRA SPECIALTY HOSP DALLAS | 452097 | long-term care | 08/01/2023–07/31/2024 | $5.4M | — | — | $13.5M | — | 39.9% | as submitted |
| VIBRA SPECIALTY HOSP DALLAS | 452097 | long-term care | 08/01/2024–07/31/2025 | $5.1M | — | — | $11.2M | — | 45.8% | as submitted |
| VIBRA SPECIALTY HOSP DALLAS | 452097 | long-term care | 08/01/2025–10/31/2025 | $1.2M | — | — | $2.8M | — | 42.8% | as submitted |
| WEATHERFORD REHABILITATION HOSPITAL | 673062 | rehabilitation | 01/01/2022–12/31/2022 | $5.1M | — | — | $9.3M | — | 55.2% | settled without audit |
| WEATHERFORD REHABILITATION HOSPITAL | 673062 | rehabilitation | 01/01/2023–12/31/2023 | $5.8M | — | — | $10.3M | — | 56.0% | settled without audit |
| WEATHERFORD REHABILITATION HOSPITAL | 673062 | rehabilitation | 01/01/2024–12/31/2024 | $6.1M | — | — | $11.0M | — | 55.5% | as submitted |
| WEATHERFORD REHABILITATION HOSPITAL | 673062 | rehabilitation | 01/01/2025–12/31/2025 | $6.9M | — | — | $11.9M | — | 58.1% | as submitted |
| WELLBRIDGE HEALTHCARE FORT WORTH | 454128 | psychiatric | 01/01/2022–12/31/2022 | $6.1M | $0.7M | $0.4M | $11.8M | 61.2% |  | settled without audit |
| WELLBRIDGE HEALTHCARE FORT WORTH | 454128 | psychiatric | 01/01/2023–12/31/2023 | $6.1M | $0.8M | $0.4M | $11.9M | 62.2% |  | settled without audit |
| WELLBRIDGE HEALTHCARE FORT WORTH | 454128 | psychiatric | 01/01/2024–06/30/2024 | $3.2M | $0.4M | $0.0M | $6.2M | 58.2% |  | as submitted |
| WELLBRIDGE HEALTHCARE FORT WORTH | 454128 | psychiatric | 07/01/2024–06/30/2025 | $6.2M | $1.0M | $0.1M | $12.4M | 59.2% |  | settled without audit |
| WELLBRIDGE HEALTHCARE GREATER DALLAS | 454130 | psychiatric | 01/01/2022–12/31/2022 | $5.0M | $0.6M | $1.1M | $11.4M | 59.1% |  | settled without audit |
| WELLBRIDGE HEALTHCARE GREATER DALLAS | 454130 | psychiatric | 01/01/2023–12/31/2023 | $5.8M | $1.0M | $1.0M | $12.4M | 63.0% |  | settled without audit |
| WELLBRIDGE HEALTHCARE GREATER DALLAS | 454130 | psychiatric | 01/01/2024–06/30/2024 | $3.3M | $0.4M | $0.1M | $6.1M | 61.6% |  | settled without audit |
| WELLBRIDGE HEALTHCARE GREATER DALLAS | 454130 | psychiatric | 07/01/2024–09/29/2024 | $1.1M | $0.2M | $0.0M* | $2.3M | 56.7% |  | settled without audit |
| WHITE ROCK MEDICAL CENTER | 450678 | short-term acute | 06/01/2022–05/31/2023 | $37.2M | $6.5M | $8.9M | $134.5M | 39.1% |  | settled without audit |
| WHITE ROCK MEDICAL CENTER | 450678 | short-term acute | 06/01/2023–05/31/2024 | $34.5M | $2.8M | $0.0M* | $82.6M | 45.2% |  | settled without audit |
| WHITE ROCK MEDICAL CENTER | 450678 | short-term acute | 06/01/2024–05/31/2025 | $20.4M | $2.6M | $0.0M* | $53.8M | 42.7% |  | as submitted |
| WISE HEALTH SYSTEM - PARKWAY | 670116 | short-term acute | 01/01/2022–12/31/2022 | $18.0M | $3.5M | $0.5M | $417.0M | 5.3% |  | settled without audit |
| WISE HEALTH SYSTEM - PARKWAY | 670116 | short-term acute | 01/01/2023–11/30/2023 | $15.1M | $3.0M | $0.0M | $356.7M | 5.1% |  | settled without audit |

\* No contract-labor amount entered on a filed Part V; shown as $0 (cost report files store only filled-in cells).
