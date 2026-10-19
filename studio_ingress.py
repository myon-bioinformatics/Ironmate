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
    # The rounded encoded-length bound alone permits up to two excess bytes.
    size = len(encoded) // 4 * 3 - (len(encoded) - len(encoded.rstrip("=")))
    if size > max_bytes:
        raise ValueError("empty or oversized image")
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


def _image_text(text: str) -> bool:
    """Recognize explicit data URIs or raw Base64 with an image signature."""
    if text.lower().startswith("data:"):
        return True
    # Inspect only a small prefix; do not decode an entire ambiguous text note.
    prefix = ""
    for char in text:
        if not char.isspace():
            prefix += char
            if len(prefix) == 16:
                break
    if prefix.startswith(("iVBORw0KGg", "/9j/")):
        return True
    try:
        return sniff(base64.b64decode(prefix, validate=True)) is not None
    except (ValueError, binascii.Error):
        return False


def _text_size(text: str, remaining: int) -> int:
    # Count UTF-8 with bounded temporary allocations, including multibyte notes.
    if len(text) > remaining:
        raise ValueError("total shelf bytes exceed limit")
    size = 0
    for start in range(0, len(text), 4096):
        size += len(text[start:start + 4096].encode("utf-8"))
        if size > remaining:
            raise ValueError("total shelf bytes exceed limit")
    return size


def parse_shelf(items: list[dict | str], *, max_bytes: int = MAX_BYTES) -> list[dict]:
    """Parse a list of shelf items (dicts or raw Base64/data URI strings).

    Enforces decoded image bytes + UTF-8 note bytes <= max_bytes (default 32MiB)
    and item count <= 20. Each decode receives only the remaining byte budget.
    data: URIs, dicts with type='image' or a MIME, and raw Base64 with a known
    image signature are image inputs: validation errors propagate, never become
    text notes. Other strings are plain text. A dict MIME must match the image.
    Returns dicts with 'type', 'data' (bytes|None), 'mime', 'text', and 'label'.
    """
    if not isinstance(items, list):
        raise ValueError("shelf items must be a list")
    if len(items) > 20:
        raise ValueError("shelf item count exceeds limit (max 20)")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    parsed = []
    total_bytes = 0
    for idx, item in enumerate(items):
        if isinstance(item, str):
            text = item.strip()
            label, declared = f"Item {idx + 1}", None
            explicit = False
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("data") or "").strip()
            label = str(item.get("label") or f"Item {idx + 1}")
            declared = item.get("mime")
            explicit = item.get("type") == "image" or declared is not None
        else:
            raise ValueError("shelf item must be string or dict")
        text = text.removeprefix("\ufeff").strip()
        if explicit or _image_text(text):
            mime, data = decode(text, max_bytes=max_bytes - total_bytes)
            if declared is not None:
                normalized = str(declared).lower()
                if normalized == "image/jpg":
                    normalized = "image/jpeg"
                if normalized != mime:
                    raise ValueError("unsupported image or MIME mismatch")
            total_bytes += len(data)
            kind = "image"
        else:
            if not text:
                continue
            total_bytes += _text_size(text, max_bytes - total_bytes)
            mime, data, kind = None, None, "text"
        parsed.append({"type": kind, "data": data, "mime": mime, "text": text, "label": label})
    return parsed
