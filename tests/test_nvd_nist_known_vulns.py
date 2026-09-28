import importlib.util
import json
import unittest
from pathlib import Path

from provenance import git_blob_sha
from repository_metadata import load_cpe_manifest, repository_security_metadata


VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "nvd_nist_known_vulns.py"
UPSTREAM_COMMIT = "a3d8f1835e4a82bc6e50682d6a79e22a851c4c91"
UPSTREAM_VENDOR_BLOB = "9daa3938dfa4226198e94273c18af5362c1ccb8b"
CPE = "cpe:2.3:a:example:example:1:*:*:*:*:*:*:*"

SPEC = importlib.util.spec_from_file_location("vendored_nvd_nist_known_vulns", VENDOR)
NVD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NVD)


class NvdNistKnownVulnsVendorTest(unittest.TestCase):
    def test_vendored_file_name_matches_upstream(self):
        self.assertEqual(VENDOR.name, "nvd_nist_known_vulns.py")

    def test_vendored_snapshot_matches_upstream_blob(self):
        self.assertEqual(git_blob_sha(VENDOR), UPSTREAM_VENDOR_BLOB)

    def test_vendored_module_keeps_upstream_schema(self):
        self.assertEqual(NVD.SCHEMA_VERSION, "nvd-cve-summary/1")

    def test_upstream_jsonl_consumer_drives_repository_metadata(self):
        rows = NVD.parse_jsonl("\n".join([
            json.dumps({"schema":NVD.SCHEMA_VERSION,"kind":"cve","query":{"cpe_name":CPE},"id":"CVE-2026-0001"}),
            json.dumps({"schema":NVD.SCHEMA_VERSION,"kind":"query_complete","query":{"cpe_name":CPE},"cve_count":1}),
        ]))
        manifest = load_cpe_manifest(json.dumps({
            "schema":"ironmate-security-cpe/1","repositories":{"owner/repo":[CPE,CPE]}
        }))
        result = repository_security_metadata("owner/repo", manifest, rows, nvd_module=NVD)
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["cve_ids"], ["CVE-2026-0001"])

    def test_unmapped_repository_remains_not_measured(self):
        result = repository_security_metadata("owner/repo", {}, [], nvd_module=NVD)
        self.assertEqual(result["reason"], "no_explicit_cpe_mapping")


if __name__ == "__main__":
    unittest.main()
