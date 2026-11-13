"""site_r2.publish tries failed copies again before giving up (Nov 13, 2026)."""
import os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))
import site_r2


def setup(monkeypatch, fail_times):
    keys = ["site/a.json", "site/b.json", "site/c.json"]
    tries = {}
    monkeypatch.setattr(site_r2, "enabled", lambda: True)
    monkeypatch.setattr(site_r2, "mark_moved", lambda dry=False: None)
    monkeypatch.setattr(site_r2, "refs", lambda d: ([], list(keys)))
    monkeypatch.setattr(site_r2, "src", lambda: (None, "s"))
    monkeypatch.setattr(site_r2, "dst", lambda: (None, "d"))
    monkeypatch.setattr(site_r2, "switched_at", lambda s, sb: 0.0)
    monkeypatch.setattr(site_r2, "_head", lambda c, b, k: (1, 1.0) if b == "s" else None)
    monkeypatch.setattr(site_r2.time, "sleep", lambda s: None)

    def copy(k):
        tries[k] = tries.get(k, 0) + 1
        if k == "site/b.json" and tries[k] <= fail_times:
            raise RuntimeError("Reduce your concurrent request rate for the same object")
        return k
    monkeypatch.setattr(site_r2, "_copy", copy)
    return tries


def test_one_failed_copy_is_tried_again(monkeypatch):
    tries = setup(monkeypatch, fail_times=1)
    out = site_r2.publish("functions", log=lambda *a: None)
    assert tries == {"site/a.json": 1, "site/b.json": 2, "site/c.json": 1}
    assert out["to_copy"] == 3


def test_still_failing_copy_stops_the_deploy(monkeypatch):
    setup(monkeypatch, fail_times=5)
    with pytest.raises(RuntimeError, match="1 of 3 copies failed"):
        site_r2.publish("functions", log=lambda *a: None)
