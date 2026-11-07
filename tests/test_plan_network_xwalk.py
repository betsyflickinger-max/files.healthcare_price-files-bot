"""Plan -> network crosswalk snapshots from made-up catalog files; a plan followed across a file-format change.
Run: python -m pytest tests/"""
import csv
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "insurers"))
import plan_network_xwalk as X  # noqa: E402


def catalog_month(root, ins, month, nets, plans, sets):
    base = root / "bot" / "catalog" / ins / month
    base.mkdir(parents=True)
    (base / "catalog.json").write_text(json.dumps(dict(last_updated_on=f"{month}-01", networks=nets)))
    with gzip.open(base / "network_sets.csv.gz", "wt", newline="") as f:
        w = csv.writer(f); w.writerow(["network_set", "networks"]); w.writerows(sets)
    with gzip.open(base / "employers.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_sponsor_name", "plan_id", "plan_id_type", "plan_name", "plan_market_type", "issuer_name", "network_set"])
        w.writerows(plans)


def test_snapshots_and_follow(tmp_path):
    plan = ["ACME CORP", "123456789", "EIN", "ACME PPO", "group", "Cigna", "1"]
    # today: per-plan file keys, no network id
    catalog_month(tmp_path, "cigna", "2027-01", [dict(network="cigna_national-oap", description="Open Access Plus", state="")],
                  [plan], [["1", "cigna_national-oap"]])
    # after the change (made up): one file per network, with the network's own id and name
    catalog_month(tmp_path, "cigna", "2027-04", [dict(network="cigna_net-0042", description="", network_id="NET-0042",
                                                      network_name="Cigna OAP Texas")],
                  [plan], [["1", "cigna_net-0042"]])
    fs = X.Files(str(tmp_path))
    done = X.build(fs, ["cigna"], work=str(tmp_path / "w"))
    assert [(i, m, n) for i, m, n in done] == [("cigna", "2027-01", 1), ("cigna", "2027-04", 1)]
    assert X.build(fs, ["cigna"], work=str(tmp_path / "w")) == []          # never overwritten without --force
    hist = X.follow(fs, "123456789", work=str(tmp_path / "w"))
    assert hist == [("cigna", "2027-01", "cigna_national-oap", "", "Open Access Plus"),
                    ("cigna", "2027-04", "cigna_net-0042", "NET-0042", "")]
