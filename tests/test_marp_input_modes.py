"""Input-mode tests without requiring Marp or a browser."""
import io
import json
from pathlib import Path

import pytest
import pptx_pipeline


@pytest.mark.parametrize("mode", ["file", "text", "stdin"])
def test_input_modes_share_converter(monkeypatch, tmp_path, capsys, mode):
    captured = []
    def fake_convert(source, output, *, marp):
        content = Path(source).read_text(encoding="utf-8")
        captured.append(content)
        return {"source": str(source), "output": str(output), "slides": 1, "backend": "marp"}
    monkeypatch.setattr(marp_pptx, "convert", fake_convert)
    output = tmp_path / "out.pptx"
    source = tmp_path / "sample.md"
    source.write_text("# Hello\n", encoding="utf-8")
    if mode == "file":
        args = [str(source), "-o", str(output)]
    elif mode == "text":
        args = ["--text", "# Hello\n", "-o", str(output)]
    else:
        monkeypatch.setattr(pptx_pipeline.sys, "stdin", io.StringIO("# Hello\n"))
        args = ["-", "-o", str(output)]
    pptx_pipeline.main(args)
    assert captured == ["# Hello\n"]
    result = json.loads(capsys.readouterr().out)
    assert result["conversion"]["slides"] == 1
    assert result["conversion"]["source"] == (str(source) if mode == "file" else mode if mode == "stdin" else "inline")


def test_empty_stdin_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(pptx_pipeline.sys, "stdin", io.StringIO(" \n"))
    with pytest.raises(SystemExit) as exc:
        pptx_pipeline.main(["-", "-o", str(tmp_path / "out.pptx")])
    assert exc.value.code == 2


from pptx_pipeline import read_markdown_input


def test_file_mode(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text("# テスト\n", encoding="utf-8")
    assert read_markdown_input(source=path) == ("# テスト\n", str(path))


def test_inline_mode():
    assert read_markdown_input(text="# Hello\n") == ("# Hello\n", "inline")


def test_stdin_mode():
    assert read_markdown_input(source="-", stdin=io.StringIO("# Input\n")) == (
        "# Input\n", "stdin")


@pytest.mark.parametrize("kwargs", [{}, {"source": "sample.md", "text": "# Both"}])
def test_invalid_mode_selection(kwargs):
    with pytest.raises(ValueError, match="exactly one"):
        read_markdown_input(**kwargs)
