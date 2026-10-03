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
