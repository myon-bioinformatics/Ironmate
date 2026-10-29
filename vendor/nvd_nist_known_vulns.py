"""Dependency-free NVD CVE API 2.0 client with local CVSS score calculation.

Network requests are globally throttled per process; concurrent callers are not synchronized.
NVD currently publishes the CVE REST API at /cves/2.0 only; there is no public /cves/3.0 stem.
CVSS v3-series query filters (cvssV3Severity / cvssV3Metrics) are optional parameters on that 2.0 API.

CLI status: 0 success, including zero CVEs; 1 NVD request or output publication failure;
2 usage or local input error. ``--format json`` writes one nvd-cli-error/1 object to stderr
on failure. Success output stays JSONL for every format.
"""
from __future__ import annotations

import argparse
import configparser
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
import difflib
from email.utils import parsedate_to_datetime
from http.client import HTTPException, IncompleteRead
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NVD_CVE_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
DEFAULT_RESULTS_PER_PAGE = 2000
SCHEMA_VERSION = "nvd-cve-summary/1"
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_USAGE = 2
ERROR_SCHEMA = "nvd-cli-error/1"
UNAUTHENTICATED_INTERVAL = 6.0
AUTHENTICATED_INTERVAL = 0.6
MAX_RETRY_DELAY = 60.0
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
_CVSS3_MANDATORY = ("AV", "AC", "PR", "UI", "S", "C", "I", "A")
_CVSS3_AV = {"N": Decimal("0.85"), "A": Decimal("0.62"), "L": Decimal("0.55"), "P": Decimal("0.2")}
_CVSS3_AC = {"L": Decimal("0.77"), "H": Decimal("0.44")}
_CVSS3_PR_UNCHANGED = {"N": Decimal("0.85"), "L": Decimal("0.62"), "H": Decimal("0.27")}
_CVSS3_PR_CHANGED = {"N": Decimal("0.85"), "L": Decimal("0.68"), "H": Decimal("0.50")}
_CVSS3_UI = {"N": Decimal("0.85"), "R": Decimal("0.62")}
_CVSS3_CIA = {"H": Decimal("0.56"), "L": Decimal("0.22"), "N": Decimal("0")}
_CVSS2_MANDATORY = ("AV", "AC", "Au", "C", "I", "A")
_CVSS2_AV = {"N": Decimal("1.0"), "A": Decimal("0.646"), "L": Decimal("0.395")}
_CVSS2_AC = {"L": Decimal("0.71"), "M": Decimal("0.61"), "H": Decimal("0.35")}
_CVSS2_AU = {"N": Decimal("0.704"), "S": Decimal("0.56"), "M": Decimal("0.45")}
_CVSS2_CIA = {"C": Decimal("0.660"), "P": Decimal("0.275"), "N": Decimal("0")}
_last_request_at: float | None = None


def _cvss_roundup(value: Decimal) -> Decimal:
    """FIRST Roundup: smallest one-decimal value >= input (Decimal, not binary float)."""
    return value.quantize(Decimal("0.1"), rounding=ROUND_CEILING)


def _cvss_severity(score: Decimal, *, version: str) -> str:
    if version.startswith("2"):
        if score == 0:
            return "NONE"
        if score <= Decimal("3.9"):
            return "LOW"
        if score <= Decimal("6.9"):
            return "MEDIUM"
        return "HIGH"
    if score == 0:
        return "NONE"
    if score <= Decimal("3.9"):
        return "LOW"
    if score <= Decimal("6.9"):
        return "MEDIUM"
    if score <= Decimal("8.9"):
        return "HIGH"
    return "CRITICAL"


def _parse_cvss_metrics(vector: str) -> tuple[str | None, dict[str, str]]:
    text = vector.strip()
    if not text:
        raise ValueError("CVSS vector is empty")
    parts = text.split("/")
    # FIRST vectors use '/' between metrics, never as an empty metric.
    if any(not part for part in parts):
        raise ValueError("malformed CVSS vector: empty segment")
    version: str | None = None
    metrics: dict[str, str] = {}
    start = 0
    if parts[0].startswith("CVSS:"):
        version = parts[0].split(":", 1)[1]
        start = 1
    for part in parts[start:]:
        if ":" not in part:
            raise ValueError(f"malformed CVSS metric: {part!r}")
        key, value = part.split(":", 1)
        if key in metrics:
            raise ValueError(f"duplicate CVSS metric: {key}")
        metrics[key] = value
    return version, metrics


