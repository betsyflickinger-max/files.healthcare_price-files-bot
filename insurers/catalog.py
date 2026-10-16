"""Insurer file catalog (Oct 16, 2026): turn a huge insurer index into a short list of distinct networks.

Big insurers publish one table of contents (index) that lists every employer plan and the price files it uses. Anthem's is
one 11.4 GB file, and most of it is the same networks repeated once per employer. This reads the whole index as a stream
(nothing saved to disk), folds every copy of a network into one entry, and records for each network:

  - its price files (every part "N of M"), with each file's size, date and whether the link answers
  - which plans use it: how many employer plans, a sample of employer names, market (group/individual), plan id types,
    and the states of any marketplace (HIOS) plan ids
  - which state its providers are in: from the Blue plan named inside the file (reporting_entity_name), and from a
    sample of provider NPIs looked up in the federal NPI Registry when the name doesn't say
  - what changed since last month: new and dropped networks, files that shrank or grew by a third or more, files gone empty
  - problems for the Price File Watch: links that don't answer, empty files, incomplete part sets

The reading bot then reads one copy of each network it needs (finder "catalog" in find_links.py), never the employer copies.

Run:  python insurers/catalog.py build --insurer anthem [--month YYYY-MM] [--max-mb N] [--out DIR] [--no-enrich]
      python insurers/catalog.py rows --insurer anthem --states CO,GA,MO [--label-prefix "Anthem"]
Output (R2): bot/catalog/<insurer>/<YYYY-MM>/{catalog.json, networks.csv, changes.json, watch.csv}, bot/catalog/<insurer>/latest.json
Env: R2_* (without them, --out DIR writes the same files locally).
"""
import argparse, csv, gzip, io, json, os, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import requests

UA = "Mozilla/5.0 (compatible; price-transparency-research; +https://github.com/betsyflickinger-max/price-files-bot)"

# Each insurer: where its index lives (dated template, newest first) and how to name a network from a file link.
INSURERS = {
    "anthem": dict(
        name="Anthem (Elevance)",
        index="https://antm-pt-prod-dataz-nogbd-nophi-us-east1.s3.amazonaws.com/anthem/{date}_anthem_index.json.gz",
        dates="first_of_month",
    ),
    # Oct 16, 2026: Cigna's one national table of contents (~57 MB, plain JSON, signed link) is named in its public
    # latest.json. File names carry the date (2026-10-01_cigna-health-life-insurance-company_national-oap_in-network-rates),
    # so keys drop the date to stay the same from month to month.
    "cigna": dict(
        name="Cigna",
        latest="https://www.cigna.com/static/mrf/latest.json",
        strip_date=True,
    ),
    # Oct 16, 2026: UnitedHealthcare posts no single index: one small index per employer (~68,000, ~0.2 GB in all) in a
    # public file listing that also gives every file's size. Read them all (32 at a time) and fold them like one index.
    # Provider samples only for the 400 networks most employers use (7,000+ networks; a sample reads 3 MB each).
    "uhc": dict(
        name="UnitedHealthcare",
        blobs="https://transparency-in-coverage.uhc.com/api/v1/uhc/blobs/",
        strip_date=True,
        peek_top=400,
    ),
}

# BlueCard-style names: 2026-10_051_06B0_in-network-rates_1_of_5.json.gz  -> network 051_06B0, part 1 of 5
BLUE_RE = re.compile(r"(?P<ym>\d{4}-\d{2})_(?P<plan>[0-9A-Z]{3})_(?P<net>[0-9A-Z]{4})_in-network-rates(?:_(?P<part>\d+)_of_(?P<parts>\d+))?\.json(?:\.gz)?$", re.I)
NN_RE = re.compile(r"(?P<base>.+?)_(?P<part>\d{2})_(?P<parts>\d{2})(?P<ext>\.json(?:\.gz)?)$", re.I)   # WI_AHPFMEDWI00_01_04.json.gz
PART_RE = re.compile(r"(?P<base>.+?)[_-](?:part[_-]?)?(?P<part>\d+)[_-]of[_-](?P<parts>\d+)(?P<ext>\.json(?:\.gz)?)$", re.I)

STATES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
          "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
          "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas city": "MO", "kansas": "KS", "kentucky": "KY",
          "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
          "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
          "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
          "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
          "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
          "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"}
# one-word Blue plan names that don't spell out a state
NAMED = {"bcbsok": "OK", "bcbstx": "TX", "bcbst": "TN", "carefirst": "MD", "florida blue": "FL", "wellmark": "IA",
         "premera": "WA", "highmark": "PA", "regence": "OR", "horizon": "NJ", "excellus": "NY", "empire": "NY",
         "hmsa": "HI", "capital blue": "PA", "independence": "PA", "blue kc": "MO", "bluekc": "MO"}
LONG_STATES = sorted(STATES, key=len, reverse=True)


def state_from_name(name):
    n = (name or "").lower()
    for s in LONG_STATES:
        if re.search(r"\b" + s + r"\b", n):
            return STATES[s]
    for k, v in NAMED.items():
        if k in n:
            return v
    return ""


# ---------------- storage ----------------

