"""Regression checks for the static MCP Stub Explorer page."""

from html.parser import HTMLParser
from pathlib import Path
import unittest


PAGE = Path(__file__).resolve().parents[1] / "docs" / "mcp-stub.html"
WEB_UI_PIN = "dfdbb26a76f71b147483f212ec49ca677384b936"


class StylesheetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        values = dict(attrs)
        if values.get("rel") == "stylesheet" and values.get("href"):
            self.stylesheets.append(values["href"])


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
        self.assertIn(f"web-ui@{WEB_UI_PIN}/css/tokens.css", self.html)

        parser = StylesheetParser()
        parser.feed(self.html)
        expected_suffixes = [
            "/css/tokens.css",
            "/css/base.css",
            "/css/components.css",
            "/css/stub.css",
            "/css/themes/modern.css",
        ]
        self.assertEqual(
            [next(href for href in parser.stylesheets if href.endswith(suffix)) for suffix in expected_suffixes],
            parser.stylesheets,
        )

        # This list covers the semantic classes required by the current v1 consumer contract.
        # Additions may extend the list without implying that every future ui-* class is mandatory.
        for class_name in (
            "ui-page",
            "ui-panel",
            "ui-grid",
            "ui-card",
            "ui-button",
            "ui-input",
            "ui-muted",
            "ui-title",
            "ui-output",
        ):
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
