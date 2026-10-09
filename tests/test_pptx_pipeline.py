"""Pipeline contract tests without invoking a browser or installing Node."""
from pathlib import Path
import pytest
import pptx_pipeline

def test_pipeline_reuses_conversion_and_inspection(monkeypatch, tmp_path):
    seen = {}
    def fake_convert(source, output, *, marp):
        seen["markdown"] = Path(source).read_text(encoding="utf-8")
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": [{"status": "unknown"}]})
    result = pptx_pipeline.run(text="# Hello\n", output=tmp_path / "slide.pptx")
    assert seen["markdown"] == "# Hello\n"
    assert result["inspection"]["slides"][0]["status"] == "unknown"

def test_mermaid_source_is_preserved(monkeypatch, tmp_path):
    fence = chr(96) * 3
    source = fence + "mermaid\nflowchart LR\n A[Start] --> B[End]\n" + fence + "\n"
    captured = []
    def fake_convert(path, output, *, marp):
        captured.append(Path(path).read_text(encoding="utf-8"))
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": []})
    pptx_pipeline.run(text=source, output=tmp_path / "diagram.pptx")
    assert captured == [source]

def test_empty_input_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        pptx_pipeline.run(text=" ", output=tmp_path / "slide.pptx")
