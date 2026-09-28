#!/usr/bin/env python3
"""List open GitHub issues/PRs missing a tagged reviewer comment.

Standard-library only. The transport is injectable so pagination and matching can
be tested offline and the scanner can be reused by other repositories.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Iterator
from typing import Any

API_ROOT = "https://api.github.com"
PER_PAGE = 100
JsonObject = dict[str, Any]
Fetcher = Callable[[str], tuple[Any, dict[str, str]]]


class GitHubApiError(RuntimeError):
    """A GitHub API request failed with useful rate-limit context."""


def _next_link(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def make_fetcher(token: str | None = None, api_root: str = API_ROOT) -> Fetcher:
    root = api_root.rstrip("/")
    auth = token or os.environ.get("GITHUB_TOKEN")

    def fetch(path_or_url: str) -> tuple[Any, dict[str, str]]:
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else root + path_or_url
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "github-unreviewed-diagnostics/1",
                **({"Authorization": f"Bearer {auth}"} if auth else {}),
            },
        )
        try:
            with urllib.request.urlopen(request) as response:
                headers = {key.lower(): value for key, value in response.headers.items()}
                return json.load(response), headers
        except urllib.error.HTTPError as exc:
            remaining = exc.headers.get("X-RateLimit-Remaining")
            reset = exc.headers.get("X-RateLimit-Reset")
            detail = f"GitHub API HTTP {exc.code}: {url}"
            if remaining is not None:
                detail += f" (rate-limit remaining={remaining}, reset={reset or 'unknown'})"
            raise GitHubApiError(detail) from exc

    return fetch


def paged(fetch: Fetcher, path: str) -> Iterator[JsonObject]:
    next_url: str | None = path
    while next_url:
        payload, headers = fetch(next_url)
        if not isinstance(payload, list):
            raise GitHubApiError(f"expected a list response for {next_url}")
        yield from payload
        next_url = _next_link(headers.get("link"))


def owner_repositories(fetch: Fetcher, owner: str) -> Iterator[JsonObject]:
    quoted = urllib.parse.quote(owner, safe="")
    for endpoint in (f"/orgs/{quoted}/repos?per_page={PER_PAGE}&sort=pushed", f"/users/{quoted}/repos?per_page={PER_PAGE}&sort=pushed"):
        try:
            yield from paged(fetch, endpoint)
            return
        except GitHubApiError as exc:
            if "HTTP 404" not in str(exc):
                raise
    raise GitHubApiError(f"GitHub owner not found: {owner}")


def item_bodies(fetch: Fetcher, owner: str, repo: str, item: JsonObject) -> Iterator[str]:
    base = f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repo, safe='')}"
    number = item["number"]
    endpoints = [f"{base}/issues/{number}/comments?per_page={PER_PAGE}"]
    if "pull_request" in item:
        endpoints.extend(
            [
                f"{base}/pulls/{number}/reviews?per_page={PER_PAGE}",
                f"{base}/pulls/{number}/comments?per_page={PER_PAGE}",
            ]
        )
    for endpoint in endpoints:
        for record in paged(fetch, endpoint):
            body = record.get("body")
            if isinstance(body, str):
                yield body


def reviewer_pattern(reviewer: str) -> re.Pattern[str]:
    return re.compile(rf"(?im)^\s*from:\s*{re.escape(reviewer)}\s*$")


def unreviewed(fetch: Fetcher, owner: str, reviewer: str) -> Iterator[tuple[str, str, int, str]]:
    tagged = reviewer_pattern(reviewer)
    for repository in owner_repositories(fetch, owner):
        repo = repository["name"]
        quoted_owner = urllib.parse.quote(owner, safe="")
        quoted_repo = urllib.parse.quote(repo, safe="")
        path = f"/repos/{quoted_owner}/{quoted_repo}/issues?state=open&per_page={PER_PAGE}"
        for item in paged(fetch, path):
            if not any(tagged.search(body) for body in item_bodies(fetch, owner, repo, item)):
                kind = "PR" if "pull_request" in item else "IS"
                yield repo, kind, int(item["number"]), str(item.get("title") or "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner", help="GitHub organization or user")
    parser.add_argument("reviewer", help="reviewer tag used by 'from: <reviewer>'")
    parser.add_argument("--api-root", default=API_ROOT, help="GitHub API root")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for repo, kind, number, title in unreviewed(make_fetcher(api_root=args.api_root), args.owner, args.reviewer):
            print(f"{repo}\t{kind}#{number}\t{title[:70]}")
    except (GitHubApiError, urllib.error.URLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
