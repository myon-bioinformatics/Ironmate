"""Dependency-free NVD CVE API 2.0 client.

Network requests are globally throttled per process; concurrent callers are not synchronized.
"""
from __future__ import annotations

import argparse
import configparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException, IncompleteRead
import json
import os
from pathlib import Path
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
UNAUTHENTICATED_INTERVAL = 6.0
AUTHENTICATED_INTERVAL = 0.6
MAX_RETRY_DELAY = 60.0
RETRYABLE_HTTP = {429, 500, 502, 503, 504}
_last_request_at: float | None = None


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


def api_call(cpe_name: str, *, start_index: int = 0, results_per_page: int = DEFAULT_RESULTS_PER_PAGE, api_key: str | None = None, timeout: float = 30.0) -> dict[str, Any]:
    query = urlencode({"cpeName": cpe_name, "startIndex": start_index, "resultsPerPage": results_per_page})
    return _request_json(f"{NVD_CVE_API}?{query}", api_key=api_key, timeout=timeout)


def iter_cve_pages(cpe_name: str, *, api_key: str | None = None, timeout: float = 30.0) -> Iterable[dict[str, Any]]:
    start = 0
    expected_total: int | None = None
    while True:
        page = api_call(cpe_name, start_index=start, api_key=api_key, timeout=timeout)
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
            return {
                "version": data.get("version"),
                "base_score": data.get("baseScore"),
                "base_severity": data.get("baseSeverity") or item.get("baseSeverity"),
                "vector": data.get("vectorString"),
                "source": item.get("source"),
                "type": item.get("type"),
            }
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


def fetch_cves(cpe_name: str, *, api_key: str | None = None, timeout: float = 30.0) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for page in iter_cve_pages(cpe_name, api_key=api_key, timeout=timeout):
        records.update(format_cve_data(page))
    return [records[key] for key in sorted(records)]



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
        if kind == "cve":
            cve_id = record.get("id")
            if not isinstance(cve_id, str) or not cve_id.startswith("CVE-"):
                raise ValueError(f"incomplete NVD CVE record at line {line_number}")
        elif kind == "query_complete":
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
    """Validate completion evidence and return deduplicated CVEs for selected CPEs."""
    cpes = sorted(set(cpe_names))
    if not cpes or not all(isinstance(cpe, str) and cpe.startswith("cpe:2.3:") for cpe in cpes):
        raise ValueError("cpe_names must contain explicit CPE 2.3 names")
    rows = list(records)
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


def read_ini(path: str = "config.ini") -> list[str]:
    config = configparser.ConfigParser()
    if not config.read(path, encoding="utf-8"):
        raise FileNotFoundError(path)
    if "cpeName" not in config:
        raise ValueError(f"{path}: missing [cpeName] section")
    return [value.strip() for _, value in config["cpeName"].items() if value.strip()]


def _record(cpe: str, record: dict[str, Any]) -> str:
    return json.dumps({"schema": SCHEMA_VERSION, "kind": "cve", "query": {"cpe_name": cpe}, **record}, ensure_ascii=False, sort_keys=True)


def _completion_record(cpe: str, cve_count: int) -> str:
    """Emit positive evidence that a configured CPE query completed, including zero results."""
    return json.dumps(
        {"schema": SCHEMA_VERSION, "kind": "query_complete", "query": {"cpe_name": cpe}, "cve_count": cve_count},
        ensure_ascii=False,
        sort_keys=True,
    )

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch known CVEs from NVD by CPE.")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--config", default="config.ini")
    parser.add_argument("--output")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    temp_path: Path | None = None
    stream: Any = sys.stdout
    try:
        cpes = read_ini(args.config)
        if args.output:
            target = Path(args.output)
            handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False)
            stream = handle
            temp_path = Path(handle.name)
        for cpe in cpes:
            if not args.silent:
                print(f"Fetching NVD CVEs for {cpe}", file=sys.stderr)
            records = fetch_cves(cpe, api_key=os.environ.get("NVD_API_KEY"), timeout=args.timeout)
            for record in records:
                print(_record(cpe, record), file=stream)
            print(_completion_record(cpe, len(records)), file=stream)
        if args.output:
            stream.close()
            Path(temp_path).replace(args.output)
            temp_path = None
        return 0
    except (OSError, ValueError, RuntimeError, HTTPException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
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
