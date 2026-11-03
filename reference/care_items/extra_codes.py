"""Code types the crosswalk was missing (Nov 3, 2026; Betsy: "Are there any medical codes missing from this crosswalk?").

For each care item, the codes that sit beside its CPT/DRG codes on real claims and in price files:
  APC + OPPS status indicator + ASC payment indicator   Medicare's outpatient facility groups (CMS OPPS Addendum B and
                                                        ASC Addendum AA, July 2026; medicare_codes.csv)
  place of service (POS)                                CMS's two-digit setting codes; insurer files carry them as
                                                        service_code
  revenue codes                                         the hospital's line-item department codes on a UB-04 claim
                                                        (NUBC); "typical": hospitals vary
  modifiers                                             two-character codes that change what a CPT code pays
  Medicare HCPCS Level II versions                      where Medicare uses its own G-code instead of the CPT code
Rules are the standard billing rules for each kind of care; codes that depend on the patient (diagnoses) are not
guessed. Returns, per item, a list of (column, [(code, when)]) for atomize.py.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MED = {r["code"]: r for r in csv.DictReader(open(os.path.join(HERE, "medicare_codes.csv")))}
POS = {"11": "office", "19": "hospital outpatient, off campus", "22": "hospital outpatient, on campus",
       "24": "ambulatory surgery center", "21": "inpatient hospital", "81": "independent lab",
       "10": "telehealth at home", "02": "telehealth, not at home"}
SIDE = {"27447", "27130", "27487", "23472", "29881", "29826", "29827", "29888", "66984", "66821", "64721", "19120",
        "19303", "49650", "49505", "73721"}
ENDO = ("432", "433", "453", "4537", "4538", "4539")
CARDIAC_LAB = {"93452", "92928", "93656", "33208", "33249", "33361"}
MEDICARE_VERSION = {"colonoscopy": [("G0121", "Medicare screening colonoscopy, average risk"),
                                    ("G0105", "Medicare screening colonoscopy, high risk")],
                    "45378": [("G0121", "Medicare screening colonoscopy, average risk"),
                              ("G0105", "Medicare screening colonoscopy, high risk")],
                    "99385": [("G0438", "Medicare's first annual wellness visit (Medicare doesn't cover routine physicals)"),
                              ("G0439", "Medicare's yearly annual wellness visit after that")],
                    "99386": [("G0438", "Medicare's first annual wellness visit (Medicare doesn't cover routine physicals)"),
                              ("G0439", "Medicare's yearly annual wellness visit after that")]}
IMAGING_RC = {"70551": ("0611", "MRI, brain"), "70553": ("0611", "MRI, brain"), "72148": ("0612", "MRI, spine"),
              "73721": ("0614", "MRI, other"), "70450": ("0351", "CT, head"), "72193": ("0352", "CT, body"),
              "74177": ("0352", "CT, body"), "75571": ("0350", "CT, general"), "72110": ("0320", "x-ray, general"),
              "76700": ("0402", "ultrasound"), "76805": ("0402", "ultrasound"), "76830": ("0402", "ultrasound"),
              "77065": ("0401", "diagnostic mammogram"), "77066": ("0401", "diagnostic mammogram"),
              "77067": ("0403", "screening mammogram"), "93000": ("0730", "EKG")}


def for_item(x):
    kind, fac, doc = x["kind"], x["facility_or_lab_cpt"], x["doctor_cpt"]
    main = fac or doc
    overnight = "overnight" in x["usual_setting"]
    out = []
    m = MED.get(fac) or MED.get(main) or {}
    if m.get("apc"):
        out.append(("apc", [(m["apc"], "Medicare's outpatient facility group for " + main)]))
        out.append(("opps_si", [(m["opps_status_indicator"], "")]))
    if m.get("asc_payment_indicator"):
        out.append(("asc_pi", [(m["asc_payment_indicator"], "")]))
    mv = MEDICARE_VERSION.get(x["item_id"]) or MEDICARE_VERSION.get(main)
    if mv:
        out.append(("hcpcs_medicare", mv))

    # place of service
    if kind in ("hospital stay", "birth"):
        pos = ["21"]
    elif kind in ("office visit or checkup",):
        pos = ["11", "19", "22", "10", "02"]
    elif kind in ("therapy session",):
        pos = ["11", "10", "02", "22"]
    elif kind == "physical therapy":
        pos = ["11", "22", "19"]
    elif kind in ("lab test", "pathology (tissue check)"):
        pos = ["81", "22", "11"]
    elif kind == "imaging or test":
        pos = ["11", "22", "19"]
    else:   # surgery or procedure
        pos = ["24", "22", "19"] + (["21"] if overnight else []) + (["11"] if kind == "procedure" and not overnight else [])
    out.append(("pos", [(p, POS[p]) for p in pos]))

    # modifiers
    mods = []
    if main in SIDE:
        mods += [("RT", "right side"), ("LT", "left side"), ("50", "both sides in one session")]
    if x["item_id"] == "colonoscopy" or main in ("45378", "45380", "45385", "45391"):
        mods += [("33", "screening (preventive) colonoscopy, commercial plans"),
                 ("PT", "Medicare: a screening colonoscopy that became diagnostic")]
    if kind in ("imaging or test", "pathology (tissue check)"):
        mods += [("TC", "technical part only"), ("26", "doctor's reading only")]
    if kind in ("office visit or checkup",):
        mods += [("25", "a separate visit on the same day as a procedure")]
    if kind in ("surgery", "procedure", "same-day procedure") and not overnight:
        mods += [("SG", "older ASC facility-claim modifier; some plans still ask for it")] if False else []
    if mods:
        out.append(("modifier", mods))

    # revenue codes (facility claims)
    rc = []
    if kind in ("lab test",):
        n = int(main) if main.isdigit() else 0
        rc = [("0305", "hematology lab")] if 85000 <= n <= 85999 else [("0307", "urology lab")] if 81000 <= n <= 81099 \
            else [("0301", "chemistry lab")]
    elif kind == "pathology (tissue check)":
        rc = [("0310", "pathology lab")]
    elif kind == "imaging or test" and main in IMAGING_RC:
        rc = [IMAGING_RC[main]]
    elif kind == "office visit or checkup":
        rc = [("0510", "hospital clinic visit (only at hospital-owned clinics)")]
    elif kind == "physical therapy":
        rc = [("0420", "physical therapy (hospital outpatient)")]
    elif kind == "therapy session":
        rc = [("0915" if "group" in x["item_id"] else "0916" if "family" in x["item_id"] else "0914",
               "psychotherapy billed by a hospital program")]
    elif kind in ("surgery", "procedure", "same-day procedure", "birth", "hospital stay"):
        if kind == "birth" or x["item_id"] in ("vaginal-delivery", "c-section", "vbac"):
            rc = [("0720", "labor and delivery room"), ("0120", "room and board, semi-private"),
                  ("0170", "nursery (the baby's own bill)")]
        elif main in CARDIAC_LAB:
            rc = [("0481", "cardiac cath lab"), ("0278", "implant or device, if one is placed")]
        elif main.startswith(ENDO):
            rc = [("0750", "GI endoscopy suite"), ("0370", "anesthesia (facility part)"), ("0710", "recovery room")]
        elif kind == "hospital stay":
            rc = [("0120", "room and board, semi-private"), ("0360", "operating room")]
        else:
            rc = [("0360", "operating room"), ("0490", "ambulatory surgery (surgery center claims)"),
                  ("0370", "anesthesia (facility part)"), ("0710", "recovery room"),
                  ("0278", "implant, if one is placed")]
        if overnight and kind != "hospital stay" and ("0120", "room and board, semi-private") not in rc:
            rc.append(("0120", "room and board, semi-private (if admitted)"))
    if rc:
        out.append(("revenue", rc))
    return out
