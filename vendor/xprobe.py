"""Stdlib-only search and failure probes; copy this file to vendor it.

Importing this module performs no I/O. Probes execute only caller-supplied
callables, and are not a sandbox or a timeout mechanism.
"""

import ast
import codecs
import fnmatch
import importlib
import importlib.util
import errno
import json
import os
import random
import re
import stat
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

__version__ = "0.4.0"
__all__ = ["search_text", "search_files", "boundary_cases", "run_cases",
           "inspect_text", "inspect_environment", "scan_config",
           "known_bad_cases", "generate_cases", "corpus_to_json",
           "corpus_from_json", "merge_cases", "cases_from_junit", "main",
           "pytest_receipt", "case_factor_matrix", "generate_factor_cases",
           "explain_outcome", "pattern_presets", "normalize_text",
           "load_toml", "load_yaml", "junit_annotations", "portability_findings",
           "emoji_sequences", "emoji_identity", "emoji_name", "emoji_find", "emoji_inventory",
           "load_emoji_names", "hidden_text", "hidden_text_rules", "strip_hidden", "hidden_text_scan",
           "mojibake_text", "restore_mojibake", "mojibake_scan", "decode_text", "readable_text",
           "python_symbols", "discover_files", "discover_python"]


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(name + " must be a positive integer")


# Named regexes gathered from sibling repositories (Err-o-RoadRunner triage /
# junit_redact, gh_identity, browser-test-kit). Line-local: ^ and $ are a line.
_PRESETS = {
    'git-sha': (r'\b[0-9a-f]{40}\b', 'full lowercase Git commit SHA'),
    'sha256': (r'\b[0-9a-fA-F]{64}\b', 'SHA-256 hex digest'),
    'iso-timestamp': (r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?',
                      'ISO 8601 date-time'),
    'url': (r'''\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>"']+''', 'scheme://... URL'),
    'python-frame': (r'^  File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<func>.*))?$',
                     'Python traceback frame line'),
    'python-exception': (r'^(?:E\s+|\s*)(?P<exc>(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Warning|Exit|Interrupt|Group))'
                         r'(?::\s*(?P<msg>.*))?$',
                         'Python exception summary line, also after pytest\'s "E   " prefix'),
    'node-error': (r'^(?P<head>(?:[A-Za-z_]\w*(?:Error|Warning|Rejection)|Unhandled\s+rejection(?:\s+\([^)]+\))?))'
                   r'\s*:\s*(?P<rest>.*)$', 'Node/JS error headline'),
    'npm-error': (r'^npm ERR!\s+(?P<rest>.+)$', 'npm ERR! line'),
    'compiler-error': (r'^(?:fatal )?error(?:\[[A-Za-z0-9]+\])?:\s+(?P<rest>.+)$',
                       'lowercase compiler error line (gcc, rustc, dart, ...)'),
    'credential': (r'gh[pousr]_[A-Za-z0-9]{36,}|ghs_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{22,}'
                   r'|(?:AKIA|ASIA)[A-Z0-9]{16}|(?i:aws_secret_access_key)\s*[=:]\s*[\'"]?[A-Za-z0-9/+=]{40,}'
                   r'|Bearer\s+[A-Za-z0-9._-]{8,}|sk-[A-Za-z0-9]{20,}',
                   'GitHub/AWS/Bearer/sk- credential-like token'),
    'ci-path': (r'/home/runner/work/[^/\s]+/[^/\s]+|/Users/[^/\s<"\']+|/opt/hostedtoolcache/|/tmp/pytest-of-[^/\s]+/',
                'CI runner or user-home path'),
    'hex-address': (r'\b0x[0-9a-fA-F]{8,}\b', 'memory address'),
    'ansi': (r'\x1b\[[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]|\x9b[\x30-\x3f]*[\x20-\x2f]*[\x40-\x7e]'
             r'|\x1b\][^\x07\x1b\n]*(?:\x07|\x1b\\)?|\x1b[@-Z\\-_]', 'terminal escape sequence'),
}
_ANSI = re.compile(_PRESETS['ansi'][0])
NORMALIZE_STEPS = ('ansi', 'nfkc', 'casefold', 'spaces', 'vs16', 'mojibake')
_INVISIBLE = '\ufe0e\ufe0f\u200d'  # VS15, VS16, ZWJ (escaped: keep the source cp1252-readable)


def pattern_presets():
    """Return {name: {'regex', 'about'}} for the built-in named patterns."""
    return {name: {'regex': regex, 'about': about} for name, (regex, about) in _PRESETS.items()}


def _steps(normalize):
    if isinstance(normalize, str):
        normalize = [normalize]
    steps = tuple(normalize or ())
    unknown = [s for s in steps if s not in NORMALIZE_STEPS]
    if unknown:
        raise ValueError('unknown normalize step(s): ' + ', '.join(map(str, unknown)))
    return steps


def decode_text(data):
    """Read common Japanese text encodings without caller configuration.

    Return text, encoding, source, status, warnings and candidate metadata.
    BOMs take precedence; supported HTML/XML declarations are useful hints.
    A broken declared reading can yield to a more readable finite candidate;
    strong mojibake evidence can also favor valid UTF-8 over a legacy hint.
    Undecodable bytes become visible ``\\xHH`` escapes, never disappear. This
    is a reading view, not proof of the original encoding or a format parser.
    Keep the original bytes when exact reconstruction matters.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("data must be bytes-like")
    data = bytes(data)
    warnings = []

    def candidate(raw, encoding):
        try:
            text = raw.decode(encoding)
            partial = False
        except UnicodeDecodeError:
            text = raw.decode(encoding, errors="backslashreplace")
            partial = True
        roundtrip = not partial and text.encode(encoding) == raw
        return {"encoding": encoding, "text": text, "partial": partial,
                "roundtrip": roundtrip}

    def finish(chosen, source, candidates):
        if chosen["partial"]:
            warnings.append("undecodable bytes are shown as \\xHH escapes")
        if "\ufffd" in chosen["text"]:
            warnings.append("input already contains Unicode replacement characters")
        if not chosen["partial"] and not chosen["roundtrip"]:
            warnings.append("codec has noncanonical byte mappings; original bytes retained in source_hex")
        return {"text": chosen["text"], "encoding": chosen["encoding"],
                "source": source,
                "source_hex": data.hex(), "roundtrip": chosen["roundtrip"],
                "status": "partial" if chosen["partial"] or "\ufffd" in chosen["text"] else "decoded",
                "warnings": warnings,
                "candidates": [{k: v for k, v in item.items() if k != "text"}
                               for item in candidates]}

    def score(encoding, penalize_errors=True):
        view = data.decode(encoding, errors="replace")
        value = 0
        for char in view:
            if "\u3041" <= char <= "\u3096" or "\u30a1" <= char <= "\u30fa":
                value += 4
            elif "\u4e00" <= char <= "\u9fff":
                value += 2
            elif "\uff61" <= char <= "\uff9f":
                value += 1
            elif char == "\ufffd":
                value -= 8 if penalize_errors else 0
            elif unicodedata.category(char) in ("Co", "Cs"):
                value -= 12
            elif unicodedata.category(char) == "Cc" and char not in "\t\n\r":
                value -= 12
        return value

    def utf8_alternative(item):
        alternate = candidate(data, "utf-8")
        if alternate["partial"] or not any(ord(c) >= 128 for c in alternate["text"]):
            return None
        suspicious = any("\uff61" <= c <= "\uff9f" or
                         unicodedata.category(c) == "Co" for c in item["text"])
        old_count = max(1, sum(ord(c) >= 128 for c in item["text"]))
        new_count = max(1, sum(ord(c) >= 128 for c in alternate["text"]))
        better = score("utf-8") * old_count > score(item["encoding"]) * new_count
        return alternate if item["partial"] or (suspicious and better) else None

    # Four-byte BOMs must precede their two-byte prefixes.
    for bom, encoding in ((b"\xff\xfe\x00\x00", "utf-32-le"),
                          (b"\x00\x00\xfe\xff", "utf-32-be"),
                          (b"\xef\xbb\xbf", "utf-8"),
                          (b"\xff\xfe", "utf-16-le"),
                          (b"\xfe\xff", "utf-16-be")):
        if data.startswith(bom):
            item = candidate(data[len(bom):], encoding)
            return finish(item, "bom", [item])
    if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08",
                        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")) or b"\x00" in data:
        raise ValueError("binary/container data needs its own format parser")

    # Inspect only declaration-shaped tags, with a fixed sniffing budget.
    allowed = {"utf-8", "ascii", "cp932", "shift_jis", "euc_jp", "iso2022_jp", "cp1252"}
    for tag in re.finditer(br"<(?:meta\b|\?xml\b)[^>]{0,1024}>", data[:4096], re.I):
        match = re.search(br"(?:charset|encoding)\s*=\s*['\"]?\s*([A-Za-z0-9._-]+)",
                          tag.group(), re.I)
        if match is None:
            continue
        label = match.group(1).decode("ascii")
        try:
            encoding = codecs.lookup(label).name
        except LookupError:
            encoding = None
        if label.lower().replace("_", "-") in ("windows-31j", "ms932"):
            encoding = "cp932"
        if encoding not in allowed:
            warnings.append("unsupported encoding declaration: " + label)
            continue
        if encoding == "shift_jis":
            encoding = "cp932"
        item = candidate(data, encoding)
        alternate = utf8_alternative(item) if encoding != "utf-8" else None
        if alternate is not None:
            warnings.append("encoding declaration conflicts with a more plausible UTF-8 reading: " + label)
            return finish(alternate, "fallback", [item, alternate])
        candidates = [item]
        if item["partial"]:
            # Compare retained readable text, without letting invalid-byte
            # penalties alone outweigh a useful partial declared decoding.
            retained_score = max(0, score(encoding, penalize_errors=False))
            better = []
            for other in ("utf-8", "cp932", "euc_jp"):
                if other == encoding:
                    continue
                trial = candidate(data, other)
                trial["score"] = score(other)
                candidates.append(trial)
                if not trial["partial"] and trial["score"] > retained_score:
                    better.append(trial)
            if better:
                alternate = max(better, key=lambda trial: trial["score"])
                warnings.append("encoding declaration conflicts with a more readable candidate: " + label)
                return finish(alternate, "fallback", candidates)
        return finish(item, "declared", candidates)

    if any(escape in data for escape in (b"\x1b$B", b"\x1b$@", b"\x1b(J")):
        item = candidate(data, "iso2022_jp")
        alternate = utf8_alternative(item) if item["partial"] else None
        if alternate is not None:
            warnings.append("ISO-2022-JP escape hint conflicts with valid UTF-8; used UTF-8")
            return finish(alternate, "fallback", [item, alternate])
        return finish(item, "heuristic", [item])
    utf8 = candidate(data, "utf-8")
    if not utf8["partial"]:
        return finish(utf8, "heuristic", [utf8])

    # Keep largely valid UTF-8 readable even with one corrupt/truncated suffix.
    # This is evidence for a candidate, not a probability or a language verdict.
    preview = data.decode("utf-8", errors="replace")
    high_bytes = sum(byte >= 128 for byte in data)
    good_utf8 = sum(len(char.encode("utf-8")) for char in preview
                    if ord(char) >= 128 and char != "\ufffd")
    if good_utf8 >= 3 and good_utf8 * 4 >= high_bytes * 3:
        warnings.append("selected UTF-8 from predominantly valid multibyte sequences")
        return finish(utf8, "fallback", [utf8])

    candidates = [utf8, candidate(data, "cp932"), candidate(data, "euc_jp")]
    for item in candidates:
        item["score"] = score(item["encoding"])
    chosen = max(candidates, key=lambda item: item["score"])
    # With no positive language evidence, preserve ASCII and expose bad bytes.
    if chosen["score"] <= 0:
        chosen = utf8
    warnings.append("encoding selected heuristically; candidate scores are not probabilities")
    if sum(item["score"] == chosen["score"] for item in candidates) > 1:
        warnings.append("encoding candidates are tied; stable preference order was used")
    return finish(chosen, "fallback" if chosen["partial"] else "heuristic", candidates)


# Japanese mojibake candidates. These are reading heuristics, not language proofs.
_JP_HIRAGANA, _JP_KATAKANA, _JP_KANJI, _JP_HW_KATAKANA, _JP_ANY = (
    re.compile(r"[\u3040-\u309f]"), re.compile(r"[\u30a0-\u30ff]"),
    re.compile(r"[\u4e00-\u9fff]"), re.compile(r"[\uff65-\uff9f]"),
    re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\uff65-\uff9f\u3000-\u303f\uff01-\uff5e]")
)
_CP1252_CHARS = r"\x80-\xff\u20ac\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178"
_SJIS_LEAD = r"\u201a\u0192\u201e\u2026\u2020\u2021\u02c6\u2030\u0160\u2039\u0152\u017d\u2018\u2019\u201c\u201d\u2022\u2013\u2014\u02dc\u2122\u0161\u203a\u0153\u017e\u0178\x81-\x9f\xe0-\xea"
_SJIS_TRAIL = r"\x40-\x7e\x80-\xff"
_RE_CP932_1252 = re.compile(rf"[{_SJIS_LEAD}][{_SJIS_TRAIL}][{_SJIS_LEAD}{_SJIS_TRAIL}]*")
_RE_UTF8_1252 = re.compile(rf"[\xc2-\xf4][{_CP1252_CHARS}]+")
_RE_UTF8_CP932 = re.compile(r"(?:[\u7e3a\u7e5d\u7e67][\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u3040-\u30ff\u2460-\u24ff]+|譌[\x00-\xff]+|繧[\x00-\xff]+)+")
_CP1252_REV = {bytes([i]).decode("cp1252"): i for i in range(256)
               if i not in (0x81, 0x8d, 0x8f, 0x90, 0x9d)}


def _cp1252_compat_encode(text):
    """Accept either CP1252 glyphs or raw Latin-1/C1 byte spellings, strictly."""
    result = bytearray()
    for i, char in enumerate(text):
        value = _CP1252_REV.get(char, ord(char))
        if value > 255:
            raise UnicodeEncodeError("cp1252", text, i, i + 1, "not a byte spelling")
        result.append(value)
    return bytes(result)


def _classify_mojibake_hint(text):
    counts = [len(pattern.findall(text)) for pattern in
              (_JP_HIRAGANA, _JP_KATAKANA, _JP_KANJI, _JP_HW_KATAKANA)]
    return ("hiragana", "katakana", "kanji", "halfwidth_katakana")[counts.index(max(counts))]


def _mojibake_segments(chunk, source, target):
    """Yield reversible runs at both source-character and target-byte boundaries.

    A fixed-state incremental decoder visits each source character at most twice.
    Failed/pending units are left in the original text; no ignored bytes.
    """
    decoder = codecs.getincrementaldecoder(target)(errors="strict")
    run, start, end = [], 0, 0
    unit, raw, decoded = 0, bytearray(), []
    for i, char in enumerate(chunk):
        try:
            encoded = char.encode(source) if source == "cp932" else _cp1252_compat_encode(char)
        except UnicodeEncodeError:
            if run:
                yield start, end, "".join(run)
            run, raw, decoded = [], bytearray(), []
            decoder.reset()
            unit = i + 1
            continue
        for attempt in range(2):
            try:
                part = decoder.decode(encoded, final=False)
            except UnicodeDecodeError:
                retry = bool(raw) and attempt == 0
                if run:
                    yield start, end, "".join(run)
                run, raw, decoded = [], bytearray(), []
                decoder.reset()
                unit = i if retry else i + 1
                if retry:
                    continue
                break
            raw.extend(encoded)
            decoded.append(part)
            if not decoder.getstate()[0]:
                original, restored = chunk[unit:i + 1], "".join(decoded)
                valid = restored.encode(target) == raw
                if source == "cp932":
                    valid = valid and raw.decode(source) == original
                if target == "cp932" and restored != original:
                    valid = valid and any(0x80 <= _CP1252_REV.get(c, ord(c)) <= 0x9f
                                          for c in original)
                if target == "utf-8":
                    # Normal adjacent Japanese must not turn into Latin fragments.
                    valid = valid and all(ord(c) < 128 or _JP_ANY.fullmatch(c) or
                                          ord(c) >= 0x10000 for c in restored)
                    valid = valid and ("".join(c for c in original if ord(c) < 128) ==
                                       "".join(c for c in restored if ord(c) < 128))
                if valid:
                    if not run:
                        start = unit
                    run.append(restored)
                    end = i + 1
                else:
                    if run:
                        yield start, end, "".join(run)
                    run = []
                raw, decoded, unit = bytearray(), [], i + 1
            break
    if run:
        yield start, end, "".join(run)


def mojibake_text(text):
    """Return non-overlapping repair candidates and unresolved replacement chars.

    ``text`` and offsets retain the input; ``restored`` is a reading candidate.
    ``status=repaired`` means a byte-reversible conversion, not proof of intent.
    U+FFFD is kept with ``status=unrecoverable``. Unknown sequences stay untouched.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    findings, covered = [], set()
    # Prefer a valid UTF-8 interpretation over interpreting the same bytes as CP932.
    routes = ((_RE_UTF8_1252, "cp1252", "utf-8", "utf8_as_cp1252"),
              (_RE_UTF8_CP932, "cp932", "utf-8", "utf8_as_cp932"),
              (_RE_CP932_1252, "cp1252", "cp932", "cp932_as_cp1252"))
    for pattern, source, target, kind in routes:
        for match in pattern.finditer(text):
            chunk = match.group()
            for left, right, restored in _mojibake_segments(chunk, source, target):
                original = chunk[left:right]
                if restored == original or not _JP_ANY.search(restored):
                    continue
                if target == "cp932" and not any(
                        0x80 <= _CP1252_REV.get(c, ord(c)) <= 0x9f for c in original):
                    continue  # Latin words alone are ambiguous, e.g. "etude" with accents.
                start, end = match.start() + left, match.start() + right
                if any(i in covered for i in range(start, end)):
                    continue
                covered.update(range(start, end))
                findings.append({"kind": kind, "hint": _classify_mojibake_hint(restored),
                                 "start": start, "end": end, "text": original,
                                 "restored": restored, "status": "repaired", "roundtrip": True})
    # Within a recognized, partly repaired run, retain and identify strong
    # residual markers. Unknown text outside such runs is not called broken.
    unresolved_spans = set()
    for pattern, source, target, kind in routes:
        for match in pattern.finditer(text):
            if not any(i in covered for i in range(match.start(), match.end())):
                continue
            start = match.start()
            for end in range(start, match.end() + 1):
                if end == match.end() or end in covered:
                    if start < end and (text[start] in "ãäåæçèï縺繝繧" or
                                        any(0x80 <= ord(c) <= 0x9f for c in text[start:end])):
                        unresolved_spans.add((start, end))
                    start = end + 1
    retained = set()
    for start, end in sorted(unresolved_spans):
        if any(i in retained for i in range(start, end)):
            continue
        retained.update(range(start, end))
        original = text[start:end]
        findings.append({"kind": "unresolved_candidate", "hint": "uncertain",
                         "start": start, "end": end, "text": original,
                         "restored": original, "status": "unresolved", "roundtrip": False})
    for match in re.finditer(r"\ufffd+", text):
        findings.append({"kind": "replacement_char", "hint": "replacement",
                         "start": match.start(), "end": match.end(), "text": match.group(),
                         "restored": match.group(), "status": "unrecoverable", "roundtrip": False})
    return sorted(findings, key=lambda row: row["start"])


