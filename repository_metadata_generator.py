#!/usr/bin/env python3
"""Generate canonical repository metadata JSON and JSONL from a Git checkout.

Keep this file beside repository_metadata_contract.py when vendoring it.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess

from repository_metadata_contract import build_repository_record, to_json, to_jsonl


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def record_from_checkout(
    root: Path,
    full_name: str,
    *,
    env: Mapping[str, str] | None = None,
    github_reported_size_bytes: int | None = None,
    working_tree_bytes: int | None = None,
    release_artifact_bytes: int | None = None,
    tooling: Mapping[str, str] | None = None,
) -> dict:
    env = os.environ if env is None else env
    sha = git("rev-parse", "HEAD", cwd=root)
    branch = (
        (env.get("GITHUB_HEAD_REF") or "").strip()
        or (env.get("GITHUB_REF_NAME") or "").strip()
        or git("rev-parse", "--abbrev-ref", "HEAD", cwd=root)
    )
    if branch == "HEAD":
        branch = "detached"
    timestamp = git("show", "-s", "--format=%cI", "HEAD", cwd=root)
    subject = git("show", "-s", "--format=%s", "HEAD", cwd=root)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return build_repository_record(
        full_name=full_name,
        sha=sha,
        branch=branch,
        timestamp=timestamp,
        subject=subject,
        generated_at=generated_at,
        github_reported_size_bytes=github_reported_size_bytes,
        working_tree_bytes=working_tree_bytes,
        release_artifact_bytes=release_artifact_bytes,
        tooling=dict(tooling or {}),
    )


def write_metadata(record: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "repository-metadata.json"
    jsonl_path = output_dir / "repository-metadata.jsonl"
    json_path.write_text(to_json(record), encoding="utf-8")
    jsonl_path.write_text(to_jsonl(record), encoding="utf-8")
    return json_path, jsonl_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/name")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    write_metadata(record_from_checkout(args.root.resolve(), args.repository), args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
