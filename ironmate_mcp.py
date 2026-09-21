"""Stateless MCP helpers backed by public static JSON."""
from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

PORTFOLIO_SOURCE_URL = "https://myon-bioinformatics.github.io/api/repos.json"
CATALOG_BASE_URL = "https://myon-bioinformatics.github.io/Ironmate/api"
FILTER_FIELDS = ("name", "description", "language", "topics", "readmeSummary")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate(query: str, limit: int) -> tuple[str, int]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer from 1 to 20")
    return query.strip().lower(), limit


def _repository_name(name: str) -> str:
    if not isinstance(name, str) or not _REPOSITORY_RE.fullmatch(name):
        raise ValueError("repository must be a simple repository name")
    return name


def _failure(retrieved_at: str, error: str) -> dict[str, Any]:
    return {"items": [], "source_url": PORTFOLIO_SOURCE_URL, "retrieved_at": retrieved_at,
            "missing_data": ["repository fixture could not be retrieved"],
            "status": "failed", "error": error}


def _matches(item: dict[str, Any], query: str) -> bool:
    visible = {field: item.get(field) for field in FILTER_FIELDS}
    return query in json.dumps(visible, ensure_ascii=False).lower()


def _public_item(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in FILTER_FIELDS}


def _load_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10) as response:
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("static catalog item not found") from None
        raise
    if not isinstance(payload, dict):
        raise ValueError("static catalog payload must be an object")
    return payload


def list_portfolio_repositories(query: str = "", limit: int = 5) -> dict[str, Any]:
    """Filter public portfolio repositories by selected display fields."""
    query, limit = _validate(query, limit)
    retrieved_at = datetime.now(UTC).isoformat()
    try:
        with urlopen(PORTFOLIO_SOURCE_URL, timeout=10) as response:
            payload = json.load(response)
    except Exception:
        return _failure(retrieved_at, "source_fetch_failed")

    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict) and isinstance(payload.get("repos"), list):
        entries = payload["repos"]
    else:
        return _failure(retrieved_at, "source_payload_invalid")

    entries = [item for item in entries if isinstance(item, dict)]
    available_count = len(entries)
    if query:
        entries = [item for item in entries if _matches(item, query)]
    return {
        "items": [_public_item(item) for item in entries[:limit]],
        "filter": {"query": query, "fields": list(FILTER_FIELDS)},
        "matched_count": len(entries),
        "available_count": available_count,
        "source_url": PORTFOLIO_SOURCE_URL,
        "retrieved_at": retrieved_at,
        "missing_data": [],
        "status": "completed",
    }


def search_repository_metadata(query: str = "", limit: int = 5) -> dict[str, Any]:
    """Search the compact organization-wide metadata index."""
    query, limit = _validate(query, limit)
    url = f"{CATALOG_BASE_URL}/catalog.min.json"
    payload = _load_json(url)
    entries = [item for item in payload.get("repos", []) if isinstance(item, dict)]
    if query:
        entries = [
            item for item in entries
            if query in json.dumps(item, ensure_ascii=False).lower()
        ]
    return {
        "items": entries[:limit],
        "matched_count": len(entries),
        "generated_at": payload.get("generated_at"),
        "source_url": url,
    }


def get_repository_metadata(repository: str) -> dict[str, Any]:
    """Return a compact repository snapshot.\n\n    ``latest_pr`` is latest-created by PR number; ``latest_updated_pr`` is the\n    PR with the most recent ``updated_at`` timestamp. CI metadata is latest-run only.\n    """
    repository = _repository_name(repository)
    url = f"{CATALOG_BASE_URL}/repos/{quote(repository)}.json"
    payload = _load_json(url)
    readme = payload.get("readme") if isinstance(payload.get("readme"), dict) else {}
    important = payload.get("important_files") if isinstance(payload.get("important_files"), dict) else {}
    fields = ("version", "latest_release", "latest_tag", "ci", "api", "readme", "important_files")
    availability = {
        field: (payload.get(field) or {}).get("status")
        for field in fields
        if isinstance(payload.get(field), dict)
    }
    return {
        "name": payload.get("name"),
        "description": payload.get("description"),
        "language": payload.get("language"),
        "topics": payload.get("topics"),
        "default_branch": payload.get("default_branch"),
        "latest_commit": payload.get("latest_commit"),
        "latest_pr": payload.get("latest_pr"),
        "latest_updated_pr": payload.get("latest_updated_pr"),
        "pr_count": payload.get("pr_count"),
        "version": payload.get("version"),
        "latest_release": payload.get("latest_release"),
        "latest_tag": payload.get("latest_tag"),
        "ci": payload.get("ci"),
        "readme": readme.get("value"),
        "important_files": important.get("value"),
        "availability": availability,
        "pushed_at": payload.get("pushed_at"),
        "generated_at": payload.get("generated_at"),
        "source_url": url,
    }


def get_repository_exports(repository: str, limit: int = 50) -> dict[str, Any]:
    """Return detected public API names without returning the entire repository snapshot."""
    repository = _repository_name(repository)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    url = f"{CATALOG_BASE_URL}/repos/{quote(repository)}.json"
    payload = _load_json(url)
    api = payload.get("api")
    if not isinstance(api, dict):
        return {"repository": repository, "status": "not_found", "items": [], "source_url": url}
    if api.get("status") != "detected":
        return {
            "repository": repository,
            "status": api.get("status") or "not_found",
            "items": [],
            "source_url": url,
        }

    items: list[dict[str, Any]] = []
    for record in api.get("value") or []:
        if not isinstance(record, dict) or record.get("status") != "detected":
            continue
        value = record.get("value") or {}
        source = record.get("source")
        for name in value.get("exports") or []:
            items.append({"name": name, "source": source, "kind": "export"})
    return {
        "repository": repository,
        "status": "detected",
        "items": items[:limit],
        "matched_count": len(items),
        "generated_at": payload.get("generated_at"),
        "source_url": url,
    }


def get_pull_request_metadata(repository: str, pr_number: int | str = "latest") -> dict[str, Any]:
    """Return ``/Ironmate/api/prs/<repo>/<number>.json`` metadata.

    ``latest`` means the greatest GitHub PR number (latest-created PR), not the
    PR with the most recent ``updated_at`` timestamp.
    """
    repository = _repository_name(repository)
    if pr_number == "latest":
        repo = get_repository_metadata(repository)
        latest = repo.get("latest_pr")
        if not isinstance(latest, dict) or latest.get("number") is None:
            raise ValueError("repository has no pull requests")
        return get_pull_request_metadata(repository, latest["number"])

    if isinstance(pr_number, bool):
        raise ValueError("pr_number must be a positive integer or 'latest'")
    try:
        number = int(pr_number)
    except (TypeError, ValueError) as exc:
        raise ValueError("pr_number must be a positive integer or 'latest'") from exc
    if number < 1 or str(number) != str(pr_number):
        raise ValueError("pr_number must be a positive integer or 'latest'")

    url = f"{CATALOG_BASE_URL}/prs/{quote(repository)}/{number}.json"
    payload = _load_json(url)
    payload["source_url"] = url
    return payload


if __name__ == "__main__":
    from fastmcp import FastMCP
    mcp = FastMCP("Ironmate Metadata")
    mcp.tool()(list_portfolio_repositories)
    mcp.tool()(search_repository_metadata)
    mcp.tool()(get_repository_metadata)
    mcp.tool()(get_repository_exports)
    mcp.tool()(get_pull_request_metadata)
    mcp.run()
