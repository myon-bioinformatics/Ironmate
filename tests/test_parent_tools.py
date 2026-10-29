# test_parent_tools.py
# __all__: 0
"""Offline compatibility of canonical parent tools with adjacent vendored GHI."""
__all__ = []

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"


def test_parent_tools_match_recorded_bytes():
    entries = json.loads((ROOT / "vendor.lock.json").read_text())["files"]
    for entry in entries:
        if entry["repository"] == "myon-bioinformatics/myon-bioinformatics":
            data = (ROOT / entry["destination"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
            assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == entry["blob_sha"]


def test_gh_ops_help_is_standalone():
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "gh_ops.py"), "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "git-push" in result.stdout


def test_git_push_dry_run_uses_actual_adjacent_identity_without_network(tmp_path):
    # A deliberately unusable remote and guarded real Git runner keep this offline.
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True,
                              text=True, check=True, timeout=15)
    git("init", "--initial-branch=refresh")
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "--allow-empty", "-m", "fixture")
    git("remote", "add", "origin", "https://invalid.invalid/never/pushed.git")
    head = git("rev-parse", "HEAD").stdout.strip()
    code = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import gh_ops
assert pathlib.Path(gh_ops.gh_identity.__file__).resolve() == pathlib.Path(sys.argv[1], 'gh_identity.py').resolve()
actual_run = gh_ops.gh_identity._git_run
calls = []
def local_only(cwd, args, **kwargs):
    assert args[0] in {'branch', 'check-ref-format', 'rev-parse', 'remote'}
    assert kwargs.get('inherit_auth') is False
    calls.append(args[0])
    return actual_run(cwd, args, **kwargs)
gh_ops.gh_identity._git_run = local_only
receipt = gh_ops.git_push(cwd=sys.argv[2], write=False, timeout=10)
assert calls == ['branch', 'check-ref-format', 'rev-parse', 'remote']
print(json.dumps(receipt))
"""
    result = subprocess.run([sys.executable, "-S", "-c", code, str(VENDOR), str(tmp_path)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["ok"] and receipt["dry_run"]
    assert receipt["pushed"] is False
    assert receipt["head_sha"] == head
    assert receipt["branch"] == "refresh"
    assert receipt["mutation_status"] == receipt["verification_status"] == "not_attempted"
    assert "invalid.invalid" not in result.stdout
    assert not git("for-each-ref", "refs/remotes/").stdout


def test_gh_workflow_invalid_inputs_remain_private_and_fail_closed():
    marker = "private-test-input-not-a-real-secret"
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "gh_workflow.py"),
                             "owner/repo", "ci.yml", "--inputs", marker],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "preflight_failed"
    assert receipt["error"] == "invalid_argument"
    assert receipt["hint"]
    assert marker not in result.stdout + result.stderr


def test_ci_status_help_exposes_opt_in_options():
    # Help is offline; actual CI observation has a separately tracked pre-existing
    # vendored GHI lookup issue and is not claimed to be validated here.
    result = subprocess.run([sys.executable, "-S", str(VENDOR / "ci_status.py"), "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "--explain" in result.stdout
    assert "--ci-check" in result.stdout
