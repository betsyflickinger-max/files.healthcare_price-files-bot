"""Rent and return DigitalOcean machines. Every machine is tagged so the bot can always find and delete it."""
import os
import time

import requests

API = "https://api.digitalocean.com/v2"
TAG = "upfront-bot"
REGION = "nyc3"            # near AWS us-east-1, where most insurer files are hosted
IMAGE = "ubuntu-24-04-x64"
DEFAULT_SIZE = "s-4vcpu-8gb"  # 4 vCPU / 8 GB / 160 GB disk; new accounts can't rent 8 vCPU


def _h():
    tok = "".join(os.environ.get("DIGITALOCEAN_TOKEN", "").split())
    if not tok:
        raise RuntimeError("DIGITALOCEAN_TOKEN is not set")
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


FALLBACK_REGIONS = ["nyc1", "sfo3"]  # same list the website build uses when nyc3 has no room


# Oct 12-13, 2026: DigitalOcean answered "Size is not available in this region" for s-4vcpu-8gb in nyc3, nyc1 and
# sfo3, which left 151 queued files waiting. When a size has no room anywhere, try these similar sizes in turn.
SIMILAR = {"s-4vcpu-8gb": ["s-4vcpu-8gb-amd", "s-4vcpu-8gb-intel", "s-8vcpu-16gb-amd"]}


def create(name, user_data, size=DEFAULT_SIZE):
    """Rent a machine in nyc3; if DigitalOcean has no room for that size there (422), try nyc1, then sfo3, then
    the same regions with a similar size (and finally the default size)."""
    r = None
    sizes = [size] + SIMILAR.get(size, []) + ([DEFAULT_SIZE] + SIMILAR[DEFAULT_SIZE] if size != DEFAULT_SIZE else [])
    for s in dict.fromkeys(sizes):
        for region in [REGION] + FALLBACK_REGIONS:
            body = dict(name=name, region=region, size=s, image=IMAGE, tags=["upfront", TAG], user_data=user_data,
                        monitoring=False, ipv6=False)
            r = requests.post(f"{API}/droplets", json=body, headers=_h(), timeout=60)
            if r.status_code != 422:
                break
        if r.status_code != 422:
            break
    if r.status_code >= 300:
        raise RuntimeError(f"DigitalOcean {r.status_code}: {r.text[:300]}")
    return r.json()["droplet"]


def mine():
    """Every machine the bot rented that still exists: list of (id, name, created_at)."""
    r = requests.get(f"{API}/droplets", params={"tag_name": TAG, "per_page": 200}, headers=_h(), timeout=60)
    r.raise_for_status()
    return [(d["id"], d["name"], d["created_at"]) for d in r.json()["droplets"]]


def delete(droplet_id):
    for _ in range(3):
        r = requests.delete(f"{API}/droplets/{droplet_id}", headers=_h(), timeout=60)
        if r.status_code in (204, 404):
            return True
        time.sleep(10)
    return False


def names():
    """Names of every machine on the account, including other jobs' (e.g. website builds)."""
    r = requests.get(f"{API}/droplets", params={"per_page": 200}, headers=_h(), timeout=60)
    r.raise_for_status()
    return [d["name"] for d in r.json()["droplets"]]


def room():
    """Free machine slots on the account (DigitalOcean caps how many can exist at once)."""
    acct = requests.get(f"{API}/account", headers=_h(), timeout=60).json()["account"]
    r = requests.get(f"{API}/droplets", params={"per_page": 200}, headers=_h(), timeout=60)
    r.raise_for_status()
    return int(acct.get("droplet_limit") or 3) - len(r.json()["droplets"])
