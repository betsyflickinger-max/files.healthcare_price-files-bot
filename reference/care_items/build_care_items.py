"""One master list of care items: procedure -> every bill -> the code that prices each bill (Nov 2, 2026; Betsy: "is
there a way to standardize all this?").

The same surgery is priced under different code systems depending on who bills and where:
  surgeon / doctor            CPT (professional)
  hospital or surgery center  CPT (institutional) for same-day care; MS-DRG for an overnight hospital stay
  anesthesia                  anesthesia CPT (00100-01999), paid as base units + time, never a fixed price
  pathology, imaging reads    their own CPT codes, only sometimes
Insurer and hospital files price each bill separately and never say which go together. This list says which usually
do, for each care item, with how sure we are and the source. Pages show the bills side by side; nothing here is ever
added into one total.

Reads (all in this repo):  packages/packages.csv (5 same-day procedures already on the site)
                           reference/care_items/source_crosswalk_oct.csv (37 surgeries, CPT -> ICD-10-PCS -> MS-DRG ->
                           anesthesia; project doc claude/cpt-drg-anesthesia-crosswalk.md)
Writes:                    reference/care_items/care_items.csv        one row per care item
                           reference/care_items/care_item_bills.csv   one row per bill x setting
Run:  python reference/care_items/build_care_items.py
"""
import csv
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

ITEM_FIELDS = ["item_id", "plain_name", "kind", "usual_setting", "shoppable", "main_cpt", "usual_drg", "status", "why_listed"]
BILL_FIELDS = ["item_id", "bill", "setting", "code_system", "codes", "related_codes", "billing_class", "priced_as",
               "when", "confidence", "source"]

# CMS backing found Oct 25, 2026 (project copy of the crosswalk; the branch copy only had the first four)
TEAM = "CMS TEAM Clinical Episode Construction Specifications (Sept 2025), Table 10"
BPCI = "CMS BPCI Advanced (2022 episode definitions, AR6 Appendix B)"
CMS_BACKED = {
    "27447": TEAM, "27130": TEAM, "22551": TEAM, "22633": TEAM, "63030": BPCI, "43775": BPCI, "43644": BPCI,
    "33405": BPCI, "33361": BPCI, "23472": BPCI, "92928": BPCI, "33208": BPCI, "33249": BPCI, "33533": BPCI,
    "44204": BPCI, "27245": BPCI,
}
DRG_SRC = "CMS MS-DRG v44.0 Definitions Manual, Appendix E (FY2027): PCS code -> DRG"
ROLE = {"facility": "hospital or surgery center", "doctor": "surgeon or doctor", "anesthesia": "anesthesia",
        "pathology": "pathology lab"}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def setting_of(note):
    n = (note or "").lower()
    if "usually outpatient" in n or "often" in n or "sometimes" in n:
        return "same day or overnight"
    return "overnight stay" if "inpatient" in n else "same day or overnight"


RETIRED_DRGS = {"460": "AAPC lists MS-DRG 460 as deleted (CMS split spinal fusion into 402, 426-430, 447-451 in FY2024); "
                       "insurer files may still use it"}


