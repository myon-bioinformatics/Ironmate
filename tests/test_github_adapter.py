import io
import json
from pathlib import Path
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from source_adapter import build_url

from github_adapter import (
    GitHubResource,
    actions_run_html_url,
    content_api_url,
    _ScopedRedirect,
    fetch_json,
    inspect_public,
    parse_github_resource,
    is_rate_limited,
    normalize_actions_run,
    normalize_commit,
    normalize_pull,
    compare_pull_head_identity,
    normalize_release,
    normalize_tag,
    pull_html_url,
    release_tag_html_url,
    repository_tree_api_url,
    repository_collection_api_url,
    repositories_api_url,
)


class GitHubAdapterTest(unittest.TestCase):
    def test_parse_owner_repo_and_build_without_network(self):
        result = inspect_public("openai/openai-python", fetch=False)
        self.assertEqual(result["kind"], "repository")
        self.assertEqual(result["html_url"], "https://github.com/openai/openai-python")
        self.assertEqual(result["api_url"], "https://api.github.com/repos/openai/openai-python")
        self.assertEqual(result["fetch"]["status"], "skipped")

    def test_parse_common_html_resources(self):
        cases = {
            "https://github.com/o/r/issues/12": ("issue", "12"),
            "https://github.com/o/r/pull/34": ("pull", "34"),
            "https://github.com/o/r/commit/abc123": ("commit", "abc123"),
            "https://github.com/o/r/actions/runs/56": ("actions_run", "56"),
            "https://github.com/o/r/releases/tag/v1.2.0": ("release_tag", "v1.2.0"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                resource = parse_github_resource(url)
                self.assertEqual((resource.kind, resource.identifier), expected)

    def test_url_builders_quote_user_controlled_segments(self):
        self.assertEqual(
            content_api_url("a b", "r#", "dir/file name.md", ref="feature/a b"),
            "https://api.github.com/repos/a%20b/r%23/contents/dir/file%20name.md?ref=feature%2Fa%20b",
        )
        self.assertEqual(pull_html_url("o", "r", 7), "https://github.com/o/r/pull/7")
        self.assertEqual(actions_run_html_url("o", "r", 9), "https://github.com/o/r/actions/runs/9")
        self.assertEqual(
            release_tag_html_url("o", "r", "release/one"),
            "https://github.com/o/r/releases/tag/release/one",
        )

    def test_provider_neutral_url_builder(self):
        self.assertEqual(
            build_url("https://example.test/api/", "search", query={"q": "初音 ミク", "limit": 10, "skip": None}),
            "https://example.test/api/search?q=%E5%88%9D%E9%9F%B3+%E3%83%9F%E3%82%AF&limit=10",
        )

    def test_collection_and_tree_url_builders(self):
        self.assertEqual(repositories_api_url("a b"), "https://api.github.com/users/a%20b/repos")
        self.assertEqual(repository_collection_api_url("o", "r", "pulls"), "https://api.github.com/repos/o/r/pulls")
        self.assertEqual(
            repository_tree_api_url("o", "r", "feature/a b"),
            "https://api.github.com/repos/o/r/git/trees/feature%2Fa%20b?recursive=1",
        )

    def test_api_mapping(self):
        self.assertEqual(
            GitHubResource("o", "r", "pull", "2").api_url,
            "https://api.github.com/repos/o/r/pulls/2",
        )
        self.assertEqual(
            GitHubResource("o", "r", "actions_run", "3").api_url,
            "https://api.github.com/repos/o/r/actions/runs/3",
        )

    def test_parse_normalizes_clone_suffix_and_subpaths(self):
        self.assertEqual(parse_github_resource("o/r.git").repo, "r")
        pull = parse_github_resource("https://github.com/o/r/pull/34/files")
        self.assertEqual((pull.kind, pull.identifier), ("pull", "34"))

    def test_rejects_non_numeric_identifiers(self):
        for url in (
            "https://github.com/o/r/issues/abc",
            "https://github.com/o/r/pull/abc",
            "https://github.com/o/r/actions/runs/abc",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_github_resource(url)

    def test_missing_numeric_identifier_never_builds_zero_url(self):
        for kind in ("issue", "pull", "actions_run"):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                _ = GitHubResource("o", "r", kind).html_url

    def test_fetch_json_normalizes_success_and_failures_offline(self):
        headers = Message()
        headers["X-RateLimit-Remaining"] = "59"
        headers["X-RateLimit-Limit"] = "60"

        class Response:
            def __init__(self):
                self.headers = headers
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"ok": true}'

        with patch("github_adapter._opener.open", return_value=Response()):
            result = fetch_json("https://api.github.com/example")
        self.assertEqual(result["status"], "detected")
        self.assertEqual(result["value"], {"ok": True})
        self.assertEqual(result["rate_limit"]["remaining"], "59")

        error_headers = Message()
        error_headers["X-RateLimit-Remaining"] = "0"
        error_headers["X-RateLimit-Reset"] = "123"
        http_error = HTTPError(
            "https://api.github.com/example", 403, "forbidden", error_headers, io.BytesIO()
        )
        with patch("github_adapter._opener.open", side_effect=http_error):
            result = fetch_json("https://api.github.com/example")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["rate_limit"]["remaining"], "0")
        self.assertEqual(result["rate_limit"]["reset"], "123")

        with patch("github_adapter._opener.open", side_effect=URLError("offline")):
            result = fetch_json("https://api.github.com/example")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "URLError")

    def test_rate_limit_classification_includes_429(self):
        self.assertTrue(is_rate_limited({"http_status": 429}))
        self.assertTrue(is_rate_limited({"http_status": 403, "rate_limit": {"remaining": "0"}}))
        self.assertFalse(is_rate_limited({"http_status": 403, "rate_limit": {"remaining": "1"}}))

    def test_normalizers_match_offline_fixture(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "github_adapter_normalization.json").read_text(encoding="utf-8")
        )
        expected = {
            "commit": {"sha": "abc123", "date": "2026-01-01T00:00:00Z", "message": "fixture commit",
                       "html_url": "https://github.com/o/r/commit/abc123",
                       "api_url": "https://api.github.com/repos/o/r/commits/abc123", "source_url": None},
            "pull": {"number": 7, "title": "fixture", "state": "open", "draft": False,
                     "head_sha": "head", "base_sha": "base", "created_at": "2026-01-02T01:02:03Z", "updated_at": "2026-01-03T04:05:06Z",
                     "closed_at": "2026-01-04T07:08:09Z", "merged_at": "2026-01-04T07:08:10Z", "html_url": "https://github.com/o/r/pull/7",
                     "api_url": "https://api.github.com/repos/o/r/pulls/7", "source_url": None},
            "release": {"tag_name": "v1.0.0", "name": "v1", "published_at": "2026-01-05T10:11:12Z",
                        "html_url": "https://github.com/o/r/releases/tag/v1.0.0",
                        "api_url": "https://api.github.com/repos/o/r/releases/1", "source_url": None},
            "tag": {"name": "v1.0.0", "sha": "abc123", "html_url": None, "api_url": None, "source_url": None},
            "actions_run": {"name": "CI", "status": "completed", "conclusion": "success",
                            "head_sha": "abc123", "updated_at": "2026-01-06T13:14:15Z",
                            "html_url": "https://github.com/o/r/actions/runs/1",
                            "api_url": "https://api.github.com/repos/o/r/actions/runs/1", "source_url": None},
        }
        normalizers = {"commit": normalize_commit, "pull": normalize_pull, "release": normalize_release,
                       "tag": normalize_tag, "actions_run": normalize_actions_run}
        for name, fn in normalizers.items():
            with self.subTest(name=name):
                self.assertEqual(fn(fixture[name]), expected[name])

    def test_normalizer_api_url_override_wins(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "github_adapter_normalization.json").read_text(encoding="utf-8")
        )
        override = "https://api.github.com/repos/o/r/tags?per_page=1"
        self.assertEqual(normalize_tag(fixture["tag"], api_url=override)["api_url"], override)
        self.assertEqual(normalize_actions_run(fixture["actions_run"], api_url=override)["api_url"], override)
        self.assertEqual(normalize_commit(fixture["commit"], api_url=override)["api_url"], override)
        self.assertEqual(normalize_release(fixture["release"], api_url=override)["api_url"], override)
        source = "https://api.github.com/repos/o/r/tags?per_page=1"
        normalized = normalize_tag(fixture["tag"], source_url=source)
        self.assertIsNone(normalized["api_url"])
        self.assertEqual(normalized["source_url"], source)

    def test_normalize_commit_falls_back_to_author_date(self):
        result = normalize_commit({"sha": "x", "commit": {
            "message": "m", "committer": {}, "author": {"date": "2026-02-03T04:05:06Z"}
        }})
        self.assertEqual(result["date"], "2026-02-03T04:05:06Z")

    def test_normalize_commit_accepts_empty_message(self):
        self.assertEqual(normalize_commit({"sha": "x", "commit": {"message": ""}})["message"], "")

    def test_inspect_public_exposes_rate_limit_classification(self):
        for payload, expected in [
            ({"status": "error", "http_status": 429, "error_type": "http"}, True),
            ({"status": "error", "http_status": 403, "error_type": "http",
              "rate_limit": {"remaining": "0"}}, True),
            ({"status": "detected", "value": {}}, False),
        ]:
            with self.subTest(payload=payload), patch("github_adapter.fetch_json", return_value=payload.copy()):
                result = inspect_public("o/r", fetch=True)
                self.assertEqual(result["fetch"]["rate_limited"], expected)

    def test_fetch_token_is_scoped_to_https_github_api(self):
        class Response:
            headers = Message()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{}'

        seen = []
        def fake_open(request, timeout):
            seen.append(request)
            return Response()

        with patch("github_adapter._opener.open", side_effect=fake_open):
            fetch_json("https://api.github.com/repos/o/r", token="secret")
            fetch_json("https://example.com/repos/o/r", token="secret")
            fetch_json("http://api.github.com/repos/o/r", token="secret")

        self.assertEqual(seen[0].get_header("Authorization"), "Bearer secret")
        self.assertIsNone(seen[1].get_header("Authorization"))
        self.assertIsNone(seen[2].get_header("Authorization"))

    def test_redirect_strips_authorization_outside_github_api(self):
        handler = _ScopedRedirect()
        original = Request(
            "https://api.github.com/repos/o/r",
            headers={"Authorization": "Bearer secret"},
        )
        same_host = handler.redirect_request(
            original, None, 302, "Found", Message(),
            "https://api.github.com/repositories/1",
        )
        self.assertEqual(same_host.get_header("Authorization"), "Bearer secret")

        external = handler.redirect_request(
            original, None, 302, "Found", Message(),
            "https://example.com/redirected",
        )
        self.assertIsNone(external.get_header("Authorization"))

    def test_rejects_unknown_hosts_and_shapes(self):
        with self.assertRaises(ValueError):
            parse_github_resource("https://example.com/o/r")
        with self.assertRaises(ValueError):
            parse_github_resource("https://github.com/o/r/settings")
        with self.assertRaises(ValueError):
            parse_github_resource("https://github.com/o/r/tree/main")


    def test_pull_head_identity_uses_ghi_comparison_contract(self):
        sha = "A" * 40
        pr = {"number": 7, "head": {"sha": sha}, "base": {"sha": "b" * 40}}
        result = compare_pull_head_identity(pr, {"sha": "a" * 40})
        self.assertEqual(result["schema"], "gh-identity-comparison/1")
        self.assertTrue(result["comparable"])
        self.assertTrue(result["same"])
        self.assertEqual(result["pull_number"], 7)

    def test_pull_head_identity_preserves_unknown_local_identity(self):
        pr = {"number": 8, "head": {"sha": "c" * 40}, "base": {"sha": "d" * 40}}
        result = compare_pull_head_identity(pr, {"sha": None})
        self.assertFalse(result["comparable"])
        self.assertIsNone(result["same"])
        self.assertEqual(result["remote_sha"], "c" * 40)


if __name__ == "__main__":
    unittest.main()
