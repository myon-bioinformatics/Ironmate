# test_studio_workspace.py
# __all__: 0
"""Browser-independent workspace contract and HTML control regression."""
import re, shutil, subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

__all__ = []
ROOT = Path(__file__).resolve().parents[1]


class _Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.setdefault(attrs["id"], []).append(tag)


def test_studio_html_contains_unique_controls_used_by_initialization():
    parser = _Controls()
    parser.feed((ROOT / "studio/index.html").read_text())
    script = (ROOT / "studio/studio.js").read_text()
    required = set(re.findall(r'\$\("([a-z][a-z0-9-]*)"\)', script))
    assert required
    assert all(len(parser.ids.get(name, [])) == 1 for name in required)
    for name in ("save", "save-workspace", "trim-history"):
        assert parser.ids[name] == ["button"]
    assert parser.ids["open-workspace"] == ["input"]


def test_shared_workspace_contracts_in_node():
    if not shutil.which("node"):
        pytest.skip("Node.js required for browser-independent workspace contracts")
    result = subprocess.run(["node", "--test", "tests/studio_workspace.test.cjs"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
