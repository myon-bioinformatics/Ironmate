import json
import subprocess
from pathlib import Path
import sys

import pytest

from repository_metadata_generator import record_from_checkout, write_metadata


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_checkout_generator_writes_equivalent_json_and_jsonl(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial metadata fixture")

    record = record_from_checkout(root, "octo/demo", env={})
    json_path, jsonl_path = write_metadata(record, tmp_path / "out")

    assert json.loads(json_path.read_text(encoding="utf-8")) == record
    assert json.loads(jsonl_path.read_text(encoding="utf-8")) == record
    assert jsonl_path.read_text(encoding="utf-8").count("\n") == 1
    assert record["head"]["sha"] == _git(root, "rev-parse", "HEAD")
    assert record["head"]["branch"] == "main"
    assert record["measurements"] == {
        "github_reported_size_bytes": None,
        "working_tree_bytes": None,
        "release_artifact_bytes": None,
    }


def test_checkout_generator_rejects_non_repository(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        record_from_checkout(tmp_path, "octo/demo")


def test_generator_cli_runs_from_outside_repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "cli metadata fixture")

    source_root = Path(__file__).resolve().parents[1]
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    for name in ("repository_metadata_generator.py", "repository_metadata_contract.py"):
        (vendor_dir / name).write_bytes((source_root / name).read_bytes())
    generator = vendor_dir / "repository_metadata_generator.py"
    out = tmp_path / "out"
    subprocess.run(
        [
            sys.executable,
            "-S",
            str(generator),
            "--repository",
            "octo/demo",
            "--root",
            str(root),
            "--output-dir",
            str(out),
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads((out / "repository-metadata.json").read_text(encoding="utf-8"))[
        "repository"
    ]["full_name"] == "octo/demo"
    assert (out / "repository-metadata.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_checkout_generator_prefers_ci_branch_name(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "branch metadata fixture")

    record = record_from_checkout(
        root,
        "octo/demo",
        env={"GITHUB_HEAD_REF": "feat/portable-metadata"},
    )
    assert record["head"]["branch"] == "feat/portable-metadata"


def test_checkout_generator_accepts_optional_measurements_and_tooling(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "enriched metadata fixture")

    record = record_from_checkout(
        root,
        "octo/demo",
        env={},
        working_tree_bytes=1234,
        release_artifact_bytes=5678,
        tooling={"python": "3.12"},
    )
    assert record["measurements"]["working_tree_bytes"] == 1234
    assert record["measurements"]["release_artifact_bytes"] == 5678
    assert record["tooling"] == {"python": "3.12"}

def test_checkout_generator_uses_ref_name_when_head_ref_is_empty(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "ref metadata fixture")

    record = record_from_checkout(
        root,
        "octo/demo",
        env={"GITHUB_HEAD_REF": "", "GITHUB_REF_NAME": "release/test"},
    )
    assert record["head"]["branch"] == "release/test"


def test_checkout_generator_labels_detached_head(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "detached metadata fixture")
    sha = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "--detach", sha)

    record = record_from_checkout(root, "octo/demo", env={})
    assert record["head"]["sha"] == sha
    assert record["head"]["branch"] == "detached"

def test_checkout_generator_keeps_head_identity_coherent_across_commits(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("first\\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "first metadata fixture")
    first_sha = _git(root, "rev-parse", "HEAD")

    (root / "README.md").write_text("second\\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "second metadata fixture")
    second_sha = _git(root, "rev-parse", "HEAD")

    record = record_from_checkout(
        root,
        "octo/demo",
        env={"GITHUB_SHA": first_sha},
    )

    assert first_sha != second_sha
    assert record["head"]["sha"] == second_sha
    assert record["head"]["timestamp"] == _git(root, "show", "-s", "--format=%cI", second_sha)
    assert record["head"]["subject"] == "second metadata fixture"


def test_git_forces_utf8_log_output_and_decoding(monkeypatch, tmp_path):
    import repository_metadata_generator

    observed = {}

    class Result:
        stdout = "日本語 commit — ✓\n"

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return Result()

    monkeypatch.setattr(repository_metadata_generator.subprocess, "run", fake_run)

    assert repository_metadata_generator.git(
        "show", "-s", "--format=%s", "HEAD", cwd=tmp_path
    ) == "日本語 commit — ✓"
    assert observed["command"][:3] == [
        "git", "-c", "i18n.logOutputEncoding=UTF-8"
    ]
    assert observed["kwargs"]["encoding"] == "utf-8"
    assert observed["kwargs"]["text"] is True

