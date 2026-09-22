"""Regression checks for the static MCP Stub Explorer page."""

from pathlib import Path
import unittest


PAGE = Path(__file__).resolve().parents[1] / "docs" / "mcp-stub.html"


class McpStubPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_uses_canonical_repository_catalog(self):
        self.assertIn(
            "https://raw.githubusercontent.com/myon-bioinformatics/"
            "myon-bioinformatics.github.io/main/api/repos.json",
            self.html,
        )

    def test_repository_catalog_fetch_avoids_stale_cache(self):
        self.assertIn('cache:"no-store"', self.html)
        self.assertIn("?t=${Date.now()}", self.html)

    def test_query_searches_public_repository_fields(self):
        for field in ("name", "description", "language", "topics", "readmeSummary"):
            self.assertIn(f'"{field}"', self.html)
        self.assertIn(
            "JSON.stringify(publicItem(x)).toLowerCase().includes(query)",
            self.html,
        )


if __name__ == "__main__":
    unittest.main()
