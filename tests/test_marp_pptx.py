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
    # Inspect actual Open XML elements rather than assuming editable slide text.
    import json
    import zipfile
    from xml.etree import ElementTree as ET

    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
          "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    inspection = []
    with zipfile.ZipFile(output) as archive:
        for index, slide in enumerate(Presentation(output).slides, 1):
            xml = ET.fromstring(archive.read(f"ppt/slides/slide{index}.xml"))
            texts = [n.text or "" for n in xml.findall(".//a:t", ns)]
            pictures = len(xml.findall(".//p:pic", ns))
            shapes = len(xml.findall(".//p:sp", ns))
            editable_runs = sum(len(p.runs) for shape in slide.shapes
                                if shape.has_text_frame for p in shape.text_frame.paragraphs)
            inspection.append({"slide": index, "texts": texts,
                               "pictures": pictures, "shapes": shapes,
                               "editable_runs": editable_runs})
    evidence = tmp_path / "marp-openxml-inspection.json"
    evidence.write_text(json.dumps(inspection, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(inspection) == result["slides"]
    assert all(row["pictures"] + row["shapes"] > 0 for row in inspection)
    # This is observational evidence, not an editability guarantee.

