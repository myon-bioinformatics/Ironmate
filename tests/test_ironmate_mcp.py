import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from ironmate_mcp import (
    _repository_name,
    _validate,
    get_pull_request_metadata,
    get_repository_metadata,
    list_portfolio_repositories,
    search_repository_metadata,
)


class ValidateTest(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(_validate(" Flutter ", 5), ("flutter", 5))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            _validate("", 0)

    def test_repository_name_blocks_paths(self):
        self.assertEqual(_repository_name("markdown"), "markdown")
        with self.assertRaises(ValueError):
            _repository_name("../private")

    def test_filters_fixture(self):
        fixture = b'{"repos":[{"name":"Flutter","topics":["dart"],"internal":"nope"},{"name":"Python"}]}'
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(fixture)):
            result = list_portfolio_repositories("flutter", 1)
        self.assertEqual(
            result["items"],
            [{"name":"Flutter","description":None,"language":None,"topics":["dart"],"readmeSummary":None}],
        )
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["available_count"], 2)

    def test_failure_is_safe(self):
        with patch("ironmate_mcp.urlopen", side_effect=OSError("private detail")):
            result = list_portfolio_repositories()
        self.assertEqual(result["error"], "source_fetch_failed")

    def test_bad_shape_is_safe(self):
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(b"null")):
            result = list_portfolio_repositories()
        self.assertEqual(result["error"], "source_payload_invalid")

    def test_missing_repository_key_is_safe(self):
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(b"{}")):
            result = list_portfolio_repositories()
        self.assertEqual(result["error"], "source_payload_invalid")

    def test_search_metadata_is_compact(self):
        fixture = {
            "generated_at": "2026-09-21T00:00:00Z",
            "repos": [
                {"name":"markdown","sha":"abc","latest_pr":54,"language":"Python"},
                {"name":"Ironmate","sha":"def","latest_pr":9,"language":"Python"},
            ],
        }
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(json.dumps(fixture).encode())):
            result = search_repository_metadata("mark", 5)
        self.assertEqual([item["name"] for item in result["items"]], ["markdown"])

    def test_repository_metadata_returns_only_llm_fields(self):
        fixture = {
            "name":"markdown",
            "default_branch":"main",
            "latest_commit":{"sha":"abc","date":"2026-09-21T00:00:00Z"},
            "latest_pr":{"number":54,"head_sha":"def"},
            "pr_count":54,
            "pushed_at":"2026-09-21T00:00:00Z",
            "generated_at":"2026-09-21T00:01:00Z",
            "extra":"not returned",
        }
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(json.dumps(fixture).encode())):
            result = get_repository_metadata("markdown")
        self.assertNotIn("extra", result)
        self.assertEqual(result["latest_pr"]["number"], 54)

    def test_specific_pr_metadata(self):
        fixture = {"repository":"markdown","number":54,"head_sha":"abc","updated_at":"2026-09-21T00:00:00Z"}
        with patch("ironmate_mcp.urlopen", return_value=io.BytesIO(json.dumps(fixture).encode())):
            result = get_pull_request_metadata("markdown", 54)
        self.assertEqual(result["number"], 54)
        self.assertTrue(result["source_url"].endswith("/prs/markdown/54.json"))

    def test_latest_pr_uses_exact_pr_payload_shape(self):
        latest = {"number":54,"head_sha":"abc","updated_at":"2026-09-21T00:00:00Z"}
        pr_fixture = {
            "repository":"markdown",
            "number":54,
            "head_sha":"abc",
            "updated_at":"2026-09-21T00:00:00Z",
            "generated_at":"2026-09-21T00:01:00Z",
            "html_url":"https://github.com/example/markdown/pull/54",
        }
        with patch("ironmate_mcp.get_repository_metadata", return_value={"latest_pr":latest}),              patch("ironmate_mcp.urlopen", return_value=io.BytesIO(json.dumps(pr_fixture).encode())):
            result = get_pull_request_metadata("markdown", "latest")
        self.assertEqual(result["number"], 54)
        self.assertEqual(result["generated_at"], "2026-09-21T00:01:00Z")
        self.assertEqual(result["html_url"], "https://github.com/example/markdown/pull/54")
        self.assertTrue(result["source_url"].endswith("/prs/markdown/54.json"))

    def test_missing_static_item_is_normalized(self):
        error = HTTPError("https://example.invalid/missing.json", 404, "Not Found", None, None)
        with patch("ironmate_mcp.urlopen", side_effect=error):
            with self.assertRaisesRegex(ValueError, "static catalog item not found"):
                get_repository_metadata("missing")


if __name__ == "__main__":
    unittest.main()
