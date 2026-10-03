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
SNAPSHOT = ['vendor.lock.json',
 'vendor/ascii_artist.py',
 'vendor/git_inspector.py',
 'vendor/markdown.py',
 'vendor/nvd_nist_known_vulns.py',
 'vendor/ascii_artist-LICENSE',
 'vendor/markdown-LICENSE',
 'vendor/nvd_nist_known_vulns-LICENSE',
 'vendor/ascii_artist.provenance.json',
 'vendor/git_inspector.provenance.json',
 'vendor/markdown.provenance.json']
EXPECTED = {('myon-bioinformatics/ascii_artist', 'LICENSE', 'vendor/ascii_artist-LICENSE'),
 ('myon-bioinformatics/ascii_artist', 'ascii_artist.py', 'vendor/ascii_artist.py'),
 ('myon-bioinformatics/markdown', 'LICENSE', 'vendor/markdown-LICENSE'),
 ('myon-bioinformatics/markdown', 'markdown.py', 'vendor/markdown.py'),
 ('myon-bioinformatics/myon-bioinformatics', 'git_inspector.py', 'vendor/git_inspector.py'),
 ('myon-bioinformatics/nvd_nist_known_vulns',
  'LICENSE',
  'vendor/nvd_nist_known_vulns-LICENSE'),
 ('myon-bioinformatics/nvd_nist_known_vulns',
  'nvd_nist_known_vulns.py',
  'vendor/nvd_nist_known_vulns.py')}


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
    assert len(records) == len(EXPECTED)
    assert {(e["repository"], e["source"], e["destination"]) for e in records.values()} == EXPECTED


def test_public_vendor_ci_updates_without_repository_writes():
    ci = _workflow()
    jobs = ci["jobs"]
    resolve = jobs["resolve-vendor"]["steps"]
    test = jobs[TEST_JOB]["steps"]
    assert jobs['resolve-vendor']['permissions'] == jobs[TEST_JOB]['permissions'] == {'contents': 'read'}
    update = next(s for s in resolve if s.get("name") == "Update public vendor files for this run")
    assert update["if"] == "inputs.vendor-mode != 'locked'"
    assert update["shell"] == "bash"
    assert 'continue-on-error' not in update
    assert update['run'].splitlines() == [
        'python -S .vendor-sync-tools/vendor_sync.py update --manifest vendor.lock.json',
        'python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json']
    assert ci['on']['workflow_dispatch']['inputs']['vendor-mode']['default'] == 'update'
    needs = jobs[TEST_JOB]['needs']
    assert 'resolve-vendor' in ([needs] if isinstance(needs, str) else needs)
    assert sum('vendor_sync.py update' in s.get('run', '') for steps in (resolve,test) for s in steps) == 1
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
        assert set(upload['with']['path'].splitlines()) == set(SNAPSHOT)
    pins = [s['with']['ref'] for steps in (resolve,test) for s in steps
            if s.get('with',{}).get('repository') == 'myon-bioinformatics/myon-bioinformatics']
    assert pins == ['90bc069c33901bd4b5373eb02311026e0acf2e2e'] * 2
    for steps in (resolve,test):
        for step in steps:
            if step.get('uses','').startswith('actions/checkout@'):
                assert step['with']['persist-credentials'] == 'false'
            assert not any(x in step.get('run','') for x in ('|| true','|| :','set +e','git push','git commit','gh pr'))
            assert 'continue-on-error' not in step
    text = (ROOT / WORKFLOW).read_text(encoding='utf-8')
    assert not any(x in text for x in ('VENDOR_UPDATE_TOKEN','VENDOR_UPDATES_ENABLED','GH_TOKEN'))


def test_failed_update_does_not_reach_successful_check(tmp_path):
    update = next(s for s in _workflow()['jobs']['resolve-vendor']['steps']
                  if s.get('name') == 'Update public vendor files for this run')
    tool = tmp_path / '.vendor-sync-tools/vendor_sync.py'
    tool.parent.mkdir()
    tool.write_text("import pathlib, sys\nif sys.argv[1] == 'update': sys.exit(2)\npathlib.Path('check-reached').touch()\n", encoding='utf-8')
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
