"""One-shot PR observations and explicit comments using the canonical parent producer.

Stdlib-only. No scheduler, notification delivery or automatic comment retry.
Snapshots are local JSON; serialize callers that share the same snapshot path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from vendor import gh_ops
from github_adapter import local_identity_from_repository_metadata, compare_pull_head_identity


def _load_snapshot(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("snapshot must be a JSON object")
    gh_ops.pr_observation_diff(value, value)  # Producer owns schema/staleness validation.
    return value


def _save_snapshot(path: Path, observation: dict) -> None:
    """Replace only after a complete JSON file has been written successfully."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pr-observation-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(observation, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def observe_pr(repo: str, number: int, *, snapshot: str | Path | None = None,
               min_checks: int = 1, local_metadata: str | Path | None = None,
               client: gh_ops.Client | None = None) -> dict:
    """Observe once; optionally compare and replace a last-successful local snapshot.

    First observation has no diff (not a CI transition). Stale/read failures leave
    the prior snapshot untouched. Pending/failed CI is a valid observation, not
    an observation failure. The returned ``ok`` does not mean CI is green.
    """
    path = Path(snapshot) if snapshot is not None else None
    previous = None
    if path is not None:
        try:
            previous = _load_snapshot(path)
        except FileNotFoundError:
            pass
        if previous is not None and (previous.get("repo"), previous.get("number")) != (repo, number):
            raise ValueError("snapshot belongs to a different pull request")
    current = gh_ops.pr_observe(repo, number, min_checks=min_checks, client=client)
    identity = None
    if local_metadata is not None:
        record = json.loads(Path(local_metadata).read_text(encoding="utf-8"))
        local = local_identity_from_repository_metadata(record)
        identity = compare_pull_head_identity(
            {"number": number, "head": {"sha": current.get("head_sha")}, "base": {}},
            local,
        )
    if not current["ok"]:
        return {"ok": False, "observation": current, "diff": None, "snapshot_saved": False,
                "identity": identity}
    difference = gh_ops.pr_observation_diff(previous, current) if previous is not None else None
    if path is not None:
        _save_snapshot(path, current)
    return {"ok": True, "observation": current, "diff": difference,
            "snapshot_saved": path is not None, "identity": identity}


def compare_pr_snapshots(before: str | Path, after: str | Path) -> dict:
    """Compare saved observations offline using the producer's event contract."""
    return gh_ops.pr_observation_diff(_load_snapshot(Path(before)), _load_snapshot(Path(after)))


def comment_pr(repo: str, number: int, *, body: str, write: bool = False,
               client: gh_ops.Client | None = None) -> dict:
    """Return the producer result unchanged, including posted/verified uncertainty."""
    return gh_ops.issue_comment_create(repo, number, body=body, write=write, client=client)


def main(argv: list[str] | None = None, *, client: gh_ops.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe", help="observe once, optionally compare/save a snapshot")
    observe.add_argument("repo")
    observe.add_argument("number", type=int)
    observe.add_argument("--snapshot", type=Path)
    observe.add_argument("--min-checks", type=int, default=1)
    observe.add_argument("--local-metadata", type=Path)
    diff = commands.add_parser("diff", help="compare two saved snapshots offline")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    comment = commands.add_parser("comment", help="preview a PR comment; --write explicitly posts it")
    comment.add_argument("repo")
    comment.add_argument("number", type=int)
    comment.add_argument("--body-file", required=True, type=Path)
    comment.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "observe":
            result = observe_pr(args.repo, args.number, snapshot=args.snapshot,
                                min_checks=args.min_checks, local_metadata=args.local_metadata,
                                client=client)
        elif args.command == "diff":
            result = compare_pr_snapshots(args.before, args.after)
        else:
            result = comment_pr(args.repo, args.number, body=args.body_file.read_text(encoding="utf-8"),
                                write=args.write, client=client)
    except (gh_ops.GhOpsError, OSError, ValueError) as error:
        print(gh_ops.scrub(f"error: {error}"), file=sys.stderr)
        return 2
    print(gh_ops.scrub(json.dumps(result, ensure_ascii=False, indent=2)))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
