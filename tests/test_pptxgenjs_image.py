"""PptxGenJS image embedding (exercises the pinned image-size override)."""
import base64
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 1x1 PNG
_MIN_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD0lEQVQImWNgYGBgAAAABQABDavlc2QAAAABJRU5ErkJggg=='
)

_NODE_SCRIPT = """
const PptxGenJS = require('pptxgenjs');
(async () => {
  const pptx = new PptxGenJS();
  const slide = pptx.addSlide();
  slide.addImage({ path: process.argv[1], x: 1, y: 1, w: 2, h: 2 });
  await pptx.writeFile({ fileName: process.argv[2] });
})();
"""


def test_pptxgenjs_embeds_image_with_overridden_image_size(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node.js required for pptxgenjs image-size check')
    if not (ROOT / 'node_modules' / 'pptxgenjs' / 'package.json').is_file():
        pytest.skip('pinned pptxgenjs is not installed; run npm ci from the repository root')
    image = tmp_path / 'dot.png'
    image.write_bytes(_MIN_PNG)
    deck = tmp_path / 'deck.pptx'
    run = subprocess.run(
        ['node', '-e', _NODE_SCRIPT, str(image), str(deck)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stderr
    assert deck.is_file() and deck.stat().st_size > 0
    with zipfile.ZipFile(deck) as archive:
        media = [name for name in archive.namelist() if name.startswith('ppt/media/') and not name.endswith('/')]
    assert media, 'expected at least one embedded media part'
