"""The committed README preview must be exactly what grid_preview.py generates (no drift)."""
import subprocess, sys
from pathlib import Path

import grid_preview
import photo_grid

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / 'docs' / 'pixel-grid-preview.png'


def test_committed_preview_matches_generator():
    data = grid_preview.png()
    assert data == grid_preview.png()
    assert SHEET.read_bytes() == data, 'regenerate: python -S grid_preview.py -o docs/pixel-grid-preview.png --force'


def test_preview_is_small_and_decodes():
    w, h, rows = photo_grid.decode_png(SHEET.read_bytes())
    assert (w, h) == (grid_preview.build()['width'] * 3, grid_preview.build()['height'] * 3)
    assert SHEET.stat().st_size < 64 * 1024


def test_cli_refuses_overwrite(tmp_path):
    out = tmp_path / 'p.png'
    run = lambda *a: subprocess.run([sys.executable, '-S', 'grid_preview.py', '-o', str(out), *a],
                                    cwd=ROOT, capture_output=True)
    assert run().returncode == 0 and out.read_bytes() == SHEET.read_bytes()
    assert run().returncode == 2
    assert run('--force').returncode == 0
