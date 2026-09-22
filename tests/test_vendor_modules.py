# test_vendor_modules.py
# __all__: 0

__all__ = []

from vendor import ascii_artist, markdown


def test_vendor_ascii_artist_smoke():
    assert ascii_artist.generate_square(2) == "**\n**"


def test_vendor_markdown_smoke(tmp_path):
    path = tmp_path / "sample.md"
    result = markdown.save_markdown("# Hello\n", str(path))
    assert result.startswith("Saved successfully:")
    loaded = markdown.read_markdown(str(path))
    assert loaded["success"] is True
    assert loaded["content"] == "# Hello\n"
