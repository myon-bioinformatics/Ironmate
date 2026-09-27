"""Read-only GitHub source adapter.

Pure URL construction/parsing is deliberately independent of network access.
Fetch helpers use only the standard library and work anonymously for public
resources; a token is optional for rate-limit headroom.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
HTML_ROOT = "https://github.com"


def _q(value: str) -> str:
    return quote(value, safe="")


def repository_html_url(owner: str, repo: str) -> str:
    return f"{HTML_ROOT}/{_q(owner)}/{_q(repo)}"


def repository_api_url(owner: str, repo: str) -> str:
    return f"{API_ROOT}/repos/{_q(owner)}/{_q(repo)}"


def issue_html_url(owner: str, repo: str, number: int) -> str:
    return f"{repository_html_url(owner, repo)}/issues/{int(number)}"


def pull_html_url(owner: str, repo: str, number: int) -> str:
    return f"{repository_html_url(owner, repo)}/pull/{int(number)}"


def commit_html_url(owner: str, repo: str, sha: str) -> str:
    return f"{repository_html_url(owner, repo)}/commit/{_q(sha)}"


def actions_run_html_url(owner: str, repo: str, run_id: int) -> str:
    return f"{repository_html_url(owner, repo)}/actions/runs/{int(run_id)}"


def release_tag_html_url(owner: str, repo: str, tag: str) -> str:
    return f"{repository_html_url(owner, repo)}/releases/tag/{_q(tag)}"


def content_api_url(owner: str, repo: str, path: str, *, ref: str | None = None) -> str:
    url = f"{repository_api_url(owner, repo)}/contents/{quote(path, safe='/')}"
    return f"{url}?ref={_q(ref)}" if ref else url


def resource_api_url(resource: "GitHubResource") -> str:
    root = repository_api_url(resource.owner, resource.repo)
    if resource.kind == "repository":
        return root
    if resource.kind == "issue":
        return f"{root}/issues/{int(resource.identifier)}"
    if resource.kind == "pull":
        return f"{root}/pulls/{int(resource.identifier)}"
    if resource.kind == "commit":
        return f"{root}/commits/{_q(resource.identifier)}"
    if resource.kind == "actions_run":
        return f"{root}/actions/runs/{int(resource.identifier)}"
    if resource.kind == "release_tag":
        return f"{root}/releases/tags/{_q(resource.identifier)}"
    raise ValueError(f"unsupported GitHub resource kind: {resource.kind}")


@dataclass(frozen=True)
class GitHubResource:
    owner: str
    repo: str
    kind: str = "repository"
    identifier: str | None = None

    @property
    def html_url(self) -> str:
        if self.kind == "repository":
            return repository_html_url(self.owner, self.repo)
        if self.kind == "issue":
            return issue_html_url(self.owner, self.repo, int(self.identifier or 0))
        if self.kind == "pull":
            return pull_html_url(self.owner, self.repo, int(self.identifier or 0))
        if self.kind == "commit":
            return commit_html_url(self.owner, self.repo, self.identifier or "")
        if self.kind == "actions_run":
            return actions_run_html_url(self.owner, self.repo, int(self.identifier or 0))
        if self.kind == "release_tag":
            return release_tag_html_url(self.owner, self.repo, self.identifier or "")
        raise ValueError(f"unsupported GitHub resource kind: {self.kind}")

    @property
    def api_url(self) -> str:
        return resource_api_url(self)


def parse_github_resource(value: str) -> GitHubResource:
    raw = value.strip()
    if "://" not in raw:
        parts = raw.strip("/").split("/")
    else:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("not a github.com URL")
        parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("expected owner/repo or a github.com resource URL")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        raise ValueError("owner and repository must be non-empty")
    if len(parts) == 2:
        return GitHubResource(owner, repo)
    tail = parts[2:]
    if len(tail) >= 2 and tail[0] in {"issues", "pull", "commit"}:
        kind = {"issues": "issue", "pull": "pull", "commit": "commit"}[tail[0]]
        identifier = tail[1]
        if kind in {"issue", "pull"} and not identifier.isdigit():
            raise ValueError(f"{kind} identifier must be numeric")
        return GitHubResource(owner, repo, kind, identifier)
    if len(tail) >= 3 and tail[:2] == ["actions", "runs"]:
        if not tail[2].isdigit():
            raise ValueError("actions run identifier must be numeric")
        return GitHubResource(owner, repo, "actions_run", tail[2])
    if len(tail) >= 3 and tail[:2] == ["releases", "tag"]:
        return GitHubResource(owner, repo, "release_tag", "/".join(tail[2:]))
    raise ValueError("unsupported GitHub resource URL")


def fetch_json(url: str, *, token: str = "", timeout: int = 30) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Ironmate-github-adapter",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return {
                "status": "detected",
                "value": json.load(response),
                "url": url,
                "rate_limit": {
                    "remaining": response.headers.get("X-RateLimit-Remaining"),
                    "limit": response.headers.get("X-RateLimit-Limit"),
                    "reset": response.headers.get("X-RateLimit-Reset"),
                },
            }
    except HTTPError as exc:
        return {
            "status": "error",
            "error_type": "http",
            "http_status": exc.code,
            "url": url,
        }
    except (URLError, TimeoutError, ValueError) as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "url": url,
        }


def inspect_public(value: str, *, token: str = "", fetch: bool = True) -> dict[str, Any]:
    resource = parse_github_resource(value)
    result: dict[str, Any] = {
        "source": "github",
        "kind": resource.kind,
        "owner": resource.owner,
        "repository": resource.repo,
        "identifier": resource.identifier,
        "html_url": resource.html_url,
        "api_url": resource.api_url,
    }
    if fetch:
        result["fetch"] = fetch_json(resource.api_url, token=token)
    else:
        result["fetch"] = {"status": "skipped"}
    return result
