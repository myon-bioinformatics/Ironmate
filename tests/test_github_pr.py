"""Consumer integration against the real vendored producer, with offline HTTP."""
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

import pytest

import github_pr
from vendor import gh_ops

REPO = 'octo/demo'
HEAD = 'a' * 40
OTHER = 'b' * 40
ROOT = Path(__file__).resolve().parents[1]


def client_for(*, final_head=HEAD, checks=1, conclusion='success', comment=False,
               verify='hello\n', missing_id=False, activity=()):
    calls = []
    reads = 0

    def transport(method, url, body, headers):
        nonlocal reads
        path = urlsplit(url).path
        calls.append((method, path, body))
        if path == '/repos/octo/demo/pulls/11':
            reads += 1
            data = {'head': {'sha': HEAD if reads == 1 else final_head, 'ref': 'feature'},
                    'base': {'ref': 'main'}, 'state': 'open', 'merged': False, 'draft': False}
        elif path.endswith('/check-runs'):
            assert path == f'/repos/octo/demo/commits/{HEAD}/check-runs'
            data = {'check_runs': [{'id': i, 'name': str(i), 'head_sha': HEAD, 'status': 'completed',
                                   'conclusion': conclusion} for i in range(checks)]}
        elif method == 'POST':
            assert comment and path == '/repos/octo/demo/issues/11/comments'
            return gh_ops.Response(201, {} if missing_id else {'id': 9})
        elif path == '/repos/octo/demo/issues/comments/9':
            if verify is None:
                raise gh_ops.GhOpsError('verification unavailable')
            data = {'id': 9, 'body': verify}
        elif path == '/repos/octo/demo/issues/11/comments':
            data = list(activity)
        elif path in ('/repos/octo/demo/pulls/11/reviews', '/repos/octo/demo/pulls/11/comments'):
            data = []
        else:
            raise AssertionError((method, path))
        return gh_ops.Response(200, data)

    return gh_ops.Client(token='', transport=transport), calls


def test_first_observation_has_no_transition_then_emits_green_and_activity(tmp_path):
    path = tmp_path / 'pr.json'
    client, calls = client_for(checks=0)
    first = github_pr.observe_pr(REPO, 11, snapshot=path, client=client)
    assert first['ok'] and first['diff'] is None and first['snapshot_saved']
    assert first['observation']['checks']['state'] == 'pending'
    assert json.loads(path.read_text()) == first['observation']
    client, _ = client_for(activity=[{'id': 1, 'updated_at': '2026-10-05T00:00:00Z'}])
    second = github_pr.observe_pr(REPO, 11, snapshot=path, client=client)
    assert [e['type'] for e in second['diff']['events']] == ['ci_became_green', 'issue_comments_changed']
    client, _ = client_for(activity=[{'id': 1, 'updated_at': '2026-10-05T00:00:00Z'}])
    third = github_pr.observe_pr(REPO, 11, snapshot=path, client=client)
    assert third['diff']['events'] == []
    assert all(method == 'GET' for method, _, _ in calls)


@pytest.mark.parametrize('checks,minimum,conclusion,state', [
    (0, 1, 'success', 'pending'), (1, 2, 'success', 'pending'), (1, 1, 'failure', 'failed')])
def test_ci_status_is_not_observation_success(tmp_path, checks, minimum, conclusion, state):
    client, _ = client_for(checks=checks, conclusion=conclusion)
    result = github_pr.observe_pr(REPO, 11, min_checks=minimum, client=client)
    assert result['ok'] and not result['snapshot_saved']
    assert result['observation']['checks']['state'] == state
    assert not result['observation']['checks']['ok']


def test_stale_snapshot_never_overwrites_last_success(tmp_path):
    path = tmp_path / 'pr.json'
    github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for()[0])
    before = path.read_bytes()
    result = github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for(final_head=OTHER)[0])
    assert not result['ok'] and result['observation']['stale']
    assert not result['snapshot_saved'] and result['diff'] is None
    assert path.read_bytes() == before


def test_read_failure_preserves_snapshot(tmp_path):
    path = tmp_path / 'pr.json'
    github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for()[0])
    before = path.read_bytes()
    def fail(*args):
        raise gh_ops.GhOpsError('offline')
    with pytest.raises(gh_ops.GhOpsError, match='offline'):
        github_pr.observe_pr(REPO, 11, snapshot=path, client=gh_ops.Client(token='', transport=fail))
    assert path.read_bytes() == before


