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
def list_portfolio_repositories(query="", limit=5, source_url=SOURCE_URL):
    query, limit = _validate(query, limit); retrieved_at = datetime.now(UTC).isoformat()
    try:
        with urlopen(source_url, timeout=10) as response: payload = json.load(response)
    except Exception as exc:
        return {"items":[],"source_url":source_url,"retrieved_at":retrieved_at,"missing_data":["repository fixture could not be retrieved"],"status":"failed","error":str(exc)}
    entries = payload if isinstance(payload,list) else payload.get("repositories",[])
    entries = entries if isinstance(entries,list) else []
    if query: entries=[x for x in entries if query in json.dumps(x,ensure_ascii=False).lower()]
    return {"items":entries[:limit],"source_url":source_url,"retrieved_at":retrieved_at,"missing_data":[],"status":"completed"}
if __name__ == "__main__":
    from fastmcp import FastMCP
    mcp=FastMCP("Ironmate Portfolio Stub"); mcp.tool()(list_portfolio_repositories); mcp.run()
