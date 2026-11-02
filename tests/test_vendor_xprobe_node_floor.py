"""Consumer regression for the canonical single-file xprobe Node contract."""
import shutil
import subprocess

import pytest

from vendor import xprobe


@pytest.mark.parametrize("major", [24, 25])
@pytest.mark.parametrize("explicit", [False, True])
def test_old_node_reports_found_version_without_running_backend(monkeypatch, major, explicit):
    path = "/fake/node"
    probes = []

    def version_probe(command, **kwargs):
        assert tuple(command) == (path, "--version")
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 5.0
        probes.append(command)
        return subprocess.CompletedProcess(command, 0, f"v{major}.0.0\n".encode(), b"")

    def unexpected_backend(*args, **kwargs):
        pytest.fail("a rejected Node runtime must never execute the backend")

    monkeypatch.setattr(shutil, "which", lambda name: path if name == "node" else None)
    monkeypatch.setattr(subprocess, "run", version_probe)
    monkeypatch.setattr(subprocess, "Popen", unexpected_backend)
    monkeypatch.setattr(xprobe, "_NODE_LAUNCH", xprobe._stdlib_node_launch())
    with pytest.raises(RuntimeError, match=rf"Node 26\+.*found Node {major}"):
        xprobe._node_load("yaml-failsafe", "a: 1\n", path if explicit else None, 30)
    assert len(probes) == 1


def test_xprobe_lock_uses_accepted_canonical_source():
    import json
    from pathlib import Path

    lock = json.loads((Path(__file__).resolve().parents[1] / "vendor.lock.json").read_text())
    entry = next(item for item in lock["files"] if item["destination"] == "vendor/xprobe.py")
    assert entry["ref"] == entry["commit"] == "1ffbb7b984075c683690bbe4e9deb06199cdfe94"
    assert entry["blob_sha"] == "7595fe5eb7fd2e375b82e7c702079f6496a3276d"
