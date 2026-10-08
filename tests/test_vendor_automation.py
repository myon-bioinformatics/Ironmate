"""Automatic public vendor placement, failure propagation and provenance regression."""
import importlib.util
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/mcp-tests.yml'
TEST_JOB = 'test'
HELPER = 'scripts/sync_vendor_provenance.py'
PIN = '974da5eb9593df652b132e4b0f1a679f67422566'
def _lock_files(root=ROOT):
    lock = json.loads((root / 'vendor.lock.json').read_text(encoding='utf-8'))
    assert lock['schema'] == 'vendor-lock/1'
    return lock['files']


SNAPSHOT = ['vendor.lock.json', *[entry['destination'] for entry in _lock_files()],
            'vendor/ascii_artist.provenance.json',
            'vendor/git_inspector.provenance.json',
            'vendor/markdown.provenance.json']



def _workflow():
    import yaml
    return yaml.load((ROOT / WORKFLOW).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _projector():
    spec = importlib.util.spec_from_file_location("vendor_projection_regression", ROOT / HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_snapshot(root):
    for name in SNAPSHOT:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)


def test_vendor_lock_has_explicit_sources_and_verified_bytes():
    records = _projector().records(ROOT)
    expected = {(e['repository'], e['source'], e['destination']) for e in _lock_files()}
    assert {(e['repository'], e['source'], e['destination']) for e in records.values()} == expected



def test_canonical_vendor_evidence_membership_is_derived_from_lock():
    """New enrollments must not require another manually maintained membership list."""
    lock = json.loads((ROOT / 'vendor.lock.json').read_text(encoding='utf-8'))
    destinations = [entry['destination'] for entry in lock['files']]
    assert len(destinations) == len(set(path.casefold() for path in destinations))
    locked = sorted(['vendor.lock.json', *destinations], key=lambda p: (p.casefold(), p))
    assert 'vendor-promotion.json' not in locked
    assert set(locked) == {'vendor.lock.json', *(entry['destination'] for entry in lock['files'])}
    assert all((ROOT / path).is_file() for path in locked)

def test_public_vendor_ci_updates_without_repository_writes():
    ci = _workflow()
    assert {"push", "pull_request"} <= set(ci["on"])
    assert "schedule" not in ci["on"]
    assert ci.get("permissions", {"contents": "read"}) == {"contents": "read"}
    jobs = ci["jobs"]
    for job in (jobs["resolve-vendor"], jobs[TEST_JOB]):
        assert "continue-on-error" not in job
    resolve = jobs["resolve-vendor"]["steps"]
    test = jobs[TEST_JOB]["steps"]
    assert jobs['resolve-vendor']['permissions'] == jobs[TEST_JOB]['permissions'] == {'contents': 'read'}
    update = next(s for s in resolve if s.get("name") == "Update public vendor files for this run")
    assert update["if"] == "inputs.vendor-mode != 'locked'"
    assert update["shell"] == "bash"
    assert 'continue-on-error' not in update
    assert update['run'].splitlines() == [
        'python -S .vendor-sync-tools/vendor_sync.py promote --manifest vendor.lock.json | tee vendor-promotion.json',
        'python -S -m json.tool vendor-promotion.json > /dev/null',
        'python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json']
    recreate = next(s for s in resolve if s.get("name") == "Recreate locked vendor files from GitHub")
    assert recreate["shell"] == "bash"
    assert recreate["run"].splitlines() == [
        "python -S - <<'PY'", "import json", "from pathlib import Path",
        "for entry in json.loads(Path('vendor.lock.json').read_text(encoding='utf-8'))['files']:",
        "    Path(entry['destination']).unlink()", "PY",
        "python -S .vendor-sync-tools/vendor_sync.py materialize --manifest vendor.lock.json",
        "python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json"]
    save = next(i for i, s in enumerate(resolve) if s.get("name") == "Save checked-in vendor identities")
    assert resolve[save]["run"] == "cp vendor.lock.json .vendor-baseline.lock.json"
    assert save < resolve.index(recreate) < resolve.index(update)
    summary = next(s for s in resolve if s.get("name") == "Summarize snapshot and checked-in baseline")
    assert summary["if"] == "always()"
    assert summary["shell"] == "bash"
    assert summary["env"] == {"VENDOR_UPDATE_OUTCOME": "${{ steps.vendor-update.outcome }}"}
    assert update["id"] == "vendor-update"
    assert summary["run"] == ('python -S ' + HELPER +
        ' --summary-baseline .vendor-baseline.lock.json --summary-output "$GITHUB_STEP_SUMMARY"'
        ' --update-outcome "$VENDOR_UPDATE_OUTCOME"')
    assert ci['on']['workflow_dispatch']['inputs']['vendor-mode']['default'] == 'update'
    needs = jobs[TEST_JOB]['needs']
    assert 'resolve-vendor' in ([needs] if isinstance(needs, str) else needs)
    assert sum('vendor_sync.py promote' in s.get('run', '') for steps in (resolve,test) for s in steps) == 1
    download = next(i for i,s in enumerate(test) if s.get('name') == 'Download resolved vendor snapshot')
    verify = next(i for i,s in enumerate(test) if s.get('name') == 'Verify resolved vendor snapshot')
    tests = [i for i,s in enumerate(test) if 'pytest ' in s.get('run','')]
    assert tests and download < verify < min(tests)
    assert test[download]['with']['name'] == 'vendor-snapshot'
    assert test[verify]['shell'] == 'bash'
    assert test[verify]['run'].splitlines() == [
        'python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json',
        'python -S ' + HELPER]
    project = next(i for i,s in enumerate(resolve) if s.get('name') == 'Refresh legacy provenance from the verified lock')
    assert resolve[project]['run'] == 'python -S ' + HELPER
    for steps,name in ((resolve,'Preserve resolved vendor snapshot'),(test,'Preserve vendor lock used by this run')):
        upload = next(s for s in steps if s.get('name') == name)
        assert upload['if'] == 'always()'
        assert upload['with']['if-no-files-found'] == 'error'
        expected = ('build/vendor-evidence-candidate' if steps is resolve
                    else 'build/vendor-evidence-test')
        assert upload['with']['path'] == expected
    pins = [s['with']['ref'] for steps in (resolve,test) for s in steps
            if s.get('with',{}).get('repository') == 'myon-bioinformatics/myon-bioinformatics']
    assert pins == [PIN] * 2
    for steps in (resolve,test):
        for step in steps:
            if step.get('uses','').startswith('actions/checkout@'):
                assert step['with']['persist-credentials'] == 'false'
            assert not any(x in step.get('run','') for x in ('|| true','|| :','set +e','git push','git commit','gh pr'))
            assert 'continue-on-error' not in step
    text = (ROOT / WORKFLOW).read_text(encoding='utf-8')
    assert not any(x in text for x in ('secrets.', 'VENDOR_UPDATE_TOKEN','VENDOR_UPDATES_ENABLED','GH_TOKEN'))


def test_failed_promotion_does_not_reach_receipt_validation_or_check(tmp_path):
    update = next(s for s in _workflow()['jobs']['resolve-vendor']['steps']
                  if s.get('name') == 'Update public vendor files for this run')
    tool = tmp_path / '.vendor-sync-tools/vendor_sync.py'
    tool.parent.mkdir()
    tool.write_text("import pathlib, sys\nif sys.argv[1] == 'promote': sys.exit(2)\npathlib.Path('check-reached').touch()\n", encoding='utf-8')
    script = tmp_path / 'update.sh'
    script.write_text(update['run'].replace('python -S ', shlex.quote(sys.executable)+' -S '), encoding='utf-8')
    result = subprocess.run([shutil.which('bash'),'--noprofile','--norc','-e','-o','pipefail',str(script)],
                            cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode == 2
    assert not (tmp_path / 'check-reached').exists()


def test_updated_lock_projects_exact_identity_and_keeps_reader_formats(tmp_path):
    _copy_snapshot(tmp_path)
    lock_path = tmp_path / 'vendor.lock.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    for e in lock['files']: e['commit'] = 'a' * 40
    lock_path.write_text(json.dumps(lock),encoding='utf-8')
    projector = _projector()
    projector.project(tmp_path)
    before = {name:(tmp_path / name).read_bytes() for name in SNAPSHOT}
    projector.project(tmp_path)
    assert before == {name:(tmp_path / name).read_bytes() for name in SNAPSHOT}
    records = projector.records(tmp_path)
    for path,destination,fields in projector.BINDINGS:
        projected = json.loads((tmp_path / path).read_text(encoding='utf-8'))
        entry = records[destination]
        for target,source in fields.items():
            assert projected[target] == ('https://github.com/'+entry['repository'] if source == 'repository_url' else entry[source])
    # Grouped formats are absent in this consumer.


@pytest.mark.parametrize('license_file', [False, True])
def test_invalid_source_or_license_does_not_rewrite_any_provenance(tmp_path, license_file):
    _copy_snapshot(tmp_path)
    entries = json.loads((tmp_path / 'vendor.lock.json').read_text(encoding='utf-8'))['files']
    entry = next(e for e in entries if (e['source'] == 'LICENSE') == license_file)
    before = {p:(tmp_path / p).read_bytes() for p in SNAPSHOT if p.endswith('.json')}
    (tmp_path / entry['destination']).write_bytes(b'corrupt source or license')
    with pytest.raises(ValueError, match='locked bytes mismatch'):
        _projector().project(tmp_path)
    assert before == {p:(tmp_path / p).read_bytes() for p in before}


def test_projection_cli_help_and_unknown_options_do_not_need_or_write_sources(tmp_path):
    # Help must succeed before reading any lock or running the projection.
    helper = tmp_path / 'tool/sync_vendor_provenance.py'
    helper.parent.mkdir()
    shutil.copyfile(ROOT / HELPER, helper)
    for option, expected in (('--help', 0), ('--unknown-option', 2)):
        result = subprocess.run([sys.executable, '-S', str(helper), option],
                                cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == expected
        assert 'usage:' in (result.stdout + result.stderr).lower()
        assert set(tmp_path.rglob('*')) == {helper.parent, helper}


@pytest.mark.parametrize("mutation", ["blob", "sha256", "extra", "ref", "commit"])
def test_projection_cli_rejects_invalid_lock_before_metadata_writes(tmp_path, mutation):
    _copy_snapshot(tmp_path)
    helper = tmp_path / HELPER
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / HELPER, helper)
    path = tmp_path / "vendor.lock.json"
    lock = json.loads(path.read_text(encoding="utf-8"))
    entry = lock["files"][0]
    if mutation == "blob":
        entry["blob_sha"] = "0" * 40
    elif mutation == "sha256":
        entry["sha256"] = "0" * 64
    elif mutation == "extra":
        lock["files"].append(dict(entry))
    elif mutation == "ref":
        entry["ref"] = "refs/heads/unexpected"
    else:
        entry["commit"] = "short-sha"
    path.write_text(json.dumps(lock), encoding="utf-8")
    before = {p: (tmp_path / p).read_bytes() for p in SNAPSHOT if p.endswith(".json")}
    result = subprocess.run([sys.executable, "-S", str(helper)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "vendor-provenance:" in result.stderr
    assert "Traceback" not in result.stderr
    assert before == {p: (tmp_path / p).read_bytes() for p in before}


@pytest.mark.parametrize("outcome,changed", [("success", True), ("success", False),
                                           ("failure", False), ("skipped", False)])
def test_summary_reports_drift_without_claiming_baseline_success(tmp_path, outcome, changed):
    _copy_snapshot(tmp_path)
    baseline = tmp_path / ".vendor-baseline.lock.json"
    path = tmp_path / "vendor.lock.json"
    baseline.write_bytes(path.read_bytes())
    lock = json.loads(path.read_text(encoding="utf-8"))
    entry = lock["files"][0]
    old = entry["commit"]
    if changed:
        entry.update(commit="a" * 40, sha256="b" * 64)
        path.write_text(json.dumps(lock), encoding="utf-8")
    before = {p: (tmp_path / p).read_bytes() for p in SNAPSHOT}
    output = tmp_path / "summary.md"
    _projector().summarize(tmp_path, baseline, output, outcome)
    text = output.read_text(encoding="utf-8")
    assert "Update outcome: **" + outcome + "**" in text
    assert "not a baseline test result" in text
    assert "failed update remains a failed job" in text
    row = "| `" + entry["destination"] + "` | `" + old + "` | `" + entry["commit"] + "` | "
    row += ("yes" if changed else "no") + " |"
    assert row in text.splitlines()
    expected = [entry["destination"]] if changed else []
    assert "Changed source/LICENSE paths: `" + json.dumps(expected) + "`" in text
    assert before == {p: (tmp_path / p).read_bytes() for p in SNAPSHOT}


def test_projection_cli_missing_required_license_lock_entry_is_exit_two(tmp_path):
    _copy_snapshot(tmp_path)
    helper = tmp_path / HELPER
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / HELPER, helper)
    lock_path = tmp_path / "vendor.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["files"] = [entry for entry in lock["files"]
                     if entry["destination"] != "vendor/myon-bioinformatics-LICENSE"]
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    before = {p: (tmp_path / p).read_bytes() for p in SNAPSHOT if p.endswith(".json")}
    result = subprocess.run([sys.executable, "-S", str(helper)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "unexpected source or destination" in result.stderr
    assert "Traceback" not in result.stderr
    assert before == {p: (tmp_path / p).read_bytes() for p in before}


def test_locked_baseline_runs_automatically_without_candidate_snapshot():
    ci = _workflow()
    job = ci['jobs']['test-locked']
    assert job['permissions'] == {'contents': 'read'}
    assert 'continue-on-error' not in job
    assert job.get('needs') == ci['jobs']['resolve-vendor'].get('needs')
    assert job.get('if') == ci['jobs']['resolve-vendor'].get('if')
    matrix = job.get('strategy', {}).get('matrix', {})
    assert all(len(values) == 1 for values in matrix.values())
    steps = job['steps']
    assert not any('vendor_sync.py update' in s.get('run', '') for s in steps)
    assert not any(s.get('uses', '').startswith('actions/download-artifact@') for s in steps)
    verify = next(i for i,s in enumerate(steps) if s.get('name') == 'Verify checked-in vendor copies')
    recreate = next(i for i,s in enumerate(steps) if s.get('name') == 'Recreate locked vendor files from GitHub')
    project = next(i for i,s in enumerate(steps) if s.get('name') == 'Refresh legacy provenance from the verified lock')
    tests = [i for i,s in enumerate(steps) if 'pytest ' in s.get('run', '')]
    assert tests and verify < recreate < project < min(tests)
    original = next(s for s in ci['jobs']['resolve-vendor']['steps']
                    if s.get('name') == 'Recreate locked vendor files from GitHub')
    assert steps[recreate] == original
    tool = next(s for s in steps if s.get('name') == 'Fetch pinned shared vendor tool')
    assert tool['with']['ref'] == PIN
    for step in steps:
        assert 'continue-on-error' not in step
        if step.get('uses', '').startswith('actions/checkout@'):
            assert step['with']['persist-credentials'] == 'false'
        if step.get('uses', '').startswith('actions/upload-artifact@'):
            assert step['with']['name'].startswith('locked-')
            if step['with']['name'].startswith(('locked-vendor-', 'locked-junit-', 'locked-controlled-')):
                assert step['if'] == 'always()'
            assert step['with']['if-no-files-found'] == 'error'
    lock = next(s for s in steps if s.get('name') == 'Preserve vendor lock used by this run')
    assert lock['with']['path'] == 'build/vendor-evidence-locked'


@pytest.mark.parametrize('kind,receipt', [('candidate', True), ('candidate', False), ('locked', True)])
def test_workflow_uses_real_parent_staging_with_exact_members_and_digests(tmp_path, kind, receipt):
    import hashlib
    import os
    _copy_snapshot(tmp_path)
    tools = Path(os.environ.get('IRONMATE_CANONICAL_TOOLS', ROOT / '.vendor-sync-tools'))
    if receipt:
        (tmp_path / 'vendor-promotion.json').write_text('{"schema":"vendor-promotion/1"}')
    steps = _workflow()['jobs']['resolve-vendor' if kind == 'candidate' else 'test-locked']['steps']
    stage = next(s for s in steps if s.get('name') == 'Stage canonical vendor evidence')
    assert stage['if'] == 'always()'
    command = stage['run'].replace('python -S .vendor-sync-tools/vendor_stage.py',
        shlex.quote(sys.executable) + ' -S ' + shlex.quote(str(tools / 'vendor_stage.py')))
    env = dict(os.environ, VENDOR_EVIDENCE_KIND=kind)
    result = subprocess.run([shutil.which('bash'), '-e', '-c', command], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    output = tmp_path / ('build/vendor-evidence-candidate' if kind == 'candidate' else 'build/vendor-evidence-locked')
    meta = json.loads((output / 'vendor-evidence.json').read_text())
    sources = {'vendor.lock.json'} | {e['destination'] for e in _lock_files()}
    legacy = {name for name in SNAPSHOT if name.endswith('.provenance.json')}
    runtime = {'vendor-promotion.json'} if kind == 'candidate' and receipt else set()
    assert meta['kind'] == kind and set(meta[kind]) == sources
    assert set(meta['legacy']) == legacy and set(meta['runtime']) == runtime
    expected = sources | legacy | runtime
    assert set(meta['sha256']) == expected
    assert {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()} == expected | {'vendor-evidence.json'}
    for name in expected:
        data = (output / name).read_bytes()
        assert data == (tmp_path / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == meta['sha256'][name]


def test_new_canonical_tools_do_not_require_legacy_projector_membership_edits(tmp_path):
    import hashlib
    _copy_snapshot(tmp_path)
    lock_path = tmp_path / 'vendor.lock.json'
    lock = json.loads(lock_path.read_text())
    data = b'additional canonical tool\n'
    (tmp_path / 'extra.py').write_bytes(data)
    entry = dict(lock['files'][0], source='extra.py', destination='extra.py',
                 blob_sha=hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
                 sha256=hashlib.sha256(data).hexdigest())
    lock['files'].append(entry)
    lock_path.write_text(json.dumps(lock))
    _projector().project(tmp_path)
    assert 'extra.py' in _projector().records(tmp_path)
