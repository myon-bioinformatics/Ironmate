"""Public repository metadata contract v1.

Stdlib-only: deterministic generation/validation/serialization for static Pages.
The contract deliberately excludes host/user identity, environment variables,
credentials, local absolute paths and private remotes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "1.0"
PUBLIC_FIELDS = ("schema_version", "repository", "head", "measurements", "tooling", "generated_at")
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def repository_identity(full_name: str) -> tuple[str, str]:
    """Validate and split a public GitHub repository identity."""
    if not isinstance(full_name, str) or full_name.count("/") != 1:
        raise ValueError("full_name must be owner/name")
    owner, name = full_name.split("/", 1)
    if not _OWNER_RE.fullmatch(owner):
        raise ValueError("owner must use GitHub-safe alphanumeric/hyphen form")
    if not _REPO_RE.fullmatch(name) or name in {".", ".."}:
        raise ValueError("repository name is invalid")
    return owner, name


def pages_candidate_url(full_name: str) -> str:
    """Return the canonical GitHub Pages candidate URL, without claiming reachability."""
    owner, name = repository_identity(full_name)
    if name.lower() == f"{owner.lower()}.github.io":
        return f"https://{owner}.github.io/"
    return f"https://{owner}.github.io/{name}/"



def _validate_measurements(measurements: dict[str, Any]) -> None:
    expected = {"github_reported_size_bytes", "working_tree_bytes", "release_artifact_bytes"}
    if set(measurements) != expected:
        raise ValueError("invalid measurements")
    if any(
        value is not None and
        (not isinstance(value, int) or isinstance(value, bool) or value < 0)
        for value in measurements.values()
    ):
        raise ValueError("measurements must be non-negative integers or null")


def _iso8601(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return value


def build_repository_record(
    *,
    full_name: str,
    sha: str,
    branch: str,
    timestamp: str,
    subject: str,
    generated_at: str,
    github_reported_size_bytes: int | None = None,
    working_tree_bytes: int | None = None,
    release_artifact_bytes: int | None = None,
    tooling: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one canonical, public-safe repository metadata record."""
    if not sha or not branch or not subject:
        raise ValueError("sha, branch and subject are required")
    repository_identity(full_name)
    _iso8601(timestamp)
    _iso8601(generated_at)
    sizes = {
        "github_reported_size_bytes": github_reported_size_bytes,
        "working_tree_bytes": working_tree_bytes,
        "release_artifact_bytes": release_artifact_bytes,
    }
    _validate_measurements(sizes)
    record = {
        "schema_version": SCHEMA_VERSION,
        "repository": {"full_name": full_name},
        "head": {
            "sha": sha,
            "short_sha": sha[:8],
            "branch": branch,
            "timestamp": timestamp,
            "subject": subject.splitlines()[0],
        },
        "measurements": sizes,
        "tooling": dict(tooling or {}),
        "generated_at": generated_at,
    }
    validate_repository_record(record)
    return record


def validate_repository_record(record: dict[str, Any]) -> None:
    """Validate the stable v1 shape without third-party schema packages."""
    if set(record) != set(PUBLIC_FIELDS):
        raise ValueError("unexpected or missing top-level fields")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    head = record.get("head", {})
    if set(head) != {"sha", "short_sha", "branch", "timestamp", "subject"}:
        raise ValueError("invalid head")
    if head["short_sha"] != head["sha"][:8]:
        raise ValueError("short_sha must be the first 8 characters of sha")
    _iso8601(head["timestamp"])
    _iso8601(record["generated_at"])
    if set(record.get("repository", {})) != {"full_name"}:
        raise ValueError("invalid repository")
    repository_identity(record["repository"]["full_name"])
    _validate_measurements(record.get("measurements", {}))


def format_commit_line(record: dict[str, Any]) -> str:
    """Canonical first line shared by every repository."""
    validate_repository_record(record)
    head = record["head"]
    return f"Commit {head['short_sha']} · {head['branch']} · {head['timestamp']} · {head['subject']}"


def to_json(record: dict[str, Any]) -> str:
    validate_repository_record(record)
    return json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def to_jsonl(record: dict[str, Any]) -> str:
    validate_repository_record(record)
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
