"""Build the Plan Calculator's DFW plan and cost-sharing tables from the HealthCare.gov Marketplace API.

Usage: MARKETPLACE_API_KEY=... python calculator/api_to_dfw.py 2027 [--out DIR] [--prev calculator/data/2026]
       python calculator/api_to_dfw.py 2026 --check calculator/data/2026   # compare against the PUF build

Why: CMS posts the Marketplace PUFs late (2027 was still missing on Oct 15, 2026). The Marketplace API
serves the same plan data (same issuer filings) as soon as window shopping opens. This writes the same
two files, with the same columns, as puf_to_dfw.py, so oop.py runs on them unchanged:
  dfw_exchange_plans_<year>.csv, dfw_exchange_cost_sharing_<year>.csv
When the PUFs come out, the calculator workflow rebuilds from them (the PUF build is the reference copy).

What the API does not give, and how it is filled:
  network_name / network_id: not in the API. Copied from the previous year's table for the same 14-character
    plan ID, else from the same insurer + network web address when that points to exactly one network.
    Anything still blank shows up in oop.py's unmatched_networks file for review.
  "Expanded Bronze": the API says "Bronze". Kept as "Expanded Bronze" when last year's same plan ID was.
Key: free, from https://developer.cms.gov/marketplace-api/key-request.html. Passed as ?apikey=.
"""
import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from puf_to_dfw import BENEFITS, DFW, parse  # noqa: E402  same benefit list, counties and string parsing

API = "https://marketplace.api.healthcare.gov/api/v1"
# Several ZIPs per county so plans whose service area covers only part of a county are still found.
ZIPS = ["75002", "75070", "75093", "75098", "75201", "75080", "75061", "75150", "75217", "75038",
        "76201", "75067", "75034", "76226", "75165", "75104", "76048", "75401", "76031", "76028",
        "75142", "75126", "76086", "76008", "75087", "75032", "76102", "76010", "76137", "76051",
        "76234", "76020"]
CSR = {"CSR73": ("04", "CSR 73%", "73%"), "CSR87": ("05", "CSR 87%", "87%"), "CSR94": ("06", "CSR 94%", "94%")}
HOUSEHOLD = {"income": 150000, "people": [{"age": 40, "aptc_eligible": False, "uses_tobacco": False, "gender": "Female"}],
             "has_married_couple": False}


