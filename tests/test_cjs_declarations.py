"""Every Node API (*.cjs that exports something) has a .d.cts declaring exactly its exports.

Names only; CI type-checks the declarations themselves with tsc. CLI-only scripts
(studio/raster.cjs, studio/render.cjs) run on load and export nothing, so they are
never required here and must not have a declaration.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALL = sorted(p for p in [*ROOT.glob("*.cjs"), *ROOT.glob("studio/*.cjs"), *ROOT.glob("scripts/*.cjs")])
MODULES = [p for p in ALL if "module.exports" in p.read_text(encoding="utf-8")]
SCRIPTS = [p for p in ALL if p not in MODULES]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_declarations_match_exports():
    script = "process.stdout.write(JSON.stringify(process.argv.slice(1).map(f => Object.keys(require(f)))))"
    exports = json.loads(subprocess.run(["node", "-e", script, *map(str, MODULES)], capture_output=True, text=True,
                                        timeout=60, check=True).stdout)
    for script_path in SCRIPTS:
        assert not script_path.with_suffix(".d.cts").exists(), f"{script_path.name} is a CLI script"
    checked = 0
    for module, names in zip(MODULES, exports):
        types = module.with_suffix(".d.cts")
        assert types.exists(), f"{module.relative_to(ROOT)} exports {names} but has no {types.name}"
        declared = set(re.findall(r"^export (?:function|const) (\w+)", types.read_text(encoding="utf-8"), re.M))
        assert declared == set(names), module.name
        checked += 1
    assert checked >= 4
