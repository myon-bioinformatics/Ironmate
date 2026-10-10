"""Shared Markdown input mode contract for the Marp adapter and pipeline."""
import io
from pathlib import Path

import pytest
from marp_pptx import read_markdown_input


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
