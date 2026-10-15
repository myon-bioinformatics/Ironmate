"""Regression checks for vendor verification CI wiring."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ".github/workflows/mcp-tests.yml"
PIN = "b000e5967cb7596f6f9f20fe396a686fdc700c16"


def _workflow():
    import yaml

    return yaml.load((ROOT / WORKFLOW).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _lock_files(root=ROOT):
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    assert lock["schema"] == "vendor-lock/1"
    return lock["files"]


def test_vendor_ci_verifies_lock_without_auto_updates():
    ci = _workflow()
    assert {"push", "pull_request"} <= set(ci["on"])
    assert "schedule" not in ci["on"]
    assert "workflow_dispatch" not in ci["on"]
    assert ci.get("permissions", {"contents": "read"}) == {"contents": "read"}
    jobs = ci["jobs"]
    assert "resolve-vendor" not in jobs
    assert "test-locked" not in jobs
    job = jobs["test"]
    assert job["permissions"] == {"contents": "read"}
    assert "continue-on-error" not in job
    steps = job["steps"]
    text = (ROOT / WORKFLOW).read_text(encoding="utf-8")
    assert "vendor_sync.py promote" not in text
    assert "vendor_sync.py update" not in text
    assert "sync_vendor_provenance" not in text
    verify = next(i for i, s in enumerate(steps) if s.get("name") == "Verify checked-in vendor copies")
    recreate = next(
        i for i, s in enumerate(steps) if s.get("name") == "Recreate locked vendor files from GitHub"
    )
    tests = [i for i, s in enumerate(steps) if "pytest " in s.get("run", "")]
    assert tests and verify < recreate < min(tests)
    pins = [
        s["with"]["ref"]
        for s in steps
        if s.get("with", {}).get("repository") == "myon-bioinformatics/myon-bioinformatics"
    ]
    assert pins == [PIN]
    for step in steps:
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"
        assert not any(x in step.get("run", "") for x in ("|| true", "|| :", "set +e", "git push", "git commit", "gh pr"))
        assert "continue-on-error" not in step
    assert not any(x in text for x in ("secrets.", "VENDOR_UPDATE_TOKEN", "VENDOR_UPDATES_ENABLED", "GH_TOKEN"))


def test_canonical_vendor_evidence_membership_is_derived_from_lock():
    lock = json.loads((ROOT / "vendor.lock.json").read_text(encoding="utf-8"))
    destinations = [entry["destination"] for entry in lock["files"]]
    assert len(destinations) == len(set(path.casefold() for path in destinations))
    locked = sorted(["vendor.lock.json", *destinations], key=lambda p: (p.casefold(), p))
    assert set(locked) == {"vendor.lock.json", *(entry["destination"] for entry in lock["files"])}
    assert all((ROOT / path).is_file() for path in locked)


@pytest.mark.parametrize("workflow_path", [WORKFLOW, ".github/workflows/vendor-catalog-audit.yml"])
def test_parent_vendor_sync_checkout_is_pinned(workflow_path):
    text = (ROOT / workflow_path).read_text(encoding="utf-8")
    assert PIN in text
    assert "974da5eb9593df652b132e4b0f1a679f67422566" not in text
    assert "14ef53c8316015d1350e62ff9cce3301103e65a7" not in text


def test_workflow_stages_locked_vendor_evidence(tmp_path):
    lock_path = tmp_path / "vendor.lock.json"
    shutil.copyfile(ROOT / "vendor.lock.json", lock_path)
    for entry in _lock_files():
        dest = tmp_path / entry["destination"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / entry["destination"], dest)
    tools = Path(os.environ.get("IRONMATE_CANONICAL_TOOLS", ROOT / ".vendor-sync-tools"))
    if not (tools / "vendor_stage.py").is_file():
        pytest.skip("parent vendor tools checkout not present")
    steps = _workflow()["jobs"]["test"]["steps"]
    stage = next(s for s in steps if s.get("name") == "Stage canonical vendor evidence")
    assert stage["if"] == "always()"
    command = stage["run"].replace(
        "python -S .vendor-sync-tools/vendor_stage.py",
        shlex.quote(sys.executable) + " -S " + shlex.quote(str(tools / "vendor_stage.py")),
    )
    result = subprocess.run(
        [shutil.which("bash"), "-e", "-c", command],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    output = tmp_path / "build/vendor-evidence-test"
    meta = json.loads((output / "vendor-evidence.json").read_text())
    sources = {"vendor.lock.json"} | {e["destination"] for e in _lock_files()}
    assert meta["kind"] == "locked" and set(meta["locked"]) == sources
    assert meta.get("legacy") == []
    assert set(meta["sha256"]) == sources
    expected = sources | {"vendor-evidence.json"}
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == expected
    for name in sources:
        data = (output / name).read_bytes()
        assert data == (tmp_path / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta["sha256"][name]
