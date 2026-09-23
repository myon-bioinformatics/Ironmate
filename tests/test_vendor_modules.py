"""Integration checks for pinned vendored sibling utilities."""

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.build_web_ui_consumer_examples import (
    ASCII_ARTIST_SHA,
    MARKDOWN_SHA,
    WEB_UI_SHA,
    build_documents,
)
from vendor import ascii_artist, markdown


ROOT = Path(__file__).resolve().parents[1]

class VendorModuleIntegrationTest(unittest.TestCase):
    def test_vendor_ascii_artist_smoke(self):
        self.assertEqual(ascii_artist.generate_square(2), "**\n**")
        self.assertTrue(hasattr(ascii_artist, "to_web_ui_v1_html"))

    def test_vendor_markdown_smoke(self):
        self.assertTrue(hasattr(markdown, "markdown_to_web_ui_v1"))
        html = markdown.markdown_to_web_ui_v1(
            "# Hello\n",
            title="Ironmate",
            theme="modern",
        )
        self.assertIn('class="ui-page"', html)
        self.assertIn('class="ui-panel"', html)

    def test_builder_direct_execution_resolves_vendor(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_web_ui_consumer_examples.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("index.html", "markdown.html", "ascii.html"):
            self.assertTrue((ROOT / "docs" / "consumer-v1" / name).exists(), name)

    def test_generated_consumer_examples_use_v1_contract_and_pins(self):
        documents = build_documents()
        self.assertEqual(set(documents), {"index.html", "markdown.html", "ascii.html"})
        for name, html in documents.items():
            self.assertIn('data-ui-theme="modern"', html, name)
            self.assertIn('class="ui-page"', html, name)
            self.assertIn(f"web-ui@{WEB_UI_SHA}", html, name)

        provenance = (
            f"web-ui={WEB_UI_SHA} "
            f"markdown={MARKDOWN_SHA} ascii_artist={ASCII_ARTIST_SHA}"
        )
        self.assertIn(provenance, documents["markdown.html"])
        self.assertIn(provenance, documents["ascii.html"])
        self.assertIn('class="ui-output"', documents["ascii.html"])

        index = documents["index.html"]
        self.assertIn('class="ui-grid"', index)
        self.assertGreaterEqual(index.count('class="ui-card"'), 2)
        self.assertIn('href="./markdown.html"', index)
        self.assertIn('href="./ascii.html"', index)

    def test_builder_propagates_invalid_theme(self):
        with self.assertRaises(ValueError):
            build_documents(theme="unknown")

    def test_generated_consumer_examples_remain_text_safe(self):
        markdown_html = markdown.markdown_to_web_ui_v1(
            "body",
            title="<unsafe>",
        )
        ascii_html = ascii_artist.to_web_ui_v1_html(
            "<unsafe> & text",
            title="<ascii>",
        )
        self.assertIn("&lt;unsafe&gt;", markdown_html)
        self.assertNotIn("<unsafe>", markdown_html)
        self.assertIn("&lt;unsafe&gt; &amp; text", ascii_html)
        self.assertIn("&lt;ascii&gt;", ascii_html)


if __name__ == "__main__":
    unittest.main()
