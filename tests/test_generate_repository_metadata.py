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


@pytest.mark.parametrize(
    ("tool", "raw", "expected"),
    [
        ("git", "git version 2.51.0\n", "2.51.0"),
        ("git", "git version 2.51.0.windows.1\n", "2.51.0.windows.1"),
        ("gh", "gh version 2.80.0 (2026-09-01)\nhttps://example.invalid\n", "2.80.0"),
        ("node", "v22.20.0\n", "22.20.0"),
        ("npm", "10.9.3\n", "10.9.3"),
        ("npx", "10.9.3\n", "10.9.3"),
        ("pytest", "9.0.1\n", "9.0.1"),
        ("pytest", "9.0.1+local.2\n", "9.0.1+local.2"),
        ("pytest", "1.0rc1\n", "1.0rc1"),
        ("pytest", "2.0a1\n", "2.0a1"),
        ("pytest", "2024\n", "2024"),
        ("python", "3.14.0rc1\n", "3.14.0rc1"),
    ],
)
def test_normalize_version_output_is_tool_specific(tool, raw, expected):
    import repository_metadata_generator as generator
    assert generator.normalize_version_output(tool, raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "not a version", "https://user:token@example.invalid/x", "3.12\x00oops", "1." + "2" * 40],
)
def test_normalize_version_output_omits_malformed_or_unsafe_values(raw):
    import repository_metadata_generator as generator
    assert generator.normalize_version_output("pytest", raw) is None


def test_command_probe_uses_stdout_then_stderr_only_after_success(monkeypatch):
    import repository_metadata_generator as generator

    monkeypatch.setattr(generator.shutil, "which", lambda name: "/private/bin/" + name)

    class Result:
        returncode = 0
        stdout = ""
        stderr = "node should not parse this"

    def success_stderr(argv, **kwargs):
        assert argv == ["/private/bin/git", "--version"]
        Result.stderr = "git version 2.51.0\n"
        return Result()

    monkeypatch.setattr(generator.subprocess, "run", success_stderr)
    assert generator.observe_command_version("git") == "2.51.0"

    def nonzero(argv, **kwargs):
        Result.returncode = 1
        Result.stdout = ""
        Result.stderr = "git version 9.9.9\n"
        return Result()

    monkeypatch.setattr(generator.subprocess, "run", nonzero)
    assert generator.observe_command_version("git") is None


@pytest.mark.parametrize("error", [OSError("boom"), subprocess.TimeoutExpired(["git"], 1)])
def test_command_probe_failures_are_nonfatal(monkeypatch, error):
    import repository_metadata_generator as generator
    monkeypatch.setattr(generator.shutil, "which", lambda name: "/private/bin/" + name)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(generator.subprocess, "run", fail)
    assert generator.observe_command_version("git") is None


def test_missing_command_and_package_are_omitted(monkeypatch):
    import repository_metadata_generator as generator

    monkeypatch.setattr(generator.shutil, "which", lambda name: None)
    assert generator.observe_command_version("gh") is None

    def missing(name):
        raise generator.importlib_metadata.PackageNotFoundError(name)

    monkeypatch.setattr(generator.importlib_metadata, "version", missing)
    assert generator.observe_package_version("not-installed") is None


def test_collect_portable_tooling_is_collision_safe_and_deterministic(monkeypatch):
    import repository_metadata_generator as generator

    monkeypatch.setattr(generator.platform, "python_version", lambda: "3.14.0")
    monkeypatch.setattr(generator, "observe_command_version", lambda name: {"git": "2.51.0", "node": "22.20.0"}[name])
    monkeypatch.setattr(generator, "observe_package_version", lambda name: {"pytest": "9.0.1"}[name])

    first = generator.collect_portable_tooling(
        commands=("git", "node"), distributions=(("pytest", "pytest"),)
    )
    second = generator.collect_portable_tooling(
        commands=("node", "git"), distributions=(("pytest", "pytest"),)
    )
    assert first == {"python": "3.14.0", "git": "2.51.0", "node": "22.20.0", "pytest": "9.0.1"}
    assert first == second

    with pytest.raises(ValueError, match="exactly one canonical source"):
        generator.collect_portable_tooling(commands=("git",), distributions=(("git", "GitPython"),))
    with pytest.raises(ValueError, match="exactly one canonical source"):
        generator.collect_portable_tooling(distributions=(("python", "python"),))


def test_record_rejects_caller_overlap_with_canonical_tooling(tmp_path, monkeypatch):
    import repository_metadata_generator as generator

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "tooling collision fixture")

    monkeypatch.setattr(
        generator,
        "collect_portable_tooling",
        lambda **kwargs: {"python": "3.14.0"},
    )
    with pytest.raises(ValueError, match="overlaps canonical tooling"):
        generator.record_from_checkout(
            root,
            "octo/demo",
            env={},
            tooling={"python": "3.13.0"},
            include_python_tooling=True,
        )


def test_optional_tooling_failures_do_not_change_checkout_identity(tmp_path, monkeypatch):
    import repository_metadata_generator as generator

    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "identity fixture")

    baseline = generator.record_from_checkout(root, "octo/demo", env={})
    monkeypatch.setattr(generator, "observe_command_version", lambda name: None)
    monkeypatch.setattr(generator.platform, "python_version", lambda: "")
    observed = generator.record_from_checkout(
        root,
        "octo/demo",
        env={},
        tooling_commands=("git", "gh", "node", "npm", "npx"),
    )
    assert observed["tooling"] == {}
    assert observed["head"] == baseline["head"]


def test_caller_overlap_is_rejected_even_when_probe_would_be_omitted(tmp_path, monkeypatch):
    import repository_metadata_generator as generator

    root = tmp_path / "repo-overlap"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "requested ownership fixture")

    called = []
    monkeypatch.setattr(
        generator,
        "observe_command_version",
        lambda name: called.append(name) or None,
    )
    with pytest.raises(ValueError, match="overlaps canonical tooling"):
        generator.record_from_checkout(
            root,
            "octo/demo",
            env={},
            tooling={"git": "9.9.9"},
            tooling_commands=("git",),
        )
    assert called == []


def test_commands_reject_bare_string():
    import repository_metadata_generator as generator

    with pytest.raises(TypeError, match="commands must be a sequence"):
        generator.collect_portable_tooling(commands="git")
