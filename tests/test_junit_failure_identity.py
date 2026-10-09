"""Contract tests for the pinned shared xprobe JUnit importer."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def xprobe():
    path = ROOT / "build/shared/xprobe.py"
    data = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert blob == "dbc5b7d55005d6288c072a7612584d6170c216f4"
    spec = importlib.util.spec_from_file_location("issue58_xprobe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("junit", [False, True])
def test_real_child_failure_evidence(tmp_path, junit, xprobe):
    """Real pytest producer; classification/redaction uses the shared importer."""
    (tmp_path / "test_controlled.py").write_text('''import sys
import pytest


@pytest.mark.parametrize("expected", ["SECRET_PARAM_ONE", "SECRET_PARAM_TWO"])
def test_wrong_expectation(expected):
    print("SECRET_STDOUT")
    print("SECRET_STDERR", file=sys.stderr)
    assert "actual" == expected, "SECRET_MESSAGE"

@pytest.fixture
def wrong_setup():
    assert "actual_setup" == "SECRET_SETUP"

def test_setup(wrong_setup): pass

def test_pass():
    assert "actual" == "actual"

@pytest.mark.skip(reason="SECRET_SKIP")
def test_skip(): pass
''', encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, "-m", "pytest", "-q"]
    if junit:
        command += ["--junitxml=junit.xml", "-o", "junit_logging=all"]
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True,
                            text=True, timeout=30)
    directory = None
    destination = os.environ.get("IRONMATE_FAILURE_EVIDENCE") if junit else None
    if destination:
        directory = ROOT / destination
        directory.mkdir(parents=True)  # Reject reuse rather than mix old evidence.
        (directory / "child-exit.json").write_text(
            json.dumps({"returncode": result.returncode}) + "\n", encoding="utf-8")
        if (tmp_path / "junit.xml").exists():
            shutil.copyfile(tmp_path / "junit.xml", directory / "junit.xml")
    if junit:
        xml = (tmp_path / "junit.xml").read_text(encoding="utf-8")
        report = xprobe.cases_from_junit(
            xml, repository="myon-bioinformatics/Ironmate",
            commit_sha=None, report_id="controlled-child")
        compact = xprobe.corpus_to_json(report["cases"], jsonl=True)
        if directory is not None:
            (directory / "failures.jsonl").write_text(compact, encoding="utf-8")
        assert report["truncated"] is False
        assert sorted((r["value"]["test"], r["value"]["kind"]) for r in report["cases"]) == [
            ("test_setup", "error"),
            ("test_wrong_expectation", "failure"),
            ("test_wrong_expectation", "failure")]
        assert all(r["context"]["commit_sha"] is None for r in report["cases"])
        assert all(token in xml for token in (
            "SECRET_PARAM_ONE", "SECRET_PARAM_TWO", "SECRET_MESSAGE",
            "SECRET_SETUP", "SECRET_STDOUT", "SECRET_STDERR"))
        assert "SECRET_" not in compact
        assert "Traceback" not in compact
    assert result.returncode == 1
    assert "2 failed, 1 passed, 1 skipped, 1 error" in result.stdout


def test_workflow_keeps_suite_failure_and_exact_reports(tmp_path):
    import yaml

    jobs = yaml.load((ROOT / '.github/workflows/mcp-tests.yml').read_text(),
                     Loader=yaml.BaseLoader)['jobs']
    steps = jobs['test']['steps']
    suite = next(s for s in steps if s.get('name') == 'Run default pytest suite (exclude heavy tests)')
    assert 'continue-on-error' not in jobs['test']
    assert all('continue-on-error' not in s for s in steps)
    assert suite['if'] == "${{ !cancelled() && steps.compile.outcome == 'success' }}"
    compile_index = next(i for i, s in enumerate(steps) if s.get('id') == 'compile')
    unittest_index = next(i for i, s in enumerate(steps) if 'python -m unittest ' in s.get('run', ''))
    assert compile_index < unittest_index < steps.index(suite)
    # Run the actual workflow command; reject wrappers that hide pytest's rc=1.
    executable = tmp_path / 'python'
    for rc in (0, 1):
        executable.write_text(f'#!/bin/sh\nexit {rc}\n', encoding='utf-8')
        executable.chmod(0o755)
        env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
        result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', suite['run']],
                                cwd=tmp_path, env=env, timeout=10)
        assert result.returncode == rc
    reports = []
    for name in ('Preserve raw suite JUnit', 'Preserve controlled child evidence'):
        upload = next(s for s in steps if s.get('name') == name)
        assert upload['if'] == 'always()'
        assert upload['with']['if-no-files-found'] == 'error'
        path = upload['with']['path']
        reports.append(upload['with']['name'] + '/' +
                       ('junit.xml' if path.endswith('/') else Path(path).name))
    collector = jobs['failure-identity']
    assert collector['needs'] == ['test', 'marp-integration']
    assert collector['if'] == 'always()'
    assert collector['uses'].endswith('@4dfda95d6573250477f991a0421fa6acb9bc0258')
    marp_steps = jobs['marp-integration']['steps']
    marp_upload = next(s for s in marp_steps if s.get('name') == 'Preserve Marp JUnit')
    assert marp_upload['if'] == 'always()'
    assert marp_upload['with']['if-no-files-found'] == 'warn'
    reports.append(marp_upload['with']['name'] + '/' + Path(marp_upload['with']['path']).name)
    assert json.loads(collector['with']['expected-reports']) == reports
    assert collector['with']['artifact-pattern'] == 'junit-*'
