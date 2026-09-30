"""Verify Ironmate's vendored Markdown source against its pinned provenance."""

import hashlib
import json
from pathlib import Path

from provenance import git_blob_sha
from scripts.build_web_ui_consumer_examples import MARKDOWN_SHA


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PROVENANCE = {
    "repository": "https://github.com/myon-bioinformatics/markdown",
    "path": "markdown.py",
    "commit": "c3063e0887c6eb6a531ee774793682ceff8a164d",
    "blob_sha": "a20c59e7e28d811e48152b7359275cb0888c304d",
    "sha256": "a07648ec6ec6db6b431404e0735cc0b4947c62bc824f9adffbb0bf6c2b92040b",
    "date": "2026-09-30",
}


def test_vendor_markdown_matches_literal_provenance_pin():
    manifest = json.loads(
        (ROOT / "vendor" / "markdown.provenance.json").read_text(encoding="utf-8")
    )
    assert manifest == EXPECTED_PROVENANCE
    assert manifest["commit"] == MARKDOWN_SHA

    source = ROOT / "vendor" / "markdown.py"
    source_bytes = source.read_bytes()
    assert git_blob_sha(source) == EXPECTED_PROVENANCE["blob_sha"]
    assert hashlib.sha256(source_bytes).hexdigest() == EXPECTED_PROVENANCE["sha256"]
