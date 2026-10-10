"""Mermaid SVG preprocessing: source retention, fail closed and pipeline handoff."""
from pathlib import Path
from types import SimpleNamespace
import pytest
import mermaid_svg
import pptx_pipeline


def test_mermaid_to_svg_preserves_source_and_uses_local_image(monkeypatch, tmp_path):
    source = "Before\n```mermaid\nflowchart LR\n A --> B\n```\nAfter\n"
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: "/fake/mmdc")
    def fake_run(command, **kwargs):
        Path(command[command.index("-o") + 1]).write_text("<svg></svg>", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(mermaid_svg.subprocess, "run", fake_run)
    transformed, images = mermaid_svg.render_mermaid(source, tmp_path, mmdc="mmdc")
    assert len(images) == 1
    assert images[0].is_file()
    assert "```mermaid" not in transformed
    assert "![Diagram 1 h:480](./mermaid-" in transformed
    assert transformed.startswith("Before\n") and transformed.endswith("\nAfter\n")
    assert source == "Before\n```mermaid\nflowchart LR\n A --> B\n```\nAfter\n"


def test_missing_mmdc_fails_explicitly(monkeypatch, tmp_path):
    monkeypatch.setattr(mermaid_svg.shutil, "which", lambda binary: None)
    with pytest.raises(RuntimeError, match="not installed"):
        mermaid_svg.render_mermaid("```mermaid\nA-->B\n```", tmp_path)


def test_pipeline_opt_in_uses_svg_and_preserves_original(monkeypatch, tmp_path):
    source = "```mermaid\nflowchart LR\n A --> B\n```\n"
    seen = {}
    def fake_render(raw, directory, *, mmdc):
        assert raw == source
        return "# Diagram\n", [directory / "mermaid-1.svg"]
    def fake_convert(path, output, *, marp, allow_local_files=False):
        assert allow_local_files
        seen["prepared"] = Path(path).read_text(encoding="utf-8")
        return {"slides": 1}
    monkeypatch.setattr(pptx_pipeline, "render_mermaid", fake_render)
    monkeypatch.setattr(pptx_pipeline, "convert", fake_convert)
    monkeypatch.setattr(pptx_pipeline, "inspect", lambda path: {"slides": []})
    result = pptx_pipeline.run(text=source, output=tmp_path / "out.pptx", mmdc="mmdc")
    assert seen["prepared"] == "# Diagram\n"
    assert result["conversion"]["mermaid_svg_count"] == 1
