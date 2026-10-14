"""Check one state's hospital price files: find the current link, see if it changed, save new versions.

  python bot/run.py --state TX            # normal daily run (only hospitals due today)
  python bot/run.py --state TX --all      # every hospital in the state
  python bot/run.py --state RI --limit 3 --local   # try it without R2 (writes to ./local/)

For each hospital due today:
  1. Read its cms-hpt.txt and pick its file link (discover.py).
  2. Check the file without downloading if possible; download only if changed or unproven (check.py).
  3. New version: save the original (zstd) to R2 raw/hospitals/<yyyy-mm>/<state>/<sha12>_<name>.zst and
     to archive.org, count its rows with the fixed reader, extract the site's target codes.
  4. Write one status row per hospital (for the coverage spreadsheet and the Price File Watch) and
     flag problems: broken/missing file, not a price file, unreadable, rows down by more than half.
Hospitals sharing one system-wide file are checked once.
Files over the size cap (Oct 14, 2026) go into the shared machine queue (insurers/fleet.py) as a "hospital" job. A rented
machine with enough disk runs the same steps (process_file) on it and saves the result to R2
bot/fleet/results/hospital/<state>/<id>.json; the state's next daily run folds that result into its manifests and status.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import zstandard

sys.path.insert(0, str(Path(__file__).parent))
import check  # noqa: E402
import discover  # noqa: E402
import reader  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 6 * 1024 ** 3      # GitHub's free runner has ~14 GB disk; original + compressed copy must fit
DROP_ALERT = 0.5               # alert when rows fall by more than half
FIRST_WEEK_ENDS = date(2026, 10, 19)

FILE_FIELDS = ["url", "etag", "last_modified", "size", "sample_fp", "sha256", "bytes", "r2_key", "format",
               "records", "file_last_updated_on", "first_seen", "last_checked", "last_changed",
               "last_full_download", "fails", "last_error"] + reader.ATTEST_FIELDS
HOSP_FIELDS = ["ccn", "mrf_url", "index_url", "status", "alert", "last_checked", "last_ok"]
STATUS_FIELDS = ["checked_at", "state", "ccn", "hospital", "city", "type", "status", "alert", "detail",
                 "mrf_url", "index_url", "index_found", "link_source", "link_changed", "check_method", "http",
                 "etag", "last_modified", "size", "sha256", "r2_key", "ia_item", "records", "prev_records",
                 "file_last_updated_on", "first_seen", "last_changed", "cert_unverified",
                 "file_version", "license_number", "license_state", "attested", "attester_name"]

QUEUED = "queued for a rented machine"
RESULTS = f"{store.R2_PREFIX}fleet/results/hospital/"

PROBLEM = {"link broken", "not a price file", "unreadable file", "no price file found", "too large for free runner"}


def due(h, hosp_prev, today, force):
    if force:
        return True
    last = (hosp_prev or {}).get("last_checked", "")
    bucket = int(hashlib.md5(h["ccn"].encode()).hexdigest(), 16) % 7 == today.weekday()
    if not last:                                        # first check: spread over the first week,
        return bucket or today >= FIRST_WEEK_ENDS       # then sweep up anything a time limit left over
    age = (today - date.fromisoformat(last[:10])).days
    if age >= 8:
        return True                                     # overdue (e.g. a run hit the time limit)
    if hosp_prev.get("status") in PROBLEM and hosp_prev.get("status") != "no price file found" and age >= 1:
        return True                                     # retry broken links daily
    found = (h.get("found_by") or "").split()[-1:]      # a site/file link found (find_sites, search_files) since the
    if found and found[0] > last[:10] and age >= 1:     # last check: check it on the next daily run, not next week
        return True
    return bucket and age >= 1


class Saver:
    """Keeps the state's manifests and today's status rows, in R2 (or ./local/ when testing)."""

    def __init__(self, state, day, local):
        self.state, self.day, self.local = state, day, local
        self.keys = dict(files=f"{store.R2_PREFIX}manifest/files/{state}.csv",
                         hosp=f"{store.R2_PREFIX}manifest/hospitals/{state}.csv",
                         status=f"{store.R2_PREFIX}status/{day}/{state}.csv")
        if local:
            self.dir = ROOT / "local"
        else:
            self.s3, self.bucket = store.r2()

    def read(self, which):
        if self.local:
            p = self.dir / self.keys[which]
            return list(csv.DictReader(open(p))) if p.exists() else []
        return store.read_csv(self.s3, self.bucket, self.keys[which])

    def write(self, which, rows, fields):
        if self.local:
            p = self.dir / self.keys[which]
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", newline="") as f:
                w = csv.DictWriter(f, fields, extrasaction="ignore")
                w.writeheader(); w.writerows(rows)
        else:
            store.write_csv(self.s3, self.bucket, self.keys[which], rows, fields)

    def put_file(self, path, key):
        if self.local:
            p = self.dir / key
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(path, p)
        elif not store.exists(self.s3, self.bucket, key):
            self.s3.upload_file(str(path), self.bucket, key)


def safe_name(url):
    return re.sub(r"[^A-Za-z0-9._-]", "_", url.split("?")[0].rstrip("/").split("/")[-1])[-120:] or "file"


def extract_codes(raw, out_csv, meta):
    """Target-code rows from one file, with the same trace columns as the October runs."""
    parser = reader.parse_json if reader.is_json(raw) else reader.parse_csv
    n = 0
    with open(out_csv, "w", newline="") as fo:
        w = csv.DictWriter(fo, reader.FIELDS + ["state", "ccn"], extrasaction="ignore")
        w.writeheader()
        for row in parser(raw):
            w.writerow(dict(row, **meta)); n += 1
    return n


def process_file(url, prev, ctx):
    """Check / download one file. Returns (file_entry, result dict shared by every hospital on this file)."""
    now = ctx["now"]
    e = dict(prev or {}, url=url, last_checked=now)
    e.setdefault("first_seen", now)
    res = dict(status="", alert="", detail="", check_method="", http="", cert_unverified="", ia_item="",
               prev_records=(prev or {}).get("records", ""))

    def fail(status, detail):
        e["fails"] = str(int(e.get("fails") or 0) + 1)
        e["last_error"] = detail[:300]
        res.update(status=status, alert="yes", detail=detail[:300])
        return e, res

    h = check.headers(url)
    res["http"] = h["http"]
    if not h["ok"]:
        return fail("link broken", h["error"])
    if h.get("html"):
        return fail("not a price file", "link returns a web page (text/html), not a price file")
    e["etag"], e["last_modified"] = h["etag"] or e.get("etag", ""), h["last_modified"] or e.get("last_modified", "")

    same, why = check.unchanged_by_headers(prev, h)
    fp = check.sample_fingerprint(h["final_url"], h["size"]) if h["ranges"] else ""
    if not same and fp and prev and prev.get("sha256") and fp == prev.get("sample_fp") and h["size"] == prev.get("size"):
        same, why = True, "same size and first/last 64 KB"
    last_full = (prev or {}).get("last_full_download", "")
    full_due = not last_full or (ctx["today"] - date.fromisoformat(last_full[:10])).days >= check.FULL_EVERY_DAYS
    if same and not full_due and (prev or {}).get("records"):
        e["size"], e["sample_fp"], e["fails"], e["last_error"] = h["size"] or e.get("size", ""), fp or e.get("sample_fp", ""), "0", ""
        res.update(status="unchanged", check_method=why, records=e.get("records", ""))
        return e, res

    if h["size"].isdigit() and int(h["size"]) > MAX_BYTES:
        e["size"] = h["size"]
        if ctx.get("enqueue"):
            res.update(status=QUEUED, detail=ctx["enqueue"](url, int(h["size"]), prev))
            return prev, res
        return fail("too large for free runner", f"{int(h['size']) / 1024 ** 3:.1f} GB; needs a rented machine")
    if time.time() > ctx["stop_downloads_at"]:
        res.update(status="skipped", detail="time limit reached; checked next run")
        return prev, res

    work = ctx["work"]
    raw, zst = work / "f.raw", work / "f.zst"
    for p in (raw, zst):
        p.unlink(missing_ok=True)
    try:
        ok, err, insecure = check.download(h["final_url"], str(raw))
        if not ok:
            return fail("link broken", err)
        res["cert_unverified"] = "yes" if insecure else ""
        if raw.stat().st_size > MAX_BYTES:
            if ctx.get("enqueue"):
                res.update(status=QUEUED, detail=ctx["enqueue"](url, raw.stat().st_size, prev))
                return prev, res
            return fail("too large for free runner", f"{raw.stat().st_size / 1024 ** 3:.1f} GB")
        if check.looks_like_web_page(raw):
            return fail("not a price file", "link returns a web page, not a price file")
        sha, nbytes = check.sha256_file(raw)
        e.update(size=h["size"] or str(nbytes), sample_fp=fp, last_full_download=now)
        method = (why + "; " if why else "") + "full download"
        if prev and sha == prev.get("sha256"):
            if not prev.get("records"):  # seeded from the October runs: count rows once
                fmt, n, _, upd = reader.count_records(raw)
                e.update(format=fmt, records=str(n), file_last_updated_on=upd)
            if not e.get("file_version") and not e.get("attested"):  # older entries: read the header once
                e.update(reader.header_info(raw))
            e.update(fails="0", last_error="")
            res.update(status="unchanged", check_method=method + ", same SHA-256", records=e.get("records", ""))
            return e, res
        try:
            fmt, n, _, upd = reader.count_records(raw)
        except Exception as ex:
            fmt, n, upd = "", None, ""
            read_err = f"{type(ex).__name__}: {str(ex)[:200]}"
        # Save the original even if unreadable: it is the evidence for the Price File Watch.
        with open(raw, "rb") as fi, open(zst, "wb") as fz:
            zstandard.ZstdCompressor(level=6, threads=-1).copy_stream(fi, fz)
        key = f"raw/hospitals/{ctx['month']}/{ctx['state']}/{sha[:12]}_{safe_name(url)}.zst"
        ctx["saver"].put_file(zst, key)
        if not ctx["local"]:
            ia_err = store.ia_upload(str(zst), ctx["state"], ctx["month"], key.split("/")[-1])
            res["ia_item"] = "" if ia_err else store.ia_item(ctx["state"], ctx["month"])
            if ia_err:
                res["detail"] = ia_err
        old_records = (prev or {}).get("records", "")
        e.update(sha256=sha, bytes=str(nbytes), r2_key=key, last_changed=now, format=fmt,
                 records="" if n is None else str(n), file_last_updated_on=upd, fails="0", last_error="",
                 **reader.header_info(raw))
        res.update(status="changed - new version saved" if prev and prev.get("sha256") else "new - first version saved",
                   check_method=method, records=e["records"])
        if n is None:
            res.update(status="unreadable file", alert="yes", detail=read_err)
            e["last_error"] = read_err
        elif old_records.isdigit() and int(old_records) > 0 and n < int(old_records) * (1 - DROP_ALERT):
            res.update(alert="yes", detail=f"rows fell from {int(old_records):,} to {n:,}")
        if n and ctx["codes"]:
            out_csv = work / "rows.csv"
            try:
                meta = dict(raw_key=key, source_url=url, sha256=sha, state=ctx["state"], ccn=";".join(ctx["ccns_for"][url]))
                if extract_codes(raw, out_csv, meta):
                    with open(out_csv, "rb") as fi, open(str(out_csv) + ".zst", "wb") as fz:
                        zstandard.ZstdCompressor(level=6).copy_stream(fi, fz)
                    ctx["saver"].put_file(Path(str(out_csv) + ".zst"),
                                          f"{store.R2_PREFIX}rows/{ctx['day']}/{ctx['state']}/{sha[:12]}.csv.zst")
            except Exception as ex:
                res["detail"] = (res["detail"] + "; " if res["detail"] else "") + f"code extraction failed: {ex}"[:200]
        return e, res
    finally:
        for p in (raw, zst, work / "rows.csv", work / "rows.csv.zst"):
            p.unlink(missing_ok=True)


def machine_size(nbytes):
    """A machine whose disk holds the original, its compressed copy and the extracted rows (about 2.3x the file):
    8 GB machines have 160 GB of disk, 16 GB machines 320 GB, 32 GB machines 640 GB."""
    gb = nbytes / 1024 ** 3
    return "s-4vcpu-8gb" if gb <= 60 else "s-8vcpu-16gb-amd" if gb <= 130 else "s-8vcpu-32gb-amd"


def file_id(state, url):
    return f"{state}-{hashlib.sha1(url.encode()).hexdigest()[:12]}"


def enqueuer(state, ccns_for, links_for, s3, bucket):
    """Returns enqueue(url, nbytes, prev) for process_file: adds a hospital job to the shared machine queue once."""
    sys.path.insert(0, str(ROOT / "insurers"))
    import fleet

    def enqueue(url, nbytes, prev):
        fid = file_id(state, url)
        jid = fleet.job_id("hospitals", fid)
        size = machine_size(nbytes)
        if store.exists(s3, bucket, fleet.Q + jid + ".json"):
            return f"{nbytes / 1024 ** 3:.1f} GB; already in the machine queue"
        L = links_for.get(url, {})
        fleet.put_job(s3, bucket, dict(
            id=jid, kind="hospital", scope="hospitals", slot=fid, url=url, state=state, ccns=ccns_for.get(url, []),
            index_url=L.get("index_url", ""), index_found=bool(L.get("index_found")), link_source=L.get("how", ""),
            prev=prev or {}, size=size, mem=fleet.mem_gb(size), bytes=nbytes,
            done_key=f"{RESULTS}{state}/{fid}.json", hold_key=f"{store.R2_PREFIX}fleet/hold_hospitals.txt"))
        return f"{nbytes / 1024 ** 3:.1f} GB; added to the machine queue ({size} machine)"
    return enqueue


def run_on_machine(job, s3, bucket, log=print):
    """On a rented machine: the free runner's steps (process_file) for one oversized hospital file, with no size cap.
    Returns the result saved to job['done_key']."""
    global MAX_BYTES
    MAX_BYTES = 10 ** 15
    st, url = job["state"], job["url"]
    now_dt = datetime.now(timezone.utc)
    today = now_dt.date()
    work = Path("/mnt/work" if Path("/mnt").is_dir() else ROOT / "work") / st
    work.mkdir(parents=True, exist_ok=True)
    reader.load_codes(ROOT / "reference" / "codes89.csv")
    ctx = dict(now=now_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), today=today, day=today.isoformat(), month=today.strftime("%Y-%m"),
               state=st, saver=Saver(st, today.isoformat(), False), work=work, local=False, codes=True,
               ccns_for={url: job.get("ccns") or []}, stop_downloads_at=time.time() + 10 ** 7)
    t0 = time.time()
    entry, res = process_file(url, job.get("prev") or None, ctx)
    shutil.rmtree(work, ignore_errors=True)
    log(f"[{job['id']}] {res['status']} in {round(time.time() - t0)}s {res.get('detail', '')[:200]}")
    return dict(ok=res["status"] not in PROBLEM, kind="hospital", url=url, state=st, ccns=job.get("ccns") or [],
                index_url=job.get("index_url", ""), index_found=job.get("index_found", False),
                link_source=job.get("link_source", ""), entry=entry or {}, res=res, finished_at=ctx["now"],
                secs=round(time.time() - t0))


def status_row(h, L, res, f, now, st):
    known = discover.clean(h["mrf_url"]) if h.get("mrf_url") else ""
    u = L["mrf_url"]
    return dict(checked_at=now, state=st, ccn=h["ccn"], hospital=h["name"], city=h["city"], type=h["type"],
                status=res["status"], alert=res.get("alert", ""), detail=res.get("detail", ""), mrf_url=u,
                index_url=L["index_url"], index_found="yes" if L["index_found"] else "no",
                link_source=L["how"], link_changed="yes" if known and u and u != known else "",
                check_method=res.get("check_method", ""), http=res.get("http", ""),
                etag=f.get("etag", ""), last_modified=f.get("last_modified", ""), size=f.get("size", ""),
                sha256=f.get("sha256", ""), r2_key=f.get("r2_key", ""), ia_item=res.get("ia_item", ""),
                records=f.get("records", ""), prev_records=res.get("prev_records", ""),
                file_last_updated_on=f.get("file_last_updated_on", ""), first_seen=f.get("first_seen", ""),
                last_changed=f.get("last_changed", ""), cert_unverified=res.get("cert_unverified", ""),
                **{k: f.get(k) or "" for k in ("file_version", "license_number", "license_state", "attested", "attester_name")})


def machine_results(saver, st):
    """Results rented machines saved for this state's oversized files: [(key, result)]."""
    if saver.local:
        return []
    out = []
    for page in saver.s3.get_paginator("list_objects_v2").paginate(Bucket=saver.bucket, Prefix=f"{RESULTS}{st}/"):
        for o in page.get("Contents", []):
            try:
                out.append((o["Key"], json.loads(saver.s3.get_object(Bucket=saver.bucket, Key=o["Key"])["Body"].read())))
            except Exception as ex:
                print("could not read machine result", o["Key"], ex)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--all", action="store_true", help="check every hospital, not only those due today")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many files (testing)")
    ap.add_argument("--local", action="store_true", help="no R2/archive.org; write to ./local/")
    ap.add_argument("--minutes", type=float, default=300, help="stop starting downloads after this long")
    ap.add_argument("--no-codes", action="store_true", help="skip target-code extraction")
    a = ap.parse_args()
    st = a.state.upper()
    t0 = time.time()
    now_dt = datetime.now(timezone.utc)
    today = now_dt.date()
    day, now = today.isoformat(), now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    saver = Saver(st, day, a.local)
    codes = ROOT / "reference" / "codes89.csv"
    if not a.no_codes:
        reader.load_codes(codes)

    hospitals = [r for r in csv.DictReader(open(ROOT / "data" / "hospitals.csv")) if r["state"] == st]
    files = {r["url"]: r for r in saver.read("files")}
    hosp_prev = {r["ccn"]: r for r in saver.read("hosp")}
    # First run: start from the originals already archived in October, so unchanged files aren't re-saved.
    for h in hospitals:
        u = discover.clean(h["mrf_url"]) if h.get("mrf_url") else ""
        if u and u not in files and h.get("last_sha256"):
            files[u] = dict(url=u, sha256=h["last_sha256"], r2_key=h["last_key"], bytes=h.get("last_bytes", ""),
                            first_seen=h.get("last_archived_run", ""))

    # Results from rented machines (oversized files): fold them in before today's checks, so they count as done.
    by_ccn = {h["ccn"]: h for h in hospitals}
    merged_rows, merged_keys = [], []
    for key, r in machine_results(saver, st):
        res = r.get("res") or dict(status="too large for free runner", alert="yes",
                                   detail=f"rented machine failed: {r.get('error', 'no result')}"[:300])
        if r.get("entry"):
            files[r["url"]] = r["entry"]
        L = dict(mrf_url=r["url"], index_url=r.get("index_url", ""), index_found=r.get("index_found", False),
                 how=(r.get("link_source") or "") + " (read on a rented machine)")
        for ccn in r.get("ccns") or []:
            h = by_ccn.get(ccn)
            if not h:
                continue
            merged_rows.append(status_row(h, L, res, files.get(r["url"], {}), r.get("finished_at") or now, st))
            prev = hosp_prev.get(ccn, {})
            hosp_prev[ccn] = dict(ccn=ccn, mrf_url=r["url"], index_url=L["index_url"], status=res["status"],
                                  alert=res.get("alert", ""), last_checked=r.get("finished_at") or now,
                                  last_ok=(r.get("finished_at") or now) if res["status"] not in PROBLEM else prev.get("last_ok", ""))
        merged_keys.append(key)
    if merged_keys:
        print(f"{st}: {len(merged_keys)} oversized file(s) read on rented machines folded in", flush=True)
    merged_ccns = {row["ccn"] for row in merged_rows}

    todo = [h for h in hospitals if h["ccn"] not in merged_ccns and due(h, hosp_prev.get(h["ccn"]), today, a.all)]
    print(f"{st}: {len(hospitals)} hospitals, {len(todo)} due today", flush=True)

    # 1. Current link for each hospital (from its own cms-hpt.txt)
    links = {}
    for h in todo:
        links[h["ccn"]] = discover.current_link(h)
    ccns_for = {}
    for h in todo:
        u = links[h["ccn"]]["mrf_url"]
        if u:
            ccns_for.setdefault(u, []).append(h["ccn"])

    work = ROOT / "work" / st
    work.mkdir(parents=True, exist_ok=True)
    ctx = dict(now=now, today=today, day=day, month=today.strftime("%Y-%m"), state=st, saver=saver, work=work,
               local=a.local, codes=not a.no_codes, ccns_for=ccns_for,
               stop_downloads_at=t0 + a.minutes * 60)
    if not a.local:  # oversized files go to the shared machine queue instead of being skipped
        ctx["enqueue"] = enqueuer(st, ccns_for, {L["mrf_url"]: L for L in links.values() if L.get("mrf_url")},
                                  saver.s3, saver.bucket)

    # 2. Check each distinct file once
    results = {}
    for i, url in enumerate(ccns_for, 1):
        if a.limit and i > a.limit:
            break
        t1 = time.time()
        try:
            entry, res = process_file(url, files.get(url), ctx)
        except Exception as ex:  # one bad file must not stop the state
            entry = dict(files.get(url) or {}, url=url, last_checked=now, last_error=str(ex)[:300])
            res = dict(status="link broken", alert="yes", detail=f"bot error: {type(ex).__name__}: {str(ex)[:200]}")
        if entry:
            files[url] = entry
        results[url] = res
        print(f"  [{i}/{len(ccns_for)}] {res['status']:28} {round(time.time() - t1):>5}s  {url[:110]}", flush=True)
        if i % 10 == 0:
            saver.write("files", list(files.values()), FILE_FIELDS)

    # 3. One status row per hospital checked
    rows = []
    for h in todo:
        L = links[h["ccn"]]
        u = L["mrf_url"]
        if u and u not in results:
            continue  # not reached (limit / time); stays due for the next run
        res = results.get(u) or dict(status="no price file found", alert="yes",
                                     detail="no cms-hpt.txt entry or known link for this hospital")
        if res.get("status") == "skipped":
            continue
        rows.append(status_row(h, L, res, files.get(u, {}), now, st))
        prev = hosp_prev.get(h["ccn"], {})
        hosp_prev[h["ccn"]] = dict(ccn=h["ccn"], mrf_url=u, index_url=L["index_url"], status=res["status"],
                                   alert=res.get("alert", ""), last_checked=now,
                                   last_ok=now if res["status"] not in PROBLEM | {QUEUED} else prev.get("last_ok", ""))

    saver.write("files", list(files.values()), FILE_FIELDS)
    saver.write("hosp", list(hosp_prev.values()), HOSP_FIELDS)
    rows = merged_rows + rows
    saver.write("status", rows, STATUS_FIELDS)
    for key in merged_keys:  # folded in and saved: done with these results
        saver.s3.delete_object(Bucket=saver.bucket, Key=key)
    Path(ROOT / "out").mkdir(exist_ok=True)
    with open(ROOT / "out" / f"status_{st}.csv", "w", newline="") as fo:
        w = csv.DictWriter(fo, STATUS_FIELDS); w.writeheader(); w.writerows(rows)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{st} done in {round((time.time() - t0) / 60)} min: {json.dumps(counts)}", flush=True)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
