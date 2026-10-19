"""Every top-level Node module (*.cjs) ships a .d.cts with the same exported names."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_every_cjs_has_a_declaration():
    assert {p.stem for p in ROOT.glob('*.cjs')} == {p.name[:-len('.d.cts')] for p in ROOT.glob('*.d.cts')}


def test_declared_names_match_runtime_exports():
    if shutil.which('node') is None:
        pytest.skip('node not installed')
    run = subprocess.run(['node', '--test', 'tests/types.test.cjs'], cwd=ROOT, capture_output=True, text=True,
                         timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
