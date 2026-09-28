import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

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
    normalize_release,
    normalize_tag,
    pull_html_url,
    release_tag_html_url,
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

    def test_normalizers_preserve_html_and_api_provenance(self):
        cases = [
            (normalize_commit, {"sha": "abc", "commit": {"message": "first\\nbody", "committer": {"date": "2026-01-01"}}, "html_url": "https://github.com/o/r/commit/abc", "url": "https://api.github.com/repos/o/r/commits/abc"}, "abc"),
            (normalize_pull, {"number": 7, "head": {"sha": "h"}, "base": {"sha": "b"}, "html_url": "https://github.com/o/r/pull/7", "url": "https://api.github.com/repos/o/r/pulls/7"}, 7),
            (normalize_release, {"tag_name": "v1", "html_url": "https://github.com/o/r/releases/tag/v1", "url": "https://api.github.com/repos/o/r/releases/1"}, "v1"),
            (normalize_tag, {"name": "v1", "commit": {"sha": "abc"}, "url": "https://api.github.com/repos/o/r/git/refs/tags/v1"}, "v1"),
            (normalize_actions_run, {"name": "CI", "status": "completed", "html_url": "https://github.com/o/r/actions/runs/1", "url": "https://api.github.com/repos/o/r/actions/runs/1"}, "CI"),
        ]
        for fn, payload, expected in cases:
            with self.subTest(fn=fn.__name__):
                value = fn(payload)
                self.assertTrue(value["api_url"].startswith("https://api.github.com/"))
                self.assertTrue(value.get("html_url") is None or value["html_url"].startswith("https://github.com/"))
                self.assertIn(expected, value.values())

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


if __name__ == "__main__":
    unittest.main()
