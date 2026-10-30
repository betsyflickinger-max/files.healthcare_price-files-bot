"""CareSource adapter (Oct 29, 2026): turn CareSource's in-network files into the CMS layout the reader expects.

CareSource (IN, KY, OH marketplace) posts each file as a zip of zips of JSON parts, and the JSON is not the CMS schema:
  - the list is "in_networks" (CMS: "in_network")
  - "negotiated_rates" is one object (IN) or a list of prices (OH), not CMS's list of {provider_references,
    negotiated_prices}; prices are either in "negotiated_prices" or written straight onto that object
  - the price is "Price" (CMS: "negotiated_rate"); the expiry key is "expiration_date," (with the comma)
  - "provider_references" sits on the item, not inside the negotiated rate
  - each part has its own provider_references list, so group ids repeat across parts
  - "last_updated_on" appears twice in the header (2026-10-27 and 10/27/2026), or only in the zip's index JSON (OH)
  - IN's nonspecific file is a zip of zips; OH's specific file is a zip of JSON parts plus an index

Nothing is estimated or dropped: every price keeps its own negotiated_type (CareSource lists "percentage" rates too,
where Price is a percent, not dollars), billing class, setting, service codes and expiry. Group ids are renumbered per
part so they can't collide. Inner zips are unpacked to disk once (KY's file is 6.7 GB), not held in memory.

    python caresource.py <caresource zip> <out .json.gz>
"""
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime

import ijson


def unpack(path, work):
    """Unpack the outer zip's inner zips to `work` once; return [(kind, path, member)] for every JSON part."""
    out, outer = [], zipfile.ZipFile(path)
    for n in sorted(outer.namelist()):
        if n.endswith("/"):
            continue
        if n.lower().endswith(".zip"):
            dst = os.path.join(work, os.path.basename(n))
            with outer.open(n) as src, open(dst, "wb") as f:
                shutil.copyfileobj(src, f, 16 << 20)
            out += [("zip", dst, m) for m in sorted(zipfile.ZipFile(dst).namelist()) if m.lower().endswith(".json")]
        elif n.lower().endswith(".json"):
            out.append(("zip", path, n))
    return out


def parts(plist):
    """Yield (name, binary stream) for every JSON part."""
    for _, zpath, m in plist:
        with zipfile.ZipFile(zpath) as z, z.open(m) as fb:
            yield m, fb


def iso(d):
    d = (d or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(d, fmt).date().isoformat()
        except ValueError:
            pass
    return d


def header(plist):
    """Top-level fields from the parts, up to the price list. Ohio's parts carry no last_updated_on; its date is in the
    zip's own index JSON (careSource_HIXOH_in-network-rates_index.json), so keep looking until one turns up."""
    h = {}
    for _, fb in parts(plist):
        for prefix, event, value in ijson.parse(fb):
            if prefix in ("in_networks", "provider_references", "in_network_files"):
                break
            if event in ("string", "number") and "." not in prefix and prefix:
                h.setdefault(prefix, value)   # the first of two last_updated_on values
        if h.get("last_updated_on"):
            break
    return h


def price(p):
    out = {"negotiated_type": p.get("negotiated_type"),
           "negotiated_rate": p.get("negotiated_rate", p.get("Price")),
           "expiration_date": p.get("expiration_date", p.get("expiration_date,")),
           "billing_class": p.get("billing_class")}
    for k in ("service_code", "billing_code_modifier", "additional_information"):
        if p.get(k) not in (None, "", []):
            out[k] = p[k]
    if p.get("setting"):
        out["setting"] = p["setting"]   # the reader keeps a setting column
    return out


def num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def convert(src, dest):
    work = tempfile.mkdtemp(dir=os.path.dirname(os.path.abspath(dest)))
    try:
        return _convert(unpack(src, work), dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _convert(src, dest):
    h = header(src)
    head = {"reporting_entity_name": h.get("reporting_entity_name", "CareSource"),
            "reporting_entity_type": h.get("reporting_entity_type", "Health Insurance Issuer"),
            "last_updated_on": iso(h.get("last_updated_on")), "version": "1.0.0"}
    ids = {}   # (part, original id) -> new id

    def new_id(part, old):
        k = (part, str(old).strip())
        if k not in ids:
            ids[k] = len(ids) + 1
        return ids[k]

    n_refs = n_items = n_prices = 0
    with gzip.open(dest, "wt", encoding="utf-8", compresslevel=3) as out:
        out.write(json.dumps(head)[:-1] + ', "provider_references": [')
        first = True
        for i, (name, fb) in enumerate(parts(src)):
            for r in ijson.items(fb, "provider_references.item", use_float=True):
                r = dict(r, provider_group_id=new_id(i, r.get("provider_group_id")))
                for g in r.get("provider_groups") or []:
                    t = g.get("tin") or {}
                    if isinstance(t.get("value"), str):
                        t["value"] = t["value"].strip()   # CareSource pads some TINs with a space
                out.write(("" if first else ",") + json.dumps(r))
                first = False
                n_refs += 1
        out.write('], "in_network": [')
        first = True
        for i, (name, fb) in enumerate(parts(src)):
            for it in ijson.items(fb, "in_networks.item", use_float=True):
                nr = it.get("negotiated_rates") or {}
                groups = nr if isinstance(nr, list) else [nr]
                rates = []
                for g in groups:
                    ps = g.get("negotiated_prices")
                    ps = ps if isinstance(ps, list) else ([g] if ("Price" in g or "negotiated_rate" in g) else [])
                    refs = g.get("provider_references") or it.get("provider_references") or []
                    refs = [new_id(i, x) for x in (refs if isinstance(refs, list) else [refs])]
                    if ps and refs:
                        rates.append({"provider_references": refs, "negotiated_prices": [price(p) for p in ps]})
                        n_prices += len(ps)
                item = {k: it.get(k) for k in ("negotiation_arrangement", "name", "billing_code_type",
                                                 "billing_code_type_version", "billing_code", "description")}
                for k in ("bundled_codes", "covered_services", "severity_of_illness"):
                    if it.get(k) not in (None, "", []):
                        item[k] = it[k]
                item["negotiated_rates"] = rates
                out.write(("" if first else ",") + json.dumps(item))
                first = False
                n_items += 1
        out.write("]}")
    print(f"  CareSource adapter: {n_items:,} items, {n_prices:,} prices, {n_refs:,} provider groups "
          f"(file dated {head['last_updated_on']}) -> CMS layout", flush=True)
    return dest


def is_caresource(url):
    return bool(re.search(r"(^|//|\.)caresource\.com/", url or "")) and (url or "").split("?")[0].lower().endswith(".zip")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
