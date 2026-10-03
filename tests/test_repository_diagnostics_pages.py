import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from scripts import build_repository_diagnostics as diagnostics


def _locked(destination):
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    return next(e for e in lock["files"] if e["destination"] == destination)


FIXTURE = Path(__file__).parent / "fixtures" / "repository_metadata_v1.json"


class Response:
    def __init__(self, status=200, url="https://example.test/final", headers=None):
        self.status = status
        self._url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self._url


def sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_public_candidates_cover_github_pages_raw_and_api():
    rows = diagnostics.public_candidates(
        "myon-bioinformatics/Ironmate", ref="main", path="README.md"
    )
    assert {row["kind"] for row in rows} == {
        "repository", "api", "pages", "raw", "contents_api"
    }
    assert any(
        row["url"] == "https://myon-bioinformatics.github.io/Ironmate/"
        for row in rows
        if row["kind"] == "pages"
    )


def test_payload_without_probe_is_explicitly_not_checked():
    payload = diagnostics.diagnostics_payload(sample(), probe=False)
    assert payload["metadata"]["schema_version"] == "1.0"
    assert payload["resolver"]["auth"] == "anonymous"
    assert payload["resolver"]["status"] == "not_checked"
    assert payload["resolver"]["observations"] == []


@pytest.mark.parametrize(
    ("code", "headers", "expected"),
    [
        (200, {}, "reachable"),
        (302, {}, "reachable"),
        (401, {}, "auth_required"),
        (403, {}, "auth_required"),
        (403, {"X-RateLimit-Remaining": "0"}, "rate_limited"),
        (403, {"retry-after": "60"}, "rate_limited"),
        (404, {}, "not_found"),
        (429, {}, "rate_limited"),
        (500, {}, "http_error"),
    ],
)
def test_probe_status_contract(code, headers, expected):
    def opener(request, timeout):
        assert request.get_header("Authorization") is None
        if code >= 400:
            raise HTTPError(request.full_url, code, "x", headers, None)
        return Response(code, request.full_url, headers)

    result = diagnostics.probe_url("https://example.test/resource", opener=opener)
    assert result["status"] == expected
    assert result["http_status"] == code
    assert result["evidence"] == "http_response"


def test_network_failure_is_unverified():
    def opener(request, timeout):
        raise URLError("offline")

    result = diagnostics.probe_url("https://example.test/resource", opener=opener)
    assert result["status"] == "unverified"
    assert result["http_status"] is None


def test_page_uses_pinned_repository_diagnostics_renderer():
    html = diagnostics.page_html()
    assert diagnostics.WEB_UI_SHA in html
    assert "/css/repository-diagnostics.css" in html
    assert "/js/repository-diagnostics.js" in html
    assert "Unverified is not inaccessible." in html
    assert 'textContent = item.url' in html


def test_git_inspector_provenance_matches_vendored_bytes():
    root = Path(__file__).resolve().parents[1]
    path = root / "vendor" / "git_inspector.py"
    provenance = json.loads(
        (root / "vendor" / "git_inspector.provenance.json").read_text(encoding="utf-8")
    )
    data = path.read_bytes()
    blob = hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data
    ).hexdigest()
    assert provenance["source_commit"] == _locked('vendor/git_inspector.py')['commit']
    assert blob == provenance["blob_sha"]
    assert hashlib.sha256(data).hexdigest() == provenance["sha256"]


def test_tracked_bytes_uses_shared_inventory(tmp_path, monkeypatch):
    (tmp_path / "space 日本語.txt").write_bytes(b"abc")

    class Inspector:
        @staticmethod
        def ls_files(root):
            return {"paths": ["space 日本語.txt", "missing.txt"], "truncated": False}

    monkeypatch.setattr(diagnostics, "_load_git_inspector", lambda: Inspector)
    assert diagnostics._tracked_bytes(tmp_path) == 3


def test_tracked_bytes_rejects_truncated_inventory(tmp_path, monkeypatch):
    class Inspector:
        @staticmethod
        def ls_files(root):
            return {"paths": ["partial"], "truncated": True}

    monkeypatch.setattr(diagnostics, "_load_git_inspector", lambda: Inspector)
    with pytest.raises(RuntimeError, match="truncated"):
        diagnostics._tracked_bytes(tmp_path)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    import subprocess

    for key in ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "GITHUB_SHA"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-09-30T12:34:56+09:00")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-09-30T12:34:56+09:00")

    def git(*args):
        return subprocess.check_output(
            ["git", *args], cwd=tmp_path, text=True, encoding="utf-8"
        ).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / "tracked 日本語.txt").write_bytes(b"abc")
    (tmp_path / "missing.txt").write_bytes(b"missing")
    git("add", ".")
    git("commit", "-m", "diagnostics 日本語 fixture")
    (tmp_path / "missing.txt").unlink()
    (tmp_path / "untracked.txt").write_bytes(b"excluded")
    return tmp_path, git


