"""Build the public repository diagnostics Pages artifact.

Stdlib-only. Metadata uses repository_metadata_contract v1. URL observations are
anonymous and read-only: no GitHub token is read or attached.
"""
from __future__ import annotations

from datetime import UTC, datetime
import http.client
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repository_metadata_contract import (
    build_repository_record,
    pages_candidate_url,
    repository_identity,
)

OUTPUT_JSON = ROOT / "docs" / "api" / "repository-diagnostics.json"
OUTPUT_HTML = ROOT / "docs" / "repository-diagnostics.html"
REPOSITORY = "myon-bioinformatics/Ironmate"
WEB_UI_SHA = "adb23d7ba6ea94672b76457573f6655a081ee054"
WEB_UI_BASE = f"https://cdn.jsdelivr.net/gh/myon-bioinformatics/web-ui@{WEB_UI_SHA}"


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args],
        text=True,
        encoding="utf-8",
    ).strip()


def _tracked_bytes(root: Path) -> int:
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    total = 0
    for item in raw.split(b"\0"):
        if not item:
            continue
        path = root / item.decode("utf-8", errors="surrogateescape")
        if path.is_file():
            total += path.stat().st_size
    return total


def _header(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    try:
        value = headers.get(name)
        if value is not None:
            return str(value)
    except (AttributeError, TypeError):
        pass
    try:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value)
    except (AttributeError, TypeError):
        pass
    return None


def _status(code: int, headers: Any = None) -> str:
    if 200 <= code < 400:
        return "reachable"
    if code == 403 and (
        (_header(headers, "X-RateLimit-Remaining") or "").strip() == "0"
        or _header(headers, "Retry-After") is not None
    ):
        return "rate_limited"
    if code in (401, 403):
        return "auth_required"
    if code == 404:
        return "not_found"
    if code == 429:
        return "rate_limited"
    return "http_error"


def public_candidates(full_name: str, *, ref: str, path: str = "README.md") -> list[dict[str, str]]:
    owner, name = repository_identity(full_name)
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    encoded_ref = quote(ref, safe="/")
    api_ref = quote(ref, safe="")
    return [
        {"kind": "repository", "url": f"https://github.com/{owner}/{name}"},
        {"kind": "api", "url": f"https://api.github.com/repos/{owner}/{name}"},
        {"kind": "pages", "url": pages_candidate_url(full_name)},
        {
            "kind": "raw",
            "url": f"https://raw.githubusercontent.com/{owner}/{name}/{encoded_ref}/{encoded_path}",
        },
        {
            "kind": "contents_api",
            "url": f"https://api.github.com/repos/{owner}/{name}/contents/{encoded_path}?ref={api_ref}",
        },
    ]


def probe_url(
    url: str,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 10,
) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    request = Request(url, headers={"User-Agent": "Ironmate-public-diagnostics/1"})
    try:
        with opener(request, timeout=timeout) as response:
            code = int(getattr(response, "status", response.getcode()))
            resolved_url = response.geturl()
            headers = getattr(response, "headers", None)
    except HTTPError as exc:
        code = exc.code
        resolved_url = exc.geturl()
        headers = exc.headers
    except (URLError, TimeoutError, OSError, http.client.HTTPException):
        return {
            "status": "unverified",
            "url": url,
            "resolved_url": None,
            "http_status": None,
            "checked_at": checked_at,
            "evidence": "network_error",
        }
    return {
        "status": _status(code, headers),
        "url": url,
        "resolved_url": resolved_url,
        "http_status": code,
        "checked_at": checked_at,
        "evidence": "http_response",
    }


