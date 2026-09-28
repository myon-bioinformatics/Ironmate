"""Stdlib-only consumer for nvd-cve-summary/1 JSONL records.

Ironmate intentionally does not infer package names to CPEs.  Callers provide an
explicit repository-to-CPE manifest and feed normalized records produced by the
nvd_nist_known_vulns adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "nvd-cve-summary/1"
MANIFEST_SCHEMA = "ironmate-security-cpe/1"


def load_cpe_manifest(text: str) -> dict[str, list[str]]:
    """Parse an explicit repo -> CPE manifest; reject ambiguous/invalid entries."""
    data = json.loads(text)
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
    """Validate and deterministically order normalized NVD JSONL records."""
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(record, dict) or record.get("schema") != SCHEMA:
            raise ValueError(f"unsupported NVD record at line {line_number}")
        cve_id = record.get("id")
        query = record.get("query")
        cpe = query.get("cpe_name") if isinstance(query, dict) else None
        if not isinstance(cve_id, str) or not cve_id.startswith("CVE-") or not isinstance(cpe, str):
            raise ValueError(f"incomplete NVD record at line {line_number}")
        records.append(record)
    return sorted(records, key=lambda item: (item["query"]["cpe_name"], item["id"]))


def security_metadata(repository: str, manifest: dict[str, list[str]], records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build deterministic repository security metadata from explicit CPE evidence."""
    cpes = manifest.get(repository)
    if cpes is None:
        return {"status": "not_measured", "schema": SCHEMA, "reason": "no_explicit_cpe_mapping"}
    allowed = set(cpes)
    matched = [record for record in records if record.get("query", {}).get("cpe_name") in allowed]
    matched.sort(key=lambda item: (item["query"]["cpe_name"], item["id"]))
    return {
        "status": "measured",
        "schema": SCHEMA,
        "cpe_names": cpes,
        "cve_count": len(matched),
        "cve_ids": [item["id"] for item in matched],
    }


def load_path(path: str | Path) -> list[dict[str, Any]]:
    return parse_nvd_jsonl(Path(path).read_text(encoding="utf-8"))
