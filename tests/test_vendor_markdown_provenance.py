"""Verify Ironmate's vendored Markdown source against its pinned provenance."""

import hashlib
import json
from pathlib import Path

from provenance import git_blob_sha


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PROVENANCE = {
    "repository": "https://github.com/myon-bioinformatics/markdown",
    "path": "markdown.py",
    "commit": "fa5183818cdec658d223a2dd3d127eccb76e04ba",
    "blob_sha": "5b428826e03780036bac3a0439b62b2ad8a8403b",
    "sha256": "14326092ea5d4dc03142e5254394c59723ce46b07112352d4d1f9f650dfc04e5",
    "date": "2026-09-27",
}


def test_vendor_markdown_matches_literal_provenance_pin():
    manifest = json.loads(
        (ROOT / "vendor" / "markdown.provenance.json").read_text(encoding="utf-8")
    )
    assert manifest == EXPECTED_PROVENANCE

    source = ROOT / "vendor" / "markdown.py"
    source_bytes = source.read_bytes()
    assert git_blob_sha(source) == EXPECTED_PROVENANCE["blob_sha"]
    assert hashlib.sha256(source_bytes).hexdigest() == EXPECTED_PROVENANCE["sha256"]