def restore_mojibake(text):
    """Return a readable view, repairing known spans and preserving all other text."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    result, last = [], 0
    for finding in mojibake_text(text):
        result.extend((text[last:finding["start"]], finding["restored"]))
        last = finding["end"]
    result.append(text[last:])
    return "".join(result)


def readable_text(data):
    """Decode bytes automatically, then repair known mojibake; retain the evidence."""
    report = decode_text(data)
    original = report["text"]
    report["decoded_text"] = original
    report["findings"] = mojibake_text(original)
    report["decoding_status"] = report["status"]
    unresolved = any(row["status"] in ("unresolved", "unrecoverable") for row in report["findings"])
    repaired = any(row["status"] == "repaired" for row in report["findings"])
    report["restoration_status"] = "partial" if unresolved else ("candidates_applied" if repaired else "unchanged")
    if unresolved:
        report["status"] = "partial"
        report["warnings"].append("unresolved mojibake candidates retained; see findings for original spans")
    parts, last = [], 0
    for finding in report["findings"]:
        parts.extend((original[last:finding["start"]], finding["restored"]))
        last = finding["end"]
    parts.append(original[last:])
    report["text"] = "".join(parts)
    if any(row["status"] == "repaired" for row in report["findings"]):
        report["warnings"].append("applied reversible mojibake candidates; decoded_text preserves the original view")
    return {"schema": "xprobe.readable-text.v1", **report}


def mojibake_scan(roots=(".",), *, max_files=5000, max_bytes=1_000_000, max_findings=1000):
    """Auto-decode text files, then report mojibake with decoding diagnostics."""
    if isinstance(roots, (str, os.PathLike)):
        roots = [roots]
    roots = list(roots)
    for value, label in ((max_files, "max_files"), (max_bytes, "max_bytes"), (max_findings, "max_findings")):
        _limit(value, label)
    findings, counts, scanned, skipped, truncated = [], {}, 0, 0, False
    decodings = []
    for root in roots:
        base = Path(root)
        paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file() and not any(part in _EMOJI_SKIP for part in p.relative_to(base).parts))
        for path in paths:
            if scanned == max_files:
                truncated = True
                break
            label = path.name if base.is_file() else path.relative_to(base).as_posix()
            if len(roots) > 1:
                label = os.fspath(root).rstrip("/") + "/" + label
            try:
                with path.open("rb") as stream:
                    data = stream.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError
                decoding = decode_text(data)
                text = decoding.pop("text")
            except (OSError, ValueError):
                skipped += 1
                continue
            scanned += 1
            decodings.append({"path": label, **decoding})
            for number, line in enumerate(text.split("\n"), 1):
                for row in mojibake_text(line):
                    counts[row["kind"]] = counts.get(row["kind"], 0) + 1
                    if len(findings) == max_findings:
                        truncated = True
                        continue
                    row = {"path": label, "line": number, "column": row.pop("start") + 1, **row}
                    row.pop("end")
                    findings.append(row)
    return {"schema": "xprobe.mojibake.v1", "files": scanned, "skipped": skipped,
            "truncated": truncated, "counts": counts, "findings": findings, "decodings": decodings}


def _combining(char):
    return unicodedata.combining(unicodedata.normalize('NFKC', char)[:1] or 'x')


def _normalized_line(line, steps):
    """(normalized text, [(orig_start, orig_end)] per normalized character)."""
    removed = set()
    if 'ansi' in steps:
        for match in _ANSI.finditer(line):
            removed.update(range(match.start(), match.end()))
    moji_spans = {}
    if 'mojibake' in steps:
        for row in mojibake_text(line):
            moji_spans[row['start']] = row
    out, spans, i, n = [], [], 0, len(line)
    while i < n:
        if i in removed:
            i += 1
            continue
        if i in moji_spans:
            f = moji_spans[i]
            restored = f['restored']
            if 'nfkc' in steps:
                restored = unicodedata.normalize('NFKC', restored)
            if 'casefold' in steps:
                restored = restored.casefold()
            for char in restored:
                if ('spaces' in steps and char.isspace()) or ('vs16' in steps and char in _INVISIBLE):
                    continue
                out.append(char)
                spans.append((f['start'], f['end']))
            i = f['end']
            continue
        j = i + 1
        if 'nfkc' in steps:
            # Keep combining marks (including half-width voiced marks) with their base.
            while j < n and j not in removed and _combining(line[j]):
                j += 1
        cluster = line[i:j]
        if 'nfkc' in steps:
            cluster = unicodedata.normalize('NFKC', cluster)
        if 'casefold' in steps:
            cluster = cluster.casefold()
        for char in cluster:
            if ('spaces' in steps and char.isspace()) or ('vs16' in steps and char in _INVISIBLE):
                continue
            out.append(char)
            spans.append((i, j))
        i = j
    return ''.join(out), spans


def normalize_text(text, normalize=NORMALIZE_STEPS):
    """Apply normalize steps line by line (newlines kept), as search sees the text."""
    steps = _steps(normalize)
    return '\n'.join(_normalized_line(line, steps)[0] for line in text.split('\n'))


def _pattern(pattern, regex, ignore_case, preset=None, steps=()):
    if preset is not None:
        if pattern is not None:
            raise ValueError("give a pattern or a preset, not both")
        if preset not in _PRESETS:
            raise ValueError("unknown preset: " + str(preset))
        pattern, regex = _PRESETS[preset][0], True
    if not isinstance(pattern, str) or not pattern:
        raise ValueError("pattern must be a non-empty string")
    if steps and not regex:
        pattern = normalize_text(pattern, [s for s in steps if s != 'ansi'])
        if not pattern:
            raise ValueError("pattern is empty after normalization")
    return re.compile(pattern if regex else re.escape(pattern),
                      re.IGNORECASE if ignore_case else 0)


def _matches(text, compiled, steps=()):
    for number, line in enumerate(text.splitlines(), 1):
        if not steps:
            for match in compiled.finditer(line):
                yield {"line": number, "column": match.start() + 1,
                       "end_column": match.end() + 1,
                       "match": match.group(), "text": line}
            continue
        view, spans = _normalized_line(line, steps)
        for match in compiled.finditer(view):
            start, end = match.span()
            if end > start:
                left, right = spans[start][0], spans[end - 1][1]
            else:
                left = right = spans[start][0] if start < len(spans) else len(line)
            yield {"line": number, "column": left + 1, "end_column": right + 1,
                   "match": line[left:right], "normalized": match.group(), "text": line}


def search_text(text, pattern=None, *, regex=False, ignore_case=False,
                max_matches=1000, normalize=(), preset=None):
    """Return non-overlapping, line-local matches with 1-based coordinates.

    end_column is exclusive. Literal search is the default. Empty patterns
    are rejected; regex syntax errors propagate as re.error. preset names a
    built-in regex (see pattern_presets) instead of pattern. normalize steps
    (ansi, nfkc, casefold, spaces, vs16, mojibake) search a normalized view of each line
    but report original coordinates and text; "normalized" holds the matched
    view. Literal patterns get the same steps; regexes are written for the view.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    _limit(max_matches, "max_matches")
    steps = _steps(normalize)
    compiled = _pattern(pattern, regex, ignore_case, preset, steps)
    result = []
    for match in _matches(text, compiled, steps):
        result.append(match)
        if len(result) == max_matches:
            break
    return result


def search_files(root, pattern=None, *, regex=False, ignore_case=False,
                 include_hidden=False, max_bytes=1_000_000,
                 max_matches=1000, encoding=None, include=("*",),
                 exclude_dirs=(), normalize=(), preset=None):
    """Search a file or directory, returning matches, skipped files and errors.

    Sorted traversal; symlinks and special files are never deliberately read.
    Binary/NUL, oversized and undecodable files are reported as skipped.
    Read/walk errors are reported, not interpreted as no matches. No gitignore
    interpretation; hidden entries are excluded by default. Root path errors
    raise OSError. Ordinary concurrent filesystem changes are not isolated.
    normalize and preset behave as in search_text. With encoding omitted, the
    mojibake normalization step also auto-detects common text encodings. Other
    searches keep the UTF-8 default. Explicit encoding="auto" returns decoding
    diagnostics; an explicit codec retains strict decoding and skip behavior.
    """
    _limit(max_bytes, "max_bytes")
    _limit(max_matches, "max_matches")
    include, exclude_dirs = _globs(include), _globs(exclude_dirs)
    steps = _steps(normalize)
    compiled = _pattern(pattern, regex, ignore_case, preset, steps)
    encoding = encoding if encoding is not None else ("auto" if "mojibake" in steps else "utf-8")
    # Validate codec even when no files are encountered.
    if encoding != "auto":
        "".encode(encoding)
    root = Path(root)
    mode = root.lstat().st_mode
    if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise ValueError("root must be a regular file or directory, not a symlink")
    report = {"matches": [], "skipped": [], "errors": [], "truncated": False}
    if encoding == "auto":
        report["decodings"] = []

    def label(path):
        return path.relative_to(root).as_posix() if root.is_dir() else path.name

    def candidates():
        if stat.S_ISREG(mode):
            yield root
            return
        def walk_error(error):
            report["errors"].append({"path": str(error.filename),
                                     "reason": type(error).__name__})
        for directory, dirs, files in os.walk(root, followlinks=False,
                                              onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if
                             (include_hidden or not d.startswith(".")) and
                             not (Path(directory) / d).is_symlink() and
                             not any(fnmatch.fnmatchcase(d, g) or
                                     fnmatch.fnmatchcase((Path(directory) / d).relative_to(root).as_posix(), g)
                                     for g in exclude_dirs))
            for filename in sorted(files):
                if include_hidden or not filename.startswith("."):
                    yield Path(directory) / filename

    for path in candidates():
        name = label(path)
        if not any(fnmatch.fnmatchcase(name, g) or fnmatch.fnmatchcase(path.name, g)
                   for g in include):
            continue
        try:
            mode_now = path.lstat().st_mode
            if not stat.S_ISREG(mode_now):
                report["skipped"].append({"path": name, "reason": "non_regular"})
                continue
            with path.open("rb") as stream:
                data = stream.read(max_bytes + 1)
            if len(data) > max_bytes:
                reason = "too_large"
            elif encoding != "auto" and b"\x00" in data:
                reason = "binary"
            else:
                reason = None
            if reason:
                report["skipped"].append({"path": name, "reason": reason})
                continue
            try:
                if encoding == "auto":
                    decoding = decode_text(data)
                    text = decoding.pop("text")
                    report["decodings"].append({"path": name, **decoding})
                else:
                    text = data.decode(encoding)
            except UnicodeError:
                report["skipped"].append({"path": name, "reason": "decode_error"})
                continue
            except ValueError:
                report["skipped"].append({"path": name, "reason": "binary"})
                continue
            for match in _matches(text, compiled, steps):
                # Look one match ahead, so exactly max_matches is not truncated.
                if len(report["matches"]) == max_matches:
                    report["truncated"] = True
                    return report
                report["matches"].append({"path": name, **match})
        except OSError as error:
            report["errors"].append({"path": name, "reason": type(error).__name__})
    return report


def python_symbols(source, *, pattern="*", kinds=()):
    """Find Python definitions by shell-style name pattern, without importing.

    ``source`` is str or Python source bytes (encoding cookies/BOM supported).
    ``pattern`` is a glob or sequence of globs (OR); optional ``kinds`` narrows
    to class/function/async_function. Match short or lexical dotted names on
    every OS. Return classes, functions and async functions sorted by qualified
    name, then line. Nested/conditional definitions are included, but imports,
    inherited/dynamically attached members and lambdas are not. This is source
    discovery, not unittest/pytest collection. SyntaxError is left to the caller;
    parsing follows the running interpreter's grammar and is not a sandbox.
    """
    if not isinstance(source, (str, bytes)):
        raise TypeError("source must be str or bytes")
    patterns = _globs((pattern,) if isinstance(pattern, str) else pattern)
    kinds = _globs(kinds)
    if any(kind not in ("class", "function", "async_function") for kind in kinds):
        raise ValueError("unknown symbol kind")
    definitions = {ast.ClassDef: "class", ast.FunctionDef: "function",
                   ast.AsyncFunctionDef: "async_function"}
    rows = []
    pending = [(ast.parse(source), "")]
    while pending:
        node, scope = pending.pop()
        kind = definitions.get(type(node))
        if kind is not None:
            qualified = scope + node.name
            if (not kinds or kind in kinds) and any(
                    fnmatch.fnmatchcase(node.name, glob) or fnmatch.fnmatchcase(qualified, glob)
                    for glob in patterns):
                rows.append({"name": node.name, "qualname": qualified,
                             "kind": kind, "line": node.lineno})
            scope = qualified + "."
        pending.extend((child, scope) for child in ast.iter_child_nodes(node))
    return sorted(rows, key=lambda row: (row["qualname"], row["line"]))


def boundary_cases(kind="text"):
    """Return fresh named input values; no target function is inferred.

    These are test inputs, not assertions that every target must reject them.
    """
    if kind == "text":
        values = [("empty", ""), ("space", " "), ("newline", "\n"),
                  ("nul", "\x00"), ("unicode", "日本語🙂"),
                  ("long", "x" * 4096)]
    elif kind == "number":
        values = [("negative", -1), ("zero", 0), ("positive", 1),
                  ("large", 2 ** 63), ("none", None), ("wrong_type", "1")]
    else:
        raise ValueError("kind must be text or number")
    return [{"name": name, "value": value} for name, value in values]


