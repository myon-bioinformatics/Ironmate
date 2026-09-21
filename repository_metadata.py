"""Stdlib-only helpers for optional repository metadata extraction."""
from __future__ import annotations

import ast
import json
import re
from typing import Any

_STATUS = {"detected", "not_found", "unsupported", "fetch_failed", "parse_failed"}
README_MAX_HEADINGS = 8
README_MAX_EXCERPT = 480
IMPORTANT_FILES_LIMIT = 12


def availability(status: str, value: Any = None, *, source: str | None = None) -> dict[str, Any]:
    if status not in _STATUS:
        raise ValueError(f"unknown availability status: {status}")
    result: dict[str, Any] = {"status": status}
    if value is not None:
        result["value"] = value
    if source:
        result["source"] = source
    return result


def parse_manifest_version(path: str, text: str) -> dict[str, Any]:
    """Extract a package version from common manifest formats without dependencies."""
    name = path.rsplit("/", 1)[-1].lower()
    try:
        if name == "package.json":
            value = json.loads(text).get("version")
        elif name in {"pyproject.toml", "cargo.toml"}:
            match = re.search(r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']\s*$', text)
            value = match.group(1) if match else None
        elif name == "pubspec.yaml":
            match = re.search(r"(?m)^version\s*:\s*([^\s#]+)", text)
            value = match.group(1) if match else None
        elif name == "setup.cfg":
            match = re.search(r"(?mi)^\s*version\s*=\s*([^\s#]+)", text)
            value = match.group(1) if match else None
        else:
            return availability("unsupported", source=path)
    except (json.JSONDecodeError, TypeError):
        return availability("parse_failed", source=path)
    return availability("detected", str(value), source=path) if value else availability("not_found", source=path)


def parse_python_api(text: str, *, source: str) -> dict[str, Any]:
    """Return literal __all__ plus public top-level defs/classes from Python source."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return availability("parse_failed", source=source)

    literal_all: list[str] | None = None
    functions: list[str] = []
    classes: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            classes.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "__all__" for target in targets):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    value = None
                if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                    literal_all = list(value)

    value = {
        "exports": literal_all if literal_all is not None else functions + classes,
        "export_source": "__all__" if literal_all is not None else "public_top_level",
        "functions": functions,
        "classes": classes,
    }
    return availability("detected", value, source=source)


def readme_digest(
    text: str,
    *,
    max_headings: int = README_MAX_HEADINGS,
    max_excerpt: int = README_MAX_EXCERPT,
) -> dict[str, Any]:
    """Produce a deterministic, non-LLM README digest."""
    headings: list[str] = []
    prose: list[str] = []
    in_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("~~~") or line.startswith(chr(96) * 3):
            in_fence = not in_fence
            continue
        if in_fence or not line:
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading and len(headings) < max_headings:
                headings.append(heading)
            continue
        if line.startswith(("![", "[![", "<", "|")):
            continue
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", line)
        cleaned = re.sub(r"[\x60*_~]", "", cleaned).strip()
        if cleaned:
            prose.append(cleaned)
        if sum(len(item) + 1 for item in prose) >= max_excerpt:
            break
    excerpt = " ".join(prose)[:max_excerpt].strip()
    return {"headings": headings, "excerpt": excerpt}


def select_manifest(tree: list[dict[str, Any]]) -> str | None:
    priority = ("pyproject.toml", "package.json", "pubspec.yaml", "Cargo.toml", "setup.cfg")
    paths = {str(item.get("path")) for item in tree if item.get("type") == "blob"}
    return next((name for name in priority if name in paths), None)


def select_readme(tree: list[dict[str, Any]]) -> str | None:
    files = [str(item.get("path")) for item in tree if item.get("type") == "blob" and "/" not in str(item.get("path"))]
    by_lower = {path.lower(): path for path in files}
    for candidate in ("readme.md", "readme.rst", "readme.txt", "readme"):
        if candidate in by_lower:
            return by_lower[candidate]
    return next((path for path in files if path.lower().startswith("readme")), None)


def select_python_sources(tree: list[dict[str, Any]], limit: int = 3) -> list[str]:
    ignored = ("tests/", "test/", "vendor/", ".venv/", "venv/", "docs/")
    paths = []
    for item in tree:
        path = str(item.get("path") or "")
        if item.get("type") != "blob" or not path.endswith(".py") or path.startswith(ignored):
            continue
        depth = path.count("/")
        paths.append((depth, len(path), path))
    paths.sort()
    return [path for _, _, path in paths[:limit]]


def important_file_shas(
    tree: list[dict[str, Any]], limit: int = IMPORTANT_FILES_LIMIT
) -> list[dict[str, Any]]:
    """Return stable identifiers for useful files without fetching file contents."""
    # Rank manifests/README/container entry points first, then source files.
    preferred_names = {
        "readme.md", "readme.rst", "pyproject.toml", "package.json", "pubspec.yaml",
        "cargo.toml", "setup.cfg", "dockerfile", "compose.yaml", "compose.yml",
    }
    ranked: list[tuple[int, int, str, dict[str, Any]]] = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        basename = path.rsplit("/", 1)[-1].lower()
        score = 0 if basename in preferred_names else 1 if path.endswith((".py", ".dart", ".js", ".ts", ".rs")) else 2
        ranked.append((score, path.count("/"), path, item))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]))
    return [
        {"path": path, "sha": item.get("sha"), "size": item.get("size")}
        for _, _, path, item in ranked[:limit]
    ]
