"""Integration checks for pinned vendored sibling utilities."""

import unittest

from scripts.build_web_ui_consumer_examples import (
    ASCII_ARTIST_SHA,
    MARKDOWN_SHA,
    WEB_UI_SHA,
    build_documents,
)
from vendor import ascii_artist, markdown


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

    def test_generated_consumer_examples_use_v1_contract_and_pins(self):
        documents = build_documents()
        self.assertEqual(set(documents), {"index.html", "markdown.html", "ascii.html"})
        for name, html in documents.items():
            self.assertIn('data-ui-theme="modern"', html, name)
            self.assertIn('class="ui-page"', html, name)
            self.assertIn(f"web-ui@{WEB_UI_SHA}", html, name)

        self.assertIn(MARKDOWN_SHA, documents["markdown.html"])
        self.assertIn(ASCII_ARTIST_SHA, documents["ascii.html"])
        self.assertIn('class="ui-output"', documents["ascii.html"])

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
