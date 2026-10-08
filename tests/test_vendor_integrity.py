"""Check every retained source and license against the consumer lock."""
import hashlib
import json
from pathlib import Path


def test_all_locked_files_match_recorded_identity():
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "vendor.lock.json").read_text())
    assert lock["schema"] == "vendor-lock/1"
    for entry in lock["files"]:
        path = root / entry["destination"]
        assert not path.is_symlink(), entry["destination"]
        data = path.read_bytes()
        blob = b"blob " + str(len(data)).encode() + b"\0" + data
        assert hashlib.sha1(blob).hexdigest() == entry["blob_sha"], entry["destination"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["destination"]