def s3():
    if not os.environ.get("R2_ACCOUNT_ID"):
        return None
    import boto3
    E = {k: os.environ[k].strip() for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")}   # secrets may end in a newline
    return boto3.client("s3", endpoint_url=f"https://{E['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=E["R2_ACCESS_KEY_ID"], aws_secret_access_key=E["R2_SECRET_ACCESS_KEY"], region_name="auto")


class Store:
    def __init__(self, out=None):
        self.c, self.b, self.out = s3(), (os.environ.get("R2_BUCKET") or "").strip(), out

    def get(self, key, default=None):
        try:
            if self.c:
                return json.loads(self.c.get_object(Bucket=self.b, Key=key)["Body"].read())
            p = os.path.join(self.out or ".", key)
            return json.load(open(p)) if os.path.exists(p) else default
        except Exception:
            return default

    def put(self, key, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))).encode()
        if self.c:
            self.c.put_object(Bucket=self.b, Key=key, Body=data, ContentType=ctype)
        if self.out or not self.c:
            p = os.path.join(self.out or ".", key)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data)


# ---------------- index ----------------

def find_index(ins, month=None):
    """Newest index that answers: the 1st of this month, then the previous two months (or, for an insurer with a
    'latest' pointer, the table of contents that pointer names)."""
    cfg = INSURERS[ins]
    if cfg.get("blobs"):
        return cfg["blobs"], 0, ""
    if cfg.get("latest"):
        d = requests.get(cfg["latest"], headers={"User-Agent": UA}, timeout=60).json()
        url = next(f["url"] for m in d["mrfs"] if m.get("kind") == "TOC" for f in m["files"])
        r = requests.get(url, headers={"User-Agent": UA, "Range": "bytes=0-0"}, timeout=60)
        size = int((r.headers.get("Content-Range") or "/0").rsplit("/", 1)[-1] or 0) if r.status_code == 206 else int(r.headers.get("Content-Length", 0))
        return url, size, r.headers.get("Last-Modified", "")
    today = date.today()
    y, m = (int(month[:4]), int(month[5:7])) if month else (today.year, today.month)
    for back in range(3):
        mm, yy = m - back, y
        while mm < 1:
            mm += 12; yy -= 1
        url = cfg["index"].format(date=f"{yy:04d}-{mm:02d}-01")
        try:
            h = requests.head(url, headers={"User-Agent": UA}, timeout=60)
            if h.status_code == 200:
                return url, int(h.headers.get("Content-Length", 0)), h.headers.get("Last-Modified", "")
        except requests.RequestException:
            pass
    raise SystemExit(f"STOP: no {cfg['name']} index answered for the last 3 months")


class Counted(io.RawIOBase):
    """Wraps the download so we can report progress and stop early (--max-mb, for tests)."""
    def __init__(self, raw, limit=0):
        self.raw, self.n, self.limit, self.t0 = raw, 0, limit, time.time()
    def readable(self): return True
    def readinto(self, b):
        if self.limit and self.n >= self.limit:
            return 0
        chunk = self.raw.read(len(b))
        if not chunk:
            return 0
        b[:len(chunk)] = chunk
        self.n += len(chunk)
        if self.n // (1 << 30) != (self.n - len(chunk)) // (1 << 30):
            print(f"  {self.n / 1e9:.1f} GB read, {self.n / 1e6 / (time.time() - self.t0):.0f} MB/s", flush=True)
        return len(chunk)


DATE_PREFIX = re.compile(r"^\d{4}[-_]\d{2}[-_]\d{2}_")
BLOBS = False        # set from the insurer's settings (UnitedHealthcare): many small indexes from a file listing
PEEK_TOP = 0         # set from the insurer's settings: provider samples only for the N networks most employers use
STRIP_DATE = False   # set from the insurer's settings (Cigna): drop the leading date and "_in-network-rates" from keys


UHC_MARKET = re.compile(r"_(Third-Party-Administrator|Insurer|Health-Insurance-Issuer|Group-Health-Plan)_", re.I)


def network_of(url):
    info = _network_of(url)
    if STRIP_DATE and info["kind"] != "bluecard":
        k = DATE_PREFIX.sub("", info["key"])
        k = re.sub(r"[_-]in-network-rates$", "", k, flags=re.I)
        if BLOBS:   # UnitedHealthcare posts the same network file under each company that uses it: one key per network
            m = UHC_MARKET.search(k)
            if m:
                info["company"] = k[:m.start()]
                k = k[m.end():]
        info["key"] = k
    return info


