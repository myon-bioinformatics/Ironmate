"""Public repository metadata contract v1.

Stdlib-only: deterministic generation/validation/serialization for static Pages.
The contract deliberately excludes host/user identity, environment variables,
credentials, local absolute paths and private remotes.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "1.0"
PUBLIC_FIELDS = ("schema_version", "repository", "head", "measurements", "tooling", "generated_at")


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
    if "/" not in full_name or not sha or not branch or not subject:
        raise ValueError("full_name, sha, branch and subject are required")
    _iso8601(timestamp)
    _iso8601(generated_at)
    sizes = {
        "github_reported_size_bytes": github_reported_size_bytes,
        "working_tree_bytes": working_tree_bytes,
        "release_artifact_bytes": release_artifact_bytes,
    }
    if any(value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in sizes.values()):
        raise ValueError("measurements must be non-negative integers or null")
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
    if set(record.get("measurements", {})) != {
        "github_reported_size_bytes", "working_tree_bytes", "release_artifact_bytes"
    }:
        raise ValueError("invalid measurements")


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
