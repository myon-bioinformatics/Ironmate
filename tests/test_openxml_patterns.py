"""Contract tests for tri-state editability master registry."""
from pathlib import Path
import tomllib

REGISTRY = Path(__file__).parent / "fixtures/openxml/editability_patterns.toml"


def test_registry_has_unique_ids_and_fail_closed_default():
    with REGISTRY.open("rb") as stream:
        data = tomllib.load(stream)
    assert data["schema_version"] == 1
    assert data["default_status"] == "unknown"
    patterns = data["patterns"]
    assert len(patterns) >= 3
    assert len({p["id"] for p in patterns}) == len(patterns)
    assert all(p["status"] in {"editable", "unsupported", "unknown"} for p in patterns)
    assert all(p["operation"] and p["condition"] for p in patterns)
    assert all(p.get("evidence") for p in patterns if p["status"] == "editable")


def test_registry_does_not_claim_marp_image_text_is_editable():
    with REGISTRY.open("rb") as stream:
        patterns = tomllib.load(stream)["patterns"]
    image = next(p for p in patterns if p["id"] == "rasterized-slide-text")
    assert image["status"] == "unsupported"
    assert image["alternative"] == "regenerate_from_markdown"
