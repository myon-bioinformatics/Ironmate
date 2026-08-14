"""A stateless MCP stub backed by the public portfolio JSON."""
from __future__ import annotations
from datetime import UTC, datetime
from urllib.request import urlopen
import json
SOURCE_URL = "https://myon-bioinformatics.github.io/api/repos.json"
def _validate(query, limit):
    if not isinstance(query, str): raise ValueError("query must be a string")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20: raise ValueError("limit must be an integer from 1 to 20")
    return query.strip().lower(), limit
def _failure(retrieved_at, error):
    return {"items":[],"source_url":SOURCE_URL,"retrieved_at":retrieved_at,"missing_data":["repository fixture could not be retrieved"],"status":"failed","error":error}
def list_portfolio_repositories(query="", limit=5):
    query, limit = _validate(query, limit); retrieved_at = datetime.now(UTC).isoformat()
    try:
        with urlopen(SOURCE_URL, timeout=10) as response: payload = json.load(response)
    except Exception:
        return _failure(retrieved_at, "source_fetch_failed")
    if isinstance(payload,list): entries = payload
    elif isinstance(payload,dict) and isinstance(payload.get("repositories",[]),list): entries = payload["repositories"]
    else: return _failure(retrieved_at, "source_payload_invalid")
    if query: entries=[x for x in entries if query in json.dumps(x,ensure_ascii=False).lower()]
    return {"items":entries[:limit],"source_url":SOURCE_URL,"retrieved_at":retrieved_at,"missing_data":[],"status":"completed"}
if __name__ == "__main__":
    from fastmcp import FastMCP
    mcp=FastMCP("Ironmate Portfolio Stub"); mcp.tool()(list_portfolio_repositories); mcp.run()
