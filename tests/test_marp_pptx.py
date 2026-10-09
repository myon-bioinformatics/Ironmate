import pytest
from pathlib import Path
from pptx import Presentation
from marp_pptx import convert


def test_missing_marp_is_explicit(tmp_path):
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    with pytest.raises(RuntimeError, match="Marp CLI not installed"):
        convert(source, tmp_path / "sample.pptx", marp="nonexistent-marp-cli-ironmate")


def test_existing_output_is_preserved(tmp_path):
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    output = tmp_path / "sample.pptx"
    output.write_bytes(b"preserved")
    with pytest.raises(ValueError, match="new file"):
        convert(source, output)
    assert output.read_bytes() == b"preserved"


def test_marp_cli_integration_when_enabled(tmp_path):
    import os
    import shutil
    import subprocess
    import sys

    marp = os.environ.get("IRONMATE_MARP_BIN", "marp")
    if os.environ.get("IRONMATE_RUN_MARP_INTEGRATION") != "1":
        pytest.skip("optional Marp integration not enabled")
    if shutil.which(marp) is None:
        pytest.fail("Marp integration requested but executable is missing")
    source = Path(__file__).parent / "fixtures" / "mini_readme.md"
    output = tmp_path / "sample.pptx"
    result = convert(source, output, marp=marp)
    assert result["slides"] >= 1
    assert len(Presentation(output).slides) >= 1
    # Standard Marp PPTX may consist of slide images, not editable text runs.
    # Editing fidelity is assessed separately before integrating a one-liner.