def _network_of(url):
    path = url.split("?", 1)[0]
    host = path.split("/")[2] if "://" in path else ""
    fname = path.rsplit("/", 1)[-1]
    m = BLUE_RE.search(fname)
    if m:
        return dict(key=f"{m['plan']}_{m['net']}".upper(), part=int(m["part"] or 1), parts=int(m["parts"] or 1), ym=m["ym"],
                    plan_code=m["plan"].upper(), net_code=m["net"].upper(), fname=fname, host=host, kind="bluecard")
    m = PART_RE.search(fname)
    if m:
        return dict(key=m["base"], part=int(m["part"]), parts=int(m["parts"]), ym="", plan_code="", net_code="",
                    fname=fname, host=host, kind="parts")
    m = NN_RE.search(fname)
    if m and 1 <= int(m["part"]) <= int(m["parts"]):
        return dict(key=m["base"], part=int(m["part"]), parts=int(m["parts"]), ym="", plan_code="", net_code="",
                    fname=fname, host=host, kind="parts")
    base = re.sub(r"\.(json(\.gz)?|zip)$", "", fname, flags=re.I)
    return dict(key=base, part=1, parts=1, ym="", plan_code="", net_code="", fname=fname, host=host, kind="single")


def blob_structures(list_url, stats, limit=0):
    """UnitedHealthcare: every employer's own small index from the public listing, newest month only, read 32 at a
    time; yields their reporting_structure items in listing order. stats gets files, failed and bytes."""
    blobs = requests.get(list_url, headers={"User-Agent": UA}, timeout=600).json()["blobs"]
    idx = [b for b in blobs if b["name"].endswith("_index.json")]
    month = max(b["name"][:10] for b in idx)
    idx = [b for b in idx if b["name"].startswith(month)]
    if limit:
        idx = idx[:limit]
    stats.update(files=len(idx), failed=0, bytes=0, month=month)
    print(f"{len(idx):,} employer indexes dated {month}", flush=True)

    def get(b):
        for t in range(4):
            try:
                r = requests.get(b["downloadUrl"], headers={"User-Agent": UA}, timeout=120)
                if r.status_code == 200:
                    return r.content
            except requests.RequestException:
                pass
            time.sleep(2 * (t + 1))
        return None

    with ThreadPoolExecutor(64) as ex:
        for i, body in enumerate(ex.map(get, idx), 1):
            if body is None:
                stats["failed"] += 1
                continue
            stats["bytes"] += len(body)
            try:
                j = json.loads(body)
            except ValueError:
                stats["failed"] += 1
                continue
            if i == 1:
                stats["head"] = {k: j.get(k, "") for k in ("reporting_entity_name", "last_updated_on", "version")}
            for rs in j.get("reporting_structure") or []:
                yield rs
            if i % 5000 == 0:
                print(f"  {i:,} of {len(idx):,} indexes read ({stats['failed']} failed)", flush=True)


