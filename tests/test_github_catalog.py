import unittest
from unittest.mock import patch

import github_catalog


class GitHubCatalogTransportTest(unittest.TestCase):
    url = "https://api.github.com/repos/example/repo/commits/main"

    def setUp(self):
        github_catalog.RATE_LIMIT.update({"remaining": None, "limit": None, "reset": None})

    def _cases(self):
        return [
            (
                "success",
                {"status": "detected", "value": {"ok": True}, "url": self.url,
                 "rate_limit": {"remaining": "59", "limit": "60", "reset": "123"}},
                ("detected", {"ok": True}),
                None,
            ),
            (
                "not found",
                {"status": "error", "error_type": "http", "http_status": 404, "url": self.url,
                 "rate_limit": {"remaining": None, "limit": None, "reset": None}},
                ("not_found", None),
                LookupError,
            ),
            (
                "conflict",
                {"status": "error", "error_type": "http", "http_status": 409, "url": self.url,
                 "rate_limit": {"remaining": None, "limit": None, "reset": None}},
                ("fetch_failed", None),
                RuntimeError,
            ),
            (
                "rate limited",
                {"status": "error", "error_type": "http", "http_status": 403, "url": self.url,
                 "rate_limit": {"remaining": "0", "limit": "60", "reset": "456"}},
                ("fetch_failed", None),
                RuntimeError,
            ),
            (
                "network failure",
                {"status": "error", "error_type": "URLError", "url": self.url},
                ("fetch_failed", None),
                RuntimeError,
            ),
        ]

    def test_optional_and_required_fetch_preserve_vocabulary_and_diagnostics(self):
        for name, result, optional_expected, error_type in self._cases():
            with self.subTest(case=name):
                with patch("github_catalog.fetch_json", return_value=result) as fetch:
                    self.assertEqual(github_catalog._optional_json(self.url), optional_expected)
                    fetch.assert_called_once_with(self.url, token=github_catalog.TOKEN)

                with patch("github_catalog.fetch_json", return_value=result):
                    if error_type is None:
                        self.assertEqual(github_catalog._request_json(self.url), {"ok": True})
                    else:
                        with self.assertRaises(error_type) as raised:
                            github_catalog._request_json(self.url)
                        message = str(raised.exception)
                        self.assertIn(self.url, message)
                        if result.get("http_status") is not None:
                            self.assertIn(str(result["http_status"]), message)
                        if result.get("http_status") == 404:
                            self.assertTrue(message.startswith("not_found "))
                        elif result.get("http_status") == 403:
                            self.assertTrue(message.startswith("rate_limited 403 "))
                        elif result.get("http_status") == 409:
                            self.assertTrue(message.startswith("http 409 "))
                        else:
                            self.assertTrue(message.startswith("URLError "))

    def test_catalog_tag_and_actions_keep_source_provenance(self):
        tag_url = "https://api.github.com/repos/myon-bioinformatics/demo/tags?per_page=1"
        with patch("github_catalog._optional_json", return_value=("detected", [{"name": "v1", "commit": {"sha": "abc"}}])):
            tag = github_catalog._tag_metadata("demo")["value"]
        self.assertIsNone(tag["api_url"])
        self.assertEqual(tag["source_url"], tag_url)

        run_url = "https://api.github.com/repos/myon-bioinformatics/demo/actions/runs?branch=main&per_page=1"
        run = {"name": "CI", "status": "completed", "conclusion": "success", "head_sha": "abc",
               "url": "https://api.github.com/repos/myon-bioinformatics/demo/actions/runs/9"}
        with patch("github_catalog._optional_json", return_value=("detected", {"workflow_runs": [run]})):
            ci = github_catalog._ci_metadata("demo", "main")["value"]
        self.assertEqual(ci["api_url"], run["url"])
        self.assertEqual(ci["source_url"], run_url)

    def test_missing_rate_limit_headers_do_not_clear_last_known_values(self):
        github_catalog.RATE_LIMIT.update({"remaining": "12", "limit": "60", "reset": "789"})
        result = {"status": "error", "error_type": "URLError", "url": self.url}
        with patch("github_catalog.fetch_json", return_value=result):
            self.assertEqual(github_catalog._optional_json(self.url), ("fetch_failed", None))
        self.assertEqual(github_catalog.RATE_LIMIT, {"remaining": "12", "limit": "60", "reset": "789"})

    def test_partial_rate_limit_headers_update_only_present_values(self):
        github_catalog.RATE_LIMIT.update({"remaining": "12", "limit": "60", "reset": "789"})
        result = {
            "status": "error",
            "error_type": "http",
            "http_status": 500,
            "url": self.url,
            "rate_limit": {"remaining": "3", "limit": None, "reset": None},
        }
        with patch("github_catalog.fetch_json", return_value=result):
            github_catalog._optional_json(self.url)
        self.assertEqual(github_catalog.RATE_LIMIT, {"remaining": "3", "limit": "60", "reset": "789"})


if __name__ == "__main__":
    unittest.main()
