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


def test_catalog_does_not_claim_locked_installation():
    catalog = json.loads((ROOT / "vendor-catalog.json").read_text(encoding="utf-8"))
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    locked = {entry["repository"] for entry in lock["files"]}
    assert "myon-bioinformatics/cli_args" not in locked
    assert len({item["repository"] for item in catalog["tools"]}) > len(locked)
