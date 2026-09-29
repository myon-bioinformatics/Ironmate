"""Stdlib-only provenance contract for Python single-file vendoring artifacts."""
from __future__ import annotations

import ast
from datetime import datetime
import re
from typing import Any

HEADER_PREFIX = "# metadata:"
_HEADER_RE = re.compile(
    r"^# metadata: __all__=(?P<count>[0-9]+) \| "
    r"base_sha=(?P<sha>(?:[0-9a-f]{40}|[0-9a-f]{64})) \| "
    r"updated_at=(?P<updated_at>\S+)$"
)
_HEADER_SCAN_LINES = 8
_CODING_RE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
_FILENAME_COMMENT_RE = re.compile(r"#\s+[^\r\n]+\.py\s*$")


def _validate_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("updated_at must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("updated_at must include a timezone")
    return value


def _validate_sha(value: str) -> str:
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
        raise ValueError("base_sha must be a full lowercase 40- or 64-hex commit SHA")
    return value


def _header_indices(source: str) -> list[int]:
    if source.startswith("\ufeff"):
        source = source[1:]
    return [
        index
        for index, line in enumerate(source.splitlines())
        if line.startswith(HEADER_PREFIX)
    ]


def _parse_source(source: str) -> ast.Module:
    """Parse source text, accepting a single leading UTF-8 BOM."""
    if source.startswith("\ufeff"):
        source = source[1:]
    return ast.parse(source)


def _is_all_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "__all__"


def _literal_all_names(tree: ast.Module) -> tuple[str, ...]:
    """Return the one canonical literal top-level __all__ declaration."""
    values: list[tuple[str, ...]] = []
    for node in tree.body:
        value_node = None
        if isinstance(node, ast.Assign):
            if any(_is_all_name(target) for target in node.targets):
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and _is_all_name(node.target):
            value_node = node.value
        elif isinstance(node, ast.AugAssign) and _is_all_name(node.target):
            raise ValueError("__all__ must use one literal top-level assignment")
        elif isinstance(node, ast.Expr):
            call = node.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and _is_all_name(call.func.value)
            ):
                raise ValueError("__all__ must use one literal top-level assignment")

        if value_node is not None:
            try:
                value = ast.literal_eval(value_node)
            except (ValueError, TypeError) as exc:
                raise ValueError("__all__ must be a literal list or tuple of strings") from exc
            if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
                raise ValueError("__all__ must be a literal list or tuple of strings")
            values.append(tuple(value))

    if len(values) != 1:
        raise ValueError("expected exactly one top-level literal __all__ assignment")

    names = values[0]
    if len(names) != len(set(names)):
        raise ValueError("__all__ must not contain duplicate names")
    return names


def _defined_top_level_names(tree: ast.Module) -> set[str]:
    """Return names implemented directly by the artifact, excluding imports."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id != "__all__":
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id != "__all__":
                names.add(node.target.id)
    return names


def _validate_public_api(tree: ast.Module, exported: tuple[str, ...]) -> None:
    """Keep __all__ aligned with public implementation names.

    Underscored helpers are internal and intentionally excluded. Imported names are not
    treated as artifact implementation. Runtime/dynamic mutation below nested control flow
    is outside this static contract.
    """
    exported_set = set(exported)
    defined = _defined_top_level_names(tree)

    missing = sorted(name for name in exported if name not in defined)
    if missing:
        raise ValueError(f"__all__ contains names not implemented by the artifact: {missing}")

    public_defs = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }
    unexported = sorted(public_defs - exported_set)
    if unexported:
        raise ValueError(f"public functions/classes missing from __all__: {unexported}")

    private_exports = sorted(name for name in exported if name.startswith("_"))
    if private_exports:
        raise ValueError(f"internal underscored names must not be exported: {private_exports}")


def count_literal_all(source: str) -> int:
    """Return the number of names in the canonical public __all__ declaration."""
    tree = _parse_source(source)
    return len(_literal_all_names(tree))


def format_header(*, all_count: int, base_sha: str, updated_at: str) -> str:
    """Return the canonical single-line artifact provenance header."""
    if not isinstance(all_count, int) or isinstance(all_count, bool) or all_count < 0:
        raise ValueError("all_count must be a non-negative integer")
    _validate_sha(base_sha)
    _validate_timestamp(updated_at)
    return (
        f"{HEADER_PREFIX} __all__={all_count} | "
        f"base_sha={base_sha} | updated_at={updated_at}"
    )


def parse_header(line: str) -> dict[str, Any]:
    """Parse and validate one canonical provenance header."""
    match = _HEADER_RE.fullmatch(line.rstrip("\r\n"))
    if match is None:
        raise ValueError("invalid Python artifact provenance header")
    result = {
        "all_count": int(match.group("count")),
        "base_sha": match.group("sha"),
        "updated_at": match.group("updated_at"),
    }
    _validate_timestamp(result["updated_at"])
    return result


def find_header(source: str) -> tuple[int, str]:
    """Return (zero-based line index, line) for the unique header near the top."""
    body = source[1:] if source.startswith("\ufeff") else source
    lines = body.splitlines()
    indices = _header_indices(body)
    if len(indices) > 1:
        raise ValueError("expected exactly one Python artifact provenance header")
    if not indices:
        raise ValueError(f"provenance header must appear within the first {_HEADER_SCAN_LINES} lines")
    index = indices[0]
    if index >= _HEADER_SCAN_LINES:
        raise ValueError(f"provenance header must appear within the first {_HEADER_SCAN_LINES} lines")
    line = lines[index]
    parse_header(line)
    return index, line


def validate_source_header(source: str) -> dict[str, Any]:
    """Validate provenance plus the artifact's static public API contract."""
    _, line = find_header(source)
    metadata = parse_header(line)
    tree = _parse_source(source)
    exported = _literal_all_names(tree)
    _validate_public_api(tree, exported)
    actual = len(exported)
    if metadata["all_count"] != actual:
        raise ValueError(
            f"provenance __all__ count mismatch: header={metadata['all_count']} actual={actual}"
        )
    return metadata


def upsert_header(source: str, *, base_sha: str, updated_at: str) -> str:
    """Insert or replace the canonical header while preserving the rest of the source."""
    header = format_header(
        all_count=count_literal_all(source),
        base_sha=base_sha,
        updated_at=updated_at,
    )
    bom = "\ufeff" if source.startswith("\ufeff") else ""
    body = source[1:] if bom else source
    lines = body.splitlines(keepends=True)
    indices = _header_indices(body)
    if len(indices) > 1:
        raise ValueError("expected at most one Python artifact provenance header")
    if indices:
        index = indices[0]
        if index >= _HEADER_SCAN_LINES:
            raise ValueError(
                f"existing provenance header must appear within the first {_HEADER_SCAN_LINES} lines"
            )
        raw = lines[index]
        ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
        lines[index] = header + ending
        return bom + "".join(lines)

    insert_at = 0
    seen: set[str] = set()
    while insert_at < len(lines):
        raw = lines[insert_at].rstrip("\r\n")
        kind = None
        if insert_at == 0 and raw.startswith("#!"):
            kind = "shebang"
        elif insert_at < 2 and _CODING_RE.match(raw):
            kind = "coding"
        elif _FILENAME_COMMENT_RE.fullmatch(raw):
            kind = "filename"

        if kind is None or kind in seen:
            break
        seen.add(kind)
        insert_at += 1

    ending = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    lines.insert(insert_at, header + ending)
    return bom + "".join(lines)
