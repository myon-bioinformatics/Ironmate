"""A stateless MCP stub backed by the public portfolio JSON."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from urllib.request import urlopen

SOURCE_URL = "https://myon-bioinformatics.github.io/api/repos.json"
FILTER_FIELDS = ("name", "description", "language", "topics", "readmeSummary")


def _validate(query: str, limit: int) -> tuple[str, int]:
    if not isinstance(query, str):
        raise ValueError("query must be a string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer from 1 to 20")
    return query.strip().lower(), limit


def _failure(retrieved_at: str, error: str) -> dict[str, Any]:
    return {"items": [], "source_url": SOURCE_URL, "retrieved_at": retrieved_at,
            "missing_data": ["repository fixture could not be retrieved"],
            "status": "failed", "error": error}


def _matches(item: dict[str, Any], query: str) -> bool:
    visible = {field: item.get(field) for field in FILTER_FIELDS}
    return query in json.dumps(visible, ensure_ascii=False).lower()


def list_portfolio_repositories(query: str = "", limit: int = 5) -> dict[str, Any]:
    """Filter public portfolio repositories by selected display fields."""
    query, limit = _validate(query, limit)
    retrieved_at = datetime.now(UTC).isoformat()
    try:
        with urlopen(SOURCE_URL, timeout=10) as response:
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
        "items": entries[:limit],
        "filter": {"query": query, "fields": list(FILTER_FIELDS)},
        "matched_count": len(entries),
        "available_count": available_count,
        "source_url": SOURCE_URL,
        "retrieved_at": retrieved_at,
        "missing_data": [],
        "status": "completed",
    }


if __name__ == "__main__":
    from fastmcp import FastMCP
    mcp = FastMCP("Ironmate Portfolio Stub")
    mcp.tool()(list_portfolio_repositories)
    mcp.run()
