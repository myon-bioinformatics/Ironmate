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

    def test_uses_pinned_web_ui_contract(self):
        self.assertNotIn("<style>", self.html)
        self.assertIn('data-ui-theme="modern"', self.html)
        self.assertIn("web-ui@77ae752599a59e50b6595233f6162a38ebc572b7/css/tokens.css", self.html)
        for stylesheet in ("base.css", "components.css", "stub.css", "themes/modern.css"):
            self.assertIn(stylesheet, self.html)
        for class_name in ("ui-page", "ui-panel", "ui-grid", "ui-card", "ui-button", "ui-input"):
            self.assertIn(class_name, self.html)

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
