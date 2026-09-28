import json
import tempfile
import unittest
from pathlib import Path

from security_nvd import load_cpe_manifest, load_path, parse_nvd_jsonl, security_metadata


CPE = "cpe:2.3:a:example:example:1:*:*:*:*:*:*:*"
CPE2 = "cpe:2.3:a:example:example:2:*:*:*:*:*:*:*"
FIXTURE = Path(__file__).parent / "fixtures" / "nvd_summary.jsonl"


def cve(cve_id, cpe=CPE, description=None):
    return {"schema": "nvd-cve-summary/1", "kind": "cve", "query": {"cpe_name": cpe}, "id": cve_id, "description": description}


def complete(cpe=CPE, count=0):
    return {"schema": "nvd-cve-summary/1", "kind": "query_complete", "query": {"cpe_name": cpe}, "cve_count": count}


class SecurityNvdTest(unittest.TestCase):
    def test_manifest_requires_object_and_explicit_cpe23(self):
        manifest = load_cpe_manifest(json.dumps({"schema": "ironmate-security-cpe/1", "repositories": {"owner/repo": [CPE, CPE]}}))
        self.assertEqual(manifest["owner/repo"], [CPE])
        for invalid in ("[]", '"text"', '{"schema":"ironmate-security-cpe/1","repositories":{"owner/repo":["requests"]}}'):
            with self.assertRaises(ValueError):
                load_cpe_manifest(invalid)

    def test_parser_uses_jsonl_newline_not_unicode_line_separator(self):
        text = json.dumps(cve("CVE-2026-0001", description="left\u2028right"), ensure_ascii=False) + "\n" + json.dumps(complete())
        rows = parse_nvd_jsonl(text)
        self.assertEqual(rows[0]["description"], "left\u2028right")

    def test_fixture_is_consumed_and_has_upstream_shape(self):
        # First line is copied from nvd_nist_known_vulns sample_result.txt at merge 54b689a;
        # second line is the query-completion contract introduced by NVD PR #3.
        rows = load_path(FIXTURE)
        self.assertEqual(rows[0]["id"], "CVE-EXAMPLE-0001")
        self.assertEqual(rows[1]["kind"], "query_complete")

    def test_missing_completion_is_not_measured(self):
        result = security_metadata("owner/repo", {"owner/repo": [CPE]}, [cve("CVE-2026-0001")])
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["reason"], "missing_query_completion")
        self.assertNotIn("cve_count", result)

    def test_zero_cves_requires_positive_completion_evidence(self):
        result = security_metadata("owner/repo", {"owner/repo": [CPE]}, [complete(CPE, 0)])
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["cve_count"], 0)

    def test_all_mapped_cpes_must_be_completed(self):
        result = security_metadata("owner/repo", {"owner/repo": [CPE, CPE2]}, [complete(CPE)])
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["missing_cpe_names"], [CPE2])

    def test_duplicate_cve_across_cpes_is_counted_once(self):
        rows = [cve("CVE-2026-0001", CPE), cve("CVE-2026-0001", CPE2), complete(CPE, 1), complete(CPE2, 1)]
        result = security_metadata("owner/repo", {"owner/repo": [CPE, CPE2]}, rows)
        self.assertEqual(result["cve_count"], 1)
        self.assertEqual(result["cve_ids"], ["CVE-2026-0001"])

    def test_bom_files_are_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "nvd.jsonl"
            path.write_text("\ufeff" + json.dumps(complete()), encoding="utf-8")
            self.assertEqual(load_path(path)[0]["kind"], "query_complete")

    def test_unmapped_repository_is_not_measured(self):
        result = security_metadata("owner/unmapped", {}, [complete()])
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["reason"], "no_explicit_cpe_mapping")


if __name__ == "__main__":
    unittest.main()
