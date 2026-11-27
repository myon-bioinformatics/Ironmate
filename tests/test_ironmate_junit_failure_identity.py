"""Contract tests for the pinned shared xprobe JUnit importer."""

from __future__ import annotations

import hashlib, importlib.util, json, os, shutil, subprocess, sys
from pathlib import Path

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
    destination = os.environ.get("FAILURE_EVIDENCE_DIR") if junit else None
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

    jobs = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(),
                     Loader=yaml.BaseLoader)['jobs']
    steps = jobs['test']['steps']
    suite = next(s for s in steps if s.get('name') == 'Run default pytest suite (exclude heavy tests)')
    assert 'continue-on-error' not in jobs['test']
    assert all('continue-on-error' not in s for s in steps)
    assert suite['if'] == "${{ !cancelled() && steps.compile.outcome == 'success' }}"
    compile_index = next(i for i, s in enumerate(steps) if s.get('id') == 'compile')
    assert compile_index < steps.index(suite)
    # pytest already collects the vendor and repository-hygiene TestCase
    # classes. A separate unittest command would execute those cases twice.
    assert all('python -m unittest ' not in s.get('run', '') for s in steps)
    assert suite['run'] == (
        'uv run --locked python -m pytest -q -m "not heavy and not network" '
        '--junitxml=build/test-results/pytest-3.15.xml'
    )
    # Run the actual workflow command; reject wrappers that hide pytest's rc=1.
    executable = tmp_path / 'uv'
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
    assert collector['needs'] == ['test', 'marp-integration', 'studio-clipboard']
    assert collector['if'] == 'always()'
    assert collector['uses'].endswith('@27c46411c0a07d9b4d0f1ad5751ed1bb9e869b5c')
    marp_steps = jobs['marp-integration']['steps']
    install = next(s for s in marp_steps if s.get('name') == 'Install pinned Node packages and the locked Marp CLI tools')
    assert '--ignore-scripts' in install['run']
    marp_upload = next(s for s in marp_steps if s.get('name') == 'Preserve Marp JUnit')
    assert marp_upload['if'] == 'always()'
    assert marp_upload['with']['if-no-files-found'] == 'error'
    assert marp_upload['with']['path'] == 'build/test-results/marp.xml'
    reports.append(marp_upload['with']['name'] + '/marp.xml')
    assert json.loads(collector['with']['expected-reports'])[:len(reports)] == reports
    assert collector['with']['artifact-pattern'] == 'junit-*'


@pytest.mark.parametrize("workflow", ["ci.yml", "mcp-tests.yml"])
def test_setup_junit_runs_before_tests_and_is_collected(workflow):
    import yaml

    jobs = yaml.load((ROOT / ".github" / "workflows" / workflow).read_text(),
                     Loader=yaml.BaseLoader)["jobs"]
    expected = []
    for job, first_test in (
        ("test", "Verify vendor/pillow_min.py runs standalone under python -S"),
        ("marp-integration", "Run real Markdown to Marp to PPTX integration"),
        ("studio-clipboard", "Verify clipboard ingress in the static Pages build"),
    ):
        steps = jobs[job]["steps"]
        index = next(i for i, step in enumerate(steps) if step.get("name") == first_test)
        record, upload = steps[index - 2:index]
        assert record["name"] == "Record setup JUnit before tests"
        assert upload["name"] == "Preserve setup JUnit before tests"
        assert record["if"] == upload["if"] == "${{ !cancelled() }}"
        assert record["run"].endswith(" " + upload["with"]["path"])
        tracked = [step["id"] for step in steps[:index - 2] if "id" in step]
        assert [line.partition(".outcome")[0].split("steps.", 1)[1]
                for line in record["env"]["SETUP_OUTCOMES"].splitlines()] == tracked
        artifact = upload["with"]["name"]
        filename = Path(upload["with"]["path"]).name
        if job == "studio-clipboard":
            expected.extend(artifact.replace("${{ matrix.browser }}", browser) + "/" + filename
                            for browser in jobs[job]["strategy"]["matrix"]["browser"])
        else:
            expected.append(artifact + "/" + filename)
    collector = jobs["failure-identity"]
    assert collector["needs"] == ["test", "marp-integration", "studio-clipboard"]
    assert json.loads(collector["with"]["expected-reports"])[-len(expected):] == expected


def test_failed_setup_is_imported_as_an_error(tmp_path, xprobe):
    from xml.etree import ElementTree

    result = tmp_path / "setup.xml"
    subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/ci_setup_junit.py"), "setup", str(result)],
        env=dict(os.environ, SETUP_OUTCOMES="uv=success\nApt & fonts=failure\nbrowser=skipped\n"),
        check=True,
    )
    xml = result.read_text()
    suite = ElementTree.fromstring(xml)
    assert suite.attrib == dict(name="setup", tests="3", errors="1", failures="0", skipped="1")
    report = xprobe.cases_from_junit(
        xml, repository="myon-bioinformatics/Ironmate", commit_sha=None, report_id="setup"
    )
    assert [(case["value"]["test"], case["value"]["kind"]) for case in report["cases"]] == [
        ("Apt & fonts", "error")
    ]


