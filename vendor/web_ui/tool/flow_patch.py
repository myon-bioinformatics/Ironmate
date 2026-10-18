"""Non-destructive JSON flow editing with bounded, atomic patch operations.

Keep the canonical web-ui flow JSON as the source of truth. No image is decoded.
"""
from __future__ import annotations
import argparse
import json
import sys
from tool.flow_diagram import MAX_INPUT, validate

MAX_PATCH = 64 * 1024
MAX_OPS = 64
_FIELDS = frozenset({"title", "note"})


def canonical(spec):
    """Validate and return a detached, JSON-serializable flow document."""
    return validate(spec)


def patch_flow(spec, operations):
    """Apply a batch atomically; invalid operations never mutate caller state."""
    result = canonical(spec)
    if not isinstance(operations, list) or len(operations) > MAX_OPS:
        raise ValueError("patch must be an array with at most 64 operations")
    for operation in operations:
        if not isinstance(operation, dict) or set(operation) != {"path", "value"}:
            raise ValueError("patch entries require path and value")
        path = operation["path"]
        if not isinstance(path, str):
            raise ValueError("patch path must be a string")
        if path in ("/title", "/sources_label"):
            result[path[1:]] = operation["value"]
            continue
        parts = path.split("/")
        if len(parts) != 4 or parts[0] != "" or parts[1] not in ("sources", "steps") or parts[3] not in _FIELDS:
            raise ValueError("unsupported patch path")
        index = parts[2]
        if not index.isascii() or not index.isdecimal() or str(int(index)) != index:
            raise ValueError("patch index must be canonical decimal")
        collection = result[parts[1]]
        if int(index) >= len(collection):
            raise ValueError("patch index out of range")
        collection[int(index)][parts[3]] = operation["value"]
    return validate(result)


def apply_document(document):
    if not isinstance(document, dict) or set(document) != {"spec", "patch"}:
        raise ValueError("expected spec and patch")
    return patch_flow(document["spec"], document["patch"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + MAX_PATCH + 1)
        if len(raw) > MAX_INPUT + MAX_PATCH:
            raise ValueError("patch document exceeds byte budget")
        result = apply_document(json.loads(raw.decode("utf-8")))
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None) + "\n")
    except (ValueError, UnicodeError) as exc:
        parser.exit(2, f"flow patch: {exc}\n")


if __name__ == "__main__":
    main()
