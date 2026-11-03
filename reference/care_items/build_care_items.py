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

    w = csv.DictWriter(open(os.path.join(HERE, "care_items.csv"), "w", newline="", encoding="utf-8"), ITEM_FIELDS)
    w.writeheader()
    w.writerows(sorted(items.values(), key=lambda x: (x["kind"] != "same-day procedure", x["plain_name"])))
    w = csv.DictWriter(open(os.path.join(HERE, "care_item_bills.csv"), "w", newline="", encoding="utf-8"), BILL_FIELDS)
    w.writeheader()
    w.writerows(bills)
    n_backed = sum(1 for b in bills if b["code_system"] == "MS-DRG" and b["confidence"] == "Medicare-backed")
    n_drg = sum(1 for b in bills if b["code_system"] == "MS-DRG")
    print(f"{len(items)} care items, {len(bills)} bills; hospital-stay links Medicare-backed: {n_backed} of {n_drg}")


if __name__ == "__main__":
    main()
