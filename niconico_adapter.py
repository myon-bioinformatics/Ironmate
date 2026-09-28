"""Read-only niconico Snapshot Search API v2 source adapter.

Specification baseline verified for Issue #39: 2026-04-15 revision.
No catalog/Pages publication is performed by this module.
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from source_adapter import build_url

API_ROOT = "https://snapshot.search.nicovideo.jp"
SEARCH_URL = API_ROOT + "/api/v2/snapshot/video/contents/search"
VERSION_URL = API_ROOT + "/api/v2/snapshot/version"
CONTENT_ROOT = "https://nico.ms"

DEFAULT_FIELDS = (
    "contentId", "title", "description", "tags", "categoryTags",
    "viewCounter", "mylistCounter", "likeCounter", "lengthSeconds",
    "startTime", "lastCommentTime", "commentCounter", "genre",
)
EXCLUDED_PUBLIC_FIELDS = frozenset({"userId", "lastResBody"})


def content_url(content_id: str) -> str:
    value = content_id.strip()
    if not value or not value.isascii() or not value.isalnum():
        raise ValueError("content_id must be non-empty ASCII alphanumeric")
    return build_url(CONTENT_ROOT, value)


def _validate_context(context: str) -> str:
    value = context.strip()
    if not value:
        raise ValueError("_context is required")
    if len(value) > 40:
        raise ValueError("_context must be at most 40 characters")
    return value


def build_search_url(
    *,
    q: str,
    sort: str,
    context: str,
    targets: str | None = None,
    fields: tuple[str, ...] = DEFAULT_FIELDS,
    limit: int = 10,
    offset: int = 0,
    filters: dict[str, Any] | None = None,
) -> str:
    if q is None:
        raise ValueError("q is required even when empty")
    if q and not targets:
        raise ValueError("targets is required for keyword search")
    if not sort:
        raise ValueError("_sort is required")
    context = _validate_context(context)
    if not 1 <= limit <= 100:
        raise ValueError("_limit must be between 1 and 100")
    if not 0 <= offset <= 100000:
        raise ValueError("_offset must be between 0 and 100000")
    if EXCLUDED_PUBLIC_FIELDS.intersection(fields):
        raise ValueError("personal/raw response fields are excluded by default contract")
    query: dict[str, Any] = {
        "q": q,
        "targets": targets,
        "fields": ",".join(fields),
        "_sort": sort,
        "_offset": offset,
        "_limit": limit,
        "_context": context,
    }
    if filters:
        invalid = [key for key in filters if not isinstance(key, str) or not key.startswith("filters[")]
        if invalid:
            raise ValueError("filters may only contain filters[...] keys")
        query.update(filters)
    return build_url(SEARCH_URL, query=query)


def fetch_json(
    url: str,
    *,
    user_agent: str,
    timeout: int = 30,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    if not user_agent.strip():
        raise ValueError("user_agent is required")
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    started = time.monotonic()
    try:
        with opener(request, timeout=timeout) as response:
            value = json.load(response)
            return {"status": "detected", "value": value, "url": url,
                    "elapsed_seconds": max(0.0, time.monotonic() - started)}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body) if body else None
        except json.JSONDecodeError:
            detail = None
        status = "maintenance" if exc.code == 503 else "invalid_request" if exc.code == 400 else "error"
        return {"status": status, "error_type": "http", "http_status": exc.code,
                "error": detail, "url": url,
                "elapsed_seconds": max(0.0, time.monotonic() - started)}
    except (URLError, TimeoutError, ValueError) as exc:
        return {"status": "error", "error_type": type(exc).__name__, "url": url,
                "elapsed_seconds": max(0.0, time.monotonic() - started)}


def normalize_item(item: dict[str, Any], *, source_url: str) -> dict[str, Any]:
    content_id = item.get("contentId")
    safe = {key: value for key, value in item.items() if key not in EXCLUDED_PUBLIC_FIELDS}
    try:
        html_url = content_url(content_id) if isinstance(content_id, str) else None
    except ValueError:
        html_url = None
    return {
        "provider": "niconico",
        "kind": "video",
        "identifier": content_id,
        "html_url": html_url,
        "api_url": None,
        "source_url": source_url,
        "data": safe,
    }

def classify_page(payload: dict[str, Any], *, offset: int, limit: int) -> dict[str, Any]:
    meta = payload.get("meta")
    data = payload.get("data")
    if (not isinstance(meta, dict) or meta.get("status", 200) != 200 or
            not isinstance(meta.get("totalCount"), int) or not isinstance(data, list)):
        return {
            "total_count": None, "returned": None, "complete": False,
            "truncated": False, "next_offset": None, "status": "invalid",
        }
    total = int(meta["totalCount"])
    returned = len(data)
    consumed = offset + returned
    if returned == 0 and offset < total:
        return {
            "total_count": total, "returned": 0, "complete": False,
            "truncated": False, "next_offset": None, "status": "stalled",
        }
    complete = consumed >= total
    next_offset = None
    if not complete and consumed <= 100000:
        next_offset = consumed
    truncated = not complete and next_offset is None
    return {
        "total_count": total, "returned": returned, "complete": complete,
        "truncated": truncated, "next_offset": next_offset, "status": "ok",
    }


def snapshot_consistent(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return bool(before.get("last_modified")) and before.get("last_modified") == after.get("last_modified")


def next_delay_seconds(previous_elapsed_seconds: float, *, http_status: int | None = None) -> float:
    if http_status == 503:
        # Snapshot Search API v2 guide (2026-04-15): wait five minutes after 503.
        return 300.0
    return max(0.0, float(previous_elapsed_seconds))

def completion_state(before: dict[str, Any], after: dict[str, Any], page_state: dict[str, Any]) -> dict[str, Any]:
    consistent = snapshot_consistent(before, after)
    complete = (consistent and page_state.get("status") == "ok" and
                bool(page_state.get("complete")) and not bool(page_state.get("truncated")))
    return {"complete": complete, "snapshot_consistent": consistent, "page": page_state}
