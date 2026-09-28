import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

from security_nvd import load_cpe_manifest, load_path, parse_nvd_jsonl, security_metadata


CPE = "cpe:2.3:a:example:example:1:*:*:*:*:*:*:*"
CPE2 = "cpe:2.3:a:example:example:2:*:*:*:*:*:*:*"
FIXTURE = Path(__file__).parent / "fixtures" / "nvd_summary.jsonl"
VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "nvd_nist_known_vulns.py"
UPSTREAM_COMMIT = "986e17192442b84adfae8e434ab4bf32bf2347af"
UPSTREAM_VENDOR_BLOB = "16028101be84f6c1b9dd05afb8199280e721f069"
UPSTREAM_SAMPLE_BLOB = "eb859fde7af74b59944c0aa8ee5797ca1f943a3b"


def git_blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()



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
        # Exact sample_result.txt snapshot from nvd_nist_known_vulns at UPSTREAM_COMMIT.
        self.assertEqual(git_blob_sha(FIXTURE), UPSTREAM_SAMPLE_BLOB)
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

    def test_completion_count_mismatch_is_not_measured(self):
        rows = [cve("CVE-2026-0001"), complete(CPE, 3)]
        result = security_metadata("owner/repo", {"owner/repo": [CPE]}, rows)
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["reason"], "completion_count_mismatch")
        self.assertEqual(result["mismatched_cpe_names"], [CPE])

    def test_parser_rejects_unknown_kind_invalid_id_and_bad_completion_count(self):
        bad = [
            {"schema":"nvd-cve-summary/1","kind":"future","query":{"cpe_name":CPE}},
            {"schema":"nvd-cve-summary/1","kind":"cve","query":{"cpe_name":CPE},"id":"GHSA-x"},
            {"schema":"nvd-cve-summary/1","kind":"query_complete","query":{"cpe_name":CPE},"cve_count":True},
            {"schema":"nvd-cve-summary/1","kind":"query_complete","query":{"cpe_name":CPE},"cve_count":-1},
        ]
        for record in bad:
            with self.subTest(record=record), self.assertRaises(ValueError):
                parse_nvd_jsonl(json.dumps(record))

    def test_manifest_bom_is_accepted(self):
        text = "\ufeff" + json.dumps({"schema":"ironmate-security-cpe/1","repositories":{"owner/repo":[CPE]}})
        self.assertEqual(load_cpe_manifest(text)["owner/repo"], [CPE])

    def test_vendored_nvd_snapshot_matches_upstream_blob(self):
        self.assertEqual(git_blob_sha(VENDOR), UPSTREAM_VENDOR_BLOB)

    def test_vendored_producer_output_round_trips_through_consumer(self):
        spec = importlib.util.spec_from_file_location("vendored_nvd", VENDOR)
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        record = {
            "id":"CVE-2026-0001","description":"left\u2028right","cwe":[],
            "cvss_v4":None,"cvss_v3":None,"cvss_v2":None,
            "published":None,"last_modified":None,"source_identifier":None,
        }
        with tempfile.TemporaryDirectory() as d:
            cfg=Path(d)/"c.ini"
            cfg.write_text("[cpeName]\na="+CPE+"\n",encoding="utf-8")
            output=io.StringIO()
            from unittest import mock
            with mock.patch.object(producer,"fetch_cves",return_value=[record]), contextlib.redirect_stdout(output):
                self.assertEqual(producer.main(["--silent","--config",str(cfg)]),0)
        rows=parse_nvd_jsonl(output.getvalue())
        result=security_metadata("owner/repo",{"owner/repo":[CPE]},rows)
        self.assertEqual(result["status"],"measured")
        self.assertEqual(result["cve_ids"],["CVE-2026-0001"])

    def test_unmapped_repository_is_not_measured(self):
        result = security_metadata("owner/unmapped", {}, [complete()])
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["reason"], "no_explicit_cpe_mapping")


if __name__ == "__main__":
    unittest.main()
