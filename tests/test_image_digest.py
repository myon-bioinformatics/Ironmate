"""image_digest: any rows x cols of images with a status -> one small self-contained page."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import image_digest as digest
from browser_matrix import encode_png

ROOT = Path(__file__).resolve().parents[1]


def png(path, w, h, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_png(w, h, bytes(color) * (w * h)))


def spec(**extra):
    return {"schema": "ironmate-image-digest-input/1", "title": "Run 1", "rows": ["home", "hub"],
            "cols": ["Linux-chromium-desktop", "macOS-webkit-iphone"], "meta": {"build": "abc123", "link": "https://example.test/run"},
            "cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "s/home-l.png", "status": "pass"},
                      {"row": "home", "col": "macOS-webkit-iphone", "image": "s/home-i.png", "status": "fail",
                       "notes": ["320px:overlap"]},
                      {"row": "hub", "col": "Linux-chromium-desktop", "status": "pass"}], **extra}


@pytest.fixture
def base(tmp_path):
    png(tmp_path / "s/home-l.png", 384, 800, (200, 30, 30, 255))
    png(tmp_path / "s/home-i.png", 1152, 1992, (30, 30, 200, 255))
    return tmp_path


def test_one_page_with_thumbnails_statuses_and_summary(base, tmp_path):
    page, summary, info = digest.build(spec(), base)
    assert info["tile"] == [64, 128] and info["fits"] and info["statuses"] == {"fail": 1, "pass": 2}
    assert page.count("data:image/png;base64,") == 2 and 'class="s-fail"' in page and "not run" in page
    assert "build abc123" in page and 'href="https://example.test/run"' in page and "<script" not in page
    assert summary.startswith("<!-- ironmate-image-digest -->\n### Run 1")
    assert "2/4 passed; build abc123. [Link](https://example.test/run)" in summary
    assert "| home | 1/2 | macOS-webkit-iphone (320px:overlap) |" in summary
    assert "| hub | 1/2 | macOS-webkit-iphone (not run) |" in summary
    digest.write(tmp_path / "out", page, summary, info)
    assert json.loads((tmp_path / "out/digest.json").read_text())["bytes"] == len(page.encode())
    with pytest.raises(ValueError, match="new or empty"):
        digest.write(tmp_path / "out", page, summary, info)


def test_thumbnails_are_quartered_until_the_page_fits(tmp_path):
    import random
    random.seed(1)
    noise = bytes(random.randrange(256) if i % 4 != 3 else 255 for i in range(256 * 512 * 4))  # incompressible
    (tmp_path / "n.png").write_bytes(encode_png(256, 512, noise))
    rows = [f"r{i}" for i in range(4)]
    big = {"schema": "ironmate-image-digest-input/1", "rows": rows, "cols": ["c"],
           "cells": [{"row": r, "col": "c", "image": "n.png", "status": "pass"} for r in rows]}
    _, _, roomy = digest.build(big, tmp_path, max_bytes=1_000_000)
    _, _, tight = digest.build(big, tmp_path, max_bytes=60_000)
    assert roomy["tile"] == [64, 128] and roomy["bytes"] > 60_000
    assert tight["tile"] == [32, 64] and tight["fits"]  # one halving each way = a quarter of the pixels


@pytest.mark.parametrize("change", [
    {"schema": "x"}, {"rows": []}, {"rows": ["a", "a"]}, {"cols": ["\x01"]},
    {"cells": [{"row": "nope", "col": "Linux-chromium-desktop"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "../etc/passwd"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "/abs.png"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop", "status": "Pass!"}]},
    {"cells": [{"row": "home", "col": "Linux-chromium-desktop"}, {"row": "home", "col": "Linux-chromium-desktop"}]},
    {"meta": {"link": "javascript:alert(1)"}}, {"title": ""},
])
def test_invalid_input_is_rejected(base, change):
    with pytest.raises(ValueError):
        digest.build(spec(**change), base)


def test_escaping(base):
    page, summary, _ = digest.build(spec(title="<b>t</b>", rows=["<i>", "hub"],
                                         cells=[{"row": "<i>", "col": "Linux-chromium-desktop", "status": "pass",
                                                 "notes": ["<script>"]}]), base)
    assert "<i>" not in page.split("</style>")[1] and "&lt;script&gt;" in page


def test_cli_and_node_entry_point(base, tmp_path, capsys):
    (base / "input.json").write_text(json.dumps(spec()), encoding="utf-8")
    assert digest.main([str(base / "input.json"), "--out", str(tmp_path / "cli")]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] == 2
    assert digest.main([str(base / "input.json"), "--out", str(tmp_path / "x"), "--tile", "big"]) == 2
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    run = subprocess.run(["node", "--test", "tests/image_digest.test.cjs"], cwd=ROOT, capture_output=True, text=True,
                         env={**__import__("os").environ, "DIGEST_PNG": str(base / "s/home-l.png")}, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