def run_cases(function, cases):
    """Call function(value) and check explicit per-case expectations.

    Each case needs name/value and exactly one of expected or raises (an
    Exception subclass). Validate the full case list before any execution.
    Return raw observed values for Python callers. Unexpected Exception is
    recorded; KeyboardInterrupt/SystemExit propagate. No subprocess/shell,
    isolation, timeout or automatic target discovery.
    """
    if not callable(function):
        raise TypeError("function must be callable")
    cases = list(cases)
    names = set()
    for case in cases:
        if not isinstance(case, dict) or not {"name", "value"} <= case.keys():
            raise ValueError("case needs name and value")
        name = case["name"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("case names must be non-empty and unique")
        names.add(name)
        if ("expected" in case) == ("raises" in case):
            raise ValueError("case needs exactly one of expected or raises")
        error_type = case.get("raises")
        if "raises" in case and not (isinstance(error_type, type) and
                                      issubclass(error_type, Exception)):
            raise ValueError("raises must be an Exception subclass")
    results = []
    for case in cases:
        result = {"name": case["name"], "passed": False, "value": None,
                  "error_type": None}
        try:
            value = function(case["value"])
        except Exception as error:
            result["error_type"] = type(error).__name__
            result["passed"] = ("raises" in case and
                                isinstance(error, case["raises"]))
        else:
            result["value"] = value
            if "expected" in case:
                result["passed"] = bool(value == case["expected"])
        results.append(result)
    return {"passed": all(r["passed"] for r in results), "results": results}


# Discovery reports deliberately contain key names and locations, never input
# values or surrounding lines. Generic search above remains a raw grep API.
_HEADER_WORDS = frozenset(('authorization', 'proxy-authorization', 'cookie',
                          'set-cookie', 'content-type', 'x-api-key'))
_KEY_PHRASES = ('secret', 'token', 'password', 'passwd', 'credential', 'api_key',
                'apikey', 'private_key', 'access_key', 'connection_string')
_CONFIG_WORDS = ('host', 'port', 'url', 'endpoint', 'path', 'proxy', 'docker',
                 'goma', 'compiler', 'database', 'debug', 'timeout', 'python',
                 'node', 'flutter', 'dart')
_SCHEMES = ('http', 'https', 'postgres', 'postgresql', 'mysql', 'redis', 'amqp',
            'amqps', 'mongodb', 'sqlite', 'file', 'ftp', 's3')
_ASSIGNMENT = re.compile(r'''(?<![\w-])["']?([A-Za-z_][\w.-]*)["']?\s*[:=]\s*([^\r\n,}]*)''')
_URL = re.compile(r'\b(' + '|'.join(_SCHEMES) + r')://[^\s<>"\']*', re.I)
_DEFAULT_INCLUDE = ('*.py', '*.toml', '*.ini', '*.cfg', '*.conf', '*.json',
                    '*.yaml', '*.yml', '*.env', '.env*', 'Dockerfile*', '*.sh',
                    '*.ps1', '*.txt', '*.md')
_DEFAULT_EXCLUDE = ('.git', '.venv', 'venv', 'node_modules', '__pycache__',
                    'build', 'dist')


def _globs(values):
    if isinstance(values, str):
        raise TypeError('patterns must be a sequence, not a string')
    values = tuple(values)
    if any(not isinstance(v, str) or not v for v in values):
        raise ValueError('patterns must be non-empty strings')
    return values


def discover_files(root=".", *, include=("*",), exclude_dirs=_DEFAULT_EXCLUDE,
                   include_hidden=False, max_files=5000):
    """Discover regular files using caller-supplied filename/path conventions.

    Patterns match basenames OR root-relative POSIX paths, case-sensitively;
    '*' spans '/' (fnmatch rules, not gitignore). Hidden entries are opt-in.
    Sorted traversal, no source imports or file-content reads, no symlink roots
    or deliberately followed symlinks. Filesystem races are not isolated.
    Errors/skips and exact-limit truncation remain visible in the report.
    """
    include, exclude_dirs = _globs(include), _globs(exclude_dirs)
    _limit(max_files, "max_files")
    root = Path(root)
    mode = root.lstat().st_mode
    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        raise ValueError("root must be a regular file or directory")
    directory_root = stat.S_ISDIR(mode)
    report = {"path": str(root), "files": [], "skipped": [], "errors": [], "truncated": False}

    def candidates():
        if not directory_root:
            yield root
            return
        def onerror(error):
            report["errors"].append({"path": str(error.filename), "reason": type(error).__name__})
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
            dirs[:] = sorted(d for d in dirs if (include_hidden or not d.startswith("."))
                             and not (Path(directory) / d).is_symlink()
                             and not any(fnmatch.fnmatchcase(d, g) or fnmatch.fnmatchcase(
                                 (Path(directory) / d).relative_to(root).as_posix(), g) for g in exclude_dirs))
            for name in sorted(files):
                if include_hidden or not name.startswith("."):
                    yield Path(directory) / name

    for path in candidates():
        label = path.relative_to(root).as_posix() if directory_root else path.name
        if not any(fnmatch.fnmatchcase(label, g) or fnmatch.fnmatchcase(path.name, g) for g in include):
            continue
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                report["skipped"].append({"path": label, "reason": "non_regular"})
                continue
        except OSError as error:
            report["errors"].append({"path": label, "reason": type(error).__name__})
            continue
        if len(report["files"]) == max_files:
            report["truncated"] = True
            break
        report["files"].append(label)
    return report


def discover_python(root=".", *, include=("*.py",), patterns=("*",), kinds=(),
                    exclude_dirs=_DEFAULT_EXCLUDE, include_hidden=False,
                    max_files=5000, max_bytes=1_000_000, max_symbols=1000):
    """Find Python definitions across files using injected filename/name rules.

    No test naming convention is built in. Multiple patterns are ORed; kinds
    further narrow matches. Unreadable, oversized and unparsable sources remain
    visible. Byte limits are per file; symbol/file limits cover the whole root.
    """
    _limit(max_bytes, "max_bytes")
    _limit(max_symbols, "max_symbols")
    # Validate filters even for empty roots; retain generator inputs once.
    patterns, kinds = _globs(patterns), _globs(kinds)
    python_symbols("", pattern=patterns, kinds=kinds)
    found = discover_files(root, include=include, exclude_dirs=exclude_dirs,
                           include_hidden=include_hidden, max_files=max_files)
    report = {**found, "symbols": [], "scanned": 0}
    base = Path(root)
    directory_root = base.is_dir()
    for label in found["files"]:
        path = base / label if directory_root else base
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                report["skipped"].append({"path": label, "reason": "non_regular"})
                continue
            with path.open("rb") as stream:
                source = stream.read(max_bytes + 1)
            if len(source) > max_bytes:
                report["skipped"].append({"path": label, "reason": "too_large"})
                continue
            rows = python_symbols(source, pattern=patterns, kinds=kinds)
        except (OSError, SyntaxError, ValueError, UnicodeError, RecursionError) as error:
            report["errors"].append({"path": label, "reason": type(error).__name__})
            continue
        report["scanned"] += 1
        for row in rows:
            if len(report["symbols"]) == max_symbols:
                report["truncated"] = True
                return report
            report["symbols"].append({"path": label, **row})
    return report


def _key_category(key):
    lowered = key.lower().replace('-', '_')
    if key.lower() in _HEADER_WORDS:
        return 'header'
    if any(word in lowered for word in _KEY_PHRASES):
        return 'secret_like'
    if any(word in lowered for word in _CONFIG_WORDS) or key.isupper():
        return 'configuration'
    return None


def inspect_text(text, *, source='<text>', max_findings=1000):
    """Discover dictionary-based config/header/URL evidence without values.

    Heuristic line scanner, not a parser or a complete secret detector. Raw
    values, snippets, credential userinfo and query strings are never returned.
    'secret_like' means a matching key name, not proof of a credential.
    """
    if not isinstance(text, str) or not isinstance(source, str):
        raise TypeError('text and source must be strings')
    _limit(max_findings, 'max_findings')
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        evidence = []
        for match in _ASSIGNMENT.finditer(line):
            key = match.group(1)
            category = _key_category(key)
            if category:
                evidence.append({'column': match.start(1) + 1, 'category': category,
                                 'key': key, 'value': '<redacted>'})
        for match in _URL.finditer(line):
            evidence.append({'column': match.start() + 1, 'category': 'url',
                             'key': match.group(1).lower() + '://',
                             'value': '<redacted>'})
        for item in sorted(evidence, key=lambda v: (v['column'], v['category'])):
            if len(rows) == max_findings:
                return {'findings': rows, 'truncated': True}
            rows.append({'source': source, 'line': number, **item})
    return {'findings': rows, 'truncated': False}


def inspect_environment(environ):
    """Inspect an explicitly supplied mapping; return only recognized names.

    Never reads os.environ itself and never returns environment values. Values
    are used only to report empty/present status. No raw environment dump.
    """
    rows = []
    for key in sorted(environ):
        if not isinstance(key, str) or not isinstance(environ[key], str):
            raise TypeError('environment names and values must be strings')
        category = _key_category(key)
        if category:
            rows.append({'key': key, 'category': category,
                         'present': bool(environ[key]), 'value': '<redacted>'})
    return rows


def scan_config(root, *, include=_DEFAULT_INCLUDE, exclude_dirs=_DEFAULT_EXCLUDE,
                include_hidden=True, max_bytes=1_000_000, max_findings=1000):
    """Search config evidence with glob filters and bounded, redacted results.

    Hidden configuration files such as .env are included, but .git and generated
    trees are excluded. Sorted traversal, UTF-8 decoding, no symlink following;
    skips/errors/truncation stay distinct from absence of evidence.
    """
    _limit(max_findings, 'max_findings')
    # One match per relevant line. The generic search cap bounds the lines kept
    # in memory; inspecting each line can produce multiple redacted findings.
    selector = r'(?i)^.*(?:[A-Za-z_][\w.-]*["\x27]?\s*[:=]|\b(?:' + '|'.join(_SCHEMES) + r')://)'
    raw = search_files(root, selector, regex=True, include_hidden=include_hidden,
                       max_bytes=max_bytes, max_matches=max_findings + 1,
                       include=include, exclude_dirs=exclude_dirs)
    rows, seen = [], set()
    for match in raw['matches']:
        location = (match['path'], match['line'])
        if location in seen:
            continue
        seen.add(location)
        discovered = inspect_text(match['text'], source=match['path'],
                                  max_findings=max_findings + 1)['findings']
        for item in discovered:
            item['line'] = match['line']
            if len(rows) == max_findings:
                return {'findings': rows, 'skipped': raw['skipped'],
                        'errors': raw['errors'], 'truncated': True,
                        'truncation_reason': 'finding_limit'}
            rows.append(item)
    return {'findings': rows, 'skipped': raw['skipped'], 'errors': raw['errors'],
            'truncated': raw['truncated'],
            'truncation_reason': 'candidate_limit' if raw['truncated'] else None}


# Portable, explained regression inputs, not a claim that every consumer must
# reject every value. Actual regressions can be appended with merge_cases().
_BAD_CASES = (
    ('invalid_sha', 'git', 'not-a-sha', 'Non-hex Git identity; validate full SHA before use.'),
    ('short_sha', 'git', 'abc1234', 'Abbreviation is not a full immutable identity.'),
    ('nul_placeholder', 'text', '\x00PH0\x00', 'Raw NUL can forge placeholder tokens.'),
    ('nul_fenced_code', 'markdown', '```\n\x00PH0\x00\n```', 'Fenced code can bypass inline sanitization.'),
    ('crlf', 'text', 'a\r\nb\r\n', 'Check line splitting and round-trip behavior.'),
    ('path_parent', 'path', '../outside', 'Parent traversal crosses a relative root.'),
    ('windows_device', 'path', 'CON.txt', 'Windows device names are not portable output paths.'),
    ('colon_relative', 'url', 'notes:chapter', 'A colon does not alone prove a safe URL scheme.'),
    ('javascript_url', 'url', 'javascript:alert(1)', 'Executable schemes require explicit handling.'),
    ('metadata_prefix', 'text', 'metadata:', 'Ambiguous syntax needs a regression fixture.'),
    ('data_comma', 'url', 'data:,text', 'An empty media type is valid data-URL syntax.'),
    ('escaped_sql_name', 'sql', '"a""b"', 'Quoted identifiers may contain escaped delimiters.'),
    ('null_not_measured', 'json', None, 'Null means not measured; do not conflate with empty or zero.'),
)

# Keep the original ordered sampling population stable as the corpus grows.
_LEGACY_BAD_CASES = _BAD_CASES
_BAD_CASES += (
    ('punycode_homograph', 'url', 'http://xn--pypal-4ve.com', 'Punycode IDN label decodes to mixed-script homoglyph \'pаypal\'.'),
    ('unicode_homograph_url', 'url', 'https://pаypal.com/login', 'Cyrillic \'а\' (U+0430) spoofing Latin \'a\' in URL domain label.'),
    ('whole_script_homograph_url', 'url', 'http://xn--80ak6aa92e.com', 'Punycode label decodes to Cyrillic label spoofing Latin \'apple\' under \'.com\' TLD.'),
    ('confusable_delimiter_url', 'url', 'https://google.com\u2044@evil.com', 'Fraction slash U+2044 spoofing URL path separator.'),
)


def known_bad_cases(category=None):
    """Fresh JSON-compatible inputs with explanation and stable IDs."""
    categories = {row[1] for row in _BAD_CASES}
    if category is not None and category not in categories:
        raise ValueError('unknown corpus category')
    return [{'id': ident, 'category': kind, 'value': value, 'reason': reason}
            for ident, kind, value, reason in _BAD_CASES
            if category is None or kind == category]


def generate_cases(*, seed=0, count=20, category=None):
    """Deterministic seeded samples of the explained corpus, with unique IDs.

    Sampling augments reproducible regression runs; it is not automatic fuzzing
    or target execution. No global random state is changed.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 10000:
        raise ValueError('count must be an integer between 0 and 10000')
    legacy_ids = {row[0] for row in _LEGACY_BAD_CASES}
    pool = [case for case in known_bad_cases(category) if case["id"] in legacy_ids]
    rng = random.Random(seed)
    result = []
    for index in range(count):
        case = dict(rng.choice(pool))
        case['origin_id'] = case['id']
        case['id'] = 'generated-' + str(index) + '-' + case['id']
        result.append(case)
    return result


# Ordered schema v1: bit i represents factor_names[i]. Classification is
# descriptive, not a diagnosis. Only cross-field text/number pairs are eligible.
_TEXT_FACTORS = ('ascii', 'unicode', 'empty', 'whitespace', 'newline', 'nul', 'long')
_NUMBER_FACTORS = ('negative', 'zero', 'positive', 'large', 'missing', 'wrong_type')
_FACTOR_NAMES = _TEXT_FACTORS + _NUMBER_FACTORS


def _text_factors(value):
    names = ['ascii' if value.isascii() else 'unicode']
    if not value:
        names.append('empty')
    if value.isspace():
        names.append('whitespace')
    if '\n' in value or '\r' in value:
        names.append('newline')
    if '\x00' in value:
        names.append('nul')
    if len(value) >= 4096:
        names.append('long')
    return names


def _factor_bits(names):
    return sum(1 << _FACTOR_NAMES.index(name) for name in names)


def case_factor_matrix():
    """Describe the built-in corpus and boundaries as fresh integer bitsets.

    Schema v1 covers text properties and named numeric boundaries only. Missing
    means explicit None, not an absent key. Large means the 2**63 preset; long
    means >=4096 Python characters. No coverage claim about consumer behavior.
    """
    rows = []
    for case in known_bad_cases():
        value = case['value']
        names = ['missing'] if value is None else _text_factors(value)
        rows.append({'id': case['id'], 'bits': _factor_bits(names)})
    for kind in ('text', 'number'):
        for case in boundary_cases(kind):
            names = (_text_factors(case['value']) if kind == 'text' else
                     [{'none': 'missing'}.get(case['name'], case['name'])])
            rows.append({'id': 'boundary-' + kind + '-' + case['name'],
                         'bits': _factor_bits(names)})
    uncovered = []
    for left in _TEXT_FACTORS:
        for right in _NUMBER_FACTORS:
            bits = _factor_bits((left, right))
            if not any(row['bits'] & bits == bits for row in rows):
                uncovered.append({'factors': [left, right], 'bits': bits})
    return {'schema': 'xprobe.factors.v1', 'factor_names': list(_FACTOR_NAMES),
            'rows': rows, 'uncovered_pairs': uncovered}


def _greedy_factor_cases(candidates, pairs, count):
    """Maximum marginal pair gain; stable ID ties, then fill to the budget."""
    remaining = sorted(candidates, key=lambda case: case['id'])
    masks = {case['id']: sum(1 << index for index, pair in enumerate(pairs)
                            if case['factor_bits'] & pair['bits'] == pair['bits'])
             for case in remaining}
    selected, covered = [], 0
    while remaining and len(selected) < count:
        best = max(range(len(remaining)),
                   key=lambda index: bin(masks[remaining[index]['id']] & ~covered).count('1'))
        case = remaining.pop(best)
        selected.append(case)
        covered |= masks[case['id']]
    return selected


def generate_factor_cases(*, seed=0, count=20, selection='seeded'):
    """Return bounded, reproducible composite inputs and selection evidence.

    Enumerate the built-in text/number boundary product, retaining candidates
    that carry an uncovered cross-field factor pair. Seeded selection is without
    replacement by default. Opt-in greedy selection maximizes marginal exact
    pair gain with stable ID ties (seed is validated/recorded but unused).
    Neither method approximates or removes candidates before the count limit.
    value={text, number} is an input template: callers assign its
    fields to their own API (e.g. number to an output limit). No expectations,
    target execution, global RNG changes, I/O or low-rank approximation.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an integer')
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 10000:
        raise ValueError('count must be an integer between 0 and 10000')
    if selection not in ('seeded', 'greedy'):
        raise ValueError('selection must be seeded or greedy')
    matrix = case_factor_matrix()
    pairs = matrix['uncovered_pairs']
    candidates = []
    covered = 0
    for text in boundary_cases('text'):
        for number in boundary_cases('number'):
            names = _text_factors(text['value']) + [
                {'none': 'missing'}.get(number['name'], number['name'])]
            bits = _factor_bits(names)
            if not any(bits & pair['bits'] == pair['bits'] for pair in pairs):
                covered += 1
                continue
            candidates.append({
                'id': 'factor-v1-' + text['name'] + '-' + number['name'],
                'category': 'factor_combination',
                'value': {'text': text['value'], 'number': number['value']},
                'reason': 'Uncovered text/number factor pair; caller defines behavior.',
                'factor_bits': bits,
                'origin_ids': ['boundary-text-' + text['name'],
                               'boundary-number-' + number['name']]})
    if selection == 'seeded':
        random.Random(seed).shuffle(candidates)
        selected = candidates[:count]
    else:
        selected = _greedy_factor_cases(candidates, pairs, count)
    limited = len(candidates) - len(selected)
    report = {'schema': 'xprobe.factor-generation.v1', 'seed': seed,
            'limit': count, 'candidate_total': covered + len(candidates),
            'selected_count': len(selected), 'excluded_count': covered + limited,
            'exclusions': {'already_covered': covered, 'limit': limited},
            'matrix': matrix, 'cases': selected}
    if selection == 'greedy':
        report['selection'] = {'method': 'greedy', 'tie_break': 'stable_id',
                               'approximation_excluded': 0}
    return report


def merge_cases(*corpora):
    """Validate and merge JSON-compatible cases; dedupe equal IDs, reject conflicts.

    Required fields: id/category/value/reason. Pure function; persistence is the
    caller's choice. Never execute a case's values as code or infer expectations.
    """
    result = {}
    for corpus in corpora:
        for case in corpus:
            if not isinstance(case, dict) or not {'id', 'category', 'value', 'reason'} <= case.keys():
                raise ValueError('case needs id, category, value and reason')
            if any(not isinstance(case[k], str) or not case[k] for k in ('id', 'category', 'reason')):
                raise ValueError('id, category and reason must be non-empty strings')
            if any(not isinstance(k, str) for k in case):
                raise ValueError('case keys must be strings')
            try:
                encoded = json.dumps(case, ensure_ascii=True, allow_nan=False, sort_keys=True)
                fresh = json.loads(encoded)
            except (ValueError, TypeError) as error:
                raise ValueError('case must contain finite JSON values') from error
            if fresh != case:
                raise ValueError('case values must round-trip through JSON without changes')
            ident = case['id']
            if ident in result and result[ident] != fresh:
                raise ValueError('conflicting case id: ' + ident)
            result[ident] = fresh
    return [result[ident] for ident in sorted(result)]


def corpus_to_json(cases, *, jsonl=False):
    """Validate and serialize a stable corpus as JSON or one object per line."""
    rows = merge_cases(cases)
    if jsonl:
        return ''.join(json.dumps(row, ensure_ascii=True, sort_keys=True,
                                  allow_nan=False) + '\n' for row in rows)
    return json.dumps(rows, ensure_ascii=True, sort_keys=True, indent=2,
                      allow_nan=False) + '\n'


def corpus_from_json(text, *, jsonl=False):
    """Load and validate a recorded corpus without executing anything."""
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant: ' + value)
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    options = {'parse_constant': invalid_constant, 'object_pairs_hook': unique_object}
    rows = ([json.loads(line, **options) for line in text.splitlines() if line.strip()]
            if jsonl else json.loads(text, **options))
    if not isinstance(rows, list):
        raise ValueError('corpus must be an array or JSONL objects')
    return merge_cases(rows)


def pytest_receipt(cases, *, expected_context=None):
    """Validate one complete xprobe.pytest.v1 run without importing pytest.

    A valid receipt is NOT a passing test run: exit statuses 1..5 are preserved.
    Reject interrupted/truncated runs, duplicate/missing IDs, mixed runs and
    inconsistent counts. No cause/input inference or authenticity guarantee.
    Accept JSONL text or raw case records. Validate each run before merging
    corpora (corpus_from_json/merge_cases deduplicate identical IDs).
    expected_context pins any repository/commit_sha/report_id, including None
    for unmeasured identity. Never infer environment SHA.
    """
    if isinstance(cases, str):
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate JSON key: ' + key)
                result[key] = value
            return result
        original = [json.loads(line, object_pairs_hook=unique_object)
                    for line in cases.splitlines() if line.strip()]
    else:
        original = list(cases)
    rows = merge_cases(original)
    if len(rows) < 2 or len(rows) != len(original):
        raise ValueError('receipt needs unique start and finish records')
    context = rows[0].get('context')
    keys = {'repository', 'commit_sha', 'report_id'}
    if not isinstance(context, dict) or set(context) != keys:
        raise ValueError('invalid pytest context')
    repository, sha, run = (context[k] for k in ('repository', 'commit_sha', 'report_id'))
    if repository is not None and (not isinstance(repository, str) or
            not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)):
        raise ValueError('invalid pytest repository')
    if sha is not None and (repository is None or not isinstance(sha, str) or
            not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha)):
        raise ValueError('invalid pytest commit SHA')
    if not isinstance(run, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', run):
        raise ValueError('invalid pytest report ID')
    if expected_context is not None:
        if not isinstance(expected_context, dict) or not set(expected_context) <= keys:
            raise ValueError('unsupported expected context')
        if any(context[k] != v for k, v in expected_context.items()):
            raise ValueError('pytest context does not match expected identity')
    prefix = (repository or 'unmeasured') + '/' + run + '/'
    for index, row in enumerate(rows):
        if row.get('context') != context or row['id'] != prefix + str(index).zfill(6):
            raise ValueError('mixed run or non-contiguous pytest IDs')
        if not isinstance(row['value'], dict):
            raise ValueError('invalid pytest record value')
    start, finish = rows[0], rows[-1]
    if (start['category'] != 'pytest_session' or start['value'].get('event') != 'start'
            or start['value'].get('schema') != 'xprobe.pytest.v1'):
        raise ValueError('missing supported pytest start')
    if finish['category'] != 'pytest_session' or finish['value'].get('event') != 'finish':
        raise ValueError('missing pytest finish')
    end = finish['value']
    if end.get('complete') is not True or type(end.get('dropped')) is not int or end['dropped'] != 0:
        raise ValueError('incomplete pytest receipt')
    if type(end.get('records_before_finish')) is not int or end['records_before_finish'] != len(rows) - 1:
        raise ValueError('pytest record count mismatch')
    if type(end.get('exitstatus')) is not int or not 0 <= end['exitstatus'] <= 5:
        raise ValueError('invalid pytest exit status')
    counts, phases = {}, {}
    for row in rows[1:-1]:
        value = row['value']
        phase, native = value.get('phase'), value.get('native_outcome')
        xfail, strict = value.get('wasxfail'), value.get('strict_xpass')
        if (row['category'] != 'pytest_observation' or value.get('event') != 'report'
                or phase not in ('setup', 'call', 'teardown', 'collection')
                or native not in ('passed', 'failed', 'skipped')
                or type(xfail) is not bool or type(strict) is not bool
                or not isinstance(value.get('node'), str) or len(value['node']) > 500
                or not isinstance(value.get('node_hash'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', value['node_hash'])):
            raise ValueError('invalid pytest observation')
        if strict:
            if native != 'failed' or xfail or phase != 'call':
                raise ValueError('invalid strict XPASS observation')
            outcome = 'xpass_strict'
        elif xfail:
            outcome = {'skipped': 'xfail', 'passed': 'xpass', 'failed': 'failed'}[native]
        else:
            outcome = 'error' if native == 'failed' and phase != 'call' else native
        if value.get('outcome') != outcome:
            raise ValueError('pytest outcome mismatch')
        counts[outcome] = counts.get(outcome, 0) + 1
        phase_counts = phases.setdefault(phase, {})
        phase_counts[outcome] = phase_counts.get(outcome, 0) + 1
    declared = end.get('phase_outcomes')
    if (not isinstance(declared, dict) or
            any(type(n) is not int or n < 1 for n in declared.values()) or declared != counts):
        raise ValueError('pytest outcome count mismatch')
    return {'context': dict(context), 'exitstatus': end['exitstatus'],
            'observations': len(rows) - 2, 'phase_outcomes': counts, 'phase_counts': phases}


def cases_from_junit(text, *, max_cases=1000, max_bytes=1_000_000,
                     repository=None, commit_sha=None, report_id="junit"):
    """Import pytest-compatible JUnit failure identities, omitting logs and values.

    JUnit normally does not contain reconstructable target inputs. The result
    records failed test identities; attach an explicit input via merge_cases
    rather than inventing one. Parameter labels, messages, traceback and system
    output are omitted. DTD/entity declarations are rejected before XML parsing.
    """
    if not isinstance(text, str):
        raise TypeError('JUnit text must be a string')
    _limit(max_cases, 'max_cases')
    _limit(max_bytes, 'max_bytes')
    if repository is not None and (not isinstance(repository, str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)):
        raise ValueError("repository must be owner/name")
    if commit_sha is not None and (not isinstance(commit_sha, str) or
            not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit_sha)):
        raise ValueError("commit_sha must be a full SHA supplied by the canonical producer")
    if commit_sha is not None and repository is None:
        raise ValueError("commit_sha requires repository")
    if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", report_id):
        raise ValueError("report_id must be a non-empty portable identifier")
    context = {"repository": repository,
               "commit_sha": commit_sha.lower() if commit_sha is not None else None,
               "report_id": report_id}
    prefix = (repository + "@" + (context["commit_sha"] or "unmeasured") + "/"
              if repository is not None else "") + report_id
    if len(text.encode('utf-8')) > max_bytes:
        raise ValueError('JUnit exceeds byte limit')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', text, re.I):
        raise ValueError('DTD and entity declarations are unsupported')
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("invalid JUnit XML") from error
    if root.tag not in ('testsuite', 'testsuites'):
        raise ValueError('expected testsuite or testsuites')
    rows = []
    for testcase in root.iter('testcase'):
        kinds = [child.tag for child in testcase if child.tag in ('failure', 'error')]
        if not kinds:
            continue
        if len(rows) == max_cases:
            return {'cases': rows, 'truncated': True}
        name = testcase.get('name', '').split('[', 1)[0]
        classname = testcase.get('classname', '').split('[', 1)[0]
        rows.append({'id': prefix + '-' + str(len(rows)), 'category': 'test_failure',
                     'context': dict(context),
                     'value': {'test': name, 'class': classname, 'kind': kinds[0]},
                     'reason': 'JUnit recorded a failure; attach the original input to reproduce it.'})
    return {'cases': rows, 'truncated': False}


# --- structured config loading (TOML / YAML) -------------------------------
# tomllib when the interpreter has it (3.11+); otherwise, and always for YAML,
# Node 24+ with smol-toml / js-yaml resolved through NODE_PATH or the current
# directory. A sibling ``vendor/node_launch.py`` is used when that file is
# present; a copied ``xprobe.py`` falls back to the stdlib launcher below.
# Text goes through stdin; the script is fixed; no input is evaluated.
_NODE_LOADER = r"""
const kind = process.argv[1];
let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (c) => (text += c)).on('end', () => {
  try {
    let value;
    if (kind === 'toml') {
      const toml = require('smol-toml');
      value = toml.parse(text, {integersAsBigInt: 'asNeeded'});
    } else {
      const yaml = require('js-yaml');
      const schema = kind === 'yaml-core' ? yaml.CORE_SCHEMA : yaml.FAILSAFE_SCHEMA;
      value = yaml.load(text, {schema});
    }
    const tag = (v) => {
      if (typeof v === 'bigint') return {'\u0000toml-int': v.toString()};
      if (v && typeof v.toISOString === 'function') {
        return {'\u0000toml-datetime': v.toISOString(), date: !!v.isDate && v.isDate(),
          time: !!v.isTime && v.isTime(), local: !!v.isLocal && v.isLocal()};
      }
      if (Array.isArray(v)) return v.map(tag);
      if (v && typeof v === 'object') {
        const entries = Object.entries(v).map(([k, x]) => [k, tag(x)]);
        // Quoted TOML keys can contain NUL: escape tables that resemble wire tags.
        return ['\u0000toml-int', '\u0000toml-datetime', '\u0000toml-table'].some(k => Object.hasOwn(v, k))
          ? {'\u0000toml-table': entries} : Object.fromEntries(entries);
      }
      return v;
    };
    process.stdout.write(JSON.stringify(kind === 'toml' ? tag(value) : (value === undefined ? null : value)));
  } catch (error) {
    process.stderr.write((error && error.code === 'MODULE_NOT_FOUND' ? 'missing:' : 'parse:') + String(error && error.message || error));
    process.exit(3);
  }
});
"""


def _from_node_toml(value):
    import datetime
    if isinstance(value, dict):
        if "\u0000toml-int" in value:
            return int(value["\u0000toml-int"])
        if "\u0000toml-table" in value:
            return {k: _from_node_toml(v) for k, v in value["\u0000toml-table"]}
        if "\u0000toml-datetime" in value:
            text = value["\u0000toml-datetime"]
            if value.get("date"):
                return datetime.date.fromisoformat(text[:10])
            if value.get("time"):
                return datetime.time.fromisoformat(text.split("T")[-1].rstrip("Z"))
            stamp = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            return stamp.replace(tzinfo=None) if value.get("local") else stamp
        return {k: _from_node_toml(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_node_toml(v) for v in value]
    return value


_NODE_LAUNCH = None
_MIN_NODE_MAJOR = 24


def _sibling_node_launch_path():
    return Path(__file__).resolve().parent / "vendor" / "node_launch.py"


def _node_launch_module():
    """Vendored launcher when it sits beside this file; otherwise stdlib.

    Import and non-Node commands never call this. Only TOML-without-tomllib
    and YAML need a launcher, and only those fail when Node itself is missing.
    """
    global _NODE_LAUNCH
    if _NODE_LAUNCH is None:
        path = _sibling_node_launch_path()
        if path.is_file():
            spec = importlib.util.spec_from_file_location("_vendored_node_launch", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _NODE_LAUNCH = module
        else:
            _NODE_LAUNCH = _stdlib_node_launch()
    return _NODE_LAUNCH


def _stdlib_node_launch():
    """Minimal Node 24+ spawn used when ``vendor/node_launch.py`` is absent.

    Resolves like the vendored helper with ``env_var=None`` (PATH via
    ``shutil.which``, not the ``NODE`` environment variable). Version misses
    and launch failures use the same ``NodeNotFoundError`` / ``LaunchError``
    shape ``_node_backend_error`` and ``_map_node_launch_error`` already map.
    """
    import shutil
    import subprocess
    import threading
    import types

    class NodeNotFoundError(FileNotFoundError):
        pass

    class LaunchError(RuntimeError):
        def __init__(self, message, *, code="ELAUNCHFAILURE", status=None, stdout=b"", stderr=b""):
            super().__init__(message)
            self.code = code
            self.status = status
            self.stdout = stdout
            self.stderr = stderr

    version_re = re.compile(r"(?:^|\s)v?(?P<major>\d+)(?:\.\d+)*", re.IGNORECASE)
    probed = {}

    def clear_probe_cache():
        probed.clear()

    def _reject_batch(path):
        lowered = path.lower()
        if lowered.endswith(".cmd") or lowered.endswith(".bat"):
            raise NodeNotFoundError(
                "node_launch: node batch wrappers (.cmd/.bat) are not supported: " + path
            )

    def _probe(path, probe_timeout):
        cached = probed.get(path)
        if cached is not None:
            return cached
        _reject_batch(path)
        try:
            completed = subprocess.run(
                (path, "--version"),
                capture_output=True,
                timeout=probe_timeout,
                shell=False,
                check=False,
            )
        except FileNotFoundError as exc:
            raise NodeNotFoundError("node_launch: node executable not found: " + path) from exc
        except subprocess.TimeoutExpired as exc:
            raise NodeNotFoundError("node_launch: node version probe timed out: " + path) from exc
        except OSError as exc:
            raise NodeNotFoundError("node_launch: node version probe failed: " + path) from exc
        output = _decode_node_process_bytes(completed.stdout) + _decode_node_process_bytes(completed.stderr)
        match = version_re.search(output)
        if completed.returncode != 0 or match is None:
            raise NodeNotFoundError("node_launch: node version probe failed: " + path)
        major = int(match.group("major"))
        if major < _MIN_NODE_MAJOR:
            raise NodeNotFoundError(
                f"node_launch: node version must be {_MIN_NODE_MAJOR} or newer (found {major}): " + path
            )
        probed[path] = path
        return path

    def resolve_node(node=None, *, env_var=None, probe=True, probe_timeout=5.0):
        if node is None and env_var and env_var in os.environ:
            node = os.environ[env_var]
        if node is not None:
            path = os.fspath(node)
            _reject_batch(path)
            return _probe(path, probe_timeout) if probe else path
        discovered = shutil.which("node")
        if not discovered:
            raise NodeNotFoundError("node_launch: node executable not found")
        _reject_batch(discovered)
        return _probe(discovered, probe_timeout) if probe else discovered

    def node_command(target, *args, node=None, env_var=None, probe=True, probe_timeout=5.0, **_ignored):
        executable = resolve_node(node=node, env_var=env_var, probe=probe, probe_timeout=probe_timeout)
        return [executable, os.fspath(target), *[os.fspath(value) for value in args]]

    def run(target, *args, timeout=30, node=None, probe=False, env_var=None, input=None, check=False, **_ignored):
        command = node_command(target, *args, node=node, env_var=env_var, probe=probe)
        if input is None:
            payload = None
        elif isinstance(input, str):
            payload = input.encode("utf-8")
        else:
            payload = input
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError as exc:
            raise LaunchError(f"node_launch: Node process failed: {exc}", code="ELAUNCHFAILURE") from exc

        stdout_chunks = []
        stderr_chunks = []
        stdin_closed = []
        stdin_error = []

        def read_stream(stream, sink):
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    sink.append(chunk)
            finally:
                stream.close()

        def write_stdin():
            stream = proc.stdin
            if stream is None:
                return
            try:
                if payload:
                    offset = 0
                    while offset < len(payload):
                        stream.write(payload[offset:offset + 65536])
                        offset += 65536
                    stream.flush()
                stream.close()
            except BrokenPipeError:
                stdin_closed.append(True)
                try:
                    stream.close()
                except OSError:
                    pass
            except OSError as exc:
                stdin_error.append(exc)
                try:
                    stream.close()
                except OSError:
                    pass

        threads = [
            threading.Thread(target=read_stream, args=(proc.stdout, stdout_chunks), daemon=True),
            threading.Thread(target=read_stream, args=(proc.stderr, stderr_chunks), daemon=True),
            threading.Thread(target=write_stdin, daemon=True),
        ]
        for thread in threads:
            thread.start()
        timed_out = False
        returncode = None
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            returncode = proc.returncode if proc.returncode is not None else -1
        finally:
            for thread in threads:
                thread.join()
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
        if returncode is None:
            returncode = -1
        if stdin_error:
            raise LaunchError(
                f"node_launch: Node process failed: {stdin_error[0]}",
                code="ELAUNCHFAILURE",
                stdout=stdout,
                stderr=stderr,
            ) from stdin_error[0]
        if timed_out:
            raise LaunchError(
                "node_launch: Node process timed out",
                code="ELAUNCHFAILURE",
                stdout=stdout,
                stderr=stderr,
            )
        if stdin_closed:
            raise LaunchError(
                "node_launch: Node stdin pipe closed unexpectedly",
                code="ELAUNCHSTDINCLOSED",
                status=returncode,
                stdout=stdout,
                stderr=stderr,
            )
        if check and returncode:
            message = _decode_node_process_bytes(stderr).strip() or "Node script failed"
            raise LaunchError(message, code="ELAUNCHFAILURE", status=returncode, stdout=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    return types.SimpleNamespace(
        NodeNotFoundError=NodeNotFoundError,
        LaunchError=LaunchError,
        resolve_node=resolve_node,
        node_command=node_command,
        run=run,
        clear_probe_cache=clear_probe_cache,
        subprocess=subprocess,
        MIN_NODE_MAJOR=_MIN_NODE_MAJOR,
    )


def _decode_node_process_bytes(data):
    if isinstance(data, str):
        return data
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def _node_backend_error(exc, package, node):
    """Map vendored ``NodeNotFoundError`` to legacy ``load_*`` exception types."""
    message = str(exc)
    if node is not None and "node executable not found: " in message:
        path = os.fspath(node)
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path) from exc
    version = re.search(r"must be 24 or newer \(found (\d+)\)", message)
    if version is not None:
        raise RuntimeError(
            f"needs Node 24+ with {package} (npm i --no-save {package}); "
            f"found Node {version.group(1)}"
        ) from exc
    raise RuntimeError(
        f"needs Node 24+ with {package} (npm i --no-save {package}); node not found"
    ) from exc


def _map_node_launch_error(exc, command, timeout):
    """Map vendored ``LaunchError`` to legacy ``load_*`` subprocess shapes."""
    import subprocess

    if exc.code == "ELAUNCHSTDINCLOSED":
        status = exc.status if exc.status is not None else -1
        return subprocess.CompletedProcess(command, status, exc.stdout, exc.stderr)
    if exc.code == "ELAUNCHFAILURE" and "timed out" in str(exc):
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=timeout,
            output=exc.stdout,
            stderr=exc.stderr,
        ) from exc
    raise exc


def _xprobe_node_run(target, *args, timeout=30, **kwargs):
    node_launch = _node_launch_module()
    run_kwargs = dict(kwargs)
    node = run_kwargs.pop("node", None)
    env_var = run_kwargs.pop("env_var", None)
    run_kwargs.pop("probe", None)
    executable = node_launch.resolve_node(node=node, env_var=env_var)
    command = node_launch.node_command(
        target, *args, node=executable, probe=False, env_var=env_var
    )
    try:
        return node_launch.run(
            target,
            *args,
            timeout=timeout,
            node=executable,
            probe=False,
            env_var=env_var,
            **run_kwargs,
        )
    except node_launch.LaunchError as exc:
        return _map_node_launch_error(exc, command, timeout)


def _node_load(kind, text, node, timeout):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    package = "smol-toml" if kind == "toml" else "js-yaml"
    node_launch = _node_launch_module()
    try:
        done = _xprobe_node_run(
            "-e", _NODE_LOADER, kind, input=text, node=node, timeout=timeout, check=False
        )
    except node_launch.NodeNotFoundError as exc:
        _node_backend_error(exc, package, node)
    if done.returncode:
        reason = _decode_node_process_bytes(done.stderr).strip()
        if reason.startswith("missing:"):
            raise RuntimeError(
                f"needs Node 24+ with {package} (npm i --no-save {package}): {reason[8:][:200]}"
            )
        raise ValueError(
            f"invalid {kind.split('-')[0].upper()}: {reason.removeprefix('parse:')[:300]}"
        )
    return json.loads(_decode_node_process_bytes(done.stdout))


def load_toml(text, *, node=None, timeout=30):
    """Parse TOML: ``tomllib`` on Python 3.11+, else Node 24+ + ``smol-toml``.

    Integers are lossless, including signed 64-bit values. Dates and times
    come back as ``datetime`` objects either way. Raises
    ValueError for invalid TOML and RuntimeError when no backend is available.
    """
    try:  # stdlib on 3.11+; imported by name so older interpreters do not see a non-stdlib import
        tomllib = importlib.import_module("tomllib")
    except ModuleNotFoundError:
        tomllib = None
    if tomllib is not None and node is None:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"invalid TOML: {error}") from error
    return _from_node_toml(_node_load("toml", text, node, timeout))


def load_yaml(text, *, schema="failsafe", node=None, timeout=30):
    """Parse YAML with Node 24+ + ``js-yaml`` (no PyYAML needed).

    ``schema="failsafe"`` returns only strings, lists and dicts, like PyYAML's
    ``BaseLoader`` (keys such as ``on`` stay ``"on"``); ``schema="core"`` types
    scalars by YAML 1.2 (``yes``/``no`` stay strings, unlike PyYAML's YAML 1.1
    ``safe_load``; timestamps stay strings). Multi-document input is rejected.
    """
    if schema not in ("failsafe", "core"):
        raise ValueError("schema must be 'failsafe' or 'core'")
    if isinstance(text, str) and not text.strip():
        return None  # an empty document, as PyYAML returns
    return _node_load("yaml-" + schema, text, node, timeout)


def _flatten(value, prefix=''):
    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            out.update(_flatten(inner, prefix + str(key) + '.'))
        return out
    if isinstance(value, list):
        value = json.dumps(value, sort_keys=True)
    return {prefix[:-1]: value}


def _predicates(rows, skip, max_thresholds, max_values):
    preds = {}
    for name in sorted({key for row in rows for key in row} - set(skip)):
        values = [row.get(name) for row in rows]
        seen = [v for v in values if v is not None]
        numbers = [v for v in seen if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if seen and len(numbers) == len(seen):
            distinct = sorted(set(numbers))
            mids = [(a + b) / 2 for a, b in zip(distinct, distinct[1:])]
            if len(mids) > max_thresholds:
                step = (len(mids) - 1) / max(max_thresholds - 1, 1)
                mids = sorted({mids[round(i * step)] for i in range(max_thresholds)})
            for t in mids:
                t = round(t, 6)
                preds[f'{name} <= {t:g}'] = sum(1 << i for i, v in enumerate(values) if v is not None and v <= t)
                preds[f'{name} > {t:g}'] = sum(1 << i for i, v in enumerate(values) if v is not None and v > t)
            continue
        distinct = sorted({json.dumps(v, sort_keys=True) for v in seen})
        if len(distinct) <= max_values:
            for text in distinct:
                preds[f'{name} == {text}'] = sum(
                    1 << i for i, v in enumerate(values)
                    if v is not None and json.dumps(v, sort_keys=True) == text)
    return preds


def explain_outcome(records, target, *, skip=(), id_field=None, top=5,
                    max_thresholds=12, max_values=8, max_ids=20):
    """Rank simple conditions on record fields that separate a yes/no outcome.

    records: dicts (nested dicts flatten to dotted names). target: (field, value)
    for equality, or a callable record -> bool (then list its fields in skip).
    Predicates: ``field == value`` for non-numeric fields with <= max_values
    distinct values, ``field <= t`` / ``field > t`` at midpoints of observed
    numbers; a missing field never matches. Searched: single predicates and
    ``[A] and [B]`` / ``[A] or [B]``, as integer bitsets. Ranked by MCC, then
    fewer predicates, then text; formulas selecting the same rows appear once.
    Each result lists up to max_ids counterexample ids (fp: predicted yes, was
    no; fn: missed), with *_ids_total, *_ids_omitted and *_ids_truncated.
    This describes the given sample only; no validation, no low-rank factors.
    """
    for name, value in (('top', top), ('max_thresholds', max_thresholds),
                        ('max_values', max_values), ('max_ids', max_ids)):
        _limit(value, name)
    if not isinstance(records, (list, tuple)) or not all(isinstance(r, dict) for r in records):
        raise ValueError('records must be a list of dicts')
    rows = [_flatten(record) for record in records]
    skip = set(skip) | ({id_field} if id_field else set())
    if callable(target):
        hits = [bool(target(row)) for row in rows]
    elif isinstance(target, tuple) and len(target) == 2 and isinstance(target[0], str):
        field, expected = target
        if not any(field in row for row in rows):
            raise LookupError('no record has field ' + field)
        hits = [row.get(field) == expected for row in rows]
        skip.add(field)
    else:
        raise ValueError('target must be (field, value) or a callable')
    n = len(rows)
    full = (1 << n) - 1
    want = sum(1 << i for i, hit in enumerate(hits) if hit)
    preds = _predicates(rows, skip, max_thresholds, max_values)
    best = {}

    def offer(mask, size, expr):
        if mask not in (0, full) and (mask not in best or (size, expr) < best[mask]):
            best[mask] = (size, expr)

    for expr, mask in preds.items():
        offer(mask, 1, expr)
    items = sorted(preds.items())
    for i, (left, lmask) in enumerate(items):
        for right, rmask in items[i + 1:]:
            offer(lmask & rmask, 2, f'[{left}] and [{right}]')
            offer(lmask | rmask, 2, f'[{left}] or [{right}]')
    labels = [str(row.get(id_field, i)) if id_field else str(i) for i, row in enumerate(rows)]
    scored = []
    # int.bit_count was added in 3.10; retain the same bitset counts on 3.9.
    bit_count = getattr(int, 'bit_count', lambda value: bin(value).count('1'))
    for mask, (size, expr) in best.items():
        tp, fp = bit_count(mask & want), bit_count(mask & ~want)
        fn = bit_count(want & ~mask)
        tn = n - tp - fp - fn
        denom = ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
        score = (tp * tn - fp * fn) / denom if denom else 0.0
        scored.append((-score, size, expr, mask, tp, fp, fn))
    scored.sort(key=lambda item: item[:3])
    results = []
    for neg, size, expr, mask, tp, fp, fn in scored[:top]:
        fp_ids = [labels[i] for i in range(n) if mask >> i & 1 and not want >> i & 1]
        fn_ids = [labels[i] for i in range(n) if want >> i & 1 and not mask >> i & 1]
        results.append({'expr': expr, 'predicates': size, 'mcc': round(-neg, 6),
                        'tp': tp, 'fp': fp, 'fn': fn,
                        'fp_ids': fp_ids[:max_ids], 'fn_ids': fn_ids[:max_ids],
                        'fp_ids_total': fp, 'fn_ids_total': fn,
                        'fp_ids_omitted': max(0, fp - max_ids),
                        'fn_ids_omitted': max(0, fn - max_ids),
                        'fp_ids_truncated': fp > max_ids,
                        'fn_ids_truncated': fn > max_ids})
    return {'schema': 'xprobe.explain.v1', 'rows': n, 'target_rows': bit_count(want),
            'predicate_count': len(preds), 'candidate_count': len(best),
            'scope': 'in-sample description; apply to new records before trusting',
            'results': results}


def _explain_cli(args, parser):
    import sys
    if (args.target is None) == (args.target_differs is None):
        parser.error("--explain needs exactly one of --target / --target-differs")
    text = sys.stdin.read() if args.explain == '-' else Path(args.explain).read_text(encoding='utf-8')
    text = text.strip()
    try:
        data = json.loads(text)
        records = data if isinstance(data, list) else [data]
    except ValueError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if args.target is not None:
        field, sep, literal = args.target.partition('=')
        if not sep:
            raise ValueError('--target must be FIELD=VALUE')
        target, skip = (field, json.loads(literal)), args.skip
    else:
        left, sep, right = args.target_differs.partition(',')
        if not sep:
            raise ValueError('--target-differs must be A,B')
        target = lambda row: row.get(left) != row.get(right)
        skip = args.skip + [left, right]
    report = explain_outcome(records, target, skip=skip, id_field=args.id_field, top=args.top)
    print(f"rows={report['rows']} target_rows={report['target_rows']} predicates={report['predicate_count']} ({report['scope']})")
    def format_ids(row, kind):
        shown = ','.join(row[kind + '_ids']) or '-'
        omitted = row[kind + '_ids_omitted']
        return shown + (f" (+{omitted} more)" if omitted else '')

    for rank, row in enumerate(report['results'], 1):
        print(f"{rank}. mcc={row['mcc']:.4f} tp={row['tp']} fp={row['fp']} fn={row['fn']}  {row['expr']}")
        if row['fp'] or row['fn']:
            print(f"   fp: {format_ids(row, 'fp')}  fn: {format_ids(row, 'fn')}")
    return 0 if report['results'] else 1



# --- CI helpers: JUnit annotations and portability -----------------------------
def _workflow_escape(text, *, prop=False):
    text = str(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return text.replace(":", "%3A").replace(",", "%2C") if prop else text


def junit_annotations(text, *, max_annotations=50, max_message=300, level="error"):
    """GitHub workflow-command lines (``::error file=…,line=…,title=…::message``) per failed testcase.

    CI logs and artifacts are often unreadable for an agent, while check-run
    annotations are; printing these from a step makes failing test names and
    first message lines visible there. Unlike cases_from_junit this keeps the
    first line of the failure message (it is already in the job log). File and
    line come from the ``file``/``line`` attributes when present (pytest
    ``junit_family=xunit1``), otherwise from ``classname`` (``tests.test_x`` ->
    ``tests/test_x.py``). DTD/entity declarations are rejected.
    """
    if not isinstance(text, str):
        raise TypeError("JUnit text must be a string")
    _limit(max_annotations, "max_annotations")
    _limit(max_message, "max_message")
    if level not in ("error", "warning", "notice"):
        raise ValueError("level must be error, warning or notice")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("DTD and entity declarations are unsupported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("invalid JUnit XML") from error
    lines, failed = [], 0
    for case in root.iter("testcase"):
        bad = next((child for child in case if child.tag in ("failure", "error")), None)
        if bad is None:
            continue
        failed += 1
        if len(lines) == max_annotations:
            continue
        classname, name = case.get("classname", ""), case.get("name", "")
        module = classname
        head, _, last = classname.rpartition(".")
        if head and last[:1].isupper():  # pytest: "pkg.test_mod.TestClass" for methods, "pkg.test_mod" for functions
            module = head
        path = case.get("file") or (module.replace(".", "/") + ".py" if module else "")
        message = (bad.get("message") or (bad.text or "")).strip().splitlines()
        first = message[0][:max_message] if message else bad.tag
        props = [f"file={_workflow_escape(path, prop=True)}"] if path else []
        if case.get("line", "").isdigit():
            props.append(f"line={int(case.get('line')) + 1}")
        props.append("title=" + _workflow_escape(f"{classname}::{name}" if classname else name, prop=True))
        lines.append(f"::{level} {','.join(props)}::{_workflow_escape(first)}")
    if failed > len(lines):
        lines.append(f"::{level} title=junit::{failed - len(lines)} more failing testcase(s) not annotated")
    return lines


# Modules a "min_python" interpreter lacks, and modules removed from newer ones (3.12 / 3.13).
_ADDED_IN = {"tomllib": (3, 11), "wsgiref.types": (3, 11), "zoneinfo": (3, 9), "graphlib": (3, 9)}
_REMOVED_IN = {**{m: (3, 12) for m in ("distutils", "imp", "asynchat", "asyncore", "smtpd")},
               **{m: (3, 13) for m in ("aifc", "audioop", "cgi", "cgitb", "chunk", "crypt", "imghdr", "lib2to3",
                                       "mailcap", "msilib", "nis", "nntplib", "ossaudiodev", "pipes", "sndhdr",
                                       "spwd", "sunau", "telnetlib", "uu", "xdrlib")}}
_PORTABILITY_ERRORS = ("too_new", "removed", "unparsable")
_PORTABILITY_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".tox"}


def _guarded_imports(tree):
    """Import nodes the code guards: inside ``try`` blocks whose handlers catch ImportError
    (or broader), or under ``if sys.version_info ...`` checks."""
    guarded = set()
    for node in ast.walk(tree):
        bodies = []
        if isinstance(node, ast.Try):
            names = set()
            for handler in node.handlers:
                kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
                names |= {getattr(k, "id", getattr(k, "attr", None)) for k in kinds if k is not None}
                if handler.type is None:
                    names.add("ImportError")
            if names & {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}:
                bodies = node.body
        elif isinstance(node, ast.If) and any(isinstance(n, ast.Attribute) and n.attr == "version_info"
                                              for n in ast.walk(node.test)):
            bodies = node.body + node.orelse
        for child in bodies:
            guarded |= {id(n) for n in ast.walk(child)}
    return guarded


_SUBPROCESS_TEXT = {"run", "check_output", "Popen", "call", "check_call"}


def _locale_io(node):
    """Why a call decodes or encodes text with the locale encoding (cp1252 on Windows), or None."""
    if not isinstance(node, ast.Call) or any(k.arg == "encoding" for k in node.keywords):
        return None
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
    owner = getattr(func.value, "id", None) if isinstance(func, ast.Attribute) else None
    if name == "read_text" and isinstance(func, ast.Attribute) and not node.args:
        return "read_text() without encoding="
    if name == "write_text" and isinstance(func, ast.Attribute) and len(node.args) < 2:
        return "write_text() without encoding="
    builtin = isinstance(func, ast.Name)
    if name == "open" and (builtin or owner == "io") and len(node.args) < 4:
        mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
        if mode is None or (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value):
            return "open() in text mode without encoding="
    if name in _SUBPROCESS_TEXT and (builtin or owner == "subprocess"):
        if any(k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value
               for k in node.keywords):
            return f"{name}(text=True) without encoding="
    return None


def portability_findings(root=".", *, min_python=None, max_python=(3, 14), locale_io=False,
                         undecodable=False, encoding="cp1252", max_files=5000):
    """Python sources that break on an older/newer interpreter or a non-UTF-8 Windows locale.

    Reports, per file and line (static, via ast; nothing is imported or executed):

    * ``too_new``: imports of stdlib modules newer than ``min_python`` (tomllib on 3.10);
    * ``removed``: imports of modules removed by ``max_python`` (distutils, cgi, ...);
    * ``unparsable``: files that are not UTF-8 Python;
    * ``locale_io`` (opt-in, a lint: only non-ASCII data breaks): ``read_text()``,
      ``write_text()``, text ``open()`` and ``subprocess`` ``text=True`` without
      ``encoding=``, which use cp1252 on Windows runners;
    * ``undecodable`` (opt-in): bytes ``encoding`` cannot decode, which break when
      such a call reads the file.

    Imports inside ``try``/``except ImportError`` or ``if sys.version_info`` are guarded
    and not reported. ``min_python=None`` takes ``requires-python = ">=X.Y"`` from
    ``root``'s pyproject.toml, else 3.10.
    """
    source = "argument"
    if min_python is None:
        min_python, source = (3, 10), "default"
        project = Path(root) / "pyproject.toml"
        if project.is_file():
            found = re.search(r'(?m)^\s*requires-python\s*=\s*["\']\s*>=\s*(\d+)\.(\d+)',
                              project.read_text(encoding="utf-8", errors="replace"))
            if found:
                min_python, source = (int(found.group(1)), int(found.group(2))), "pyproject.toml"
    for name, value in (("min_python", min_python), ("max_python", max_python)):
        if not (isinstance(value, tuple) and len(value) == 2 and all(type(v) is int for v in value)):
            raise ValueError(name + " must be a (major, minor) tuple")
    _limit(max_files, "max_files")
    findings, scanned, truncated = [], 0, False
    base = Path(root)
    paths = [base] if base.is_file() else sorted(
        p for p in base.rglob("*.py") if not any(part in _PORTABILITY_SKIP for part in p.relative_to(base).parts))
    for path in paths:
        if scanned == max_files:
            truncated = True
            break
        scanned += 1
        label = path.name if base.is_file() else path.relative_to(base).as_posix()
        data = path.read_bytes()
        if undecodable:
            for number, line in enumerate(data.splitlines(), 1):
                try:
                    line.decode(encoding)
                except UnicodeDecodeError as error:
                    findings.append({"path": label, "line": number, "kind": "undecodable",
                                     "detail": f"byte 0x{line[error.start]:02x} is not {encoding}"})
        try:
            tree = ast.parse(data.decode("utf-8"), filename=label)
        except (SyntaxError, UnicodeDecodeError) as error:
            findings.append({"path": label, "line": getattr(error, "lineno", None) or 1, "kind": "unparsable",
                             "detail": type(error).__name__})
            continue
        guarded = _guarded_imports(tree)
        for node in ast.walk(tree):
            if locale_io and (why := _locale_io(node)):
                findings.append({"path": label, "line": node.lineno, "kind": "locale_io", "detail": why})
                continue
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            else:
                continue
            if id(node) in guarded:
                continue
            top = modules[0].split(".")[0]
            removed = _REMOVED_IN.get(top)
            if removed and removed <= max_python:
                findings.append({"path": label, "line": node.lineno, "kind": "removed",
                                 "detail": f"{top} was removed in {removed[0]}.{removed[1]}"})
            for module in modules:
                added = _ADDED_IN.get(module)
                if added and added > min_python:
                    findings.append({"path": label, "line": node.lineno, "kind": "too_new",
                                     "detail": f"{module} is stdlib from {added[0]}.{added[1]}; "
                                               f"min_python is {min_python[0]}.{min_python[1]}"})
    findings.sort(key=lambda f: (f["path"], f["line"]))
    return {"schema": "xprobe.portability.v1", "min_python": list(min_python),
            "min_python_source": source, "max_python": list(max_python),
            "encoding": encoding, "files": scanned, "truncated": truncated, "findings": findings}



# --- emoji: sequences, inventory and reverse lookup (stdlib only) --------------
# Extended_Pictographic (UTS #51 / emoji-data.txt), the code points an emoji
# sequence may start from. The property includes reserved blocks, so the table
# stays valid as new emoji are assigned; tests compare it with Node's
# \p{Extended_Pictographic} for every code point.
_EXT_PICT_UNICODE = "16.0"  # Unicode 17 narrowed the property; this wider table is a superset of it
_EXT_PICT = ("a9 ae 203c 2049 2122 2139 2194-2199 21a9-21aa 231a-231b 2328 2388 23cf 23e9-23f3 "
             "23f8-23fa 24c2 25aa-25ab 25b6 25c0 25fb-25fe 2600-2605 2607-2612 2614-2685 2690-2705 "
             "2708-2712 2714 2716 271d 2721 2728 2733-2734 2744 2747 274c 274e 2753-2755 2757 "
             "2763-2767 2795-2797 27a1 27b0 27bf 2934-2935 2b05-2b07 2b1b-2b1c 2b50 2b55 3030 303d "
             "3297 3299 1f000-1f0ff 1f10d-1f10f 1f12f 1f16c-1f171 1f17e-1f17f 1f18e 1f191-1f19a "
             "1f1ad-1f1e5 1f201-1f20f 1f21a 1f22f 1f232-1f23a 1f23c-1f23f 1f249-1f3fa 1f400-1f53d "
             "1f546-1f64f 1f680-1f6ff 1f774-1f77f 1f7d5-1f7ff 1f80c-1f80f 1f848-1f84f 1f85a-1f85f "
             "1f888-1f88f 1f8ae-1f8ff 1f90c-1f93a 1f93c-1f945 1f947-1faff 1fc00-1fffd")


def _emoji_class():
    parts = []
    for item in _EXT_PICT.split():
        lo, _, hi = item.partition("-")
        parts.append("\\U%08x" % int(lo, 16) + ("-\\U%08x" % int(hi, 16) if hi else ""))
    return "[" + "".join(parts) + "]"


_PICT = _emoji_class()
_EMOJI_MOD = "[\\U0001F3FB-\\U0001F3FF]"
_EMOJI_ELEMENT = _PICT + "(?:\\uFE0F|" + _EMOJI_MOD + ")?"
_EMOJI_RE = re.compile(
    "[\\U0001F1E6-\\U0001F1FF]{2}"                      # flag: two regional indicators
    "|[0-9#*]\\uFE0F?\\u20E3"                            # keycap
    "|\\U0001F3F4[\\U000E0020-\\U000E007E]+\\U000E007F"  # tag sequence (subdivision flag)
    "|" + _EMOJI_ELEMENT + "(?:\\u200D" + _EMOJI_ELEMENT + ")*")
_PICT_RE = re.compile(_PICT)


def emoji_identity(sequence):
    """Comparison form: without U+FE0F, so a heading's "\\u2764\\ufe0f" and "\\u2764" are one emoji."""
    return sequence.replace("\ufe0f", "")


def load_emoji_names(path):
    """identity -> name from a QueRyu ``emoji_names.json`` (``queryu.emoji-names/1``) or a plain JSON object."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = data.get("names") if isinstance(data, dict) and data.get("schema") == "queryu.emoji-names/1" else data
    if not isinstance(names, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in names.items()):
        raise ValueError(f"{path}: expected queryu.emoji-names/1 or an object of emoji -> name")
    return {emoji_identity(k): v for k, v in names.items()}


_EMOJI_PARTS = {"\U0001F3FB": "light skin tone", "\U0001F3FC": "medium-light skin tone",
                "\U0001F3FD": "medium skin tone", "\U0001F3FE": "medium-dark skin tone",
                "\U0001F3FF": "dark skin tone", "\U0001F9B0": "red hair", "\U0001F9B1": "curly hair",
                "\U0001F9B3": "white hair", "\U0001F9B2": "bald"}


def emoji_name(sequence, names=None):
    """A readable name from stdlib data: component names joined by " + ".

    Flags become ``FLAG JP``, keycaps ``KEYCAP #``, subdivision flags ``FLAG gbsct``.
    unicodedata only names single code points (its version is ``unicodedata.unidata_version``),
    so a ZWJ sequence such as woman technologist reads ``WOMAN + PERSONAL COMPUTER``.
    ``names`` (identity -> name, e.g. ``load_emoji_names("emoji_names.json")`` from QueRyu)
    is tried first, with skin-tone/hair variants named from their base (CLDR pattern).
    """
    if names:
        key = emoji_identity(sequence)
        if key in names:
            return names[key]
        base = "\u200d".join(p for p in "".join(c for c in key if c not in _EMOJI_PARTS).split("\u200d") if p)
        parts = [_EMOJI_PARTS[c] for c in key if c in _EMOJI_PARTS]
        if parts and base in names:
            return names[base] + ": " + ", ".join(dict.fromkeys(parts))
    chars = [c for c in sequence if c not in "\ufe0f\u200d"]
    if len(chars) == 2 and all("\U0001F1E6" <= c <= "\U0001F1FF" for c in chars):
        return "FLAG " + "".join(chr(ord(c) - 0x1F1E6 + 65) for c in chars)
    if chars and chars[-1] == "\u20e3":
        return "KEYCAP " + chars[0]
    if chars and chars[0] == "\U0001F3F4" and len(chars) > 2 and chars[-1] == "\U000E007F":
        return "FLAG " + "".join(chr(ord(c) - 0xE0000) for c in chars[1:-1])
    return " + ".join(unicodedata.name(c, "U+%04X" % ord(c)) for c in chars)


def emoji_sequences(text, names=None):
    """Emoji sequences in ``text`` with offsets: flags, keycaps, tag flags, modifiers, ZWJ sequences.

    Each row has ``emoji`` (as written), ``identity`` (without U+FE0F), ``kind``
    (single/modified/zwj/flag/keycap/tag), ``start``/``end`` (str offsets) and ``name``.
    The grammar is UTS #51's possible-emoji shape over Extended_Pictographic, so it
    also accepts non-RGI combinations; text-default symbols such as (c) count only
    with U+FE0F.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    rows = []
    for match in _EMOJI_RE.finditer(text):
        seq = match.group()
        if len(seq) == 1 and ord(seq) < 0x1F000 and not unicodedata.category(seq).startswith("So"):
            continue
        if len(seq) == 1 and ord(seq) < 0x2190 and not text[match.end():match.end() + 1] == "\ufe0f":
            continue  # (c) (r) !! ?! TM i stay text unless followed by VS16 (handled by the grammar)
        kind = ("flag" if "\U0001F1E6" <= seq[0] <= "\U0001F1FF" else
                "keycap" if seq.endswith("\u20e3") else
                "tag" if seq.endswith("\U000E007F") else
                "zwj" if "\u200d" in seq else
                "modified" if any("\U0001F3FB" <= c <= "\U0001F3FF" for c in seq) else "single")
        rows.append({"emoji": seq, "identity": emoji_identity(seq), "kind": kind,
                     "start": match.start(), "end": match.end(), "name": emoji_name(seq, names)})
    return rows


def emoji_find(query, *, limit=20):
    """Single-code-point emoji whose Unicode name contains every word of ``query``.

    ``emoji_find("house")`` -> HOUSE BUILDING, HOUSE WITH GARDEN, ...; ``"flag jp"``
    returns the flag built from regional indicators. Names come from this
    interpreter's ``unicodedata`` (versions differ across Python releases).
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    _limit(limit, "limit")
    words = query.upper().split()
    if len(words) == 2 and words[0] == "FLAG" and re.fullmatch(r"[A-Z]{2}", words[1]):
        flag = "".join(chr(0x1F1E6 + ord(c) - 65) for c in words[1])
        return [{"emoji": flag, "name": emoji_name(flag), "codepoints": ["U+%04X" % ord(c) for c in flag]}]
    rows = []
    for item in _EXT_PICT.split():
        lo, _, hi = item.partition("-")
        for code in range(int(lo, 16), int(hi or lo, 16) + 1):
            name = unicodedata.name(chr(code), "")
            if name and all(w in name for w in words):
                rows.append({"emoji": chr(code), "name": name, "codepoints": ["U+%04X" % code]})
    rows.sort(key=lambda r: (len(r["name"]), r["name"]))
    return rows[:limit]


_EMOJI_SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".tox"}


def emoji_inventory(roots=(".",), *, max_files=5000, max_bytes=1_000_000, max_examples=3, names=None):
    """Which emoji appear where: counts per identity across one or more roots.

    Rows: ``identity``, ``count``, ``files``, ``forms`` (spellings with/without U+FE0F
    and their counts; two forms of one identity is a common heading inconsistency),
    ``name`` and the first ``max_examples`` ``path:line``. UTF-8 text files only;
    binary or undecodable files are skipped and counted.
    """
    if isinstance(roots, (str, os.PathLike)):
        roots = [roots]
    for value, label in ((max_files, "max_files"), (max_bytes, "max_bytes"), (max_examples, "max_examples")):
        _limit(value, label)
    stats, scanned, skipped, truncated = {}, 0, 0, False
    for root in roots:
        base = Path(root)
        paths = [base] if base.is_file() else sorted(
            p for p in base.rglob("*") if p.is_file()
            and not any(part in _EMOJI_SKIP for part in p.relative_to(base).parts))
        for path in paths:
            if scanned == max_files:
                truncated = True
                break
            label = (path.name if base.is_file() else path.relative_to(base).as_posix())
            if len(roots) > 1:
                label = os.fspath(root).rstrip("/") + "/" + label
            try:
                with path.open("rb") as stream:
                    data = stream.read(max_bytes + 1)  # never load more than the cap
                if len(data) > max_bytes or b"\0" in data[:4096]:
                    raise ValueError
                text = data.decode("utf-8")
            except (OSError, ValueError):
                skipped += 1
                continue
            scanned += 1
            for number, line in enumerate(text.splitlines(), 1):
                for row in emoji_sequences(line, names):
                    entry = stats.setdefault(row["identity"], {"identity": row["identity"], "count": 0,
                                                              "files": set(), "forms": {}, "name": row["name"],
                                                              "kind": row["kind"], "examples": []})
                    entry["count"] += 1
                    entry["files"].add(label)
                    entry["forms"][row["emoji"]] = entry["forms"].get(row["emoji"], 0) + 1
                    if len(entry["examples"]) < max_examples:
                        entry["examples"].append(f"{label}:{number}")
    rows = sorted(stats.values(), key=lambda e: (-e["count"], e["identity"]))
    for row in rows:
        row["files"] = len(row["files"])
    return {"schema": "xprobe.emoji-inventory.v1", "unicodedata": unicodedata.unidata_version,
            "files": scanned, "skipped": skipped, "truncated": truncated, "emoji": rows}


# Hidden text: characters that change what a reader, a reviewer or a model
# receives without showing on screen (prompt injection, Trojan Source, homoglyph
# spoofing, variation-selector smuggling). Matching is per code point and per
# word; nothing here decides intent, so every finding is a rule match to review.
_HIDDEN_LEVELS = ("low", "medium", "high")
_HIDDEN_RULES = {
    "tag_text": ("high", "Unicode tag characters outside an emoji subdivision flag; they spell invisible ASCII"),
    "variation_payload": ("high", "four or more variation selectors in a row; decoded as one byte per selector"),
    "bidi_control": ("high", "bidirectional embedding, override or isolate control (Trojan Source reordering)"),
    "homograph_url": ("high", "URL or domain name with IDN punycode homoglyph, mixed-script label or confusable character spoofing"),
    "zero_width": ("medium", "zero-width space, joiner, word joiner or BOM outside emoji and joining scripts"),
    "variation_selector": ("medium", "variation selector with no visible base, or repeated"),
    "invisible_format": ("medium", "other invisible format character or blank-looking filler letter"),
    "mixed_script": ("medium", "one word mixing Latin, Cyrillic, Greek, Armenian or Cherokee letters (homoglyphs)"),
    "bidi_mark": ("low", "LRM/RLM/ALM direction mark; normal inside right-to-left text"),
    "soft_hyphen": ("low", "soft hyphen: invisible unless the line breaks there; splits keywords"),
    "private_use": ("low", "private-use code point (icon fonts, or text only some fonts show)"),
}
_BIDI_OPEN = {"\u202a": "pdf", "\u202b": "pdf", "\u202d": "pdf", "\u202e": "pdf",
              "\u2066": "pdi", "\u2067": "pdi", "\u2068": "pdi"}
_BIDI_CLOSE = {"\u202c": "pdf", "\u2069": "pdi"}
_BIDI_MARKS = "\u200e\u200f\u061c"
_ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff\u180e"
_JOINERS = "\u200c\u200d"
_FILLERS = "\u115f\u1160\u3164\uffa0\u2800\u034f\u17b4\u17b5"  # Hangul fillers, braille blank, CGJ, Khmer
_SHOWN_FORMAT = set("\u0600\u0601\u0602\u0603\u0604\u0605\u06dd\u070f\u0890\u0891\u08e2\U000110bd\U000110cd")
_HOMOGLYPH_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK", "ARMENIAN", "CHEROKEE")
_UNJOINED_SCRIPTS = _HOMOGLYPH_SCRIPTS + ("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "DIGIT")
_TAG_FLAG_RE = re.compile("\U0001F3F4[\U000E0030-\U000E0039\U000E0061-\U000E007A]{3,7}\U000E007F")
_WORD_RE = re.compile(r"[^\W\d_]+")
_CONFUSABLE_URL_CHARS = {
    "\uff0e": "FULLWIDTH FULL STOP", "\u3002": "IDEOGRAPHIC FULL STOP", "\uff61": "HALFWIDTH IDEOGRAPHIC FULL STOP",
    "\u2044": "FRACTION SLASH", "\u2215": "DIVISION SLASH", "\uff0f": "FULLWIDTH SOLIDUS",
    "\uff20": "FULLWIDTH COMMERCIAL AT", "\uff1a": "FULLWIDTH COLON", "\u037e": "GREEK QUESTION MARK",
}
# Deliberately small subset of Unicode confusables (UTS #39): whole-script
# detection requires every letter to resemble ASCII, not just a Cyrillic TLD.
# This is a heuristic, not the complete Unicode skeleton or a brand allowlist.
_ASCII_CONFUSABLE_LETTERS = frozenset("аеорсхуіјѕӏαιορϲ")
_URL_CANDIDATE_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.-]*://|(?<![\w.-])[\w-]+(?:[.\uff0e\u3002\uff61][\w-]+)+)"
    r"[^\s<>\"']*"
)


def hidden_text_rules():
    """{kind: {'severity', 'about'}} for the hidden-text rules, maximum severity, most severe first."""
    return {kind: {"severity": level, "about": about} for kind, (level, about) in _HIDDEN_RULES.items()}


def _selector(char):
    code = ord(char)
    return 0xFE00 <= code <= 0xFE0F or 0xE0100 <= code <= 0xE01EF


def _script(char):
    words = unicodedata.name(char, "").split()
    while words and words[0] in ("FULLWIDTH", "HALFWIDTH"):
        words = words[1:]
    return words[0] if words else ""


def _codepoints(text, limit=16):
    return ["U+%04X" % ord(c) for c in text[:limit]]


def _hidden_rules(kinds, min_severity):
    if min_severity not in _HIDDEN_LEVELS:
        raise ValueError("min_severity must be one of " + ", ".join(_HIDDEN_LEVELS))
    if isinstance(kinds, str):
        kinds = [kinds]
    selected = set(_HIDDEN_RULES) if kinds is None else set(kinds)
    unknown = sorted(selected - set(_HIDDEN_RULES))
    if unknown:
        raise ValueError("unknown hidden-text kind(s): " + ", ".join(unknown))
    floor = _HIDDEN_LEVELS.index(min_severity)
    return {k for k in selected if _HIDDEN_LEVELS.index(_HIDDEN_RULES[k][0]) >= floor}


def _hidden(text, rules, bom=True, end="text", min_severity="low"):
    found = []

    def add(kind, start, end, detail, **extra):
        severity = extra.pop("severity", _HIDDEN_RULES[kind][0])
        if kind in rules and _HIDDEN_LEVELS.index(severity) >= _HIDDEN_LEVELS.index(min_severity):
            found.append({"kind": kind, "severity": severity, "start": start, "end": end,
                          "codepoints": _codepoints(text[start:end]), "length": end - start,
                          "detail": detail, **extra})

    emoji = set()
    for match in _EMOJI_RE.finditer(text):
        if not match.group().endswith("\U000E007F"):
            emoji.update(range(match.start(), match.end()))
    for match in _TAG_FLAG_RE.finditer(text):
        emoji.update(range(match.start(), match.end()))
    stack, i, n = [], 0, len(text)
    while i < n:
        char, code = text[i], ord(text[i])
        if 0xE0000 <= code <= 0xE007F and i not in emoji:
            j = i
            while j < n and 0xE0000 <= ord(text[j]) <= 0xE007F and j not in emoji:
                j += 1
            hidden = "".join(chr(ord(c) - 0xE0000) for c in text[i:j] if 0xE0020 <= ord(c) <= 0xE007E)
            add("tag_text", i, j, "%d tag character(s)" % (j - i), decoded=hidden)
            i = j
            continue
        if _selector(char):
            if i in emoji and i + 1 < n and _selector(text[i + 1]):
                i += 1  # the first selector is the emoji's VS16; the run starts after it
            j = i
            while j < n and _selector(text[j]):
                j += 1
            if j - i >= 4:
                data = bytes(ord(c) - 0xFE00 if ord(c) <= 0xFE0F else ord(c) - 0xE0100 + 16 for c in text[i:j])
                add("variation_payload", i, j, "%d selector(s) in a row" % (j - i),
                    decoded=data.decode("utf-8", "backslashreplace"))
            elif j - i > 1:
                add("variation_selector", i, j, "%d selector(s) in a row" % (j - i))
            elif i not in emoji and i and _selector(text[i - 1]):
                add("variation_selector", i, j, "selector after the emoji's own selector")
            elif i not in emoji and (not i or unicodedata.category(text[i - 1])[0] in "ZC"):
                add("variation_selector", i, j, "no visible base before the selector")
            i = j
            continue
        if i in emoji:
            i += 1
            continue
        if char in _BIDI_OPEN:
            add("bidi_control", i, i + 1, unicodedata.name(char))
            if "bidi_control" in rules:
                stack.append((_BIDI_OPEN[char], found[-1]))
        elif char in _BIDI_CLOSE:
            if stack and stack[-1][0] == _BIDI_CLOSE[char]:
                stack.pop()
            add("bidi_control", i, i + 1, unicodedata.name(char))
        elif char in "\n\r\u2028\u2029\x85":
            for _, row in stack:
                row["detail"] += ", not closed before end of line"
            stack = []
        elif char in _BIDI_MARKS:
            add("bidi_mark", i, i + 1, unicodedata.name(char, "ARABIC LETTER MARK"))
        elif char in _ZERO_WIDTH:
            if char == "\ufeff" and i == 0 and bom:
                i += 1
                continue
            j = i
            while j < n and text[j] in _ZERO_WIDTH and j not in emoji:
                j += 1
            left, right = text[i - 1] if i else "", text[j] if j < n else ""
            joined = (j - i == 1 and char in _JOINERS and left and right
                      and unicodedata.category(left)[0] in "LM" and unicodedata.category(right)[0] in "LM"
                      and _script(left) not in _UNJOINED_SCRIPTS)
            if not joined:
                add("zero_width", i, j, ", ".join(dict.fromkeys(unicodedata.name(c) for c in text[i:j])))
            i = j
            continue
        elif char == "\u00ad":
            add("soft_hyphen", i, i + 1, "SOFT HYPHEN")
        elif char in _FILLERS or (unicodedata.category(char) == "Cf" and char not in _SHOWN_FORMAT):
            add("invisible_format", i, i + 1, unicodedata.name(char, "U+%04X" % code))
        elif unicodedata.category(char) == "Co":
            j = i
            while j < n and unicodedata.category(text[j]) == "Co":
                j += 1
            add("private_use", i, j, "%d private-use code point(s)" % (j - i))
            i = j
            continue
        i += 1
    for _, row in stack:
        row["detail"] += ", not closed before end of " + end
    if "mixed_script" in rules:
        for match in _WORD_RE.finditer(text):
            start, word = match.start(), match.group()
            if start and text[start - 1] == "\\":
                start, word = start + 1, word[1:]  # "\\n\u0421..." in JSON/source: the n is an escape
            scripts = [_script(c) for c in word]
            present = [s for s in _HOMOGLYPH_SCRIPTS if s in scripts]
            if len(present) > 1:
                major = max(present, key=scripts.count)
                odd = [c for c, s in zip(word, scripts) if s in present and s != major]
                add("mixed_script", start, match.end(), "+".join(present) + " in one word",
                    word=word, odd=_codepoints("".join(odd)))
    if "homograph_url" in rules:
        for match in _URL_CANDIDATE_RE.finditer(text):
            url_text = match.group().rstrip(".,;!)]}")
            u_start, u_end = match.start(), match.start() + len(url_text)
            # Keep the authority separate from the path, query and fragment.
            # Inspect userinfo too: google.com⁄@evil.com disguises the boundary.
            authority = url_text.split("://", 1)[-1]
            authority = re.split(r"[/?#\\]", authority, maxsplit=1)[0]
            host_part = authority.rsplit("@", 1)[-1]
            if host_part.startswith("["):  # bracketed IPv6, including a port
                continue
            host_part = host_part.split(":", 1)[0]
            labels = re.split(r"[.\uff0e\u3002\uff61]", host_part)
            decoded_labels, label_is_puny, label_scripts = [], [], []
            for label in labels:
                dec_label, is_puny = label, False
                if label.lower().startswith("xn--"):
                    try:
                        dec_label = label.lower().encode("ascii").decode("idna")
                        is_puny = True
                    except UnicodeError:
                        pass
                decoded_labels.append(dec_label)
                label_is_puny.append(is_puny)
                label_scripts.append({_script(c) for c in dec_label if c.isalpha()})
            full_decoded = ".".join(decoded_labels)
            for char, name in _CONFUSABLE_URL_CHARS.items():
                if char in authority:
                    # IDNA explicitly accepts these three dot aliases. Retain
                    # spelling diagnostics without treating them as an attack.
                    level = "medium" if char in "\uff0e\u3002\uff61" else "high"
                    add("homograph_url", u_start, u_end,
                        f"confusable character {name} (U+{ord(char):04X}) in URL authority",
                        decoded=full_decoded, severity=level)
            for label, dec, is_puny, scripts in zip(labels, decoded_labels, label_is_puny, label_scripts):
                present = [s for s in _HOMOGLYPH_SCRIPTS if s in scripts]
                prefix = f"Punycode label {label!r} decodes to " if is_puny else "Domain label "
                if len(present) > 1:
                    add("homograph_url", u_start, u_end,
                        f"{prefix}mixed-script {dec!r} ({'+'.join(present)})",
                        decoded=full_decoded)
                elif (len(present) == 1 and "LATIN" not in scripts
                      and all(c.lower() in _ASCII_CONFUSABLE_LETTERS
                              or c in "0123456789-" for c in dec)):
                    add("homograph_url", u_start, u_end,
                        f"{prefix}{present[0].capitalize()} {dec!r} resembles ASCII letters",
                        decoded=full_decoded)
    return sorted(found, key=lambda f: (f["start"], f["kind"]))


def hidden_text(text, *, kinds=None, min_severity="low"):
    """Rule matches for invisible or deceptive characters in ``text``.

    Each row has ``kind`` (see ``hidden_text_rules()``), ``severity``,
    ``start``/``end`` (str offsets), ``codepoints`` (first 16), ``length`` and
    ``detail``; ``tag_text`` and ``variation_payload`` add ``decoded`` (the hidden
    ASCII, or the bytes as UTF-8 with ``\\x`` escapes; an emoji's own VS16 is not
    counted as the first byte), ``mixed_script`` adds ``word`` and the minority ``odd``
    code points. ``homograph_url`` adds the decoded host; IDNA dot aliases
    are medium spelling advisories, other URL findings are high. Emoji ZWJ
    sequences, VS15/VS16 after a base, valid subdivision flags, a leading BOM and ZWJ/ZWNJ between letters of joining scripts are not
    reported. ``kinds`` selects rules; ``min_severity`` drops lower ones.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return _hidden(text, _hidden_rules(kinds, min_severity), min_severity=min_severity)


def strip_hidden(text, *, kinds=None, min_severity="low"):
    """``text`` without the characters ``hidden_text`` reports (``mixed_script`` words and ``homograph_url`` are kept).

    Use before handing untrusted text to a model or a reviewer; the report from
    ``hidden_text`` is what to log, since stripping alone hides that anything was there.
    """
    drop = set()
    for row in hidden_text(text, kinds=kinds, min_severity=min_severity):
        if row["kind"] not in ("mixed_script", "homograph_url"):
            drop.update(range(row["start"], row["end"]))
    return "".join(c for i, c in enumerate(text) if i not in drop)


def hidden_text_scan(roots=(".",), *, kinds=None, min_severity="medium", max_files=5000,
                     max_bytes=1_000_000, max_findings=1000):
    """``hidden_text`` over UTF-8 files under one or more roots, with ``path``/``line``/``column``.

    Binary, oversized and undecodable files are skipped and counted. ``counts``
    covers every finding even when ``findings`` is cut at ``max_findings``
    (``truncated`` is then true).
    """
    rules = _hidden_rules(kinds, min_severity)
    if isinstance(roots, (str, os.PathLike)):
        roots = [roots]
    for value, label in ((max_files, "max_files"), (max_bytes, "max_bytes"), (max_findings, "max_findings")):
        _limit(value, label)
    findings, counts, scanned, skipped, truncated = [], {}, 0, 0, False
    for root in roots:
        base = Path(root)
        paths = [base] if base.is_file() else sorted(
            p for p in base.rglob("*") if p.is_file()
            and not any(part in _EMOJI_SKIP for part in p.relative_to(base).parts))
        for path in paths:
            if scanned == max_files:
                truncated = True
                break
            label = path.name if base.is_file() else path.relative_to(base).as_posix()
            if len(roots) > 1:
                label = os.fspath(root).rstrip("/") + "/" + label
            try:
                with path.open("rb") as stream:
                    data = stream.read(max_bytes + 1)
                if len(data) > max_bytes or b"\0" in data[:4096]:
                    raise ValueError
                text = data.decode("utf-8")
            except (OSError, ValueError):
                skipped += 1
                continue
            scanned += 1
            for number, line in enumerate(text.split("\n"), 1):
                for row in _hidden(line, rules, bom=number == 1, end="line", min_severity=min_severity):
                    counts[row["kind"]] = counts.get(row["kind"], 0) + 1
                    if len(findings) == max_findings:
                        truncated = True
                        continue
                    row = {"path": label, "line": number, "column": row.pop("start") + 1, **row}
                    row.pop("end")
                    findings.append(row)
    return {"schema": "xprobe.hidden-text.v1", "min_severity": min_severity, "files": scanned,
            "skipped": skipped, "truncated": truncated, "counts": counts, "findings": findings}


def main(argv=None):
    """Thin standalone entry point over the existing discovery/search APIs."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Standalone read-only source/configuration inspection")
    parser.add_argument("--root", action="append", help="Directory or file; repeat --root to search several repositories")
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-matches", type=int, default=1000)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--search", metavar="TEXT", help="Literal search; prints raw matching lines")
    modes.add_argument("--preset", metavar="NAME", help="Search with a named built-in regex (--presets lists them)")
    modes.add_argument("--presets", action="store_true", help="List the named regexes")
    modes.add_argument("--symbols", metavar="PATH", help="Find Python definitions in a file or directory")
    modes.add_argument("--discover", action="store_true", help="Discover files under --root using --include conventions")
    parser.add_argument("--symbol-pattern", action="append", metavar="GLOB",
                        help="--symbols: short or lexical dotted name; repeat for OR, default '*'")
    parser.add_argument("--symbol-kind", action="append", choices=("class", "function", "async_function"))
    parser.add_argument("--include", action="append", metavar="GLOB", help="Discovery filename/path rule; repeat for OR")
    parser.add_argument("--exclude-dir", action="append", metavar="GLOB", help="Additional directory exclusion")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--max-files", type=int, default=5000)
    parser.add_argument("--regex", action="store_true", help="--search TEXT is a regular expression")
    parser.add_argument("--normalize", metavar="STEPS", default="",
                        help="Comma list of " + ",".join(NORMALIZE_STEPS) + "; coordinates stay original")
    parser.add_argument("--brief", action="store_true", help="One 'path:line:column: match' line per match")
    modes.add_argument("--corpus", action="store_true", help="Show existing explained regression inputs")
    modes.add_argument("--annotate-junit", metavar="FILE", help="Print ::error workflow commands for failed JUnit testcases")
    modes.add_argument("--emoji", action="store_true", help="Emoji used under --root: counts, spellings, files")
    modes.add_argument("--emoji-find", metavar="WORDS", help="Emoji whose Unicode name has these words (e.g. 'house', 'flag jp')")
    modes.add_argument("--emoji-explain", metavar="TEXT", help="Split TEXT into emoji sequences with names and code points")
    parser.add_argument("--emoji-names", metavar="FILE", help="Names table for --emoji/--emoji-explain (QueRyu emoji_names.json)")
    modes.add_argument("--mojibake", action="store_true", help="Scan --root for Japanese mojibake findings; 1 if any")
    modes.add_argument("--read-text", "--restore-mojibake", dest="restore_mojibake", metavar="FILE",
                       help="Auto-decode FILE ('-' = stdin), repair known mojibake, and print readable UTF-8")
    parser.add_argument("--text-report", action="store_true",
                        help="With --read-text, return JSON with text, original decoded view and diagnostics")
    modes.add_argument("--hidden-text", action="store_true",
                       help="Invisible/deceptive characters under --root (tag text, bidi, zero-width, homoglyphs); 1 if any")
    modes.add_argument("--hidden-rules", action="store_true", help="List the --hidden-text rules and severities")
    modes.add_argument("--strip-hidden", metavar="FILE", help="Print FILE ('-' = stdin) without the characters --hidden-text reports")
    parser.add_argument("--min-severity", choices=_HIDDEN_LEVELS, help="--hidden-text: medium; --strip-hidden: low")
    parser.add_argument("--kinds", metavar="K1,K2", help="Only these --hidden-text/--strip-hidden rules")
    modes.add_argument("--portability", action="store_true", help="Sources that break on --min-python/--max-python or a cp1252 locale")
    parser.add_argument("--min-python", metavar="X.Y", help="Default: requires-python in ROOT/pyproject.toml, else 3.10")
    parser.add_argument("--max-python", default="3.14", metavar="X.Y")
    parser.add_argument("--windows-locale", action="store_true",
                        help="With --portability, also list I/O without encoding= and non-cp1252 bytes (hints; exit unaffected)")
    modes.add_argument("--load", nargs=2, metavar=("KIND", "FILE"),
                       help="Print a toml|yaml|yaml-core file as JSON (tomllib, else Node 24+ smol-toml/js-yaml)")
    modes.add_argument("--explain", metavar="FILE", help="Rank conditions explaining --target in a JSON array/JSONL file ('-' = stdin)")
    parser.add_argument("--target", metavar="FIELD=VALUE", help="Outcome for --explain; VALUE is a JSON literal")
    parser.add_argument("--target-differs", metavar="A,B", help="Outcome for --explain: fields A and B differ")
    parser.add_argument("--id", dest="id_field", help="Record field naming counterexamples")
    parser.add_argument("--skip", action="append", default=[], help="Field not used as a condition")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)
    if args.text_report and args.restore_mojibake is None:
        parser.error("--text-report requires --read-text or --restore-mojibake")
    roots = args.root or ["."]
    try:
        if args.discover or (args.symbols is not None and Path(args.symbols).is_dir()):
            if args.discover and len(roots) != 1:
                raise ValueError("file discovery takes one root")
            root = roots[0] if args.discover else args.symbols
            options = {"include": args.include if args.include is not None else (("*",) if args.discover else ("*.py",)),
                       "exclude_dirs": _DEFAULT_EXCLUDE + tuple(args.exclude_dir or ()),
                       "include_hidden": args.include_hidden, "max_files": args.max_files}
            report = (discover_files(root, **options) if args.discover else
                      discover_python(root, patterns=args.symbol_pattern or ("*",), kinds=args.symbol_kind or (),
                                      max_bytes=args.max_bytes, max_symbols=args.max_matches, **options))
            rows = report["files"] if args.discover else report["symbols"]
            if args.brief:
                for row in rows:
                    print(row if args.discover else f"{row['path']}:{row['line']}: {row['kind']} {row['qualname']}")
                for key in ("errors", "skipped"):
                    for row in report[key]:
                        print(f"{key}: {row['path']} ({row['reason']})", file=sys.stderr)
                if report["truncated"]:
                    print("truncated: raise --max-files/--max-matches", file=sys.stderr)
            else:
                print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
            return 2 if report["errors"] or report["skipped"] or report["truncated"] else (0 if rows else 1)
        if args.symbols is not None:
            _limit(args.max_bytes, "max_bytes")
            _limit(args.max_matches, "max_matches")
            path = Path(args.symbols)
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("symbols input must be a regular file")
            with path.open("rb") as stream:
                source = stream.read(args.max_bytes + 1)
            if len(source) > args.max_bytes:
                raise ValueError("symbols input exceeds byte limit")
            rows = python_symbols(source, pattern=args.symbol_pattern or ("*",), kinds=args.symbol_kind or ())
            report = {"path": str(path), "symbols": rows[:args.max_matches],
                      "truncated": len(rows) > args.max_matches}
            if args.brief:
                for row in report["symbols"]:
                    print(f"{path}:{row['line']}: {row['kind']} {row['qualname']}")
                if report["truncated"]:
                    print("truncated: raise --max-matches")
            else:
                print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
            return 2 if report["truncated"] else (0 if rows else 1)
        if args.annotate_junit is not None:
            for line in junit_annotations(Path(args.annotate_junit).read_text(encoding="utf-8")):
                print(line)
            return 0
        if args.emoji_find is not None or args.emoji_explain is not None:
            rows = (emoji_find(args.emoji_find, limit=args.max_matches) if args.emoji_find is not None
                    else emoji_sequences(args.emoji_explain,
                                         load_emoji_names(args.emoji_names) if args.emoji_names else None))
            for row in rows:
                points = " ".join(row.get("codepoints") or ["U+%04X" % ord(c) for c in row["emoji"]])
                print(f"{row['emoji']}\t{points}\t{row['name']}")
            return 0 if rows else 1
        if args.emoji:
            report = emoji_inventory(roots, max_bytes=args.max_bytes,
                                     names=load_emoji_names(args.emoji_names) if args.emoji_names else None)
            if args.brief:
                for row in report["emoji"][:args.max_matches]:
                    forms = "" if len(row["forms"]) == 1 else "  forms: " + " ".join(
                        f"{form}x{count}" for form, count in row["forms"].items())
                    print(f"{row['identity']}\t{row['count']}\t{row['files']} file(s)\t{row['name']}{forms}")
                print(f"emoji: {len(report['emoji'])} distinct in {report['files']} file(s); "
                      f"unicodedata {report['unicodedata']}")
            else:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.restore_mojibake is not None:
            _limit(args.max_bytes, "max_bytes")
            if args.restore_mojibake == "-":
                raw = sys.stdin.buffer.read(args.max_bytes + 1)
            else:
                with Path(args.restore_mojibake).open("rb") as stream:
                    raw = stream.read(args.max_bytes + 1)
            if len(raw) > args.max_bytes:
                print("input exceeds --max-bytes", file=sys.stderr)
                return 2
            reading = readable_text(raw)
            if args.text_report:
                print(json.dumps(reading, ensure_ascii=True, indent=2))
            else:
                sys.stdout.buffer.write(reading["text"].encode("utf-8"))
                if reading["warnings"]:
                    print("xprobe: " + reading["encoding"] + " / " + reading["status"] + "; " +
                          "; ".join(reading["warnings"]), file=sys.stderr)
            # A partial reading is usable; diagnostics, not failure, carry uncertainty.
            return 0
        if args.mojibake:
            mb_rep = mojibake_scan(roots, max_bytes=args.max_bytes, max_findings=args.max_matches)
            if args.brief:
                for f in mb_rep["findings"]:
                    print(f"{f['path']}:{f['line']}:{f['column']}: {f['kind']} ({f['hint']}) {ascii(f['text'])} -> {f['restored']}")
                print(f"mojibake: {sum(mb_rep['counts'].values())} finding(s) in {mb_rep['files']} file(s)" + ("; truncated" if mb_rep["truncated"] else ""))
                for row in mb_rep["decodings"]:
                    if row["warnings"]:
                        print(f"decode: {row['path']}: {row['encoding']} / {row['status']}; " +
                              "; ".join(row["warnings"]))
            else:
                print(json.dumps(mb_rep, ensure_ascii=False, indent=2))
            return 1 if mb_rep["counts"] else 0
        if args.hidden_rules:
            for kind, rule in hidden_text_rules().items():
                print(f"{kind}\t{rule['severity']}\t{rule['about']}")
            return 0
        kinds = [k for k in args.kinds.split(",") if k] if args.kinds else None
        if args.strip_hidden is not None:
            raw = sys.stdin.buffer.read() if args.strip_hidden == "-" else Path(args.strip_hidden).read_bytes()
            text = raw.decode("utf-8")
            sys.stdout.buffer.write(strip_hidden(text, kinds=kinds, min_severity=args.min_severity or "low")
                                    .encode("utf-8"))
            return 0
        if args.hidden_text:
            report = hidden_text_scan(roots, kinds=kinds, min_severity=args.min_severity or "medium",
                                      max_bytes=args.max_bytes, max_findings=args.max_matches)
            if args.brief:
                for f in report["findings"]:
                    extra = "".join(f" {key}={ascii(f[key])}" for key in ("decoded", "word") if key in f)
                    print(f"{f['path']}:{f['line']}:{f['column']}: {f['severity']} {f['kind']} "
                          f"{' '.join(f['codepoints'])} {f['detail']}{extra}")
                print(f"hidden-text: {sum(report['counts'].values())} finding(s) in {report['files']} file(s)"
                      + ("; truncated" if report["truncated"] else ""))
            else:
                print(json.dumps(report, ensure_ascii=True, indent=2))
            return 1 if report["counts"] else 0
        if args.portability:
            version = lambda text: tuple(int(x) for x in text.split("."))[:2]
            reports = [portability_findings(root, min_python=version(args.min_python) if args.min_python else None,
                                            max_python=version(args.max_python),
                                            locale_io=args.windows_locale,
                                            undecodable=args.windows_locale) for root in roots]
            rows = [(root, f) for root, r in zip(roots, reports) for f in r["findings"]]
            for root, f in rows:
                where = f["path"] if len(roots) == 1 else f"{root.rstrip('/')}/{f['path']}"
                print(f"{where}:{f['line']}: {f['kind']}: {f['detail']}")
            floors = ", ".join(sorted({f"{r['min_python'][0]}.{r['min_python'][1]} ({r['min_python_source']})" for r in reports}))
            print(f"portability: {len(rows)} finding(s) in {sum(r['files'] for r in reports)} file(s); min python {floors}")
            return 1 if any(f["kind"] in _PORTABILITY_ERRORS for _, f in rows) else 0
        if args.explain is not None:
            return _explain_cli(args, parser)
        if args.load is not None:
            kind, path = args.load
            if kind not in ("toml", "yaml", "yaml-core"):
                parser.error("--load KIND must be toml, yaml or yaml-core")
            text = Path(path).read_text(encoding="utf-8")
            try:
                value = load_toml(text) if kind == "toml" else load_yaml(text, schema="core" if kind == "yaml-core" else "failsafe")
            except RuntimeError as error:
                # Node is required only for this mode. Name the missing piece;
                # other commands keep their existing type-only stderr.
                print(error, file=sys.stderr)
                return 2
            print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.corpus:
            print(corpus_to_json(known_bad_cases()), end="")
            return 0
        if args.presets:
            for name, item in pattern_presets().items():
                print(f"{name}: {item['about']}")
            return 0
        searching = args.search is not None or args.preset is not None
        if searching:
            report = {"matches": [], "skipped": [], "errors": [], "truncated": False}
            for root in roots:
                remaining = args.max_matches - len(report["matches"])
                if remaining < 1:
                    report["truncated"] = True
                    break
                part = search_files(root, args.search, regex=args.regex, preset=args.preset,
                                    normalize=[s for s in args.normalize.split(",") if s],
                                    max_bytes=args.max_bytes,
                                    max_matches=remaining, exclude_dirs=_DEFAULT_EXCLUDE)
                for key in ("matches", "skipped", "errors"):
                    for row in part[key]:
                        if len(roots) > 1:
                            row["path"] = f"{root.rstrip('/')}/{row['path']}"
                        report[key].append(row)
                for row in part.get("decodings", []):
                    if len(roots) > 1:
                        row["path"] = f"{root.rstrip('/')}/{row['path']}"
                    report.setdefault("decodings", []).append(row)
                report["truncated"] = report["truncated"] or part["truncated"]
        else:
            report = scan_config(roots[0], max_bytes=args.max_bytes,
                                 max_findings=args.max_matches)
    except (OSError, ValueError, LookupError, RuntimeError, SyntaxError) as error:
        print(type(error).__name__, file=sys.stderr)
        return 2
    if args.brief and searching:
        for row in report["matches"]:
            print(f"{row['path']}:{row['line']}:{row['column']}: {row['match']!r}")
        for key in ("skipped", "errors"):
            if report[key]:
                print(f"{key}: " + ", ".join(f"{e['path']} ({e['reason']})" for e in report[key]))
        for row in report.get("decodings", []):
            if row["warnings"]:
                print(f"decode: {row['path']}: {row['encoding']} / {row['status']}; " +
                      "; ".join(row["warnings"]))
        if report["truncated"]:
            print("truncated: raise --max-matches")
    else:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True, indent=2))
    if report["errors"] or report["truncated"] or report["skipped"]:
        return 2
    return (0 if report["matches"] else 1) if searching else 0


if __name__ == "__main__":
    raise SystemExit(main())
