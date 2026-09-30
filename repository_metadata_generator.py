#!/usr/bin/env python3
"""Generate canonical repository metadata JSON and JSONL from a Git checkout.

Keep this file beside repository_metadata_contract.py when vendoring it.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
import os
import platform
import re
import shutil
import subprocess

from repository_metadata_contract import build_repository_record, to_json, to_jsonl


_TOOL_COMMANDS = {
    "git": ("--version",),
    "gh": ("--version",),
    "node": ("--version",),
    "npm": ("--version",),
    "npx": ("--version",),
}
_CLI_VERSION = r"[0-9]+(?:\.[0-9]+)+(?:[-+._][0-9A-Za-z][0-9A-Za-z.-]*)?"
_PACKAGE_VERSION = r"[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc|dev|post)[0-9]+)?(?:\+[0-9A-Za-z][0-9A-Za-z.-]*)?"
_TOOL_PATTERNS = {
    "git": re.compile(r"^git version (?P<version>" + _CLI_VERSION + r")(?:\s.*)?$"),
    "gh": re.compile(r"^gh version (?P<version>" + _CLI_VERSION + r")(?:\s.*)?$"),
    "node": re.compile(r"^v(?P<version>" + _CLI_VERSION + r")$"),
    "npm": re.compile(r"^(?P<version>" + _CLI_VERSION + r")$"),
    "npx": re.compile(r"^(?P<version>" + _CLI_VERSION + r")$"),
    "python": re.compile(r"^(?P<version>" + _PACKAGE_VERSION + r")$"),
}
_PLAIN_VERSION_RE = re.compile(r"^(?P<version>" + _PACKAGE_VERSION + r")$")
_DEFAULT_TOOL_TIMEOUT = 5.0


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", "i18n.logOutputEncoding=UTF-8", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def normalize_version_output(tool: str, text: str) -> str | None:
    """Return one short public version label, or None for unparseable output."""
    if not isinstance(text, str):
        return None
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first or any(ord(char) < 32 for char in first):
        return None
    pattern = _TOOL_PATTERNS.get(tool, _PLAIN_VERSION_RE)
    match = pattern.fullmatch(first)
    if not match:
        return None
    version = match.group("version")
    return version if len(version) <= 32 else None


def observe_command_version(command: str, *, timeout: float = _DEFAULT_TOOL_TIMEOUT) -> str | None:
    """Observe one allowlisted CLI version without leaking execution details."""
    args = _TOOL_COMMANDS.get(command)
    if args is None:
        raise ValueError("unsupported tooling command: " + command)
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    candidate = result.stdout.strip() or result.stderr.strip()
    return normalize_version_output(command, candidate)


def observe_package_version(distribution: str) -> str | None:
    """Observe one explicitly requested Python distribution version."""
    try:
        value = importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None
    return normalize_version_output(distribution, value)


def _requested_tooling_keys(
    *,
    include_python: bool,
    commands: Sequence[str],
    distributions: Sequence[tuple[str, str]],
) -> tuple[str, ...]:
    if isinstance(commands, (str, bytes)):
        raise TypeError("commands must be a sequence of command names")
    requested: list[str] = ["python"] if include_python else []
    for command in commands:
        if command not in _TOOL_COMMANDS:
            raise ValueError("unsupported tooling command: " + str(command))
        requested.append(command)
    for key, distribution in distributions:
        if not isinstance(key, str) or not key:
            raise ValueError("distribution tooling key must be non-empty")
        if not isinstance(distribution, str) or not distribution:
            raise ValueError("distribution name must be non-empty")
        requested.append(key)
    if len(requested) != len(set(requested)):
        raise ValueError("tooling keys must have exactly one canonical source")
    return tuple(requested)


def collect_portable_tooling(
    *,
    include_python: bool = True,
    commands: Sequence[str] = (),
    distributions: Sequence[tuple[str, str]] = (),
) -> dict[str, str]:
    """Collect canonical portable tooling with explicit, collision-safe ownership."""
    _requested_tooling_keys(
        include_python=include_python,
        commands=commands,
        distributions=distributions,
    )
    observed: dict[str, str] = {}
    if include_python:
        value = normalize_version_output("python", platform.python_version())
        if value is not None:
            observed["python"] = value
    for command in commands:
        value = observe_command_version(command)
        if value is not None:
            observed[command] = value
    for key, distribution in distributions:
        value = observe_package_version(distribution)
        if value is not None:
            observed[key] = value
    return observed


def record_from_checkout(
    root: Path,
    full_name: str,
    *,
    env: Mapping[str, str] | None = None,
    github_reported_size_bytes: int | None = None,
    working_tree_bytes: int | None = None,
    release_artifact_bytes: int | None = None,
    tooling: Mapping[str, str] | None = None,
    include_python_tooling: bool = False,
    tooling_commands: Sequence[str] = (),
    tooling_distributions: Sequence[tuple[str, str]] = (),
) -> dict:
    env = os.environ if env is None else env
    supplied = dict(tooling or {})
    requested = set(_requested_tooling_keys(
        include_python=include_python_tooling,
        commands=tooling_commands,
        distributions=tooling_distributions,
    ))
    overlap = set(supplied).intersection(requested)
    if overlap:
        raise ValueError("caller tooling overlaps canonical tooling: " + ", ".join(sorted(overlap)))

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

    canonical = collect_portable_tooling(
        include_python=include_python_tooling,
        commands=tooling_commands,
        distributions=tooling_distributions,
    ) if (include_python_tooling or tooling_commands or tooling_distributions) else {}
    supplied.update(canonical)

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
        tooling=supplied,
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
