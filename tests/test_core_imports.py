"""Kept prototypes must import without the retired model/UI dependencies."""
from pathlib import Path
import subprocess
import sys


def test_all_root_prototypes_import_without_site_packages():
    root = Path(__file__).resolve().parents[1]
    names = sorted(path.stem for path in root.glob('*.py'))
    result = subprocess.run(
        [sys.executable, '-S', '-c',
         'import importlib; ' + '; '.join(f'importlib.import_module({name!r})' for name in names)],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
