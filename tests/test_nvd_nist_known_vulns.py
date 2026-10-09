"""Smoke-check the retained upstream NVD consumer without network access."""
import json
from vendor import nvd_nist_known_vulns as nvd


def test_nvd_consumer_reads_completion_record():
    row = {"schema": nvd.SCHEMA_VERSION, "kind": "query_complete",
           "query": {"cpe_name": "cpe:2.3:a:example:example:1:*:*:*:*:*:*:*"}, "cve_count": 0}
    assert nvd.parse_jsonl(json.dumps(row)) == [row]


def test_upstream_fixture_remains_consumable():
    from pathlib import Path
    rows = nvd.read_jsonl(Path(__file__).parent / "fixtures/nvd_summary.jsonl")
    assert rows[-1]["kind"] == "query_complete"
