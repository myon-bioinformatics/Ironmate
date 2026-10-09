from pathlib import Path

import pytest
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches

from pptx_replace import transform


def fixture(tmp_path):
    path = tmp_path / "source.pptx"
    p = Presentation()
    slide = p.slides.add_slide(p.slide_layouts[6])
    shape = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    run = shape.text_frame.paragraphs[0].add_run()
    run.text = "Draft title"
    run.font.color.rgb = RGBColor(255, 0, 0)
    run.font.bold = True
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = RGBColor(255, 255, 255)
    p.save(path)
    return path


def test_dry_run_and_preservation(tmp_path):
    src = fixture(tmp_path)
    dst = tmp_path / "output.pptx"
    rules = [{"operation": "replace_text", "old": "Draft", "new": "Final"}, {"operation": "text_color", "color": "#000000"}]
    preview = transform(src, rules, dry_run=True)
    assert preview["change_count"] == 2
    assert not dst.exists()
    result = transform(src, rules, destination=dst)
    assert result["change_count"] == 2
    original = Presentation(src).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    updated = Presentation(dst).slides[0].shapes[0].text_frame.paragraphs[0].runs[0]
    assert original.text == "Draft title"
    assert updated.text == "Final title"
    assert updated.font.bold is True
    assert updated.font.color.rgb == RGBColor(0, 0, 0)


def test_background_and_no_overwrite(tmp_path):
    src = fixture(tmp_path)
    dst = tmp_path / "out.pptx"
    assert transform(src, [{"operation": "slide_background", "color": "#112233"}], destination=dst)["change_count"] == 1
    assert Presentation(dst).slides[0].background.fill.fore_color.rgb == RGBColor(17, 34, 51)
    with pytest.raises(ValueError, match="new file"):
        transform(src, [{"operation": "replace_text", "old": "none", "new": "x"}], destination=dst)


def test_unsupported_and_zero_match(tmp_path):
    src = fixture(tmp_path)
    assert transform(src, [{"operation": "replace_text", "old": "missing", "new": "x"}], dry_run=True)["change_count"] == 0
    with pytest.raises(ValueError, match="unsupported operation"):
        transform(src, [{"operation": "arrow", "color": "#000000"}], dry_run=True)
