"""Build static, LLM-friendly repository metadata for GitHub Pages."""
from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from repository_metadata import (
    availability,
    important_file_shas,
    parse_manifest_version,
    parse_python_api,
    readme_digest,
    select_manifest,
    select_python_sources,
    select_readme,
)

OWNER = os.environ.get("IRONMATE_GITHUB_OWNER", "myon-bioinformatics")
OUTPUT_DIR = Path(os.environ.get("IRONMATE_CATALOG_DIR", "docs/api"))
API_ROOT = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
PYTHON_SOURCE_LIMIT = max(1, int(os.environ.get("IRONMATE_PYTHON_SOURCE_LIMIT", "3")))
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


def _optional_json(url: str) -> tuple[str, Any]:
    try:
        return "detected", _request_json(url)
    except HTTPError as exc:
        if exc.code == 404:
            return "not_found", None
        return "fetch_failed", None
    except (URLError, TimeoutError, ValueError):
        return "fetch_failed", None


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


def _content_text(repo_name: str, path: str, ref: str) -> tuple[str, str | None]:
    status, data = _optional_json(
        f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/contents/"
        f"{quote(path, safe='/')}?ref={quote(ref)}"
    )
    if status != "detected" or not isinstance(data, dict):
        return status, None
    content = data.get("content")
    if not isinstance(content, str):
        return "fetch_failed", None
    try:
        return "detected", base64.b64decode(content).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return "parse_failed", None


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


def _release_metadata(repo_name: str) -> dict[str, Any]:
    status, data = _optional_json(f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/releases/latest")
    if status != "detected" or not isinstance(data, dict):
        return availability(status)
    return availability(
        "detected",
        {
            "tag_name": data.get("tag_name"),
            "name": data.get("name"),
            "published_at": data.get("published_at"),
            "html_url": data.get("html_url"),
        },
    )


def _tag_metadata(repo_name: str) -> dict[str, Any]:
    status, data = _optional_json(f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/tags?per_page=1")
    if status != "detected":
        return availability(status)
    if not isinstance(data, list) or not data:
        return availability("not_found")
    tag = data[0]
    return availability("detected", {"name": tag.get("name"), "sha": (tag.get("commit") or {}).get("sha")})


def _ci_metadata(repo_name: str, default_branch: str) -> dict[str, Any]:
    """Return only the latest Actions workflow run on the default branch."""
    status, data = _optional_json(
        f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/actions/runs"
        f"?branch={quote(default_branch)}&per_page=1"
    )
    if status != "detected" or not isinstance(data, dict):
        return availability(status)
    runs = data.get("workflow_runs")
    if not isinstance(runs, list) or not runs:
        return availability("not_found")
    run = runs[0]
    return availability(
        "detected",
        {
            "name": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "head_sha": run.get("head_sha"),
            "updated_at": run.get("updated_at"),
            "html_url": run.get("html_url"),
        },
    )


def _tree(repo_name: str, default_branch: str) -> tuple[str, list[dict[str, Any]]]:
    status, data = _optional_json(
        f"{API_ROOT}/repos/{quote(OWNER)}/{quote(repo_name)}/git/trees/"
        f"{quote(default_branch)}?recursive=1"
    )
    if status != "detected" or not isinstance(data, dict):
        return status, []
    tree = data.get("tree")
    return ("detected", [item for item in tree if isinstance(item, dict)]) if isinstance(tree, list) else ("fetch_failed", [])


def _repository_enrichment(repo_name: str, default_branch: str, language: str | None) -> dict[str, Any]:
    tree_status, tree = _tree(repo_name, default_branch)
    if tree_status != "detected":
        return {
            "version": availability(tree_status),
            "readme": availability(tree_status),
            "api": availability(tree_status),
            "important_files": availability(tree_status),
            "latest_release": _release_metadata(repo_name),
            "latest_tag": _tag_metadata(repo_name),
            "ci": _ci_metadata(repo_name, default_branch),
        }

    manifest = select_manifest(tree)
    if manifest:
        status, text = _content_text(repo_name, manifest, default_branch)
        version = parse_manifest_version(manifest, text) if status == "detected" and text is not None else availability(status, source=manifest)
    else:
        version = availability("not_found")

    readme_path = select_readme(tree)
    if readme_path:
        status, text = _content_text(repo_name, readme_path, default_branch)
        readme = availability("detected", readme_digest(text), source=readme_path) if status == "detected" and text is not None else availability(status, source=readme_path)
    else:
        readme = availability("not_found")

    if (language or "").lower() == "python":
        source_paths = select_python_sources(tree, limit=PYTHON_SOURCE_LIMIT)
        api_items = []
        for path in source_paths:
            status, text = _content_text(repo_name, path, default_branch)
            api_items.append(
                parse_python_api(text, source=path)
                if status == "detected" and text is not None
                else availability(status, source=path)
            )
        api = availability("detected", api_items) if api_items else availability("not_found")
    else:
        api = availability("unsupported")

    return {
        "version": version,
        "readme": readme,
        "api": api,
        "important_files": availability("detected", important_file_shas(tree)),
        "latest_release": _release_metadata(repo_name),
        "latest_tag": _tag_metadata(repo_name),
        "ci": _ci_metadata(repo_name, default_branch),
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
        # latest_pr is latest-created (greatest PR number); latest_updated_pr is
        # independently selected by updated_at and can change after comments/reviews.
        latest_pr = max(pr_items, key=lambda item: int(item["number"] or 0), default=None)
        recently_updated_pr = max(pr_items, key=lambda item: item.get("updated_at") or "", default=None)
        try:
            enrichment = _repository_enrichment(name, default_branch, repo.get("language"))
        except Exception as exc:
            print(
                json.dumps(
                    {"repository": name, "metadata_enrichment": "fetch_failed", "error_type": type(exc).__name__}
                )
            )
            enrichment = {
                field: availability("fetch_failed")
                for field in (
                    "version", "readme", "api", "important_files",
                    "latest_release", "latest_tag", "ci",
                )
            }

        repo_payload = {
            "name": name,
            "full_name": repo.get("full_name"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "topics": repo.get("topics") or [],
            "default_branch": default_branch,
            "latest_commit": latest_commit,
            "latest_pr": latest_pr,
            "latest_updated_pr": recently_updated_pr,
            "pr_count": len(pr_items),
            "pushed_at": repo.get("pushed_at"),
            "updated_at": repo.get("updated_at"),
            "html_url": repo.get("html_url"),
            **enrichment,
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
                "latest_updated_pr": recently_updated_pr.get("number") if recently_updated_pr else None,
                "language": repo.get("language"),
                "topics": repo.get("topics") or [],
                "version": enrichment["version"].get("value"),
                "release": (enrichment["latest_release"].get("value") or {}).get("tag_name"),
                "ci": (enrichment["ci"].get("value") or {}).get("conclusion"),
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
