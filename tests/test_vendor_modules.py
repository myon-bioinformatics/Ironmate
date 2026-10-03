"""Integration checks for pinned vendored sibling utilities."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from provenance import git_blob_sha
from python_artifact_provenance import validate_source_header
from scripts.build_web_ui_consumer_examples import (
    ASCII_ARTIST_SHA,
    MARKDOWN_SHA,
    WEB_UI_SHA,
    build_documents,
)
from vendor import ascii_artist, markdown


ROOT = Path(__file__).resolve().parents[1]
ASCII_ARTIST_PROVENANCE = {
    "schema_version": "1.0",
    "source_repository": "myon-bioinformatics/ascii_artist",
    "source_path": "ascii_artist.py",
    "source_commit": "505858627afc7e24dd6deb0a5c118e4d185d391e",
    "blob_sha": "ca46470b4a52293d722d59db0a621fec789c3690",
    "sha256": "a2ea789b38d3f8a3cc15029ec33733d472d25effee3effed795c2519bec249ea",
    "license": {
        "source_path": "LICENSE",
        "vendored_path": "vendor/ascii_artist-LICENSE",
        "blob_sha": "4ec4989b801bf1a3df6184d21f79e6e7ed5931f6",
        "sha256": "15f66204c4a6a1ce0c94f0ed4319ff9400f872e85fd32c95f21695c2f231af59",
    },
}

class VendorModuleIntegrationTest(unittest.TestCase):
    def test_vendor_ascii_artist_source_and_license_provenance(self):
        manifest = json.loads(
            (ROOT / "vendor/ascii_artist.provenance.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest, ASCII_ARTIST_PROVENANCE)
        self.assertEqual(ASCII_ARTIST_SHA, ASCII_ARTIST_PROVENANCE["source_commit"])
        for path, expected in (
            ("vendor/ascii_artist.py", ASCII_ARTIST_PROVENANCE),
            ("vendor/ascii_artist-LICENSE", ASCII_ARTIST_PROVENANCE["license"]),
        ):
            with self.subTest(path=path):
                source = ROOT / path
                self.assertEqual(git_blob_sha(source), expected["blob_sha"])
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), expected["sha256"])

    def test_vendor_ascii_artist_preserves_upstream_header(self):
        source = (ROOT / "vendor/ascii_artist.py").read_text(encoding="utf-8")
        header = validate_source_header(source)
        self.assertEqual(header["base_sha"], "7c21bacfac7b60327b77f9b31a87869ef7838a7e")
        self.assertNotEqual(header["base_sha"], ASCII_ARTIST_SHA)

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
        repository_output = ROOT / "docs" / "consumer-v1"
        repository_output.parent.mkdir(parents=True, exist_ok=True)
        stash = Path(
            tempfile.mkdtemp(
                prefix=".consumer-v1-stash-",
                dir=repository_output.parent,
            )
        )
        stash.rmdir()
        had_repository_output = repository_output.exists()

        if had_repository_output:
            repository_output.rename(stash)

        try:
            with tempfile.TemporaryDirectory() as directory:
                output_dir = Path(directory)
                result = subprocess.run(
                    [
                        sys.executable,
                        "scripts/build_web_ui_consumer_examples.py",
                        "--output-dir",
                        str(output_dir),
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                for name in ("index.html", "markdown.html", "ascii.html"):
                    self.assertTrue((output_dir / name).exists(), name)
                self.assertFalse(
                    repository_output.exists(),
                    "builder wrote outside the requested output directory",
                )
        finally:
            cleanup_error = None
            try:
                if repository_output.exists():
                    shutil.rmtree(repository_output)
            except OSError as exc:
                cleanup_error = exc

            if had_repository_output and stash.exists():
                try:
                    if repository_output.exists():
                        raise RuntimeError(
                            "cannot restore repository output because cleanup failed; "
                            f"original files remain at {stash}"
                        ) from cleanup_error
                    stash.rename(repository_output)
                except OSError as exc:
                    raise RuntimeError(
                        f"could not restore repository output; original files remain at {stash}"
                    ) from exc
            elif stash.exists():
                stash.rmdir()

            if cleanup_error is not None:
                raise RuntimeError(
                    "could not remove unexpected repository output after builder test"
                ) from cleanup_error

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

    def test_web_ui_pin_matches_mcp_stub(self):
        stub = (ROOT / "docs" / "mcp-stub.html").read_text(encoding="utf-8")
        self.assertIn(f"web-ui@{WEB_UI_SHA}/css/tokens.css", stub)
        self.assertIn(f"web-ui contract pinned to {WEB_UI_SHA}", stub)

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
