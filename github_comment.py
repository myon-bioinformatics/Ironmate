"""Post a comment to a GitHub issue or pull request in one line, and print where it landed.

    python github_comment.py OWNER/REPO NUMBER --body "text"
    python github_comment.py OWNER/REPO NUMBER --body-file reply.md
    some-command | python github_comment.py OWNER/REPO NUMBER --body-file -
    python github_comment.py OWNER/REPO NUMBER --body-file reply.md --dry-run   # show, do not post

Posting goes through the GitHub CLI (`gh api`), so authentication, proxies and
tokens stay with `gh`; this module never reads or stores a token. The body is
sent as JSON on stdin (`gh api --input -`), so quotes, newlines and Markdown
reach GitHub unchanged and no temporary file is needed.

Prints the comment URL on success (`--json` prints {"id", "url"} instead).
Exit codes: 0 posted (or shown with --dry-run), 1 gh failed, 2 bad arguments.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Callable

REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def comment_command(repo: str, number: int) -> list[str]:
    """The gh command that creates an issue/PR comment (PR comments use the issues endpoint)."""
    if not REPO_RE.match(repo):
        raise ValueError(f"repository must be OWNER/REPO: {repo!r}")
    if number <= 0:
        raise ValueError(f"issue or pull request number must be positive: {number}")
    return ["gh", "api", f"repos/{repo}/issues/{number}/comments", "--method", "POST", "--input", "-"]


def post_comment(repo: str, number: int, body: str, run: Callable = subprocess.run) -> dict:
    """Post `body` and return {"id", "url"}. Raises ValueError for bad input, RuntimeError when gh fails."""
    if not body.strip():
        raise ValueError("comment body is empty")
    cmd = comment_command(repo, number)
    try:
        done = run(cmd, input=json.dumps({"body": body}), capture_output=True, text=True)
    except OSError as exc:
        raise RuntimeError(f"failed to launch gh: {exc}") from exc
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout or "gh api failed").strip())
    try:
        data = json.loads(done.stdout)
        return {"id": data["id"], "url": data["html_url"]}
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"unexpected response from gh: {done.stdout[:200]!r}") from exc


def read_body(args: argparse.Namespace, stdin=sys.stdin) -> str:
    if args.body is not None:
        return args.body
    if args.body_file == "-":
        return stdin.read()
    with open(args.body_file, encoding="utf-8") as f:
        return f.read()


def main(argv: list[str] | None = None, run: Callable = subprocess.run, stdin=sys.stdin, out=sys.stdout,
         err=sys.stderr) -> int:
    ap = argparse.ArgumentParser(description="Post a comment to a GitHub issue or pull request and print its URL.")
    ap.add_argument("repo", help="OWNER/REPO")
    ap.add_argument("number", type=int, help="issue or pull request number")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--body", help="comment text")
    src.add_argument("--body-file", help="file with the comment text ('-' reads stdin)")
    ap.add_argument("--dry-run", action="store_true", help="print the command and body without posting")
    ap.add_argument("--json", action="store_true", help='print {"id", "url"} as JSON')
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        body = read_body(args, stdin)
        if args.dry_run:
            cmd = comment_command(args.repo, args.number)
            if not body.strip():
                raise ValueError("comment body is empty")
            print(" ".join(cmd), file=out)
            print(body, file=out)
            return 0
        result = post_comment(args.repo, args.number, body, run=run)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=err)
        return 2
    except RuntimeError as exc:
        print(f"error: {exc}", file=err)
        return 1
    print(json.dumps(result) if args.json else result["url"], file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
