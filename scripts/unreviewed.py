#!/usr/bin/env python3
"""List open GitHub issues/PRs missing a tagged reviewer response.

Standard-library only. Network transport is injectable for offline tests.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

API_ROOT = "https://api.github.com"
PER_PAGE = 100
DEFAULT_TIMEOUT = 15.0
JsonObject = dict[str, Any]
Fetcher = Callable[[str], tuple[Any, dict[str, str]]]


class GitHubApiError(RuntimeError):
    """GitHub API failure with a machine-readable HTTP status when available."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin: tuple[str, str]) -> None:
        self.origin = origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(newurl) != self.origin:
            raise GitHubApiError(
                f"refusing cross-origin redirect: {newurl}",
                status=code,
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _origin(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme.lower(), parsed.netloc.lower()


def _next_link(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _error_message(exc: urllib.error.HTTPError) -> str | None:
    try:
        payload = json.loads(exc.read().decode("utf-8", "replace"))
    except (ValueError, OSError):
        return None
    message = payload.get("message") if isinstance(payload, dict) else None
    return message if isinstance(message, str) else None


def make_fetcher(
    token: str | None = None,
    api_root: str = API_ROOT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Fetcher:
    root = api_root.rstrip("/")
    root_origin = _origin(root)
    auth = token or os.environ.get("GITHUB_TOKEN")
    opener = urllib.request.build_opener(_SameOriginRedirect(root_origin))

    def fetch(path_or_url: str) -> tuple[Any, dict[str, str]]:
        url = urllib.parse.urljoin(root + "/", path_or_url.lstrip("/"))
        if _origin(url) != root_origin:
            raise GitHubApiError(f"refusing cross-origin GitHub API URL: {url}")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "github-unreviewed-diagnostics/1",
                **({"Authorization": f"Bearer {auth}"} if auth else {}),
            },
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                headers = {key.lower(): value for key, value in response.headers.items()}
                return json.load(response), headers
        except urllib.error.HTTPError as exc:
            remaining = exc.headers.get("X-RateLimit-Remaining")
            reset = exc.headers.get("X-RateLimit-Reset")
            retry_after = exc.headers.get("Retry-After")
            detail = f"GitHub API HTTP {exc.code}: {url}"
            message = _error_message(exc)
            diagnostics = []
            if message:
                diagnostics.append(f"message={message}")
            if remaining is not None:
                diagnostics.append(f"rate-limit remaining={remaining}")
            if reset is not None:
                diagnostics.append(f"reset={reset}")
            if retry_after is not None:
                diagnostics.append(f"retry-after={retry_after}")
            if diagnostics:
                detail += " (" + ", ".join(diagnostics) + ")"
            raise GitHubApiError(detail, status=exc.code) from exc
        except (urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            raise GitHubApiError(f"GitHub API request failed: {url}: {exc}") from exc

    return fetch


def paged(fetch: Fetcher, path: str) -> Iterator[JsonObject]:
    next_url: str | None = path
    seen: set[str] = set()
    while next_url:
        if next_url in seen:
            raise GitHubApiError(f"pagination cycle detected: {next_url}")
        seen.add(next_url)
        payload, headers = fetch(next_url)
        if not isinstance(payload, list):
            raise GitHubApiError(f"expected a list response for {next_url}")
        yield from payload
        next_url = _next_link(headers.get("link"))


def owner_repositories(fetch: Fetcher, owner: str) -> Iterator[JsonObject]:
    quoted = urllib.parse.quote(owner, safe="")
    org_endpoint = f"/orgs/{quoted}/repos?per_page={PER_PAGE}&sort=pushed"
    try:
        repositories = list(paged(fetch, org_endpoint))
    except GitHubApiError as exc:
        if exc.status != 404:
            raise
    else:
        yield from repositories
        return

    user_endpoint = f"/users/{quoted}/repos?per_page={PER_PAGE}&sort=pushed"
    try:
        yield from paged(fetch, user_endpoint)
    except GitHubApiError as exc:
        if exc.status == 404:
            raise GitHubApiError(f"GitHub owner not found: {owner}", status=404) from exc
        raise


def item_records(fetch: Fetcher, owner: str, repo: str, item: JsonObject) -> Iterator[JsonObject]:
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
        try:
            yield from paged(fetch, endpoint)
        except GitHubApiError as exc:
            if exc.status in {404, 410}:
                continue
            raise


def reviewer_pattern(reviewer: str) -> re.Pattern[str]:
    return re.compile(rf"(?im)^[ \t]*from:[ \t]*{re.escape(reviewer)}[ \t]*$")


def record_is_reviewed(record: JsonObject, tagged: re.Pattern[str]) -> bool:
    body = record.get("body")
    return isinstance(body, str) and bool(tagged.search(body))


def unreviewed(
    fetch: Fetcher,
    owner: str,
    reviewer: str,
) -> Iterator[tuple[str, str, int, str]]:
    tagged = reviewer_pattern(reviewer)
    quoted_owner = urllib.parse.quote(owner, safe="")
    for repository in owner_repositories(fetch, owner):
        repo = repository["name"]
        quoted_repo = urllib.parse.quote(repo, safe="")
        path = f"/repos/{quoted_owner}/{quoted_repo}/issues?state=open&per_page={PER_PAGE}"
        try:
            items = paged(fetch, path)
            for item in items:
                records = item_records(fetch, owner, repo, item)
                if not any(record_is_reviewed(record, tagged) for record in records):
                    kind = "PR" if "pull_request" in item else "IS"
                    yield repo, kind, int(item["number"]), str(item.get("title") or "")
        except GitHubApiError as exc:
            if exc.status == 410:
                continue
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner", help="GitHub organization or user")
    parser.add_argument("reviewer", help="reviewer tag used by 'from: <reviewer>'")
    parser.add_argument("--api-root", default=API_ROOT, help="GitHub API root")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="HTTP timeout in seconds")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fetch = make_fetcher(api_root=args.api_root, timeout=args.timeout)
        for repo, kind, number, title in unreviewed(fetch, args.owner, args.reviewer):
            print(f"{repo}\t{kind}#{number}\t{title[:70]}")
    except GitHubApiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
