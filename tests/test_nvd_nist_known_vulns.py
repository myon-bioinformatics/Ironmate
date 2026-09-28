import hashlib
import importlib.util
import unittest
from pathlib import Path


VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "nvd_nist_known_vulns.py"
UPSTREAM_COMMIT = "986e17192442b84adfae8e434ab4bf32bf2347af"
UPSTREAM_VENDOR_BLOB = "16028101be84f6c1b9dd05afb8199280e721f069"


def git_blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


class NvdNistKnownVulnsVendorTest(unittest.TestCase):
    def test_vendored_file_name_matches_upstream(self):
        self.assertEqual(VENDOR.name, "nvd_nist_known_vulns.py")

    def test_vendored_snapshot_matches_upstream_blob(self):
        self.assertEqual(git_blob_sha(VENDOR), UPSTREAM_VENDOR_BLOB)

    def test_vendored_module_keeps_upstream_schema(self):
        spec = importlib.util.spec_from_file_location("vendored_nvd_nist_known_vulns", VENDOR)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.SCHEMA_VERSION, "nvd-cve-summary/1")


if __name__ == "__main__":
    unittest.main()
