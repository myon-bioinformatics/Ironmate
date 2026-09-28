"""Stdlib-only consumer for nvd-cve-summary/1 JSONL records.

Ironmate intentionally does not infer package names to CPEs. Callers provide an
explicit repository-to-CPE manifest and positive query-completion evidence from
the nvd_nist_known_vulns adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "nvd-cve-summary/1"
MANIFEST_SCHEMA = "ironmate-security-cpe/1"


def load_cpe_manifest(text: str) -> dict[str, list[str]]:
    """Parse an explicit repo -> CPE manifest; reject ambiguous/invalid entries."""
    data = json.loads(text.lstrip("\ufeff"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be an object")
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported manifest schema: {data.get('schema')!r}")
    repos = data.get("repositories")
    if not isinstance(repos, dict):
        raise ValueError("repositories must be an object")
    result: dict[str, list[str]] = {}
    for repo, cpes in repos.items():
        if not isinstance(repo, str) or not repo or not isinstance(cpes, list):
            raise ValueError("repository names and CPE lists must be explicit")
        if not cpes or not all(isinstance(cpe, str) and cpe.startswith("cpe:2.3:") for cpe in cpes):
            raise ValueError(f"invalid CPE list for {repo!r}")
        result[repo] = sorted(set(cpes))
    return result


def parse_nvd_jsonl(text: str) -> list[dict[str, Any]]:
    """Validate NVD JSONL without treating Unicode line separators as JSONL boundaries."""
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.lstrip("\ufeff").split("\n"), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            raise ValueError(f"unsupported NVD record at line {line_number}")
        query = record.get("query")
        cpe = query.get("cpe_name") if isinstance(query, dict) else None
        if not isinstance(cpe, str):
            raise ValueError(f"incomplete NVD record at line {line_number}")
        kind = record.get("kind", "cve")
        if kind == "cve":
            cve_id = record.get("id")
            if not isinstance(cve_id, str) or not cve_id.startswith("CVE-"):
                raise ValueError(f"incomplete NVD CVE record at line {line_number}")
        elif kind == "query_complete":
            if (
                isinstance(record.get("cve_count"), bool)
                or not isinstance(record.get("cve_count"), int)
                or record["cve_count"] < 0
            ):
                raise ValueError(f"incomplete NVD completion record at line {line_number}")
        else:
            # v1 permits additive record kinds; consumers ignore kinds they do not understand.
            continue
        records.append(record)
    return sorted(records, key=lambda item: (item["query"]["cpe_name"], item.get("kind", "cve"), item.get("id", "")))


def security_metadata(repository: str, manifest: dict[str, list[str]], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build metadata only when every explicitly mapped CPE has completion evidence."""
    cpes = manifest.get(repository)
    if cpes is None:
        return {"status": "not_measured", "schema": SCHEMA, "reason": "no_explicit_cpe_mapping"}
    rows = list(records)
    completed = {
        row["query"]["cpe_name"]
        for row in rows
        if row.get("kind") == "query_complete" and row.get("query", {}).get("cpe_name") in cpes
    }
    missing = sorted(set(cpes) - completed)
    if missing:
        return {
            "status": "not_measured",
            "schema": SCHEMA,
            "reason": "missing_query_completion",
            "cpe_names": cpes,
            "missing_cpe_names": missing,
        }
    completion_counts = {
        row["query"]["cpe_name"]: row["cve_count"]
        for row in rows
        if row.get("kind") == "query_complete" and row.get("query", {}).get("cpe_name") in cpes
    }
    mismatched = []
    for cpe in cpes:
        observed = len({
            row["id"]
            for row in rows
            if row.get("kind", "cve") == "cve"
            and row.get("query", {}).get("cpe_name") == cpe
        })
        if completion_counts.get(cpe) != observed:
            mismatched.append(cpe)
    if mismatched:
        return {
            "status": "not_measured",
            "schema": SCHEMA,
            "reason": "completion_count_mismatch",
            "cpe_names": cpes,
            "mismatched_cpe_names": sorted(mismatched),
        }
    # One CVE can match several CPEs. Repository-level counts are unique by CVE ID.
    cve_ids = sorted({
        row["id"]
        for row in rows
        if row.get("kind", "cve") == "cve"
        and row.get("query", {}).get("cpe_name") in cpes
    })
    return {
        "status": "measured",
        "schema": SCHEMA,
        "cpe_names": cpes,
        "cve_count": len(cve_ids),
        "cve_ids": cve_ids,
    }


def load_path(path: str | Path) -> list[dict[str, Any]]:
    return parse_nvd_jsonl(Path(path).read_text(encoding="utf-8-sig"))
