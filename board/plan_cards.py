"""The control center's Project plan tab, kept current from chats (Nov 2, 2026; Betsy: "I kind of have no idea where
we are and where we still have to go ... Is there a way for that to not be the case?").

The tab reads R2 control/plan.json (one row per card: id, title, lane, owner, area, next, detail, progress, order,
updated). Until now only chats with R2 keys on Betsy's Mac could change it. This lets any chat do it through GitHub:

  python board/plan_cards.py show                 # print every card, by lane (the workflow puts it in the run summary)
  python board/plan_cards.py apply FILE.json      # add or update cards: a list of cards, matched by id. Fields given
                                                  # replace those fields; fields left out are kept. Cards are never
                                                  # deleted (move them to the "Done" or "Someday" lane instead).
A copy of plan.json is saved to control/plan-backups/<UTC time>.json before every change.
"""
import json
import os
import sys
from datetime import datetime, timezone

import boto3

LANES = ["you", "now", "next", "stuck", "auto", "someday", "done"]   # Your move, Being worked on now, Up next, Stuck, On autopilot, Someday, Done


def r2():
    E = os.environ
    # Nov 9, 2026 (storage move): the control center edits plan.json on R2 itself, so it stays on R2 after the bot moves
    # to Backblaze, and this edits it there (SITE_R2_* = the R2 keys)
    if E.get("STORAGE_ENDPOINT"):
        k = {n: "".join(E.get(n, "").split()) for n in ("SITE_R2_ACCESS_KEY_ID", "SITE_R2_SECRET_ACCESS_KEY", "SITE_R2_BUCKET")}
        if not all(k.values()):
            raise SystemExit("SITE_R2_* secrets missing: the plan lives on R2")
        return boto3.client("s3", endpoint_url=f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com",
                            region_name="auto", aws_access_key_id=k["SITE_R2_ACCESS_KEY_ID"],
                            aws_secret_access_key=k["SITE_R2_SECRET_ACCESS_KEY"]), k["SITE_R2_BUCKET"]
    s3 = boto3.client("s3", endpoint_url=(E.get("STORAGE_ENDPOINT") or f"https://{''.join(E['R2_ACCOUNT_ID'].split())}.r2.cloudflarestorage.com"),
                      aws_access_key_id="".join(E["R2_ACCESS_KEY_ID"].split()), aws_secret_access_key="".join(E["R2_SECRET_ACCESS_KEY"].split()),
                      region_name=(E.get("STORAGE_REGION") or "auto"))
    return s3, "".join(E["R2_BUCKET"].split())


def load(s3, b):
    raw = json.loads(s3.get_object(Bucket=b, Key="control/plan.json")["Body"].read())
    return raw, (raw if isinstance(raw, list) else raw.get("cards", raw.get("rows", [])))


def show(cards):
    out = []
    for lane in LANES + sorted({c.get("lane", "") for c in cards} - set(LANES)):
        cs = sorted((c for c in cards if c.get("lane", "") == lane), key=lambda c: (float(c.get("order") or 999), c.get("title", "")))
        if not cs:
            continue
        out.append(f"\n## {lane} ({len(cs)})\n")
        for c in cs:
            out.append(f"- **{c.get('title', '')}** [{c.get('id', '')}] ({c.get('owner', '')}, {c.get('area', '')}, "
                       f"updated {c.get('updated', '')})")
            if c.get("next"):
                out.append(f"  - Next: {c['next']}")
            if c.get("detail"):
                out.append(f"  - {str(c['detail'])[:400]}")
    return "\n".join(out)


def main():
    s3, b = r2()
    raw, cards = load(s3, b)
    if len(sys.argv) >= 3 and sys.argv[1] == "apply":
        upd = json.load(open(sys.argv[2]))
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        s3.put_object(Bucket=b, Key=f"control/plan-backups/{stamp}.json", Body=json.dumps(raw).encode())
        by = {c.get("id"): c for c in cards}
        added = changed = 0
        today = datetime.now(timezone.utc).date().isoformat()
        for u in upd:
            if not u.get("id"):
                raise SystemExit(f"STOP: a card without an id: {u}")
            if u.get("lane") and u["lane"] not in LANES:
                raise SystemExit(f"STOP: unknown lane {u['lane']!r} (use one of {LANES})")
            u.setdefault("updated", today)
            if u["id"] in by:
                by[u["id"]].update(u)
                changed += 1
            else:
                cards.append(u)
                by[u["id"]] = u
                added += 1
        body = cards if isinstance(raw, list) else dict(raw, **{("cards" if "cards" in raw else "rows"): cards})
        s3.put_object(Bucket=b, Key="control/plan.json", Body=json.dumps(body).encode(), ContentType="application/json",
                      CacheControl="no-cache")
        print(f"plan: {added} cards added, {changed} updated, {len(cards)} in all (backup control/plan-backups/{stamp}.json)")
    text = f"# Project plan ({len(cards)} cards)\n" + show(cards)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text + "\n")
    os.makedirs("out", exist_ok=True)
    json.dump(cards, open("out/plan.json", "w"), indent=1)


if __name__ == "__main__":
    main()
