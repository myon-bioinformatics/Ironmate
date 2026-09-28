import json
import unittest

from security_nvd import load_cpe_manifest, parse_nvd_jsonl, security_metadata


CPE = "cpe:2.3:a:example:widget:1.0:*:*:*:*:*:*:*"


def record(cve, cpe=CPE):
    return {"schema": "nvd-cve-summary/1", "query": {"cpe_name": cpe}, "id": cve}


class SecurityNvdTest(unittest.TestCase):
    def test_manifest_requires_explicit_cpe23(self):
        manifest = load_cpe_manifest(json.dumps({
            "schema": "ironmate-security-cpe/1",
            "repositories": {"owner/repo": [CPE, CPE]},
        }))
        self.assertEqual(manifest["owner/repo"], [CPE])
        with self.assertRaises(ValueError):
            load_cpe_manifest('{"schema":"ironmate-security-cpe/1","repositories":{"owner/repo":["requests"]}}')

    def test_jsonl_validates_schema_and_sorts(self):
        text = "\n".join(json.dumps(record(cve)) for cve in ("CVE-2026-0002", "CVE-2026-0001"))
        rows = parse_nvd_jsonl(text)
        self.assertEqual([row["id"] for row in rows], ["CVE-2026-0001", "CVE-2026-0002"])
        with self.assertRaises(ValueError):
            parse_nvd_jsonl('{"schema":"other","id":"CVE-2026-1","query":{"cpe_name":"x"}}')

    def test_mapped_repository_is_measured(self):
        manifest = {"owner/repo": [CPE]}
        result = security_metadata("owner/repo", manifest, [record("CVE-2026-0002"), record("CVE-2026-0001")])
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["cve_count"], 2)
        self.assertEqual(result["cve_ids"], ["CVE-2026-0001", "CVE-2026-0002"])

    def test_unmapped_repository_is_not_measured_not_safe(self):
        result = security_metadata("owner/unmapped", {}, [record("CVE-2026-0001")])
        self.assertEqual(result["status"], "not_measured")
        self.assertEqual(result["reason"], "no_explicit_cpe_mapping")
        self.assertNotIn("cve_count", result)


if __name__ == "__main__":
    unittest.main()
