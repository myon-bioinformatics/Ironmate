"""Parent vendor catalog snapshot: visibility does not imply enrollment."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_complete_and_explicit():
    catalog = json.loads((ROOT / "vendor-catalog.json").read_text(encoding="utf-8"))
    assert catalog["schema"] == "vendor-catalog/1"
    tools = catalog["tools"]
    assert len(tools) == 30
    assert len({(item["repository"], item.get("source")) for item in tools}) == len(tools)
    assert any(item["repository"] == "myon-bioinformatics/cli_args" for item in tools)
    assert any(item.get("default_enrollment", {}).get("enrollment") == "skipped" for item in tools)


def test_catalog_enrollment_is_explicit_and_complete():
    catalog = json.loads((ROOT / "vendor-catalog.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    assert len(lock["files"]) == 53
    locked = {(entry["repository"], entry["source"]) for entry in lock["files"]}
    assert all(
        (item["repository"], item.get("source", item["repository"].split("/")[1] + ".py")) in locked
        for item in catalog["tools"]
    )
    assert ("myon-bioinformatics/cli_args", "cli_args.py") in locked
    assert len({entry["destination"] for entry in lock["files"]}) == 53