class Client:
    def __init__(self, key):
        self.s, self.key = requests.Session(), key

    def call(self, method, path, ok404=False, **kw):
        params = {"apikey": self.key, **kw.pop("params", {})}
        for i in range(6):
            r = self.s.request(method, API + path, params=params, timeout=60, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i)
                continue
            if r.status_code == 404 and ok404:
                return None
            if r.status_code >= 400:
                raise SystemExit(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
            return r.json()
        raise SystemExit(f"{method} {path} kept failing (last HTTP {r.status_code})")


def money(v, per_person=False):
    if v is None or v == "":
        return ""
    v = float(v)
    return f"${v:.0f} per person" if per_person else f"${v:,.0f}"


def pick(items, word, csr_label, family=False):
    """In-network individual (or family-per-person) amount whose type contains `word`, for this CSR variant."""
    hits = [x for x in items or [] if word in (x.get("type") or "").lower()
            and (x.get("network_tier") or "In-Network") == "In-Network"
            and (bool(x.get("family")) == family) and (not family or "Per Person" in (x.get("family_cost") or ""))]
    mine = [x for x in hits if csr_label in (x.get("csr") or "")] or hits
    return mine[0].get("amount") if mine else None


def raw_strings(c):
    """Rebuild the PUF-style strings ("$30.00 Copay after deductible", "20.00% Coinsurance after deductible")."""
    co, ci = (c.get("copay_options") or "").lower(), (c.get("coinsurance_options") or "").lower()
    ds = (c.get("display_string") or "").lower()
    amt, rate = c.get("copay_amount"), c.get("coinsurance_rate")
    unit = " per Stay" if "per stay" in ds else " per Day" if "per day" in ds else ""
    if "no charge" in co:
        copay = "No Charge after deductible" if "after" in co else "No Charge"
    elif amt is not None and amt != "" and (float(amt) > 0 or "copay" in co):
        when = " after deductible" if "after" in co else " with deductible" if "with" in co else ""
        copay = f"${float(amt):,.2f}" + (f" Copay{unit}{when}" if unit or when else "")
    else:
        copay = "Not Applicable"
    if "no charge" in ci:
        coins = "No Charge after deductible" if "after" in ci else "No Charge"
    elif rate is not None and rate != "" and (float(rate) > 0 or "coinsurance" in ci):
        pct = float(rate) * 100 if float(rate) <= 1 else float(rate)
        coins = f"{pct:.2f}%" + (" Coinsurance after deductible" if "after" in ci else "")
    else:
        coins = "Not Applicable"
    return copay, coins


COUNTY_PLACE = {}   # county name -> one ZIP/FIPS in it (filled by discover, used by the crosswalk)


def crosswalk(cl, year, pv):
    """{new plan_id14: last year's plan_id14} from the Marketplace API crosswalk, for last year's DFW plans."""
    out = {}
    for old, counties in pv.assign(b=pv.plan_id.str[:14]).drop_duplicates("b")[["b", "dfw_counties"]].itertuples(index=False):
        for c in [x.strip() for x in counties.split(";") if x.strip() in COUNTY_PLACE][:2]:
            pl = COUNTY_PLACE[c]
            r = cl.call("GET", "/crosswalk", ok404=True, params={"year": year - 1, "plan_id": old, "state": "TX",
                                                                 "zipcode": pl["zipcode"], "fips": pl["countyfips"]})
            time.sleep(0.2)
            new = ((r or {}).get("new_plan_id") or "")[:14]
            if new:
                out.setdefault(new, old)
                break
    return out


def discover(cl, year):
    """Every on-exchange individual plan sold in a DFW county: {plan_id14: (place, set(counties))}."""
    found = {}
    for z in ZIPS:
        for cty in cl.call("GET", f"/counties/by/zip/{z}", params={"year": year}).get("counties", []):
            name = DFW.get(cty["fips"])
            if not name or cty.get("zipcode", z) != z:
                continue
            place = {"countyfips": cty["fips"], "state": "TX", "zipcode": z}
            COUNTY_PLACE.setdefault(name, place)
            off, total = 0, 1
            while off < total:
                r = cl.call("POST", "/plans/search", json={"household": HOUSEHOLD, "place": place, "market": "Individual",
                                                         "year": year, "offset": off, "catastrophic_override": True})
                total = r.get("total", 0)
                for p in r.get("plans", []):
                    f = found.setdefault(p["id"], [place, set()])
                    f[1].add(name)
                off += 10
                time.sleep(0.2)
    return found


def details(cl, year, ids_places, csr=None):
    out, by_place = {}, {}
    for pid, (place, _) in ids_places.items():
        by_place.setdefault(tuple(place.items()), []).append(pid)
    for pl, ids in by_place.items():
        for i in range(0, len(ids), 10):
            body = {"household": HOUSEHOLD, "place": dict(pl), "market": "Individual", "year": year, "plan_ids": ids[i:i + 10]}
            if csr:
                body["csr_override"] = csr
            for p in cl.call("POST", "/plans", json=body).get("plans", []):
                out[p["id"]] = p
            time.sleep(0.2)
    return out


def build(cl, year, prev, force_crosswalk=False):
    found = discover(cl, year)
    if not found:
        raise SystemExit(f"The API returned no {year} DFW plans (not available yet?)")
    std = details(cl, year, found)
    silver = {k: v for k, v in found.items() if (std.get(k) or {}).get("metal_level") == "Silver"}
    variants = [(pid, "01", "standard", "Exchange variant", p) for pid, p in std.items()]
    for code, (sfx, label, csr_word) in CSR.items():
        variants += [(pid, sfx, label, csr_word, p) for pid, p in details(cl, year, silver, code).items()]

    pv = pd.read_csv(Path(prev) / f"dfw_exchange_plans_{year - 1}.csv", dtype=str, keep_default_na=False) if prev else None
    by_id = pv.assign(b=pv.plan_id.str[:14]).drop_duplicates("b").set_index("b") if pv is not None else None
    by_url = (pv.groupby(["insurer", "network_url"]).filter(lambda g: g.network_name.nunique() == 1)
              .drop_duplicates(["insurer", "network_url"]).set_index(["insurer", "network_url"])) if pv is not None else None

    xw = crosswalk(cl, year, pv) if pv is not None else {}
    how = {"same plan ID": 0, "crosswalk": 0, "network URL": 0, "none": 0}
    rows, cs = [], []
    want = {" ".join(n.lower().split()): n for n in BENEFITS}   # match names ignoring case/spacing
    seen_other, moop_kinds = {}, set()
    stamp = dt.date.today().isoformat()
    for pid, sfx, label, csr_word, p in variants:
        iss = (p.get("issuer") or {}).get("name", "").strip()
        metal, net_name, net_id = p.get("metal_level", ""), "", ""
        old = None
        if by_id is not None and pid in by_id.index and not force_crosswalk:
            old, kind = pid, "same plan ID"
        elif by_id is not None and xw.get(pid) in by_id.index and (not iss or by_id.loc[xw[pid]].insurer == iss):
            old, kind = xw[pid], "crosswalk"   # renumbered plan: same insurer, so same network
        if old is not None:
            o = by_id.loc[old]
            net_name, net_id = o.network_name, o.network_id
            iss = iss if iss else o.insurer
            if metal == "Bronze" and o.metal == "Expanded Bronze":
                metal = "Expanded Bronze"
            how[kind] += sfx == "01"
        elif by_url is not None and (iss, p.get("network_url", "")) in by_url.index:
            o = by_url.loc[(iss, p.get("network_url", ""))]
            net_name, net_id = o.network_name, o.network_id
            how["network URL"] += sfx == "01"
        else:
            how["none"] += sfx == "01"
        t_ded = money(pick(p.get("deductibles"), "combined", csr_word))
        m_ded = money(pick(p.get("deductibles"), "medical ehb", csr_word)) if not t_ded else ""
        rows.append(dict(
            plan_year=str(year), plan_id=f"{pid}-{sfx}", insurer=iss, plan_name=p.get("name", ""), variant=label,
            metal=metal, plan_type=p.get("type", ""), network_name=net_name, network_id=net_id,
            deductible_individual=t_ded, oop_max_individual=money(pick(p.get("moops"), "medical and drug", csr_word)),
            oop_max_family_per_person=money(pick(p.get("moops"), "medical and drug", csr_word, family=True), per_person=True),
            med_deductible_individual_if_separate=m_ded,
            med_oop_max_individual_if_separate=money(pick(p.get("moops"), "medical ehb", csr_word)) if m_ded else "",
            dfw_counties="; ".join(sorted(found[pid][1])), sbc_url=p.get("benefits_url", ""), brochure_url=p.get("brochure_url", ""),
            network_url=p.get("network_url", ""), referral_required="Yes" if p.get("specialist_referral_required") else "No",
            source=f"HealthCare.gov Marketplace API {year} (pulled {stamp})", deductible_for_calc=t_ded or m_ded))
        for m in p.get("moops") or []:
            moop_kinds.add((m.get("type"), m.get("family"), m.get("family_cost"), m.get("network_tier")))
        for b in p.get("benefits") or []:
            name = want.get(" ".join((b.get("name") or "").lower().split()))
            if not name:
                seen_other[b.get("name")] = seen_other.get(b.get("name"), 0) + 1
                continue
            b = {**b, "name": name}
            shares = [c for c in b.get("cost_sharings") or [] if (c.get("network_tier") or "In-Network") == "In-Network"]
            c = ([x for x in shares if csr_word in (x.get("csr") or "")] or shares or [{}])[0]
            copay, coins = raw_strings(c)
            cs.append(dict(plan_id=f"{pid}-{sfx}", benefit=b["name"], is_covered="Covered" if b.get("covered") else "Not Covered",
                           copay_raw=copay, coinsurance_raw=coins, **parse(copay, coins), notes=(b.get("explanation") or "").strip()))
    print(f"Network names for {sum(how.values())} standard plans, by source:", how,
          f"(crosswalk pairs found: {len(xw)})")
    print("API benefit names not used (name: plans):", dict(sorted(seen_other.items())))
    print("API moop kinds (type, family, family_cost, tier):", sorted(moop_kinds, key=str))
    pl = pd.DataFrame(rows).sort_values("plan_id").reset_index(drop=True)
    cols = ["plan_id", "benefit", "is_covered", "copay_raw", "coinsurance_raw", "copay_amount", "copay_unit", "copay_timing",
            "coinsurance_pct", "coinsurance_timing", "deductible_applies", "cost_share_type", "notes"]
    return pl, pd.DataFrame(cs, columns=cols).sort_values(["plan_id", "benefit"]).reset_index(drop=True)


def check(pl, cs, ref, year):
    """Compare an API build with the PUF build for the same year: what matches, what doesn't."""
    rp = pd.read_csv(Path(ref) / f"dfw_exchange_plans_{year}.csv", dtype=str, keep_default_na=False)
    rc = pd.read_csv(Path(ref) / f"dfw_exchange_cost_sharing_{year}.csv", dtype=str, keep_default_na=False)
    a, b = set(pl.plan_id), set(rp.plan_id)
    print(f"plans: API {len(a)}, PUF {len(b)}, both {len(a & b)}; only API {sorted(a - b)[:10]}; only PUF {sorted(b - a)[:10]}")
    m = pl.merge(rp, on="plan_id", suffixes=("_api", "_puf"))
    for col in ["insurer", "metal", "plan_type", "network_name", "deductible_for_calc", "oop_max_individual",
                "oop_max_family_per_person", "dfw_counties", "referral_required"]:
        bad = m[m[col + "_api"] != m[col + "_puf"]]
        print(f"  {col}: {len(bad)} differ", "" if bad.empty else bad[["plan_id", col + "_api", col + "_puf"]].head(3).to_dict("records"))
    k = ["plan_id", "benefit"]
    m = cs.merge(rc, on=k, suffixes=("_api", "_puf"))
    print(f"cost-sharing rows: API {len(cs)}, PUF {len(rc)}, both {len(m)}")
    miss = rc.merge(cs[k], on=k, how="left", indicator=True).query("_merge == 'left_only'")
    print("  PUF rows the API lacks, by benefit:", miss.benefit.value_counts().to_dict())
    for col in ["copay_amount", "copay_unit", "copay_timing", "coinsurance_pct", "coinsurance_timing", "deductible_applies"]:
        x, y = m[col + "_api"].astype(str).str.replace(".0", "", regex=False), m[col + "_puf"].astype(str).str.replace(".0", "", regex=False)
        bad = m[x != y]
        print(f"  {col}: {len(bad)} differ", "" if bad.empty else bad[k + ["copay_raw_api", "copay_raw_puf", "coinsurance_raw_api", "coinsurance_raw_puf"]].head(3).to_dict("records"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("--out", default=".")
    ap.add_argument("--prev", default="", help="folder with last year's tables (for network names); default calculator/data/<year-1>")
    ap.add_argument("--force-crosswalk", action="store_true", help="test only: ignore same-ID matches so the crosswalk is used")
    ap.add_argument("--check", default="", help="folder with a PUF build of the same year to compare against")
    a = ap.parse_args()
    key = os.environ.get("MARKETPLACE_API_KEY")
    if not key:
        raise SystemExit("Set MARKETPLACE_API_KEY (free key: https://developer.cms.gov/marketplace-api/key-request.html)")
    cl = Client(key)
    years = cl.call("GET", "/market-years")
    print("API market years:", years)
    prev = a.prev or str(Path(__file__).resolve().parent / "data" / str(a.year - 1))
    pl, cs = build(cl, a.year, prev if Path(prev, f"dfw_exchange_plans_{a.year - 1}.csv").exists() else "", a.force_crosswalk)
    Path(a.out).mkdir(parents=True, exist_ok=True)
    pl.to_csv(Path(a.out) / f"dfw_exchange_plans_{a.year}.csv", index=False)
    cs.to_csv(Path(a.out) / f"dfw_exchange_cost_sharing_{a.year}.csv", index=False)
    (Path(a.out) / "SOURCE.txt").write_text(f"HealthCare.gov Marketplace API, pulled {dt.date.today()}\n")
    print(f"{a.year}: {len(pl)} plan variants ({(pl.variant == 'standard').sum()} standard) from "
          f"{pl.insurer.nunique()} insurers; {len(cs)} cost-sharing rows; {(pl.network_name == '').sum()} without a network name")
    print(pl[pl.variant == "standard"].groupby("insurer").size().to_string())
    if a.check:
        check(pl, cs, a.check, a.year)