def read_index(url, limit_bytes=0, employers_path=None):
    """Stream the whole index once and fold every employer copy of a network into one entry. With employers_path, also
    write every plan (employer, plan id, plan name, market) with the networks it uses: the employer lookup for HR teams."""
    import ijson
    bstats = {}
    if BLOBS:   # many small indexes (UnitedHealthcare)
        raw = type("R", (), {"n": 0})()
        structures = blob_structures(url, bstats, limit=int(limit_bytes / 3000) if limit_bytes else 0)
    else:
        r = requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=(60, 600))
        r.raise_for_status()
        r.raw.decode_content = False
        raw = Counted(r.raw, limit_bytes)
        src = gzip.GzipFile(fileobj=io.BufferedReader(raw, 1 << 22)) if url.endswith(".gz") else io.BufferedReader(raw, 1 << 22)
        structures = None
    nets = {}
    head = {}
    emp = emp_f = None
    sets, set_sponsors = {}, {}   # sorted network keys -> set id; set id -> distinct employers (hashed)
    if employers_path:
        emp_f = io.TextIOWrapper(gzip.open(employers_path, 'wb', compresslevel=6), encoding='utf-8', newline='')
        emp = csv.writer(emp_f)
        emp.writerow(['plan_sponsor_name', 'plan_id', 'plan_id_type', 'plan_name', 'plan_market_type', 'issuer_name', 'network_set'])
    n_struct = n_plans = n_links = 0
    try:
        # the header (insurer name, date) sits in the first few KB: read it from a small separate request
        try:
            if BLOBS:
                raise ValueError("header comes from the first employer index")
            hb = requests.get(url, headers={"User-Agent": UA, "Range": "bytes=0-65535"}, timeout=60).content
            ht = __import__("zlib").decompressobj(16 + 15).decompress(hb)[:20000].decode("utf-8", "replace") if url.endswith(".gz") else hb.decode("utf-8", "replace")
            for k in ("reporting_entity_name", "last_updated_on", "version"):
                m = re.search(r'"%s"\s*:\s*"([^"]*)"' % k, ht)
                if m: head[k] = m.group(1)
        except Exception:
            pass
        for rs in (structures if structures is not None else ijson.items(src, "reporting_structure.item", buf_size=1 << 20)):
            n_struct += 1
            plans = rs.get("reporting_plans") or []
            n_plans += len(plans)
            files = rs.get("in_network_files") or []
            seen_here = set()
            for f in files:
                loc = (f.get("location") or "").strip()
                if not loc:
                    continue
                n_links += 1
                info = network_of(loc)
                k = info["key"]
                e = nets.get(k)
                if e is None:
                    e = nets[k] = dict(key=k, kind=info["kind"], plan_code=info["plan_code"], net_code=info["net_code"],
                                       ym=info["ym"], parts_declared=info["parts"], parts={}, descriptions=Counter(),
                                       hosts=Counter(), structures=0, plans=0, sponsor_sample=[], sample_seen=set(),
                                       market=Counter(), id_types=Counter(), hios_states=Counter())
                e["descriptions"][(info.get("company") or f.get("description") or "").strip()[:120]] += 1
                e["hosts"][info["host"]] += 1
                e["parts_declared"] = max(e["parts_declared"], info["parts"])
                p = e["parts"].get(info["part"])
                signed = "?" in loc
                # keep one link per part: prefer a link with no signature (it doesn't expire)
                if p is None or (p["signed"] and not signed):
                    e["parts"][info["part"]] = dict(url=loc, fname=info["fname"], host=info["host"], signed=signed)
                if k in seen_here:
                    continue
                seen_here.add(k)
                e["structures"] += 1
                e["plans"] += len(plans)
                for pl in plans:
                    sp = (pl.get("plan_sponsor_name") or "").strip()
                    if sp and len(e["sponsor_sample"]) < 25 and sp not in e["sample_seen"]:
                        e["sample_seen"].add(sp); e["sponsor_sample"].append(sp)
                    e["market"][(pl.get("plan_market_type") or "").lower()] += 1
                    t = (pl.get("plan_id_type") or "").upper()
                    e["id_types"][t] += 1
                    pid = str(pl.get("plan_id") or "")
                    if t == "HIOS" and len(pid) >= 7 and pid[5:7].isalpha():
                        e["hios_states"][pid[5:7].upper()] += 1
            if seen_here:
                sid = sets.setdefault('|'.join(sorted(seen_here)), len(sets) + 1)
                ss = set_sponsors.setdefault(sid, set())
                for pl in plans:
                    sp = (pl.get('plan_sponsor_name') or '').strip().upper()
                    if sp: ss.add(hash(sp) & 0xFFFFFFFFFFFF)
            if emp is not None and seen_here:
                for pl in plans:
                    emp.writerow([pl.get('plan_sponsor_name') or '', pl.get('plan_id') or '', pl.get('plan_id_type') or '',
                                  pl.get('plan_name') or '', pl.get('plan_market_type') or '', pl.get('issuer_name') or '', sid])
            if n_struct % 200000 == 0:
                print(f"  {n_struct:,} plan groups, {len(nets):,} networks so far", flush=True)
    except Exception as ex:  # a cut-off stream (--max-mb) ends here; anything else is reported
        if not limit_bytes:
            raise
        print("  stopped early (test limit):", repr(ex)[:120])
    if emp_f is not None:
        emp_f.close()
        with gzip.open(employers_path.replace('_employers.csv.gz', '_network_sets.csv.gz'), 'wt', newline='') as f:
            w = csv.writer(f); w.writerow(['network_set', 'networks'])
            for k, i in sets.items(): w.writerow([i, k])
    # distinct employers per network = union over the network sets that include it
    members = defaultdict(list)
    for k, i in sets.items():
        for net in k.split('|'): members[net].append(i)
    for net, ids in members.items():
        if net in nets:
            u = set()
            for i in ids: u |= set_sponsors.get(i, set())
            nets[net]["employers"] = len(u)
    if BLOBS:
        head.update(bstats.get("head") or {})
        head["last_updated_on"] = bstats.get("month") or head.get("last_updated_on", "")   # the listing's file date
        raw.n = bstats.get("bytes", 0)
    return head, nets, dict(structures=n_struct, plans=n_plans, links=n_links, bytes_read=raw.n, network_sets=len(sets),
                            **({"index_files": bstats.get("files"), "index_files_failed": bstats.get("failed")} if BLOBS else {}))


# ---------------- enrich: sizes, dates, states ----------------

NPI_CACHE = {}


def npi_state(npi):
    if npi in NPI_CACHE:
        return NPI_CACHE[npi]
    st = ""
    for _ in range(2):
        try:
            r = requests.get("https://npiregistry.cms.hhs.gov/api/", params={"version": "2.1", "number": npi}, timeout=20)
            res = (r.json().get("results") or [{}])[0]
            addr = next((a for a in res.get("addresses", []) if a.get("address_purpose") == "LOCATION"), {})
            st = (addr.get("state") or "").upper()
            break
        except Exception:
            time.sleep(2)
    NPI_CACHE[npi] = st
    return st


def head_part(p):
    try:
        h = requests.head(p["url"], headers={"User-Agent": UA}, timeout=60, allow_redirects=True)
        p["http"] = h.status_code
        p["bytes"] = int(h.headers.get("Content-Length") or 0)
        p["modified"] = h.headers.get("Last-Modified", "")
    except requests.RequestException as ex:
        p["http"], p["bytes"], p["error"] = 0, 0, repr(ex)[:120]
    m = re.search(r"[?&]Expires=(\d+)", p["url"])
    if m:
        p["expires"] = datetime.fromtimestamp(int(m.group(1)), timezone.utc).strftime("%Y-%m-%d")
    return p


