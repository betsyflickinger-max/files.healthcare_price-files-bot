import os, sys, pytest
from botocore.exceptions import ClientError
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import pages_spill


class S3:
    def __init__(self, has): self.has = has
    def head_object(self, Bucket, Key):
        if self.has: return {}
        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


def test_hand_publish_stops_after_move(monkeypatch):
    monkeypatch.delenv("STORAGE_ENDPOINT", raising=False)
    with pytest.raises(SystemExit) as e:
        pages_spill.refuse_if_moved(S3(True), "b")
    assert "STOP" in str(e.value)


def test_hand_publish_ok_before_move(monkeypatch):
    monkeypatch.delenv("STORAGE_ENDPOINT", raising=False)
    pages_spill.refuse_if_moved(S3(False), "b")


def test_bot_jobs_never_stop(monkeypatch):
    monkeypatch.setenv("STORAGE_ENDPOINT", "https://s3.us-east-005.backblazeb2.com")
    pages_spill.refuse_if_moved(S3(True), "b")
