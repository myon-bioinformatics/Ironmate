import unittest

from repository_metadata import (
    important_file_shas,
    parse_manifest_version,
    parse_python_api,
    readme_digest,
    select_manifest,
    select_python_sources,
)


class RepositoryMetadataTest(unittest.TestCase):
    def test_manifest_versions(self):
        self.assertEqual(
            parse_manifest_version("pyproject.toml", '[project]\nversion = "1.2.3"\n')["value"],
            "1.2.3",
        )
        self.assertEqual(
            parse_manifest_version("package.json", '{"version":"2.0.0"}')["value"],
            "2.0.0",
        )
        self.assertEqual(
            parse_manifest_version("pubspec.yaml", "name: x\nversion: 3.4.5+6\n")["value"],
            "3.4.5+6",
        )

    def test_python_api_prefers_literal_all(self):
        result = parse_python_api(
            '__all__ = ["public_api"]\n'
            'def public_api(): pass\n'
            'def helper(): pass\n'
            'class Thing: pass\n',
            source="module.py",
        )
        self.assertEqual(result["status"], "detected")
        self.assertEqual(result["value"]["exports"], ["public_api"])
        self.assertEqual(result["value"]["export_source"], "__all__")
        self.assertEqual(result["value"]["functions"], ["public_api", "helper"])

    def test_python_api_falls_back_to_public_top_level(self):
        result = parse_python_api(
            "def visible(): pass\ndef _private(): pass\nclass Public: pass\n",
            source="module.py",
        )
        self.assertEqual(result["value"]["exports"], ["visible", "Public"])
        self.assertEqual(result["value"]["export_source"], "public_top_level")

    def test_readme_digest_is_deterministic(self):
        result = readme_digest("# Project\n\nHello **world**.\n\n## Usage\n\n[Docs](https://example.com)")
        self.assertEqual(result["headings"], ["Project", "Usage"])
        self.assertIn("Hello world.", result["excerpt"])
        self.assertIn("Docs", result["excerpt"])

    def test_selection_and_file_shas(self):
        tree = [
            {"type":"blob","path":"README.md","sha":"r","size":10},
            {"type":"blob","path":"pyproject.toml","sha":"p","size":20},
            {"type":"blob","path":"main.py","sha":"m","size":30},
            {"type":"blob","path":"tests/test_main.py","sha":"t","size":40},
        ]
        self.assertEqual(select_manifest(tree), "pyproject.toml")
        self.assertEqual(select_python_sources(tree), ["main.py"])
        files = important_file_shas(tree)
        self.assertEqual(files[0]["path"], "README.md")
        self.assertTrue(any(item["path"] == "pyproject.toml" for item in files))


if __name__ == "__main__":
    unittest.main()