def peek(e, sample=12):
    """Open the start of part 1: who reports it (the Blue plan), its date, and where a sample of its providers practice."""
    first = e["parts"][min(e["parts"])]
    out = dict(reporting_entity="", last_updated_on="", npi_states={})
    try:
        # stream and stop at 3 MB: some hosts ignore Range and would send the whole file (UnitedHealthcare: 9+ GB)
        with requests.get(first["url"], headers={"User-Agent": UA, "Range": "bytes=0-3000000"}, timeout=120, stream=True) as r:
            if r.status_code not in (200, 206):
                out["peek_error"] = f"HTTP {r.status_code}"; return out
            r.raw.decode_content = False
            body = r.raw.read(3_000_001)
        d = __import__("zlib").decompressobj(16 + 15)
        text = d.decompress(body, 6_000_000).decode("utf-8", "replace") if first["fname"].endswith(".gz") else body.decode("utf-8", "replace")
    except Exception as ex:
        out["peek_error"] = repr(ex)[:120]; return out
    m = re.search(r'"reporting_entity_name"\s*:\s*"([^"]*)"', text); out["reporting_entity"] = m.group(1) if m else ""
    m = re.search(r'"last_updated_on"\s*:\s*"([^"]*)"', text); out["last_updated_on"] = m.group(1) if m else ""
    npis = list(dict.fromkeys(re.findall(r'"npi"\s*:\s*\[\s*(\d{10})', text)))
    if npis and not state_from_name(out["reporting_entity"]) and not (e.get("hios_top")):
        step = max(1, len(npis) // sample)
        picks = npis[len(npis) // 10::step][:sample] or npis[:sample]   # skip the first tenth (national labs often lead)
        with ThreadPoolExecutor(6) as ex:
            out["npi_states"] = dict(Counter(s for s in ex.map(npi_state, picks) if s))
    return out


def enrich(nets, threads=24):
    parts = [p for e in nets.values() for p in e["parts"].values()]
    print(f"checking {len(parts):,} files ({len(nets):,} networks)", flush=True)
    with ThreadPoolExecutor(threads) as ex:
        list(ex.map(head_part, parts))
    for e in nets.values():
        e["hios_top"] = e["hios_states"].most_common(1)[0][0] if e["hios_states"] else ""
    todo = list(nets)
    if STRIP_DATE:   # a network whose name already settles its state needs no provider sample
        todo = [k for k in todo if not state_of(nets[k])[0]]
    if PEEK_TOP:
        todo = sorted(nets, key=lambda k: -(nets[k].get("employers") or 0))[:PEEK_TOP]
    with ThreadPoolExecutor(12) as ex:
        peeks = dict(zip(todo, ex.map(peek, [nets[k] for k in todo])))
    for k, e in nets.items():
        e.update(peeks.get(k) or dict(reporting_entity="", last_updated_on="", npi_states={}))


# ---------------- summarize, compare, write ----------------

# Cigna-style names describe the network: a region in the name settles the state; national products are "national"
REGIONS = {"southern ca": "CA", "san francisco": "CA", "sacramento": "CA", "los angeles": "CA", "chicago": "IL", "metro new york": "NY",
           "new york": "NY", "houston": "TX", "dallas": "TX", "austin": "TX", "san antonio": "TX", "phoenix": "AZ", "denver": "CO",
           "atlanta": "GA", "miami": "FL", "south florida": "FL", "tampa": "FL", "orlando": "FL", "nashville": "TN", "memphis": "TN",
           "chattanooga": "TN", "knoxville": "TN", "charlotte": "NC", "raleigh": "NC", "st louis": "MO", "kansas city": "MO",
           "philadelphia": "PA", "pittsburgh": "PA", "boston": "MA", "seattle": "WA", "las vegas": "NV", "salt lake": "UT",
           "mid atlantic": "multi", "new england": "multi", "louisville": "KY", "tennesse": "TN", "kelseycare": "TX",
           "indianapolis": "IN", "cincinnati": "OH", "cleveland": "OH", "milwaukee": "WI", "wichita": "KS", "pensacola": "FL",
           "shreveport": "LA", "tulsa": "OK", "panama city": "FL", "savannah": "GA", "waco": "TX", "corpus christi": "TX",
           "golden triangle": "TX", "front range": "CO", "tristate": "multi", "tri state": "multi", "northern nj": "NJ", "new jersey": "NJ"}
NATIONAL_RE = re.compile(r"\b(national|pathwell|oap|open access|ppo|localplus|local plus|shared admin|surefit|priority health|"
                         r"healthpartners|mvp|sagamore|upper midwest)\b")


UHC_NATIONAL = re.compile(r"\b(choice plus|choice epo|choice|core|core epo|navigate|navigate epo|charter|charter epo|select plus|select epo|"
                          r"select|options ppo|options|nexusaco|nexusaco oa|ohph|optum|ppo ndc|doctors plan|surest|ps1)\b")


def state_of(e):
    if STRIP_DATE:
        name = re.sub(r"[-_]+", " ", e["key"].lower())
        name = re.sub(r"^cigna health life insurance company ", "", name)
        for k, v in REGIONS.items():
            if re.search(r"\b" + k + r"\b", name):
                return v, "network name"
        st = state_from_name(name)
        if st:
            return st, "network name"
        if BLOBS:   # the companies posting it: one state among them settles it (UnitedHealthcare of South Carolina, ...)
            cs = {state_from_name(re.sub(r"[-_]+", " ", c)) for c in e["descriptions"]} - {""}
            if len(cs) == 1:
                return cs.pop(), "company name"
        if BLOBS and UHC_NATIONAL.search(name):
            return "national", "national product (network name)"
        if BLOBS and re.search(r"\b(freedom|liberty)\b", name):
            return "multi", "Oxford network (NY, NJ, CT)"
        if NATIONAL_RE.search(name):
            return "national", "national product (network name)"
        if e.get("npi_states"):
            st, n = Counter(e["npi_states"]).most_common(1)[0]
            tot = sum(e["npi_states"].values())
            if tot >= 8 and n / tot >= 0.75:
                return st, f"provider sample ({n} of {tot} in {st})"
            return "", f"unclear (provider sample {n} of {tot} in {st})"
    s = state_from_name(e.get("reporting_entity", ""))
    if s:
        return s, "Blue plan named in the file"
    if e.get("hios_top"):
        return e["hios_top"], "marketplace plan ids (HIOS)"
    if e.get("npi_states"):
        st, n = Counter(e["npi_states"]).most_common(1)[0]
        tot = sum(e["npi_states"].values())
        return (st if n / tot >= 0.5 else "multi"), f"provider sample ({n} of {tot} in {st})"
    s = state_from_name(" ".join(e["descriptions"]))
    return (s, "file description") if s else ("", "unknown")


def finalize(nets):
    rows = []
    for k, e in sorted(nets.items()):
        parts = [e["parts"][i] for i in sorted(e["parts"])]
        size = sum(p.get("bytes", 0) for p in parts)
        st, how = state_of(e)
        problems = []
        if any(p.get("http") not in (200, 206) for p in parts):
            problems.append(f"{sum(p.get('http') not in (200, 206) for p in parts)} of {len(parts)} links don't answer")
        if any(p.get("http") == 200 and p.get("bytes", 1) < 1024 for p in parts):
            problems.append("empty file (under 1 KB)")
        missing = e["parts_declared"] - len(parts)
        if missing > 0:
            problems.append(f"{missing} of {e['parts_declared']} parts not listed in the index")
        desc_all = " ".join(e["descriptions"]).lower() + " " + k.lower()
        cover = "dental" if "dental" in desc_all else "vision" if "vision" in desc_all else "medical"
        rows.append(dict(
            network=k, kind=e["kind"], coverage=cover, plan_code=e["plan_code"], net_code=e["net_code"],
            description=e["descriptions"].most_common(1)[0][0] if e["descriptions"] else "",
            reporting_entity=e.get("reporting_entity", ""), state=st, state_how=how, npi_states=e.get("npi_states", {}),
            hios_states=dict(e["hios_states"]), file_date=e.get("last_updated_on", ""), month=e["ym"],
            parts=len(parts), parts_declared=e["parts_declared"], bytes=size, gb=round(size / 1e9, 2),
            employer_plans=e["structures"], plans=e["plans"], employers=e.get("employers", 0), employer_sample=e["sponsor_sample"],
            market=dict(e["market"]), id_types=dict(e["id_types"]), hosts=dict(e["hosts"]),
            files=[dict(part=i, url=e["parts"][i]["url"], fname=e["parts"][i]["fname"], host=e["parts"][i]["host"],
                        http=e["parts"][i].get("http"), bytes=e["parts"][i].get("bytes"), modified=e["parts"][i].get("modified", ""),
                        expires=e["parts"][i].get("expires", "")) for i in sorted(e["parts"])],
            problems=problems))
    return rows


def compare(rows, prev):
    if not prev:
        return dict(first_run=True)
    old = {r["network"]: r for r in prev.get("networks", [])}
    new = {r["network"]: r for r in rows}
    ch = dict(new=[k for k in new if k not in old], dropped=[k for k in old if k not in new], shrank=[], grew=[], newly_empty=[])
    for k in set(new) & set(old):
        a, b = old[k].get("bytes") or 0, new[k].get("bytes") or 0
        if a and b < a * 0.67: ch["shrank"].append(dict(network=k, before_gb=round(a / 1e9, 2), now_gb=round(b / 1e9, 2)))
        if a and b > a * 1.5: ch["grew"].append(dict(network=k, before_gb=round(a / 1e9, 2), now_gb=round(b / 1e9, 2)))
        if any("empty" in p for p in new[k]["problems"]) and not any("empty" in p for p in old[k]["problems"]):
            ch["newly_empty"].append(k)
    return ch


def build(a):
    t0 = time.time()
    st = Store(a.out)
    url, size, lm = find_index(a.insurer, a.month)
    print(f"index: {url.split('?')[0]} ({size / 1e9:.1f} GB, modified {lm})", flush=True)
    os.makedirs(a.out or '/tmp', exist_ok=True)
    emp_path = os.path.join(a.out or '/tmp', f'{a.insurer}_employers.csv.gz')
    head, nets, counts = read_index(url, int(a.max_mb * 1e6) if a.max_mb else 0, emp_path)
    print(f"read {counts['bytes_read'] / 1e9:.2f} GB: {counts['structures']:,} plan groups, {counts['plans']:,} plans, "
          f"{counts['links']:,} file links -> {len(nets):,} distinct networks ({time.time() - t0:.0f}s)", flush=True)
    if not a.no_enrich:
        enrich(nets)
    rows = finalize(nets)
    month = (head.get("last_updated_on") or date.today().isoformat())[:7]
    base = f"bot/catalog/{a.insurer}/{month}/"
    prevm = st.get(f"bot/catalog/{a.insurer}/latest.json", {}).get("month")
    prev = st.get(f"bot/catalog/{a.insurer}/{prevm}/catalog.json") if prevm and prevm != month else None
    changes = compare(rows, prev)
    watch = [dict(insurer=INSURERS[a.insurer]["name"], network=r["network"], description=r["description"], state=r["state"],
                  problem="; ".join(r["problems"]), checked=date.today().isoformat(), example_link=r["files"][0]["url"].split("?")[0] if r["files"] else "")
             for r in rows if r["problems"]]
    cat = dict(insurer=a.insurer, name=INSURERS[a.insurer]["name"], index=url.split("?")[0], index_bytes=size,
               index_modified=lm, reporting_entity=head.get("reporting_entity_name", ""), last_updated_on=head.get("last_updated_on", ""),
               built=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), complete=not a.max_mb, counts=counts,
               seconds=round(time.time() - t0), networks=rows)
    st.put(base + "catalog.json", cat)
    st.put(base + "changes.json", changes)
    if st.c:   # employer plan -> networks (gzip CSV, one row per plan)
        st.c.upload_file(emp_path, st.b, base + "employers.csv.gz")
        st.c.upload_file(emp_path.replace('_employers.csv.gz', '_network_sets.csv.gz'), st.b, base + "network_sets.csv.gz")
    elif a.out:
        os.makedirs(os.path.join(a.out, base), exist_ok=True); os.replace(emp_path, os.path.join(a.out, base, 'employers.csv.gz'))
        os.replace(emp_path.replace('_employers.csv.gz', '_network_sets.csv.gz'), os.path.join(a.out, base, 'network_sets.csv.gz'))
    flat = io.StringIO()
    cols = ["network", "coverage", "state", "state_how", "description", "reporting_entity", "file_date", "parts", "parts_declared", "gb",
            "employer_plans", "employers", "market", "problems"]
    w = csv.DictWriter(flat, fieldnames=cols, extrasaction="ignore"); w.writeheader()
    for r in rows:
        w.writerow({**r, "market": json.dumps(r["market"]), "problems": "; ".join(r["problems"])})
    st.put(base + "networks.csv", flat.getvalue(), "text/csv")
    wb = io.StringIO()
    if watch:
        ww = csv.DictWriter(wb, fieldnames=list(watch[0])); ww.writeheader(); ww.writerows(watch)
    st.put(base + "watch.csv", wb.getvalue(), "text/csv")
    if not a.max_mb:
        st.put(f"bot/catalog/{a.insurer}/latest.json", dict(month=month, built=cat["built"], networks=len(rows)))
    by_state = Counter(r["state"] or "?" for r in rows)
    summary = [f"## {cat['name']} catalog, {month}", "",
               f"Index {size / 1e9:.1f} GB read in {cat['seconds'] // 60} min: {counts['plans']:,} plans and {counts['links']:,} file links "
               f"fold into **{len(rows):,} distinct networks** ({sum(r['bytes'] for r in rows) / 1e12:.2f} TB of price files).", "",
               "Networks by state: " + ", ".join(f"{s} {n}" for s, n in by_state.most_common()), "",
               f"Problems for the Price File Watch: {len(watch)}"]
    if not changes.get("first_run"):
        summary.append(f"Since last month: {len(changes['new'])} new, {len(changes['dropped'])} dropped, {len(changes['shrank'])} shrank, "
                       f"{len(changes['newly_empty'])} newly empty")
    print("\n".join(summary))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write("\n".join(summary) + "\n")


def rows_cmd(a):
    """Network-list rows (networks*.csv format) for the catalog's networks in some states, one row per file part.
    finder 'catalog' looks up each part's current link in the newest catalog when the bot runs (signed links expire)."""
    st = Store(a.out)
    m = st.get(f"bot/catalog/{a.insurer}/latest.json", {}).get("month") or a.month
    cat = st.get(f"bot/catalog/{a.insurer}/{m}/catalog.json")
    if not cat:
        raise SystemExit("no catalog yet: run build first")
    want = {s.strip().upper() for s in a.states.split(",")}
    skip = set()   # networks the bot already reads (any networks*.csv), matched by network key in their table names
    here = os.path.dirname(os.path.abspath(__file__))
    for fn in os.listdir(here):
        if fn.startswith("networks") and fn.endswith(".csv"):
            for row in csv.DictReader(open(os.path.join(here, fn))):
                for r in cat["networks"]:
                    if r["network"].lower() in (row.get("current_table") or "").lower().replace("-", "_"):
                        skip.add(r["network"])
    cols = ["slot", "insurer", "network_label", "url_template", "current_url", "current_table", "last_updated_on",
            "machine_group", "enabled", "finder", "finder_arg"]
    w = csv.DictWriter(sys.stdout, fieldnames=cols); w.writeheader()
    for r in cat["networks"]:
        if r["state"] not in want or r.get("coverage", "medical") != "medical" or r["network"] in skip:
            continue
        if any("don't answer" in p or "empty" in p for p in r["problems"]):
            continue
        label = r["description"] if r["description"] and "In-Network Negotiated" not in r["description"] else (r["reporting_entity"] or r["network"])
        for f in r["files"]:
            grp = "bcbstx" if (f.get("bytes") or 0) > 5e9 else "bcbs" if (f.get("bytes") or 0) > 1e9 else "small"
            slot = re.sub(r"[^a-z0-9]+", "-", f"{a.insurer}-{r['state']}-{r['network']}-part-{f['part']}".lower()).strip("-")
            w.writerow(dict(slot=slot, insurer=f"{a.label_prefix or INSURERS[a.insurer]['name'].split(' (')[0]} {r['state']}".strip(), network_label=f"{label} ({r['network']})",
                            url_template="", current_url=f["url"], current_table=re.sub(r"\.json(\.gz)?$", "", f["fname"]),
                            last_updated_on=r["file_date"], machine_group=grp, enabled="yes", finder="catalog",
                            finder_arg=f"{a.insurer}|{r['network']}|{f['part']}"))


def report_cmd(a):
    """Markdown summary of the newest catalog for some states (or all), for the step summary: networks by employer count."""
    st = Store(a.out)
    m = st.get(f"bot/catalog/{a.insurer}/latest.json", {}).get("month") or a.month
    cat = st.get(f"bot/catalog/{a.insurer}/{m}/catalog.json")
    if not cat:
        raise SystemExit("no catalog yet: run build first")
    want = {s.strip().upper() for s in a.states.split(",") if s.strip()}
    nets = [r for r in cat["networks"] if not want or r["state"] in want]
    out = [f"## {a.insurer} catalog {m}: {len(nets)} networks" + (f" in {', '.join(sorted(want))}" if want else "")]
    for s_ in sorted({r["state"] for r in nets}):
        rs = sorted([r for r in nets if r["state"] == s_], key=lambda r: (-(r.get("employers") or 0), -(r.get("plans") or 0)))
        out += ["", f"### {s_} ({len(rs)})", "",
                "| network | name | coverage | employers | plans | parts | GB | file date | state from | sample employers | problems |",
                "|---|---|---|---:|---:|---:|---:|---|---|---|---|"]
        for r in rs:
            name = (r["description"] or r["reporting_entity"] or "").replace("|", "/")[:70]
            out.append(f"| {r['network']} | {name} | {r.get('coverage','')} | {r.get('employers', 0):,} | {r.get('plans', 0):,} | "
                       f"{r['parts']}/{r['parts_declared']} | {r['gb']} | {r['file_date']} | {r.get('state_how','')} | {'; '.join(str(x) for x in (r.get('employer_sample') or [])[:3]).replace('|', '/')[:90]} | {'; '.join(r['problems'])} |")
    probs = [r for r in cat["networks"] if r["problems"]]
    out += ["", f"### Problems for the Price File Watch ({len(probs)}, all states)", ""]
    out += [f"- {r['state']} {r['network']} ({(r['description'] or '')[:60]}): {'; '.join(r['problems'])}" for r in probs]
    print("\n".join(out))


def current_link(insurer, network, part, store=None):
    """Used by find_links.py (finder 'catalog'): the newest catalog's link for one file part."""
    st = store or Store()
    m = st.get(f"bot/catalog/{insurer}/latest.json", {}).get("month")
    cat = st.get(f"bot/catalog/{insurer}/{m}/catalog.json") if m else None
    if not cat:
        return None
    for r in cat["networks"]:
        if r["network"] == network:
            for f in r["files"]:
                if str(f["part"]) == str(part):
                    return dict(url=f["url"], date=r["file_date"], http=f.get("http"), month=m)
    return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "rows", "report"])
    ap.add_argument("--insurer", default="anthem", choices=sorted(INSURERS))
    ap.add_argument("--month", default=None)
    ap.add_argument("--max-mb", type=float, default=0, help="test: stop after this many MB of the index")
    ap.add_argument("--out", default=None, help="also write files here (always, when R2 isn't set)")
    ap.add_argument("--no-enrich", action="store_true", help="skip file checks and provider samples")
    ap.add_argument("--states", default="")
    ap.add_argument("--label-prefix", default="")
    a = ap.parse_args()
    STRIP_DATE = bool(INSURERS[a.insurer].get("strip_date"))
    BLOBS = bool(INSURERS[a.insurer].get("blobs"))
    PEEK_TOP = int(INSURERS[a.insurer].get("peek_top") or 0)
    {"build": build, "rows": rows_cmd, "report": report_cmd}[a.cmd](a)
