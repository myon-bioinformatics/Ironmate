"""Strict, dependency-free PNG/JPEG/WebP clipboard-text ingress.

Pure validation only: OS picker/camera/clipboard permissions belong to adapters.
"""
from __future__ import annotations

import base64
import binascii
import re

MAX_BYTES = 32 * 1024 * 1024
_DATA = re.compile(r"^data:([a-z0-9.+-]+/[a-z0-9.+-]+)?(?:;[a-z0-9.+-]+=[a-z0-9.+-]+)*;base64,", re.I)
_B64 = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def decode(text: str, *, max_bytes: int = MAX_BYTES) -> tuple[str, bytes]:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    value = text.removeprefix("\ufeff").strip()
    match = _DATA.match(value)
    declared = None
    if match:
        declared = (match.group(1) or "").lower() or None
        if declared == "image/jpg":
            declared = "image/jpeg"
        value = value[match.end():]
    elif value.lower().startswith("data:"):
        raise ValueError("invalid data URI")
    if declared and declared not in ("image/png", "image/jpeg", "image/webp"):
        raise ValueError("unsupported MIME")
    encoded = re.sub(r"\s+", "", value)
    if not encoded or len(encoded) > 4 * ((max_bytes + 2) // 3):
        raise ValueError("empty or oversized Base64")
    if len(encoded) % 4 or not _B64.fullmatch(encoded):
        raise ValueError("invalid standard padded Base64")
    try:
        data = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise ValueError("invalid Base64 padding") from exc
    if not data or len(data) > max_bytes:
        raise ValueError("empty or oversized image")
    actual = sniff(data)
    if not actual or (declared and declared != actual):
        raise ValueError("unsupported image or MIME mismatch")
    return actual, data


def parse_shelf(items: list[dict | str], *, max_bytes: int = MAX_BYTES) -> list[dict]:
    """Parse a list of shelf items (dicts or raw Base64/data URI strings).

    Enforces total image data <= max_bytes and item count <= 20.
    Returns list of dicts with keys: 'type', 'data' (bytes|None), 'mime', 'text'.
    """
    if not isinstance(items, list):
        raise ValueError("shelf items must be a list")
    if len(items) > 20:
        raise ValueError("shelf item count exceeds limit (max 20)")
    parsed = []
    total_bytes = 0
    for idx, item in enumerate(items):
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            try:
                mime, data = decode(text, max_bytes=max_bytes)
                total_bytes += len(data)
                parsed.append({"type": "image", "data": data, "mime": mime, "text": text, "label": f"Item {idx + 1}"})
            except ValueError:
                parsed.append({"type": "text", "data": None, "mime": None, "text": text, "label": f"Item {idx + 1}"})
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("data") or "").strip()
            if not text:
                continue
            try:
                mime, data = decode(text, max_bytes=max_bytes)
                total_bytes += len(data)
                parsed.append({
                    "type": "image",
                    "data": data,
                    "mime": mime,
                    "text": text,
                    "label": str(item.get("label") or f"Item {idx + 1}")
                })
            except ValueError:
                parsed.append({
                    "type": "text",
                    "data": None,
                    "mime": None,
                    "text": text,
                    "label": str(item.get("label") or f"Item {idx + 1}")
                })
        else:
            raise ValueError("shelf item must be string or dict")
    if total_bytes > max_bytes:
        raise ValueError("total shelf image bytes exceed limit")
    return parsed
