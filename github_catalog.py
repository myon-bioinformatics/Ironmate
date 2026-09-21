"""Build a static, LLM-friendly metadata catalog for myon-bioinformatics.

The generated files are intended for GitHub Pages. Runtime consumers can fetch a
small organization-wide index first, then only the repository or pull-request
record they actually need.
"""
from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

OWNER = os.environ.get("IRONMATE_GITHUB_OWNER", "myon-bioinformatics")
OUTPUT_DIR = Path(os.environ.get("IRONMATE_CATALOG_DIR", "docs/api"))
API_ROOT = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
RATE_LIMIT = {"remaining": None, "limit": None, "reset": None}


def _request_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Ironmate-static-catalog",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        RATE_LIMIT["remaining"] = response.headers.get("X-RateLimit-Remaining")
        RATE_LIMIT["limit"] = response.headers.get("X-RateLimit-Limit")
        RATE_LIMIT["reset"] = response.headers.get("X-RateLimit-Reset")
        return json.load(response)


def _paged(url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        batch = _request_json(f"{url}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError(f"expected list from {url}")
        items.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return items
        page += 1


def _commit_metadata(repo_name: str, default_branch: str) -> dict[str, Any]:
    data = _request_json(
        f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/commits/{quote(default_branch)}"
    )
    commit = data.get("commit", {}) if isinstance(data, dict) else {}
    committer = commit.get("committer", {}) if isinstance(commit, dict) else {}
    author = commit.get("author", {}) if isinstance(commit, dict) else {}
    return {
        "sha": data.get("sha") if isinstance(data, dict) else None,
        "date": committer.get("date") or author.get("date"),
        "message": (commit.get("message") or "").splitlines()[0] if isinstance(commit, dict) else "",
    }


def _pr_metadata(pr: dict[str, Any]) -> dict[str, Any]:
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "state": pr.get("state"),
        "draft": bool(pr.get("draft")),
        "head_sha": head.get("sha"),
        "base_sha": base.get("sha"),
        "created_at": pr.get("created_at"),
        "updated_at": pr.get("updated_at"),
        "closed_at": pr.get("closed_at"),
        "merged_at": pr.get("merged_at"),
        "html_url": pr.get("html_url"),
    }


def build_catalog() -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat()
    repos = _paged(
        f"{API_ROOT}/users/{quote(OWNER)}/repos?type=owner&sort=full_name&direction=asc"
    )
    public_repos = [repo for repo in repos if not repo.get("private") and not repo.get("fork")]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    repo_dir = OUTPUT_DIR / "repos"
    pr_root = OUTPUT_DIR / "prs"
    repo_dir.mkdir(parents=True, exist_ok=True)
    pr_root.mkdir(parents=True, exist_ok=True)

    compact_repos: list[dict[str, Any]] = []
    for repo in public_repos:
        name = str(repo["name"])
        default_branch = str(repo.get("default_branch") or "main")
        latest_commit = _commit_metadata(name, default_branch)
        pulls = _paged(
            f"{API_ROOT}/repos/{quote(OWNER)}/{quote(name)}/pulls"
            "?state=all&sort=created&direction=desc"
        )
        pr_items = [_pr_metadata(pr) for pr in pulls]
        # "latest" means the greatest GitHub PR number (latest-created PR in the
        # repository's monotonic numbering), not the most recently updated PR.
        latest_pr = max(pr_items, key=lambda item: int(item["number"] or 0), default=None)

        repo_payload = {
            "name": name,
            "full_name": repo.get("full_name"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "topics": repo.get("topics") or [],
            "default_branch": default_branch,
            "latest_commit": latest_commit,
            "latest_pr": latest_pr,
            "pr_count": len(pr_items),
            "pushed_at": repo.get("pushed_at"),
            "updated_at": repo.get("updated_at"),
            "url": repo.get("html_url"),
            "generated_at": generated_at,
        }
        (repo_dir / f"{name}.json").write_text(
            json.dumps(repo_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        repo_pr_dir = pr_root / name
        repo_pr_dir.mkdir(parents=True, exist_ok=True)
        for item in pr_items:
            number = item.get("number")
            if number is None:
                continue
            (repo_pr_dir / f"{number}.json").write_text(
                json.dumps(
                    {"repository": name, **item, "generated_at": generated_at},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )

        compact_repos.append(
            {
                "name": name,
                "sha": latest_commit.get("sha"),
                "date": latest_commit.get("date"),
                "latest_pr": latest_pr.get("number") if latest_pr else None,
                "pr_updated_at": latest_pr.get("updated_at") if latest_pr else None,
                "language": repo.get("language"),
                "topics": repo.get("topics") or [],
            }
        )

    catalog = {
        "owner": OWNER,
        "generated_at": generated_at,
        "repository_count": len(compact_repos),
        "repos": compact_repos,
    }
    (OUTPUT_DIR / "catalog.min.json").write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return catalog


if __name__ == "__main__":
    result = build_catalog()
    print(
        json.dumps(
            {
                "owner": result["owner"],
                "generated_at": result["generated_at"],
                "repository_count": result["repository_count"],
                "rate_limit": RATE_LIMIT,
            },
            ensure_ascii=False,
        )
    )
