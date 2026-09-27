import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from github_adapter import (
    GitHubResource,
    actions_run_html_url,
    content_api_url,
    fetch_json,
    inspect_public,
    parse_github_resource,
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

        with patch("github_adapter.urlopen", return_value=Response()):
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
        with patch("github_adapter.urlopen", side_effect=http_error):
            result = fetch_json("https://api.github.com/example")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["rate_limit"]["remaining"], "0")
        self.assertEqual(result["rate_limit"]["reset"], "123")

        with patch("github_adapter.urlopen", side_effect=URLError("offline")):
            result = fetch_json("https://api.github.com/example")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "URLError")

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
        def fake_urlopen(request, timeout):
            seen.append(request)
            return Response()

        with patch("github_adapter.urlopen", side_effect=fake_urlopen):
            fetch_json("https://api.github.com/repos/o/r", token="secret")
            fetch_json("https://example.com/repos/o/r", token="secret")
            fetch_json("http://api.github.com/repos/o/r", token="secret")

        self.assertEqual(seen[0].get_header("Authorization"), "Bearer secret")
        self.assertIsNone(seen[1].get_header("Authorization"))
        self.assertIsNone(seen[2].get_header("Authorization"))

    def test_rejects_unknown_hosts_and_shapes(self):
        with self.assertRaises(ValueError):
            parse_github_resource("https://example.com/o/r")
        with self.assertRaises(ValueError):
            parse_github_resource("https://github.com/o/r/settings")
        with self.assertRaises(ValueError):
            parse_github_resource("https://github.com/o/r/tree/main")


if __name__ == "__main__":
    unittest.main()
