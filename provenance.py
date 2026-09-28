"""Small stdlib-only helpers for verifying vendored-source provenance."""
from __future__ import annotations

import hashlib
from pathlib import Path


def git_blob_sha(path: str | Path) -> str:
    """Return the Git blob object ID for a file without invoking Git."""
    data = Path(path).read_bytes()
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()
