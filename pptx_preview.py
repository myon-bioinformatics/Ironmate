"""Chromium HTML/PDF preview adapter; this does not render edited PPTX files."""
import hashlib
import importlib.metadata
import math
import sys
from pathlib import Path


def render_preview_html(html, directory, *, expected_slides, sha, run_id, timeout=15000):
    """Print/capture Marp HTML, not a rendering of the edited PPTX.

    Uses existing Chromium and the checked-in shared browser_evidence validator.
    The caller owns a new directory; a failure must not publish a success report.
    """
    html, directory = Path(html).resolve(), Path(directory).resolve()
    if not html.is_file() or not directory.is_dir():
        raise ValueError('existing HTML and output directory required')
    if type(expected_slides) is not int or not 1 <= expected_slides <= 100:
        raise ValueError('expected_slides must be 1..100')
    if (not isinstance(sha, str) or len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha)
            or not isinstance(run_id, str) or not run_id.strip()):
        raise ValueError('full Git SHA and nonempty run ID required')
    if type(timeout) is not int or not 100 <= timeout <= 60000:
        raise ValueError('timeout must be 100..60000 milliseconds')
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
    from vendor.browser_evidence import record
    shots = directory / 'slides'
    shots.mkdir()  # No stale image reuse.
    entries = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.set_default_timeout(timeout)
            page.goto(html.as_uri(), wait_until='load', timeout=timeout)
            page.emulate_media(media='print')
            page.wait_for_function("document.fonts.status === 'loaded' && Array.from(document.images).every(i => i.complete)", timeout=timeout)
            if not page.evaluate("Array.from(document.images).every(i => i.naturalWidth > 0)"):
                raise ValueError('preview contains a broken image')
            slides = page.locator('body > svg[data-marpit-svg]')
            count = slides.count()
            if count != expected_slides or not 1 <= count <= 100:
                raise ValueError('Marp HTML and final PPTX slide counts must agree (1..100)')
            for index in range(count):
                slide = slides.nth(index)
                view_box = [float(v) for v in (slide.get_attribute('viewBox') or '').split()]
                if (len(view_box) != 4 or any(not math.isfinite(v) for v in view_box)
                        or not all(1 <= v <= 4096 for v in view_box[2:])):
                    raise ValueError('Marp SVG must provide a bounded positive viewBox')
                width, height = [round(v) for v in view_box[2:]]
                # Bare Marp print SVGs use viewport units. Match their viewBox
                # rather than capturing viewport-shaped letterboxing.
                page.set_viewport_size({'width': width, 'height': height})
                image = shots / f'slide-{index + 1:03d}.png'
                slide.screenshot(path=str(image), animations='disabled', timeout=timeout)
                entry = record('playwright', image, directory, run_id=run_id, head_sha=sha)
                entry['viewport'] = {'width': width, 'height': height}
                entries.append(entry)
            pdf = directory / 'preview.pdf'
            page.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True)
            if len(PdfReader(pdf, strict=True).pages) != expected_slides:
                raise ValueError('preview PDF and final PPTX slide counts must agree')
            result = {'stage': 'complete', 'project': 'chromium-marp-preview',
                      'renderer': 'Chromium print of Marp HTML', 'browser_version': browser.version,
                      'playwright_version': importlib.metadata.version('playwright'),
                      'slides': count, 'pdf_pages': expected_slides, 'captures': entries,
                      'pdf_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                      'html_sha256': hashlib.sha256(html.read_bytes()).hexdigest(),
                      'is_final_pptx_render': False, 'native_pptx_edits_reflected': False,
                      'visual_review': 'pending'}
        finally:
            already_failed = sys.exc_info()[0] is not None
            try:
                browser.close()
            except Exception:
                if not already_failed:
                    raise
    return result