def test_current_record_matches_before_fixture_except_canonical_utc(checkout, monkeypatch):
    from datetime import datetime, timezone
    import repository_metadata_generator as generator

    root, git = checkout

    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 1, 1, 2, 3, tzinfo=timezone.utc)

    monkeypatch.setattr(generator, "datetime", Clock)
    monkeypatch.setattr(generator.platform, "python_version", lambda: "3.12.0")
    before = json.loads(
        (FIXTURE.parent / "diagnostics_checkout_before.json").read_text(encoding="utf-8")
    )
    sha = git("rev-parse", "HEAD")
    before["metadata"]["head"].update(sha=sha, short_sha=sha[:8])
    after = diagnostics.diagnostics_payload(diagnostics.current_record(root), probe=False)
    assert before["metadata"]["generated_at"] == "2026-10-01T01:02:03+00:00"
    assert after["metadata"]["generated_at"] == "2026-10-01T01:02:03Z"
    before["metadata"]["generated_at"] = after["metadata"]["generated_at"]
    assert after == before


@pytest.mark.parametrize(
    ("env", "branch"),
    [
        ({}, "detached"),
        ({"GITHUB_HEAD_REF": "feat/head", "GITHUB_REF_NAME": "57/merge"}, "feat/head"),
        ({"GITHUB_HEAD_REF": "", "GITHUB_REF_NAME": "57/merge"}, "57/merge"),
        ({"GITHUB_HEAD_REF": "  ", "GITHUB_REF_NAME": " release/test "}, "release/test"),
        ({"GITHUB_REF_NAME": "HEAD"}, "detached"),
    ],
)
def test_current_record_detached_and_actions_context(checkout, monkeypatch, env, branch):
    root, git = checkout
    sha = git("rev-parse", "HEAD")
    git("checkout", "--detach", sha)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    record = diagnostics.current_record(root)
    assert record["head"] == {
        "sha": sha, "short_sha": sha[:8], "branch": branch,
        "timestamp": "2026-09-30T12:34:56+09:00",
        "subject": "diagnostics 日本語 fixture",
    }
    assert record["measurements"]["working_tree_bytes"] == 3


def test_current_record_fails_before_identity_on_truncated_inventory(checkout, monkeypatch):
    root, _ = checkout

    class Inspector:
        @staticmethod
        def ls_files(root):
            return {"paths": [], "truncated": True}

    monkeypatch.setattr(diagnostics, "_load_git_inspector", lambda: Inspector)
    monkeypatch.setattr(
        diagnostics, "record_from_checkout",
        lambda *args, **kwargs: pytest.fail("partial inventory must not publish metadata"),
    )
    with pytest.raises(RuntimeError, match="truncated"):
        diagnostics.current_record(root)


def test_current_record_without_site_packages_from_outside_checkout(checkout):
    import os
    import subprocess
    import sys

    root, git = checkout
    source_root = Path(__file__).resolve().parents[1]
    code = (
        "import json, sys; from pathlib import Path; "
        "sys.path.insert(0, sys.argv[1]); "
        "from scripts.build_repository_diagnostics import current_record, diagnostics_payload; "
        "print(json.dumps(diagnostics_payload(current_record(Path(sys.argv[2])), probe=False)))"
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
    output = subprocess.check_output(
        [sys.executable, "-S", "-c", code, str(source_root), str(root)],
        cwd=root, env=env, text=True, encoding="utf-8",
    )
    payload = json.loads(output)
    assert payload["metadata"]["head"]["sha"] == git("rev-parse", "HEAD")
    assert payload["metadata"]["measurements"]["working_tree_bytes"] == 3
    assert payload["metadata"]["tooling"]["python"]
    assert payload["resolver"]["observations"] == []


def test_current_record_uses_canonical_python_tooling_omission(checkout, monkeypatch):
    import repository_metadata_generator as generator

    root, _ = checkout
    baseline = diagnostics.current_record(root)
    monkeypatch.setattr(generator.platform, "python_version", lambda: "not a version")
    record = diagnostics.current_record(root)
    assert record["tooling"] == {}
    assert record["head"] == baseline["head"]
