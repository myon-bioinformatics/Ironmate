"""Verify Ironmate's vendored Markdown source against its pinned provenance."""

from datetime import date
import hashlib
import json
from pathlib import Path

from provenance import git_blob_sha
from scripts.build_web_ui_consumer_examples import MARKDOWN_SHA


def _locked(destination):
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    return next(e for e in lock["files"] if e["destination"] == destination)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PROVENANCE = {
    "repository": "https://github.com/myon-bioinformatics/markdown",
    "path": "markdown.py",
    "commit": _locked('vendor/markdown.py')['commit'],
    "blob_sha": _locked('vendor/markdown.py')['blob_sha'],
    "sha256": _locked('vendor/markdown.py')['sha256'],
}


def test_vendor_markdown_matches_literal_provenance_pin():
    manifest = json.loads(
        (ROOT / "vendor" / "markdown.provenance.json").read_text(encoding="utf-8")
    )
    assert {k: v for k, v in manifest.items() if k != "date"} == EXPECTED_PROVENANCE
    date.fromisoformat(manifest["date"])
    assert manifest["commit"] == MARKDOWN_SHA

    source = ROOT / "vendor" / "markdown.py"
    source_bytes = source.read_bytes()
    assert git_blob_sha(source) == EXPECTED_PROVENANCE["blob_sha"]
    assert hashlib.sha256(source_bytes).hexdigest() == EXPECTED_PROVENANCE["sha256"]
