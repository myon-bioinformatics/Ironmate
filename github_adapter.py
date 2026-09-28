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
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ROOT = "https://api.github.com"
HTML_ROOT = "https://github.com"


def _is_github_api_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == "api.github.com"


class _ScopedRedirect(HTTPRedirectHandler):
    """Never forward GitHub Authorization outside the HTTPS API host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and not _is_github_api_url(newurl):
            redirected.remove_header("Authorization")
        return redirected


_opener = build_opener(_ScopedRedirect)


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
    encoded_tag = quote(tag, safe="/")
    return f"{repository_html_url(owner, repo)}/releases/tag/{encoded_tag}"


def content_api_url(owner: str, repo: str, path: str, *, ref: str | None = None) -> str:
    url = f"{repository_api_url(owner, repo)}/contents/{quote(path, safe='/')}"
    return f"{url}?ref={_q(ref)}" if ref else url


def _required_numeric_identifier(resource: "GitHubResource") -> int:
    identifier = resource.identifier
    if identifier is None or not identifier.isdigit():
        raise ValueError(f"{resource.kind} identifier must be numeric")
    return int(identifier)


def resource_api_url(resource: "GitHubResource") -> str:
    root = repository_api_url(resource.owner, resource.repo)
    if resource.kind == "repository":
        return root
    if resource.kind == "issue":
        return f"{root}/issues/{_required_numeric_identifier(resource)}"
    if resource.kind == "pull":
        return f"{root}/pulls/{_required_numeric_identifier(resource)}"
    if resource.kind == "commit":
        return f"{root}/commits/{_q(resource.identifier)}"
    if resource.kind == "actions_run":
        return f"{root}/actions/runs/{_required_numeric_identifier(resource)}"
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
            return issue_html_url(self.owner, self.repo, _required_numeric_identifier(self))
        if self.kind == "pull":
            return pull_html_url(self.owner, self.repo, _required_numeric_identifier(self))
        if self.kind == "commit":
            return commit_html_url(self.owner, self.repo, self.identifier or "")
        if self.kind == "actions_run":
            return actions_run_html_url(self.owner, self.repo, _required_numeric_identifier(self))
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
    if token and _is_github_api_url(url):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with _opener.open(Request(url, headers=headers), timeout=timeout) as response:
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
            "rate_limit": {
                "remaining": exc.headers.get("X-RateLimit-Remaining") if exc.headers else None,
                "limit": exc.headers.get("X-RateLimit-Limit") if exc.headers else None,
                "reset": exc.headers.get("X-RateLimit-Reset") if exc.headers else None,
            },
        }
    except (URLError, TimeoutError, ValueError) as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "url": url,
        }


def is_rate_limited(result: dict[str, Any]) -> bool:
    """Classify GitHub primary/secondary rate-limit responses."""
    status = result.get("http_status")
    rate_limit = result.get("rate_limit")
    remaining = rate_limit.get("remaining") if isinstance(rate_limit, dict) else None
    return status == 429 or (status == 403 and remaining == "0")


def normalize_commit(data: dict[str, Any], *, api_url: str | None = None) -> dict[str, Any]:
    commit = data.get("commit") or {}
    committer = commit.get("committer") or {}
    author = commit.get("author") or {}
    return {"sha": data.get("sha"), "date": committer.get("date") or author.get("date"),
            "message": ((commit.get("message") or "").splitlines() or [""])[0],
            "html_url": data.get("html_url"), "api_url": api_url or data.get("url")}


def normalize_pull(pr: dict[str, Any], *, api_url: str | None = None) -> dict[str, Any]:
    head, base = pr.get("head") or {}, pr.get("base") or {}
    return {"number": pr.get("number"), "title": pr.get("title"), "state": pr.get("state"),
            "draft": bool(pr.get("draft")), "head_sha": head.get("sha"), "base_sha": base.get("sha"),
            "created_at": pr.get("created_at"), "updated_at": pr.get("updated_at"),
            "closed_at": pr.get("closed_at"), "merged_at": pr.get("merged_at"),
            "html_url": pr.get("html_url"), "api_url": api_url or pr.get("url")}


def normalize_release(data: dict[str, Any], *, api_url: str | None = None) -> dict[str, Any]:
    return {"tag_name": data.get("tag_name"), "name": data.get("name"),
            "published_at": data.get("published_at"), "html_url": data.get("html_url"),
            "api_url": api_url or data.get("url")}


def normalize_tag(data: dict[str, Any], *, api_url: str | None = None) -> dict[str, Any]:
    return {"name": data.get("name"), "sha": (data.get("commit") or {}).get("sha"),
            "html_url": data.get("html_url"), "api_url": api_url or data.get("url")}


def normalize_actions_run(data: dict[str, Any], *, api_url: str | None = None) -> dict[str, Any]:
    return {"name": data.get("name"), "status": data.get("status"), "conclusion": data.get("conclusion"),
            "head_sha": data.get("head_sha"), "updated_at": data.get("updated_at"),
            "html_url": data.get("html_url"), "api_url": api_url or data.get("url")}


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
        result["fetch"]["rate_limited"] = is_rate_limited(result["fetch"])
    else:
        result["fetch"] = {"status": "skipped"}
    return result
