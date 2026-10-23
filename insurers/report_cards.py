"""Insurer report cards: how usable each insurer's own price files are, from what the bots already record.

Facts only, one row per insurer, each with a stated test (no blended score, nothing estimated):
  1. Files we could find and open   networks whose current file is reachable and read without error
  2. Kept up to date                file's own "last updated" date within 45 days (the rule says monthly)
  3. Real dollar amounts            share of dollar-type prices that are $0.00 placeholders
  4. Providers with no prices       providers the insurer lists in-network that have no price at all
  5. Contract end dates             share of prices with an end date, and share already past it
Inputs (R2): bot/insurers[/tx|/s7]/manifest.csv and bot/insurers/census/<yyyy-mm>/<scope>/<table>.json.
Outputs: reports/insurer_report_cards/<yyyy-mm>.md (for review) and R2 site/watch/insurer_report_cards.json
(for the Price File Watch page once Betsy approves the wording).
Run: python insurers/report_cards.py [YYYY-MM]
"""
import csv
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import boto3

E = {k: "".join(os.environ.get(k, "").split()) for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")}
B = E["R2_BUCKET"] or "upfrontdfwdata"
MONTH = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m")
TODAY = date.today()
SCOPES = {"dfw": ("bot/insurers/", "data_full"), "tx": ("bot/insurers/tx/", "data_tx"), "s7": ("bot/insurers/s7/", "data_s7"), "nc": ("bot/insurers/nc/", "data_nc"), "ct": ("bot/insurers/ct/", "data_ct"), "il": ("bot/insurers/il/", "data_il"), "n5": ("bot/insurers/n5/", "data_n5"), "ar": ("bot/insurers/ar/", "data_ar"), "b1": ("bot/insurers/b1/", "data_b1"), "la": ("bot/insurers/la/", "data_la"), "b4": ("bot/insurers/b4/", "data_b4"), "az": ("bot/insurers/az/", "data_az")}
AREA = {"dfw": "Dallas-Fort Worth", "tx": "Texas", "s7": "TN, CO, OK, AL, MS, MO, GA", "nc": "North Carolina", "ct": "Connecticut", "il": "Illinois", "n5": "NY, CA, VA, DC, FL, WI", "ar": "Arkansas", "b1": "MD, NM, MT", "la": "Louisiana", "b4": "IN, KY, OH", "az": "Arizona"}
UP_TO_DATE_DAYS = 45
OUT = Path(__file__).resolve().parent.parent / "reports" / "insurer_report_cards"


def s3c():
    return boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com", aws_access_key_id=E["R2_ACCESS_KEY_ID"],
                        aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def days_old(s):
    try:
        return (TODAY - date.fromisoformat(str(s)[:10])).days
    except Exception:
        return None


HERE = Path(__file__).resolve().parent
NETS = {"s7": "networks_s7.csv", "nc": "networks_nc.csv", "ct": "networks_ct.csv", "il": "networks_il.csv", "n5": "networks_n5.csv", "ar": "networks_ar.csv", "b1": "networks_b1.csv", "la": "networks_la.csv", "b4": "networks_b4.csv", "az": "networks_az.csv"}  # dfw and tx use networks.csv


def main():
    s3 = s3c()
    cards = defaultdict(lambda: defaultdict(lambda: dict(networks=0, reachable=0, problems=[], dated=0, current=0, rows=0, dollar=0, zero=0,
                                                         roster=0, no_price=0, ends=0, past=0, files_counted=0)))
    for scope, (pfx, cdir) in SCOPES.items():
        try:
            man = list(csv.DictReader(io.StringIO(s3.get_object(Bucket=B, Key=pfx + "manifest.csv")["Body"].read().decode())))
        except Exception as e:
            print(f"{scope}: no manifest ({e})"); continue
        off = {n["slot"] for n in csv.DictReader(open(HERE / NETS.get(scope, "networks.csv"))) if n.get("enabled", "yes") != "yes"}
        census = {}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=B, Prefix=f"bot/insurers/census/{MONTH}/{cdir}/"):
            for o in page.get("Contents", []):
                census[o["Key"].rsplit("/", 1)[1][:-5]] = o["Key"]
        for m in man:
            c = cards[m.get("insurer") or "?"][scope]
            c["networks"] += 1
            d = (m.get("detail") or "").lower()
            broken = m.get("status") == "failed" or "link broken" in d or "could not check" in d or "keeping the last good" in d
            if m.get("slot") in off:  # the bot stopped looking: the insurer's file page or links are gone
                c["problems"].append(f"{m.get('network_label')}: file no longer posted where the insurer listed it; showing our last copy")
            elif broken:
                c["problems"].append(f"{m.get('network_label')}: {(m.get('detail') or m.get('status'))[:120]}")
            elif m.get("status") in ("processed", "queued", "running") and m.get("table"):
                c["reachable"] += 1
            age = days_old(m.get("file_last_updated_on"))
            if age is not None:
                c["dated"] += 1
                c["current"] += age <= UP_TO_DATE_DAYS
            k = census.get(m.get("table", ""))
            if not k:
                continue
            j = json.loads(s3.get_object(Bucket=B, Key=k)["Body"].read())
            if j.get("census_version", 1) < 2:
                continue  # older inventory without the $0 and roster counts; the backfill is redoing it
            c["files_counted"] += 1
            c["rows"] += j.get("rows", 0)
            c["dollar"] += j.get("dollar_rows", 0)
            c["zero"] += j.get("zero_dollar_rows", 0)
            c["roster"] += j.get("roster_rows", 0) or 0
            c["no_price"] += j.get("roster_listed_no_prices", 0) or 0
            c["ends"] += sum(e["prices"] for e in j.get("contract_ends_by_month", []) if e["month"] not in ("blank", "no set end"))
            c["past"] += j.get("prices_already_past_end_date", 0)

    out = []
    for ins, by in sorted(cards.items()):
        for scope, c in by.items():
            out.append(dict(insurer=ins, area=AREA[scope], scope=scope, networks=c["networks"],
                            files_found_and_read=c["reachable"], files_with_problems=len(c["problems"]), problems=c["problems"][:10],
                            files_updated_within_45_days=c["current"], files_with_a_date=c["dated"],
                            pct_zero_dollar_prices=pct(c["zero"], c["zero"] + c["dollar"]),
                            pct_providers_listed_with_no_prices=pct(c["no_price"], c["roster"]),
                            pct_prices_with_end_date=pct(c["ends"], c["rows"]), pct_prices_past_end_date=pct(c["past"], c["rows"]),
                            files_inventoried=c["files_counted"], price_rows=c["rows"]))
    OUT.mkdir(parents=True, exist_ok=True)
    f = lambda v: "—" if v is None else f"{v}%"
    L = [f"# Insurer report cards: {MONTH}", "",
         "How usable each insurer's own price files are, from what our bots recorded. Facts only, each with a stated test; "
         "no blended grade. For review before anything goes on the Price File Watch.", "",
         "- **Found and read:** networks whose current file we could reach and read without error.",
         f"- **Up to date:** the file's own 'last updated' date is within {UP_TO_DATE_DAYS} days (the rule requires monthly updates).",
         "- **$0.00 prices:** share of dollar-type prices listed as $0.00, which tells a patient nothing.",
         "- **Listed, no prices:** providers the insurer lists in-network in our area that have no price at all in the file.",
         "- **End dates:** share of prices with a real contract end date (placeholders like 9999-12-31 don't count); and the share whose end date has already passed.", "",
         "Counts cover the providers in each area only. '—' = not measured yet (inventory still being filled in).", ""]
    for scope in SCOPES:
        rows = [r for r in out if r["scope"] == scope]
        if not rows:
            continue
        L += [f"## {AREA[scope]}", "", "| Insurer | Found and read | Up to date | $0.00 prices | Listed, no prices | With end date | Past end date |",
              "|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['insurer']} | {r['files_found_and_read']} of {r['networks']} | {r['files_updated_within_45_days']} of {r['files_with_a_date']} | "
                     f"{f(r['pct_zero_dollar_prices'])} | {f(r['pct_providers_listed_with_no_prices'])} | {f(r['pct_prices_with_end_date'])} | "
                     f"{f(r['pct_prices_past_end_date'])} |")
        probs = [(r["insurer"], p) for r in rows for p in r["problems"]]
        if probs:
            L += ["", "Problems found:", ""] + [f"- {i}: {p}" for i, p in probs]
        L.append("")
    (OUT / f"{MONTH}.md").write_text("\n".join(L) + "\n")
    s3.put_object(Bucket=B, Key="site/watch/insurer_report_cards.json",
                  Body=json.dumps({"month": MONTH, "built": TODAY.isoformat(), "cards": out}, indent=1).encode())
    print(f"{len(out)} insurer x area cards -> reports/insurer_report_cards/{MONTH}.md")


if __name__ == "__main__":
    main()