def _calculate_cvss3_base(version: str, metrics: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in _CVSS3_MANDATORY if key not in metrics]
    if missing:
        raise ValueError(f"CVSS v{version} vector missing metrics: {', '.join(missing)}")
    try:
        scope = metrics["S"]
        if scope not in ("U", "C"):
            raise KeyError("S")
        iss = (
            Decimal(1)
            - (Decimal(1) - _CVSS3_CIA[metrics["C"]])
            * (Decimal(1) - _CVSS3_CIA[metrics["I"]])
            * (Decimal(1) - _CVSS3_CIA[metrics["A"]])
        )
        if scope == "U":
            impact = Decimal("6.42") * iss
            privileges = _CVSS3_PR_UNCHANGED[metrics["PR"]]
        else:
            impact = Decimal("7.52") * (iss - Decimal("0.029")) - Decimal("3.25") * (
                iss - Decimal("0.02")
            ) ** 15
            privileges = _CVSS3_PR_CHANGED[metrics["PR"]]
        exploitability = (
            Decimal("8.22")
            * _CVSS3_AV[metrics["AV"]]
            * _CVSS3_AC[metrics["AC"]]
            * privileges
            * _CVSS3_UI[metrics["UI"]]
        )
    except KeyError as exc:
        raise ValueError(f"unsupported CVSS v{version} metric value in {exc.args[0]}") from exc
    if impact <= 0:
        score = Decimal("0.0")
    elif scope == "U":
        score = _cvss_roundup(min(impact + exploitability, Decimal(10)))
    else:
        score = _cvss_roundup(min(Decimal("1.08") * (impact + exploitability), Decimal(10)))
    return {
        "version": version,
        "base_score": float(score),
        "base_severity": _cvss_severity(score, version=version),
    }