@pytest.mark.parametrize("workflow", ["ci.yml", "mcp-tests.yml"])
def test_workflow_uses_locked_marp_tools(workflow):
    import yaml

    config = yaml.load((ROOT / '.github/workflows' / workflow).read_text(),
                       Loader=yaml.BaseLoader)
    jobs = config['jobs']
    assert config['permissions'] == {'contents': 'read'}
    assert jobs['marp-integration']['permissions'] == {'contents': 'read'}
    marp_steps = jobs['marp-integration']['steps']
    install = next(s for s in marp_steps if s.get('name') == 'Install pinned Node packages and the locked Marp CLI tools')
    assert install['run'].splitlines() == [
        'npm ci',
        'npm ci --prefix scripts/marp-tools --ignore-scripts --no-audit --no-fund',
    ]
    assert 'continue-on-error' not in jobs['marp-integration']
    for step in marp_steps:
        assert 'continue-on-error' not in step
        if step.get('uses', '').startswith('actions/checkout@'):
            assert step['with']['persist-credentials'] == 'false'
        if step.get('uses', '').startswith('astral-sh/setup-uv@'):
            assert step['with']['save-cache'] == (
                "${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
            )
        for variable, binary in [('IRONMATE_MARP_BIN', 'marp'),
                                 ('IRONMATE_MMDC_BIN', 'mmdc')]:
            if variable in step.get('env', {}):
                assert step['env'][variable] == f'scripts/marp-tools/node_modules/.bin/{binary}'
                assert marp_steps.index(install) < marp_steps.index(step)
    render = next(s for s in marp_steps if s.get('name') == 'Run real Markdown to Marp to PPTX integration')
    flow = next(s for s in marp_steps if s.get('name') == 'Exercise common JSON flow formats and browser pixel parity')
    assert render['env']['IRONMATE_RUN_MARP_INTEGRATION'] == '1'
    assert render['env']['IRONMATE_RUN_UNO_INTEGRATION'] == '1'
    assert render['env']['IRONMATE_MARP_BIN'].endswith('/.bin/marp')
    assert render['env']['IRONMATE_MMDC_BIN'].endswith('/.bin/mmdc')
    assert flow['env']['IRONMATE_MMDC_BIN'].endswith('/.bin/mmdc')
    assert flow['env']['IRONMATE_RUN_FLOW_INTEGRATION'] == '1'
    assert 'node tests/flow_export_browser.cjs' in flow['run']
    # Do not resolve Mermaid's Puppeteer peer (or anything else) to a floating latest release.
    tools = json.loads((ROOT / 'scripts/marp-tools/package.json').read_text())
    assert tools['dependencies']['puppeteer'] == '25.15.0'
    lock = json.loads((ROOT / 'scripts/marp-tools/package-lock.json').read_text())
    assert lock['packages']['']['dependencies'] == tools['dependencies']
    assert lock['packages']['node_modules/puppeteer']['version'] == '25.15.0'
    root_package = json.loads((ROOT / 'package.json').read_text())
    root_lock = json.loads((ROOT / 'package-lock.json').read_text())
    assert root_package['devDependencies']['playwright'] == '1.64.1'
    assert root_lock['packages']['node_modules/playwright']['version'] == '1.64.1'
    assert 'playwright' not in tools['dependencies']


def test_locked_marp_tools_keep_security_overrides_scoped():
    tools = json.loads((ROOT / 'scripts/marp-tools/package.json').read_text())
    lock = json.loads((ROOT / 'scripts/marp-tools/package-lock.json').read_text())
    assert tools['dependencies']['@marp-team/marp-cli'] == '4.5.1'
    assert tools['dependencies']['@mermaid-js/mermaid-cli'] == '12.2.0'
    assert tools['overrides'] == {
        '@marp-team/marp-cli': {'puppeteer-core': '25.15.0'},
        '@marp-team/marp-core': {'katex': '0.18.10'},
    }
    packages = lock['packages']
    assert packages['']['dependencies'] == tools['dependencies']
    for name, version in (('puppeteer-core', '25.15.0'),
                          ('katex', '0.18.10'), ('zod', '4.6.7')):
        copies = [package for path, package in packages.items()
                  if path.endswith('/node_modules/' + name)
                  or path == 'node_modules/' + name]
        assert copies, f'{name} must remain in the verified toolchain'
        assert all(package['version'] == version for package in copies)
    assert not any(path == 'node_modules/basic-ftp'
                   or path.endswith('/node_modules/basic-ftp') for path in packages)