def diagnostics_payload(
    record: dict[str, Any],
    *,
    probe: bool = True,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    candidates = public_candidates(
        record["repository"]["full_name"],
        ref=record["head"]["branch"],
    )
    observations = (
        [{**candidate, **probe_url(candidate["url"], opener=opener)} for candidate in candidates]
        if probe
        else []
    )
    return {
        "metadata": record,
        "resolver": {
            "auth": "anonymous",
            "status": "observed" if probe else "not_checked",
            "candidates": candidates,
            "observations": observations,
        },
    }


def current_record(root: Path = ROOT) -> dict[str, Any]:
    sha = _git(root, "rev-parse", "HEAD")
    branch = (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or _git(root, "branch", "--show-current")
        or "detached"
    )
    timestamp = _git(root, "show", "-s", "--format=%cI", "HEAD")
    subject = _git(root, "show", "-s", "--format=%s", "HEAD")
    generated_at = datetime.now(UTC).isoformat()
    return build_repository_record(
        full_name=REPOSITORY,
        sha=sha,
        branch=branch,
        timestamp=timestamp,
        subject=subject,
        generated_at=generated_at,
        working_tree_bytes=_tracked_bytes(root),
        tooling={"python": platform.python_version()},
    )


def page_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ironmate repository diagnostics</title>
<link rel="stylesheet" href="{WEB_UI_BASE}/css/tokens.css">
<link rel="stylesheet" href="{WEB_UI_BASE}/css/base.css">
<link rel="stylesheet" href="{WEB_UI_BASE}/css/components.css">
<link rel="stylesheet" href="{WEB_UI_BASE}/css/themes/modern.css">
<link rel="stylesheet" href="{WEB_UI_BASE}/css/repository-diagnostics.css">
</head>
<body data-ui-theme="modern">
<main class="ui-page">
<header>
<h1 class="ui-title">Ironmate repository diagnostics</h1>
<p class="ui-muted">Public metadata and anonymous URL observations. Unverified is not inaccessible.</p>
</header>
<div id="metadata"></div>
<section class="ui-panel">
<h2>Public URL observations</h2>
<p id="resolver-summary" class="ui-muted">Loading…</p>
<div id="observations" class="ui-grid"></div>
</section>
<p><a href="./mcp-stub.html">Open MCP Stub Explorer</a></p>
</main>
<script src="{WEB_UI_BASE}/js/repository-diagnostics.js"></script>
<script>
(async function () {{
  "use strict";
  const metadataRoot = document.getElementById("metadata");
  const observationsRoot = document.getElementById("observations");
  const summary = document.getElementById("resolver-summary");
  try {{
    const response = await fetch("./api/repository-diagnostics.json", {{cache: "no-store"}});
    if (!response.ok) throw new Error("diagnostics fetch failed");
    const payload = await response.json();
    metadataRoot.innerHTML = RepositoryDiagnostics.render(payload.metadata);
    const resolver = payload.resolver || {{}};
    summary.textContent = "Auth: " + (resolver.auth || "unknown") + " · Status: " + (resolver.status || "unknown");
    observationsRoot.replaceChildren();
    (resolver.observations || []).forEach(function (item) {{
      const card = document.createElement("article");
      card.className = "ui-card";
      const title = document.createElement("h3");
      title.textContent = item.kind || "resource";
      const status = document.createElement("p");
      status.className = "ui-tag";
      status.textContent = item.status || "unknown";
      const code = document.createElement("p");
      code.className = "ui-muted";
      code.textContent = item.http_status === null || item.http_status === undefined
        ? "HTTP: not observed"
        : "HTTP: " + item.http_status;
      const link = document.createElement("a");
      link.href = item.url;
      link.rel = "noopener";
      link.target = "_blank";
      link.textContent = item.url;
      card.append(title, status, code, link);
      observationsRoot.append(card);
    }});
  }} catch (error) {{
    summary.textContent = "Diagnostics could not be loaded.";
    observationsRoot.replaceChildren();
  }}
}})();
</script>
</body>
</html>
"""


def write_outputs(*, probe: bool = True) -> dict[str, Any]:
    record = current_record()
    payload = diagnostics_payload(record, probe=probe)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    OUTPUT_HTML.write_text(page_html(), encoding="utf-8")
    return payload


if __name__ == "__main__":
    write_outputs()