@pytest.mark.parametrize('bad', ['[]', '{', '{"ok": false, "schema": "gh-ops-pr-observation/1"}'])
def test_invalid_saved_snapshot_fails_before_network(tmp_path, bad):
    path = tmp_path / 'pr.json'
    path.write_text(bad)
    client, calls = client_for()
    with pytest.raises((ValueError, gh_ops.GhOpsError)):
        github_pr.observe_pr(REPO, 11, snapshot=path, client=client)
    assert calls == [] and path.read_text() == bad


def test_wrong_pr_fails_before_network(tmp_path):
    path = tmp_path / 'pr.json'
    github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for()[0])
    client, calls = client_for()
    with pytest.raises(ValueError, match='different pull request'):
        github_pr.observe_pr(REPO, 12, snapshot=path, client=client)
    assert calls == []


def test_failed_atomic_replace_preserves_old_file_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / 'pr.json'
    github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for()[0])
    before = path.read_bytes()
    def fail(*args):
        raise OSError('replace failed')
    monkeypatch.setattr(github_pr.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failed'):
        github_pr.observe_pr(REPO, 11, snapshot=path, client=client_for()[0])
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]


def test_comment_default_is_preview_and_explicit_write_preserves_body(tmp_path, capsys):
    path = tmp_path / 'body.txt'
    path.write_text('日本語 🫡\n', encoding='utf-8')
    client, calls = client_for(comment=True, verify='日本語 🫡\n')
    args = ['comment', REPO, '11', '--body-file', str(path)]
    assert github_pr.main(args, client=client) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['dry_run'] and not result['posted']
    assert len(calls) == 1 and calls[0][0] == 'GET'
    assert github_pr.main(args + ['--write'], client=client) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['posted'] and result['verified']
    posts = [call for call in calls if call[0] == 'POST']
    assert len(posts) == 1 and posts[0][2] == {'body': '日本語 🫡\n'}


@pytest.mark.parametrize('verify,missing_id', [(None, False), ('different', False), ('hello\n', True)])
def test_uncertain_comment_is_not_retried(tmp_path, capsys, verify, missing_id):
    body = tmp_path / 'body.txt'
    body.write_text('hello\n')
    client, calls = client_for(comment=True, verify=verify, missing_id=missing_id)
    rc = github_pr.main(['comment', REPO, '11', '--body-file', str(body), '--write'], client=client)
    result = json.loads(capsys.readouterr().out)
    assert rc == 1 and result['posted'] and not result['verified']
    assert 'inspect' in result['reason']
    assert sum(method == 'POST' for method, _, _ in calls) == 1



def test_observation_can_attach_repository_metadata_identity(tmp_path):
    metadata = tmp_path / "repository.json"
    metadata.write_text(json.dumps({"head": {"sha": HEAD, "branch": "feature"}}), encoding="utf-8")
    result = github_pr.observe_pr(REPO, 11, local_metadata=metadata, client=client_for()[0])
    assert result["ok"]
    assert result["identity"]["schema"] == "gh-identity-comparison/1"
    assert result["identity"]["same"] is True
    assert result["identity"]["local_sha"] == HEAD
    assert result["identity"]["remote_sha"] == HEAD


def test_observation_without_local_metadata_preserves_optional_contract():
    result = github_pr.observe_pr(REPO, 11, client=client_for()[0])
    assert result["ok"]
    assert result["identity"] is None


def test_local_metadata_mismatch_is_reported_not_folded_into_ci_status(tmp_path):
    metadata = tmp_path / "repository.json"
    metadata.write_text(json.dumps({"head": {"sha": OTHER, "branch": "feature"}}), encoding="utf-8")
    result = github_pr.observe_pr(REPO, 11, local_metadata=metadata, client=client_for()[0])
    assert result["ok"]
    assert result["observation"]["checks"]["ok"]
    assert result["identity"]["comparable"]
    assert result["identity"]["same"] is False


def test_stdlib_cli_diff_offline(tmp_path):
    first, second = tmp_path / 'before.json', tmp_path / 'after.json'
    github_pr.observe_pr(REPO, 11, snapshot=first, client=client_for(checks=0)[0])
    github_pr.observe_pr(REPO, 11, snapshot=second, client=client_for()[0])
    done = subprocess.run([sys.executable, '-S', str(ROOT / 'github_pr.py'), 'diff', str(first), str(second)],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)['events'][0]['type'] == 'ci_became_green'