def search_names():
    """The site's own plain-English names for the 89 featured codes (site/procedure_pages.py SEARCH_NAMES)."""
    import ast
    tree = ast.parse(open(os.path.join(ROOT, "site", "procedure_pages.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "SEARCH_NAMES" for t in node.targets):
            return {k: v[0] for k, v in ast.literal_eval(node.value).items()}
    return {}


def bill(iid, who, setting, system, codes, cls, priced, when, conf, src, related=""):
    return dict(item_id=iid, bill=who, setting=setting, code_system=system, codes=codes, related_codes=related,
                billing_class=cls, priced_as=priced, when=when, confidence=conf, source=src)


def featured(items, bills):
    """The rest of the 89 featured codes (site/codes89.csv), by kind of code. Rules are the standard way each kind is
    billed; anything procedure-specific (anesthesia pairings) is left as 'not paired yet' rather than guessed."""
    names = search_names()
    have = {v["main_cpt"] for v in items.values()} | {v["usual_drg"] for v in items.values()}
    rule = "standard billing rule"
    for c in [l.strip() for l in open(os.path.join(ROOT, "site", "codes89.csv")) if l.strip() and l.strip() != "code"]:
        if c in have or c in ("00811", "00812"):   # already listed (colonoscopy's anesthesia codes are its own bill)
            continue
        name = names.get(c, c)
        iid = slug(name)
        n = int(c) if c.isdigit() else 0
        item = dict(item_id=iid, plain_name=name, kind="", usual_setting="", shoppable="yes", main_cpt=c, usual_drg="",
                    status="featured on the site (single-code page)", why_listed="one of the 89 featured procedures")
        B = []
        if len(c) == 3:   # an MS-DRG: the hospital stay itself
            item.update(kind="hospital stay", usual_setting="overnight stay", main_cpt="", usual_drg=c)
            B.append(bill(iid, "hospital or surgery center", "overnight stay", "MS-DRG", c, "institutional", "per stay",
                          "the whole hospital stay; the surgeon and anesthesia bill separately",
                          "check: retired code" if c in RETIRED_DRGS else "official code", RETIRED_DRGS.get(c, DRG_SRC)))
        elif 99202 <= n <= 99499:
            item.update(kind="office visit or checkup", usual_setting="office")
            B.append(bill(iid, "doctor", "office", "CPT", c, "professional", "per visit", "always", rule,
                          "office visits are billed by the clinician"))
            B.append(bill(iid, "hospital (facility fee)", "hospital-owned clinic", "HCPCS / revenue code", "G0463 (Medicare)",
                          "institutional", "per visit", "only at hospital-owned clinics", rule,
                          "hospital outpatient clinics can add a facility fee; Medicare's code is G0463"))
        elif 90785 <= n <= 90899:
            item.update(kind="therapy session", usual_setting="office")
            B.append(bill(iid, "therapist or doctor", "office", "CPT", c, "professional", "per session", "always", rule,
                          "psychotherapy is billed by the clinician"))
        elif 97010 <= n <= 97799:
            item.update(kind="physical therapy", usual_setting="office")
            B.append(bill(iid, "therapist", "office or clinic", "CPT", c, "professional", "per 15-minute unit",
                          "always; a visit is usually several units", rule, "timed therapy codes are billed per 15 minutes"))
        elif 80047 <= n <= 89398 and c != "88305":
            item.update(kind="lab test", usual_setting="lab")
            B.append(bill(iid, "lab", "lab or hospital", "CPT", c, "either", "per test",
                          "a separate blood-draw fee (36415) is common", rule, "lab tests are billed by the lab"))
        elif c == "88305":
            item.update(kind="pathology (tissue check)", usual_setting="lab")
            B.append(bill(iid, "pathology lab (technical part)", "lab", "CPT", c, "institutional", "per specimen",
                          "preparing the tissue sample", rule, "billed as one global fee, or split: technical (TC) + reading (26)"))
            B.append(bill(iid, "pathologist (professional part)", "any", "CPT", c, "professional", "per specimen",
                          "the doctor who reads the sample", rule, "the professional part is billed with modifier 26"))
        elif 70010 <= n <= 79999 or n in (93000, 95810):
            item.update(kind="imaging or test", usual_setting="same day")
            B.append(bill(iid, "imaging center, hospital or sleep lab (technical part)", "same day", "CPT", c,
                          "institutional", "per test", "the equipment and staff", rule,
                          "billed as one global fee, or split: technical (TC) + doctor's reading (26)"))
            B.append(bill(iid, "radiologist or reading doctor (professional part)", "any", "CPT", c, "professional",
                          "per test", "the doctor who reads it; sometimes included in one global fee", rule,
                          "the professional part is billed with modifier 26"))
        else:   # a procedure or surgery done by a doctor, usually same day
            ob = c in ("59400", "59510", "59610")
            item.update(kind="birth" if ob else "procedure", usual_setting="overnight stay" if ob else "same day")
            B.append(bill(iid, "surgeon or doctor", "any", "CPT", c, "professional",
                          "global fee: prenatal visits, delivery and postpartum care" if ob else "per service",
                          "always", rule, "the doctor bills the procedure's CPT code"))
            if ob:
                drg = {"59400": "807", "59510": "788", "59610": "807"}[c]
                B.append(bill(iid, "hospital", "overnight stay", "MS-DRG", drg, "institutional", "per stay",
                              "the delivery stay; the baby's care bills separately", "hand-matched (needs a check)", DRG_SRC))
                B.append(bill(iid, "anesthesia", "any", "anesthesia CPT", "01961" if c == "59510" else "01967",
                              "professional", "base units + time", "if there's an epidural or anesthesia",
                              "hand-matched (needs a check)", "our pairing; CMS anesthesia base-unit file"))
            else:
                B.append(bill(iid, "hospital or surgery center", "same day", "CPT", c, "institutional", "per service",
                              "if done at a hospital or surgery center (not in an office)", rule,
                              "outpatient facilities bill the procedure's CPT code"))
                B.append(bill(iid, "anesthesia", "any", "", "", "", "", "may apply; code not paired yet",
                              "missing: needs a pairing", ""))
        items[iid] = item
        bills += B


def main():
    items, bills = {}, []
    for r in csv.DictReader(open(os.path.join(ROOT, "packages", "packages.csv"), encoding="utf-8")):
        iid = r["package"]
        items.setdefault(iid, dict(item_id=iid, plain_name=r["name"], kind="same-day procedure", usual_setting="same day",
                                   shoppable="yes", main_cpt=r["codes"] if r["role"] == "doctor" else "", usual_drg="",
                                   status="on the site (procedure packages)", why_listed="featured procedure"))
        if r["role"] == "doctor":
            items[iid]["main_cpt"] = r["codes"]
        bills.append(dict(item_id=iid, bill=ROLE.get(r["role"], r["role"]), setting="same day",
                          code_system="anesthesia CPT" if r["role"] == "anesthesia" else "CPT", codes=r["codes"],
                          related_codes=r["family"], billing_class=r["billing_class"],
                          priced_as="base units + time" if r["role"] == "anesthesia" else "per service",
                          when=r["note"], confidence="in use on the site", source="packages/packages.csv"))

    for r in csv.DictReader(open(os.path.join(HERE, "source_crosswalk_oct.csv"), encoding="utf-8-sig")):
        cpt, name = r["surgeon_cpt"], r["surgery"]
        iid = next((k for k, v in items.items() if v["main_cpt"] == cpt), None) or slug(name)
        setting = setting_of(r["setting_note"])
        emergency = "emergency" in (r["setting_note"] or "").lower()
        backed = CMS_BACKED.get(cpt, "")
        if iid in items:   # already a same-day package: add its hospital-stay side
            items[iid].update(usual_setting=setting, usual_drg=r["usual_drg"])
        else:
            items[iid] = dict(item_id=iid, plain_name=name, kind="surgery", usual_setting=setting,
                              shoppable="no (usually an emergency)" if emergency else "yes", main_cpt=cpt,
                              usual_drg=r["usual_drg"], status="draft: not on the site",
                              why_listed=r["why_on_list"])
            bills.append(dict(item_id=iid, bill="surgeon or doctor", setting="any", code_system="CPT", codes=cpt,
                              related_codes="", billing_class="professional", priced_as="per service",
                              when="always", confidence="standard rule", source="the surgeon bills the procedure's CPT code"))
            if setting != "overnight stay":
                bills.append(dict(item_id=iid, bill="hospital or surgery center", setting="same day", code_system="CPT",
                                  codes=cpt, related_codes="", billing_class="institutional", priced_as="per service",
                                  when="if done without an overnight stay", confidence="standard rule",
                                  source="outpatient facilities bill the procedure's CPT/HCPCS code"))
        bills.append(dict(item_id=iid, bill="hospital or surgery center", setting="overnight stay", code_system="MS-DRG",
                          codes=r["usual_drg"], related_codes=r["other_drgs_and_when"], billing_class="institutional",
                          priced_as="per stay (some contracts pay per day instead: shown as 'per day', never compared "
                                    "with whole-stay prices)",
                          when="if admitted; the usual DRG is for a case without complications",
                          confidence="Medicare-backed" if backed else "hand-matched (needs a coder's check)",
                          source=backed or DRG_SRC))
        an = (r["anesthesia_code"] or "").strip()
        if any(x["item_id"] == iid and x["bill"] == "anesthesia" for x in bills):
            continue   # the package already lists its anesthesia bill
        if an and an not in ("none", "not set"):
            two = " or " in an
            bills.append(dict(item_id=iid, bill="anesthesia", setting="any", code_system="anesthesia CPT",
                              codes=an.replace(" or ", "|"), related_codes=r["anesthesia_base_units_cms"],
                              billing_class="professional", priced_as="base units + time",
                              when="when an anesthesiologist or CRNA bills separately",
                              confidence="needs a check (two possible codes)" if two else "hand-matched (needs a check)",
                              source="our pairing; codes and base units from CMS's anesthesia base-unit file"))
        else:
            bills.append(dict(item_id=iid, bill="anesthesia", setting="any", code_system="", codes="",
                              related_codes="", billing_class="", priced_as="",
                              when=(r["anesthesia_status"] or "no pairing chosen yet"),
                              confidence="no separate bill" if an == "none" else "missing: needs a source", source=""))

    featured(items, bills)
    with open(os.path.join(HERE, "care_items.csv"), "w", newline="", encoding="utf-8") as f:   # closed before the crosswalk reads it
        w = csv.DictWriter(f, ITEM_FIELDS)
        w.writeheader()
        w.writerows(sorted(items.values(), key=lambda x: (x["kind"] != "same-day procedure", x["plain_name"])))
    with open(os.path.join(HERE, "care_item_bills.csv"), "w", newline="", encoding="utf-8") as f:   # closed before the crosswalk reads it
        w = csv.DictWriter(f, BILL_FIELDS)
        w.writeheader()
        w.writerows(bills)
    n_backed = sum(1 for b in bills if b["code_system"] == "MS-DRG" and b["confidence"] == "Medicare-backed")
    n_drg = sum(1 for b in bills if b["code_system"] == "MS-DRG")
    print(f"{len(items)} care items, {len(bills)} bills; hospital-stay links Medicare-backed: {n_backed} of {n_drg}")
    import build_crosswalk   # Nov 2: every related code in its own column (crosswalk.csv), bills split the same way
    build_crosswalk.main()


if __name__ == "__main__":
    main()
