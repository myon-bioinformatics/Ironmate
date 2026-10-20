"""The CDN page count uses the same PdfReader call as the preview adapter."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cdn_pypdf_pages as pages  # noqa: E402


def test_one_page_pdf_declares_a_single_page():
    data = pages.one_page_pdf()
    assert data.startswith(b"%PDF-")
    assert b"/Count 1" in data
    assert b"/Type /Page" in data


def test_page_output_ignores_import_origin():
    left = {"pages": 1, "mediabox": ["0", "0", "612", "792"], "version": "6", "pdf_sha256": "a", "origin": "wheel"}
    right = dict(left, origin="installed")
    assert pages.page_output(left) == pages.page_output(right)
    assert pages.page_output(dict(left, pages=2)) != pages.page_output(right)


def test_preview_keeps_playwright_and_the_pypdf_page_call():
    text = (ROOT / "pptx_preview.py").read_text(encoding="utf-8")
    lines = text.splitlines()
    playwright = next(i for i, line in enumerate(lines) if "sync_playwright" in line)
    pypdf = next(i for i, line in enumerate(lines) if line.strip() == "from pypdf import PdfReader")
    assert playwright < pypdf
    assert "len(PdfReader(pdf, strict=True).pages)" in text
    script = (ROOT / "scripts" / "cdn_pypdf_pages.py").read_text(encoding="utf-8")
    assert "len(PdfReader(pdf, strict=True).pages)" in script
    assert "import playwright" not in script


@pytest.mark.skipif(sys.version_info < (3, 11), reason="Ironmate requires Python >= 3.11")
def test_installed_or_path_pypdf_counts_the_synthetic_page(tmp_path):
    pytest.importorskip("pypdf")
    pdf = tmp_path / "one-page.pdf"
    pdf.write_bytes(pages.one_page_pdf())
    observed = pages.observe_pdf(pdf)
    assert observed["pages"] == 1
    assert len(observed["mediabox"]) == 4
    assert observed["pdf_sha256"]
