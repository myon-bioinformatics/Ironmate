import unittest

from github_adapter import (
    GitHubResource,
    actions_run_html_url,
    content_api_url,
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
            "https://github.com/o/r/releases/tag/release%2Fone",
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

    def test_rejects_unknown_hosts_and_shapes(self):
        with self.assertRaises(ValueError):
            parse_github_resource("https://example.com/o/r")
        with self.assertRaises(ValueError):
            parse_github_resource("https://github.com/o/r/settings")


if __name__ == "__main__":
    unittest.main()
