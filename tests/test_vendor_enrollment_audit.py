"""Candidate generation respects owner policy and never mutates adopted locks."""
import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(monkeypatch):
    parent = types.ModuleType('vendor_sync')
    calls = []
    def inspect(repo, commit, source):
        calls.append((repo, commit, source))
        return dict(repository=repo, commit=commit, source=source,
                    blob_sha='b' * 40, sha256='c' * 64)
    parent.inspect_source = inspect
    parent.validate = lambda lock: lock
    monkeypatch.setitem(sys.modules, 'vendor_sync', parent)
    spec = importlib.util.spec_from_file_location('audit_under_test', ROOT / 'scripts/vendor_enrollment_audit.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result, calls


def run_audit(tmp_path, monkeypatch, tools):
    audit, calls = module(monkeypatch)
    catalog = tmp_path / 'catalog.json'
    lock = tmp_path / 'lock.json'
    catalog.write_text(json.dumps(dict(schema='vendor-catalog/1', tools=tools)))
    lock.write_text(json.dumps(dict(schema='vendor-lock/1', files=[])))
    original = lock.read_bytes()
    rows = audit.audit(catalog, lock, tmp_path / 'out')
    assert lock.read_bytes() == original
    proposed = json.loads((tmp_path / 'out/proposed-vendor.lock.json').read_text())
    return rows, proposed, calls


def test_retired_parent_sync_is_not_reenrolled(tmp_path, monkeypatch):
    rows, proposed, calls = run_audit(tmp_path, monkeypatch, [dict(
        repository='myon-bioinformatics/myon-bioinformatics', source='vendor_sync.py',
        commit='a' * 40, default_enrollment=dict(enrollment='skipped', reason='parent_managed_tool'))])
    assert rows[0]['status'] == 'skipped_policy'
    assert rows[0]['reason'] == 'parent_managed_tool'
    assert proposed['files'] == [] and calls == []


def test_eligible_candidate_is_pinned_and_separate(tmp_path, monkeypatch):
    rows, proposed, calls = run_audit(tmp_path, monkeypatch, [dict(
        repository='example/tool', source='tool.py', commit='a' * 40)])
    assert rows[0]['status'] == 'verified_candidate'
    assert len(calls) == len(proposed['files']) == 2
    assert all(x['ref'] == x['commit'] == 'a' * 40 for x in proposed['files'])


def test_consumer_skip_overrides_default(tmp_path, monkeypatch):
    rows, proposed, calls = run_audit(tmp_path, monkeypatch, [dict(
        repository='example/tool', source='tool.py', commit='a' * 40,
        consumers={'myon-bioinformatics/Ironmate': dict(enrollment='skipped', reason='not_used')})])
    assert rows[0]['status'] == 'skipped_policy'
    assert proposed['files'] == [] and calls == []


def test_workflow_compares_adopted_lock_before_candidate_enrollment():
    import yaml
    path = ROOT / '.github/workflows/vendor-catalog-audit.yml'
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    steps = workflow['jobs']['audit']['steps']
    compare = next(i for i, s in enumerate(steps) if s.get('name', '').startswith('Compare parent'))
    candidate = next(i for i, s in enumerate(steps) if s.get('name') == 'Verify proposed candidates in a separate root')
    assert compare < candidate
    shell = steps[candidate]['run']
    assert '--root build/vendor-enrollment-audit/candidate' in shell
    assert 'git diff --exit-code -- vendor.lock.json vendor/' in shell
    workflow_text = path.read_text(encoding="utf-8")
    assert 'cp build/vendor-enrollment-audit/proposed-vendor.lock.json vendor.lock.json' not in workflow_text
    assert "parent_vendor_tools_resolve.py" in workflow_text
    assert "steps.parent-vendor-tools.outputs.sha" in workflow_text
    network_step = next(s for s in steps if s.get('name') == 'Network enrollment audit regressions')
    assert "uv run --locked python -m pytest -q -m network" in network_step['run']


def _project_ironmate_registry(registry):
    target = next(x for x in registry['consumers'] if x['repository'] == 'myon-bioinformatics/Ironmate')
    target['entries'] = [x for x in target['entries'] if not (
        x['repository'] == 'myon-bioinformatics/myon-bioinformatics' and
        x['source'] in {'git_inspector.py', 'vendor_sync.py'})]
    return registry


@pytest.mark.network
def test_workflow_compare_matches_live_parent_registry(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "parent_vendor_tools_resolve",
        ROOT / "scripts/parent_vendor_tools_resolve.py",
    )
    resolve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolve)
    fetch_parent_vendor_tool_files = resolve.fetch_parent_vendor_tool_files
    resolve_parent_vendor_tools_head = resolve.resolve_parent_vendor_tools_head

    resolved = resolve_parent_vendor_tools_head(token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    payloads = fetch_parent_vendor_tool_files(resolved["sha"])
    registry = _project_ironmate_registry(payloads["vendor-consumers.json"])
    tools = tmp_path / 'parent-tools'
    tools.mkdir()
    (tools / 'vendor-consumers.json').write_text(json.dumps(registry))
    (tools / 'vendor_consumers.py').write_bytes(payloads["vendor_consumers.py"])
    (tools / 'vendor_sync.py').write_bytes(payloads["vendor_sync.py"])
    reg = tmp_path / 'registry.json'
    reg.write_text(json.dumps(registry))
    command = [sys.executable, '-S', str(tools / 'vendor_consumers.py'), 'compare',
               '--consumer', 'myon-bioinformatics/Ironmate', '--lock', str(ROOT / 'vendor.lock.json'),
               '--registry', str(reg)]
    env = {**os.environ, 'PYTHONPATH': str(tools)}
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['matches'] is True
    lock = json.loads((ROOT / 'vendor.lock.json').read_text())
    lock['files'].pop()
    bad = tmp_path / 'bad.json'
    bad.write_text(json.dumps(lock))
    command[command.index('--lock') + 1] = str(bad)
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode != 0
    assert json.loads(result.stdout)['matches'] is False
