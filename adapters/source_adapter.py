"""Provider-neutral primitives for read-only source adapters.

Provider adapters such as niconico_adapter.py
share URL construction and provenance vocabulary without sharing provider
resource semantics.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode


def quote_segment(value: str) -> str:
    return quote(value, safe="")


def build_url(base_url: str, *segments: str, query: dict[str, Any] | None = None) -> str:
    """Build a URL from encoded path segments and optional query parameters."""
    url = base_url.rstrip("/")
    if segments:
        url += "/" + "/".join(quote_segment(str(segment).strip("/")) for segment in segments)
    if query:
        encoded = urlencode(
            [(key, value) for key, value in query.items() if value is not None],
            doseq=True,
        )
        if encoded:
            url += "?" + encoded
    return url


def provenance(
    data: dict[str, Any],
    *,
    api_url: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Keep human, canonical API, and source/query URLs semantically distinct."""
    return {
        "html_url": data.get("html_url"),
        "api_url": api_url or data.get("url"),
        "source_url": source_url,
    }
