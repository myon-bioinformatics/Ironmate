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


def _targets_all(node: ast.AST) -> bool:
    """Return whether an assignment target mutates __all__ directly or by subscript."""
    if _is_all_name(node):
        return True
    if isinstance(node, ast.Subscript):
        return _is_all_name(node.value)
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_targets_all(item) for item in node.elts)
    return False


def _reject_noncanonical_all_mutations(tree: ast.Module) -> None:
    """Reject __all__ mutations outside the one canonical top-level assignment."""
    canonical_assignments: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(_is_all_name(target) for target in node.targets):
            canonical_assignments.add(id(node))
        elif isinstance(node, ast.AnnAssign) and _is_all_name(node.target):
            canonical_assignments.add(id(node))

    for node in ast.walk(tree):
        if id(node) in canonical_assignments:
            continue
        if isinstance(node, ast.Assign) and any(_targets_all(target) for target in node.targets):
            raise ValueError("__all__ must not be reassigned or mutated outside its canonical assignment")
        if isinstance(node, ast.AnnAssign) and _targets_all(node.target):
            raise ValueError("__all__ must not be reassigned or mutated outside its canonical assignment")
        if isinstance(node, ast.AugAssign) and _targets_all(node.target):
            raise ValueError("__all__ must not use augmented assignment")
        if isinstance(node, ast.NamedExpr) and _targets_all(node.target):
            raise ValueError("__all__ must not use assignment expressions")
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and _is_all_name(func.value)
            ):
                raise ValueError("__all__ must not be mutated by method calls")


def count_literal_all(source: str) -> int:
    """Return the number of names in one literal top-level __all__ assignment."""
    tree = _parse_source(source)
    _reject_noncanonical_all_mutations(tree)
    values: list[Any] = []
    for node in tree.body:
        value_node = None
        if isinstance(node, ast.Assign):
            if any(_is_all_name(target) for target in node.targets):
                value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if _is_all_name(node.target):
                value_node = node.value
        if value_node is not None:
            try:
                values.append(ast.literal_eval(value_node))
            except (ValueError, TypeError) as exc:
                raise ValueError("__all__ must be a literal list or tuple of strings") from exc

    if len(values) != 1:
        raise ValueError("expected exactly one top-level literal __all__ assignment")
    value = values[0]
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError("__all__ must be a literal list or tuple of strings")
    return len(value)


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
    """Validate the top header and ensure its __all__ count matches the source."""
    _, line = find_header(source)
    metadata = parse_header(line)
    actual = count_literal_all(source)
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