def _calculate_cvss2_base(metrics: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in _CVSS2_MANDATORY if key not in metrics]
    if missing:
        raise ValueError(f"CVSS v2 vector missing metrics: {', '.join(missing)}")
    try:
        impact = Decimal("10.41") * (
            Decimal(1)
            - (Decimal(1) - _CVSS2_CIA[metrics["C"]])
            * (Decimal(1) - _CVSS2_CIA[metrics["I"]])
            * (Decimal(1) - _CVSS2_CIA[metrics["A"]])
        )
        exploitability = (
            Decimal(20)
            * _CVSS2_AV[metrics["AV"]]
            * _CVSS2_AC[metrics["AC"]]
            * _CVSS2_AU[metrics["Au"]]
        )
    except KeyError as exc:
        raise ValueError(f"unsupported CVSS v2 metric value in {exc.args[0]}") from exc
    if impact == 0:
        score = Decimal("0.0")
    else:
        # CVSS v2 rounds to one decimal with round-half-up (not the v3 Roundup).
        score = (
            ((Decimal("0.6") * impact) + (Decimal("0.4") * exploitability) - Decimal("1.5"))
            * Decimal("1.176")
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if score < 0:
            score = Decimal("0.0")
        elif score > 10:
            score = Decimal("10.0")
    return {
        "version": "2.0",
        "base_score": float(score),
        "base_severity": _cvss_severity(score, version="2.0"),
    }


def calculate_cvss_base(vector: str) -> dict[str, Any]:
    """Calculate a CVSS base score from a vector string (v2.0 / v3.0 / v3.1).

    Returns ``{"version", "base_score", "base_severity"}``. CVSS v4.0 vectors are
    rejected: v4 uses MacroVector lookup tables, not the v3 closed-form equations.
    Bare vectors without a ``CVSS:`` prefix are treated as v2 when they include ``Au``.
    """
    version, metrics = _parse_cvss_metrics(vector)
    if version is None:
        if "Au" in metrics:
            return _calculate_cvss2_base(metrics)
        raise ValueError("CVSS vector is missing a CVSS:version prefix")
    if version in ("3.0", "3.1"):
        return _calculate_cvss3_base(version, metrics)
    if version in ("2.0", "2"):
        return _calculate_cvss2_base(metrics)
    if version.startswith("4"):
        raise ValueError("CVSS v4 score calculation is not implemented (MacroVector lookup)")
    raise ValueError(f"unsupported CVSS version: {version}")


def _throttle(api_key: str | None) -> None:
    global _last_request_at
    interval = AUTHENTICATED_INTERVAL if api_key else UNAUTHENTICATED_INTERVAL
    now = time.monotonic()
    if _last_request_at is not None:
        remaining = interval - (now - _last_request_at)
        if remaining > 0:
            time.sleep(remaining)
            now = time.monotonic()
    _last_request_at = now


def _retry_delay(value: str | None, attempt: int) -> float:
    fallback = min(2.0**attempt, MAX_RETRY_DELAY)
    if not value:
        return fallback
    try:
        return min(max(float(value), 0.0), MAX_RETRY_DELAY)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return min(max((when - datetime.now(timezone.utc)).total_seconds(), 0.0), MAX_RETRY_DELAY)
        except (TypeError, ValueError, OverflowError):
            return fallback


def _request_json(url: str, *, api_key: str | None = None, timeout: float = 30.0, retries: int = 3) -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "nvd_nist_known_vulns/stdlib"}
    if api_key:
        headers["apiKey"] = api_key
    for attempt in range(retries + 1):
        _throttle(api_key)
        try:
            with urlopen(Request(url, headers=headers), timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            retryable = exc.code in RETRYABLE_HTTP or (exc.code == 403 and not api_key)
            message = exc.headers.get("message") if exc.headers else None
            if retryable and attempt < retries:
                time.sleep(_retry_delay(exc.headers.get("Retry-After") if exc.headers else None, attempt))
                continue
            detail = f"; {message}" if message else ""
            hint = "; possible unauthenticated rate limit" if exc.code == 403 and not api_key else ""
            raise RuntimeError(f"NVD HTTP error {exc.code}: {exc.reason}{detail}{hint}") from exc
        except (URLError, TimeoutError, HTTPException, IncompleteRead) as exc:
            if attempt < retries:
                time.sleep(min(2.0**attempt, MAX_RETRY_DELAY))
                continue
            raise RuntimeError(f"NVD request failed: {exc}") from exc
    raise AssertionError("unreachable")


def api_call(
    cpe_name: str,
    *,
    start_index: int = 0,
    results_per_page: int = DEFAULT_RESULTS_PER_PAGE,
    api_key: str | None = None,
    timeout: float = 30.0,
    cvss_v3_severity: str | None = None,
    cvss_v3_metrics: str | None = None,
) -> dict[str, Any]:
    """Query NVD CVE API 2.0 for a CPE, with optional CVSS v3-series filters.

    ``cvss_v3_severity`` maps to NVD ``cvssV3Severity`` (LOW/MEDIUM/HIGH/CRITICAL).
    ``cvss_v3_metrics`` maps to NVD ``cvssV3Metrics`` (partial or full v3 vector).
    """
    params: dict[str, Any] = {
        "cpeName": cpe_name,
        "startIndex": start_index,
        "resultsPerPage": results_per_page,
    }
    if cvss_v3_severity is not None:
        params["cvssV3Severity"] = cvss_v3_severity
    if cvss_v3_metrics is not None:
        params["cvssV3Metrics"] = cvss_v3_metrics
    return _request_json(f"{NVD_CVE_API}?{urlencode(params)}", api_key=api_key, timeout=timeout)


def iter_cve_pages(
    cpe_name: str,
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
    cvss_v3_severity: str | None = None,
    cvss_v3_metrics: str | None = None,
) -> Iterable[dict[str, Any]]:
    start = 0
    expected_total: int | None = None
    while True:
        page = api_call(
            cpe_name,
            start_index=start,
            api_key=api_key,
            timeout=timeout,
            cvss_v3_severity=cvss_v3_severity,
            cvss_v3_metrics=cvss_v3_metrics,
        )
        total = page.get("totalResults")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError("NVD response has invalid or missing totalResults")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise RuntimeError(
                f"NVD totalResults changed during pagination: {expected_total} -> {total}"
            )
        vulnerabilities = page.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            raise RuntimeError("NVD response has invalid vulnerabilities")
        returned = len(vulnerabilities)
        next_start = start + returned
        if returned == 0 and next_start < total:
            raise RuntimeError(
                f"NVD pagination stopped before completion: {next_start}/{total}"
            )
        if next_start > total:
            raise RuntimeError(
                f"NVD pagination exceeded totalResults: {next_start}/{total}"
            )
        yield page
        start = next_start
        if start == total:
            return


def _description(cve: dict[str, Any]) -> str | None:
    items = cve.get("descriptions", [])
    for item in items:
        if item.get("lang") == "en":
            return item.get("value")
    return items[0].get("value") if items else None


def _cwes(cve: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for weakness in cve.get("weaknesses", []):
        for item in weakness.get("description", []):
            value = item.get("value")
            if value and value not in result:
                result.append(value)
    return result


def _metric(cve: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any] | None:
    metrics = cve.get("metrics", {})
    for name in names:
        candidates = metrics.get(name, [])
        if candidates:
            item = next((x for x in candidates if x.get("type") == "Primary"), candidates[0])
            data = item.get("cvssData", {})
            record = {
                "version": data.get("version"),
                "base_score": data.get("baseScore"),
                "base_severity": data.get("baseSeverity") or item.get("baseSeverity"),
                "vector": data.get("vectorString"),
                "source": item.get("source"),
                "type": item.get("type"),
            }
            vector = record["vector"]
            if isinstance(vector, str) and vector:
                try:
                    calculated = calculate_cvss_base(vector)
                except ValueError:
                    calculated = None
                if calculated is not None:
                    record["calculated_base_score"] = calculated["base_score"]
                    record["calculated_base_severity"] = calculated["base_severity"]
            return record
    return None


def format_cve_data(json_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for vulnerability in json_data.get("vulnerabilities", []):
        cve = vulnerability.get("cve", {})
        cve_id = cve.get("id")
        if not cve_id:
            continue
        records[cve_id] = {
            "id": cve_id,
            "description": _description(cve),
            "cwe": _cwes(cve),
            "cvss_v4": _metric(cve, ("cvssMetricV40",)),
            "cvss_v3": _metric(cve, ("cvssMetricV31", "cvssMetricV30")),
            "cvss_v2": _metric(cve, ("cvssMetricV2",)),
            "published": cve.get("published"),
            "last_modified": cve.get("lastModified"),
            "source_identifier": cve.get("sourceIdentifier"),
        }
    return records


def fetch_cves(
    cpe_name: str,
    *,
    api_key: str | None = None,
    timeout: float = 30.0,
    cvss_v3_severity: str | None = None,
    cvss_v3_metrics: str | None = None,
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for page in iter_cve_pages(
        cpe_name,
        api_key=api_key,
        timeout=timeout,
        cvss_v3_severity=cvss_v3_severity,
        cvss_v3_metrics=cvss_v3_metrics,
    ):
        records.update(format_cve_data(page))
    return [records[key] for key in sorted(records)]



def _query(cpe: str, severity: str | None = None, metrics: str | None = None) -> dict[str, Any]:
    """Bind completion evidence to the normalized request scope."""
    filters: dict[str, str] = {}
    if severity is not None:
        if not isinstance(severity, str) or severity.strip().upper() not in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            raise ValueError("invalid CVSS v3 severity filter")
        filters["cvss_v3_severity"] = severity.strip().upper()
    if metrics is not None:
        if not isinstance(metrics, str) or not metrics.strip():
            raise ValueError("invalid CVSS v3 metrics filter")
        filters["cvss_v3_metrics"] = metrics.strip().upper()
    query: dict[str, Any] = {"cpe_name": cpe}
    if filters:
        query["filters"] = filters
    return query


def _validate_query_scope(query: dict[str, Any], kind: str) -> None:
    filtered = kind.startswith("filtered_")
    filters = query.get("filters")
    if filtered:
        if not isinstance(filters, dict) or not filters or set(filters) - {"cvss_v3_severity", "cvss_v3_metrics"}:
            raise ValueError("filtered NVD record requires explicit supported filters")
        normalized = _query(query["cpe_name"], filters.get("cvss_v3_severity"), filters.get("cvss_v3_metrics"))
        if normalized != query:
            raise ValueError("noncanonical filtered NVD query")
    elif set(query) != {"cpe_name"}:
        raise ValueError("unfiltered NVD record cannot carry query restrictions")


def parse_jsonl(text: str) -> list[dict[str, Any]]:
    """Parse nvd-cve-summary/1 JSONL while preserving Unicode line separators."""
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.lstrip("\ufeff").split("\n"), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(record, dict) or record.get("schema") != SCHEMA_VERSION:
            raise ValueError(f"unsupported NVD record at line {line_number}")
        query = record.get("query")
        cpe = query.get("cpe_name") if isinstance(query, dict) else None
        if not isinstance(cpe, str) or not cpe:
            raise ValueError(f"incomplete NVD record at line {line_number}")
        kind = record.get("kind", "cve")
        if kind in ("cve", "filtered_cve"):
            _validate_query_scope(query, kind)
            cve_id = record.get("id")
            if not isinstance(cve_id, str) or not cve_id.startswith("CVE-"):
                raise ValueError(f"incomplete NVD CVE record at line {line_number}")
        elif kind in ("query_complete", "filtered_query_complete"):
            _validate_query_scope(query, kind)
            count = record.get("cve_count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"incomplete NVD completion record at line {line_number}")
        else:
            # v1 allows additive record kinds; old consumers must remain forward-compatible.
            continue
        records.append(record)
    return sorted(records, key=lambda item: (
        item["query"]["cpe_name"], item.get("kind", "cve"), item.get("id", "")
    ))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a UTF-8 JSONL snapshot; UTF-8 BOM is accepted."""
    return parse_jsonl(Path(path).read_text(encoding="utf-8-sig"))


def select_cpe_records(
    records: Iterable[dict[str, Any]], cpe_names: Iterable[str]
) -> dict[str, Any]:
    """Validate unfiltered completion evidence; filtered results never certify all CVEs."""
    cpes = sorted(set(cpe_names))
    if not cpes or not all(isinstance(cpe, str) and cpe.startswith("cpe:2.3:") for cpe in cpes):
        raise ValueError("cpe_names must contain explicit CPE 2.3 names")
    rows = [row for row in records
            if isinstance(row.get("query"), dict) and set(row["query"]) == {"cpe_name"}]
    completions: dict[str, int] = {}
    for row in rows:
        if row.get("kind") == "query_complete" and row.get("query", {}).get("cpe_name") in cpes:
            cpe = row["query"]["cpe_name"]
            count = row["cve_count"]
            if cpe in completions and completions[cpe] != count:
                raise ValueError(f"conflicting completion records for {cpe}")
            completions[cpe] = count
    missing = sorted(set(cpes) - set(completions))
    if missing:
        return {"status": "not_measured", "reason": "missing_query_completion",
                "cpe_names": cpes, "missing_cpe_names": missing}
    mismatched: list[str] = []
    for cpe in cpes:
        observed = len({
            row["id"] for row in rows
            if row.get("kind", "cve") == "cve"
            and row.get("query", {}).get("cpe_name") == cpe
        })
        if completions[cpe] != observed:
            mismatched.append(cpe)
    if mismatched:
        return {"status": "not_measured", "reason": "completion_count_mismatch",
                "cpe_names": cpes, "mismatched_cpe_names": sorted(mismatched)}
    cve_ids = sorted({
        row["id"] for row in rows
        if row.get("kind", "cve") == "cve"
        and row.get("query", {}).get("cpe_name") in cpes
    })
    return {"status": "measured", "cpe_names": cpes,
            "cve_count": len(cve_ids), "cve_ids": cve_ids}


def _split_cpe_components(cpe_str: str) -> list[str]:
    parts = []
    current: list[str] = []
    escaped = False
    for char in cpe_str:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            current.append(char)
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        raise ValueError("Invalid CPE 2.3 name: trailing escape")
    parts.append("".join(current))
    return parts


def _unescape_cpe_value(value: str) -> str:
    res: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            res.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            res.append(char)
    if escaped:
        res.append("\\")
    return "".join(res)


# NISTIR 7695 Figure 6-3: wildcards occur only at the edges; quoted
# punctuation is data, including an escaped colon, backslash, '*' or '?'.
_CPE_QUOTABLE = "\\*?!\"#$%&'()+,/:;<=>@[]^`{|}~"
_CPE_AVSTRING = re.compile(
    r"(?:\*|\?+)?(?:[A-Za-z0-9_.-]|\\[" + re.escape(_CPE_QUOTABLE)
    + r"])+(?:\*|\?+)?|[*-]"
)


def parse_cpe_name(cpe_name: str) -> dict[str, Any]:
    """Validate CPE 2.3 formatted-string syntax and expose display attributes.

    Attribute strings are unescaped for display, NOT for identity comparison.
    ``raw_attributes`` preserves every original field: e.g. ``*`` (ANY), ``-``
    (NA), and ``\\*`` (literal asterisk) remain distinguishable there. This is
    neither a WFN unbinder nor a CPE applicability/matching implementation.
    Invalid input raises ValueError; no CPE dictionary/network lookup is made.
    """
    if not isinstance(cpe_name, str) or not cpe_name.startswith("cpe:2.3:"):
        raise ValueError("Invalid CPE 2.3 name: must start with 'cpe:2.3:'")
    parts = _split_cpe_components(cpe_name)
    if len(parts) != 13 or parts[0] != "cpe" or parts[1] != "2.3":
        raise ValueError(
            f"Invalid CPE 2.3 format: expected 11 attributes after 'cpe:2.3:', got {len(parts) - 2}"
        )
    keys = (
        "part", "vendor", "product", "version", "update", "edition",
        "language", "sw_edition", "target_sw", "target_hw", "other",
    )
    raw = dict(zip(keys, parts[2:]))
    for key, value in raw.items():
        if key == "part":
            valid = value.lower() in ("a", "o", "h", "*", "-")
        elif key == "language":
            valid = value in ("*", "-") or re.fullmatch(
                r"[A-Za-z]{2,3}(?:-(?:[A-Za-z]{2}|[0-9]{3}))?", value
            ) is not None
        else:
            valid = _CPE_AVSTRING.fullmatch(value) is not None
        if not valid:
            raise ValueError(f"Invalid CPE 2.3 {key}: {value!r}")
    result: dict[str, Any] = {key: _unescape_cpe_value(val) for key, val in raw.items()}
    part_types = {"a": "application", "o": "operating_system", "h": "hardware"}
    result["part_type"] = part_types.get(result["part"].lower(), "unknown")
    result["raw_attributes"] = raw
    return result


def suggest_cpe_names(
    target: str, candidates: Iterable[str], *, n: int = 3, cutoff: float = 0.6
) -> list[str]:
    """Return at most n unique, syntactically valid CPE spelling suggestions.

    Uses difflib.get_close_matches on the complete original strings. Different
    vendors, products, versions, or wildcard scopes may rank highly. A score
    is textual similarity, NOT confidence, identity, or vulnerability evidence.
    Callers must verify candidates and explicitly choose an exact CPE before
    querying NVD. No automatic replacement, CVE lookup or JSONL mutation occurs.
    Wildcards are compared as text, never expanded. Invalid targets/parameters
    raise ValueError; malformed/non-string candidates are skipped.
    """
    parse_cpe_name(target)
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise ValueError("n must be a positive integer")
    if isinstance(cutoff, bool) or not isinstance(cutoff, (int, float)) or not 0 <= cutoff <= 1:
        raise ValueError("cutoff must be a number between 0 and 1")
    cand_list = []
    seen = set()
    for candidate in candidates:
        try:
            parse_cpe_name(candidate)
        except ValueError:
            continue
        if candidate not in seen:
            seen.add(candidate)
            cand_list.append(candidate)
    return difflib.get_close_matches(target, cand_list, n=n, cutoff=cutoff)


def read_ini(path: str = "config.ini") -> list[str]:
    config = configparser.ConfigParser()
    if not config.read(path, encoding="utf-8"):
        raise FileNotFoundError(path)
    if "cpeName" not in config:
        raise ValueError(f"{path}: missing [cpeName] section")
    return [value.strip() for _, value in config["cpeName"].items() if value.strip()]


def _record(cpe: str, record: dict[str, Any], *, severity: str | None = None, metrics: str | None = None) -> str:
    query = _query(cpe, severity, metrics)
    kind = "filtered_cve" if "filters" in query else "cve"
    return json.dumps({**record, "schema": SCHEMA_VERSION, "kind": kind, "query": query}, ensure_ascii=False, sort_keys=True)


def _completion_record(cpe: str, cve_count: int, *, severity: str | None = None, metrics: str | None = None) -> str:
    """Emit completion only for the explicitly recorded request scope."""
    query = _query(cpe, severity, metrics)
    kind = "filtered_query_complete" if "filters" in query else "query_complete"
    return json.dumps(
        {"schema": SCHEMA_VERSION, "kind": kind, "query": query, "cve_count": cve_count},
        ensure_ascii=False, sort_keys=True,
    )

def _positive_timeout(value: str) -> float:
    """argparse type: per-request socket timeout in seconds."""
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number of seconds"
        ) from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError(
            "timeout must be a positive finite number of seconds"
        )
    return number


def _requested_format(tokens: list[str]) -> str:
    """Read a canonical --format value even when later parsing fails."""
    value = "text"
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            break
        if token == "--format":
            if index + 1 < len(tokens):
                value = tokens[index + 1]
            index += 2
            continue
        if token.startswith("--format="):
            value = token.split("=", 1)[1]
        index += 1
    return value if value in ("text", "json") else "text"


def _status_code(value: object) -> int:
    if value is None:
        return EXIT_OK
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return EXIT_USAGE


def _report_failure(fmt: str, message: str, code: int, *, error: str) -> int:
    """Print a text line or one nvd-cli-error/1 object. Return ``code``."""
    if fmt == "json":
        payload = {
            "category": "usage" if code == EXIT_USAGE else "runtime",
            "error": error,
            "exit_code": code,
            "message": message,
            "schema": ERROR_SCHEMA,
            "status": "error",
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    else:
        print(f"error: {message}", file=sys.stderr)
    return code


class _AgentArgumentParser(argparse.ArgumentParser):
    """Flag errors can emit JSON while text mode keeps the usage summary."""

    def error(self, message: str) -> None:
        if _requested_format(getattr(self, "cli_argv", [])) == "json":
            _report_failure("json", message, EXIT_USAGE, error="usage")
            self.exit(EXIT_USAGE)
        super().error(message)


def _build_parser() -> _AgentArgumentParser:
    parser = _AgentArgumentParser(
        prog="nvd_nist_known_vulns.py",
        description=(
            "Fetch known CVEs from the NVD CVE API 2.0 for CPE 2.3 names "
            "and write nvd-cve-summary/1 JSONL."
        ),
        epilog=(
            "exit status:\n"
            "  0  success, including a CPE query that returns zero CVEs\n"
            "  1  the NVD request failed, or --output could not be published\n"
            "  2  usage or local input error (flags, config file, or CPE list)\n"
            "\n"
            "--format json writes one nvd-cli-error/1 object to stderr on failure and\n"
            "omits progress lines. Success records stay JSONL on stdout or --output.\n"
            "--format text (the default) writes error: lines for input and runtime\n"
            "failures. Flag mistakes also include the usage summary."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Do not print per-CPE progress lines on stderr. Errors are still reported.",
    )
    parser.add_argument(
        "--config",
        default="config.ini",
        help=(
            "UTF-8 INI file with a [cpeName] section, used only when --cpe is omitted. "
            "Default: config.ini. A missing, unreadable, invalid, or empty CPE list exits 2."
        ),
    )
    parser.add_argument(
        "--cpe",
        action="append",
        dest="cpes",
        help=(
            "One CPE 2.3 name to query. Repeat for multiple names. "
            "Values are not split on commas. When any --cpe is present, --config is not read."
        ),
    )
    parser.add_argument(
        "--output",
        help=(
            "Write JSONL to this UTF-8 path, replacing it only after a finished run. "
            "Default: stdout. A failed run leaves an existing file unchanged. "
            "An output path that cannot be published exits 1."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=_positive_timeout,
        default=30.0,
        metavar="SECONDS",
        help="Positive finite per-request socket timeout in seconds. Default: 30.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help=(
            "Failure report on stderr. text (default) prints error: lines for input and "
            "runtime failures. json prints one nvd-cli-error/1 object and no progress lines. "
            "Success output is always JSONL."
        ),
    )
    parser.add_argument(
        "--cvss-v3-severity",
        choices=("LOW", "MEDIUM", "HIGH", "CRITICAL"),
        help=(
            "Optional NVD cvssV3Severity filter on CVE API 2.0: "
            "LOW, MEDIUM, HIGH, or CRITICAL. Filtered output uses filtered_cve records."
        ),
    )
    parser.add_argument(
        "--cvss-v3-metrics",
        help=(
            "Optional NVD cvssV3Metrics filter: a partial or full CVSS v3 vector. "
            "Blank values are rejected. The value is trimmed and uppercased."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    tokens = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    parser.cli_argv = tokens
    try:
        args = parser.parse_args(tokens)
    except SystemExit as exc:
        return _status_code(exc.code)
    temp_path: Path | None = None
    stream: Any = sys.stdout
    try:
        try:
            scope = _query("scope", args.cvss_v3_severity, args.cvss_v3_metrics).get("filters", {})
            severity = scope.get("cvss_v3_severity")
            metrics = scope.get("cvss_v3_metrics")
            if args.cpes:
                cpes: list[str] = []
                for entry in args.cpes:
                    item_clean = entry.strip()
                    if item_clean and item_clean not in cpes:
                        cpes.append(item_clean)
            else:
                cpes = read_ini(args.config)
            if not cpes:
                raise ValueError("No CPE names specified")
        except (OSError, ValueError, configparser.Error) as exc:
            return _report_failure(args.format, str(exc), EXIT_USAGE, error=type(exc).__name__)
        try:
            if args.output:
                target = Path(args.output)
                handle = tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=target.parent,
                    prefix=target.name + ".",
                    suffix=".tmp",
                    delete=False,
                )
                stream = handle
                temp_path = Path(handle.name)
            for cpe in cpes:
                if not args.silent and args.format != "json":
                    print(f"Fetching NVD CVEs for {cpe}", file=sys.stderr)
                records = fetch_cves(
                    cpe,
                    api_key=os.environ.get("NVD_API_KEY"),
                    timeout=args.timeout,
                    cvss_v3_severity=severity,
                    cvss_v3_metrics=metrics,
                )
                for record in records:
                    print(_record(cpe, record, severity=severity, metrics=metrics), file=stream)
                print(
                    _completion_record(cpe, len(records), severity=severity, metrics=metrics),
                    file=stream,
                )
            if args.output:
                stream.close()
                Path(temp_path).replace(args.output)
                temp_path = None
            return EXIT_OK
        except (OSError, RuntimeError, HTTPException, ValueError) as exc:
            return _report_failure(args.format, str(exc), EXIT_RUNTIME, error=type(exc).__name__)
    finally:
        if args.output and stream is not sys.stdout and not stream.closed:
            stream.close()
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
