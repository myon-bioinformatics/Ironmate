"""Offline tests for portable unreviewed GitHub diagnostics."""

import io
import json
import unittest
import urllib.error
import urllib.request
from unittest import mock

from scripts.unreviewed import (
    GitHubApiError,
    _next_link,
    make_fetcher,
    owner_repositories,
    paged,
    reviewer_pattern,
    unreviewed,
)


class UnreviewedDiagnosticsTest(unittest.TestCase):
    def test_next_link_requires_next_relation(self):
        value = '<https://api.github.test/items?page=2>; rel="prev", <https://api.github.test/items?page=3>; rel="next"'
        self.assertEqual(_next_link(value), "https://api.github.test/items?page=3")
        self.assertIsNone(_next_link('<https://api.github.test/items?page=2>; rel="last"'))

    def test_paged_follows_link_and_rejects_cycle(self):
        calls = []
        responses = {
            "/items": ([{"id": 1}], {"link": '<https://api.github.test/items?page=2>; rel="next"'}),
            "https://api.github.test/items?page=2": ([{"id": 2}], {}),
        }

        def fetch(url):
            calls.append(url)
            return responses[url]

        self.assertEqual(list(paged(fetch, "/items")), [{"id": 1}, {"id": 2}])
        self.assertEqual(calls, ["/items", "https://api.github.test/items?page=2"])

        cycle_calls = 0

        def cycle(url):
            nonlocal cycle_calls
            cycle_calls += 1
            if cycle_calls > 2:
                self.fail("pagination cycle guard did not stop repeated fetches")
            return ([], {"link": f'<{url}>; rel="next"'})

        with self.assertRaisesRegex(GitHubApiError, "pagination cycle"):
            list(paged(cycle, "/loop"))

    def test_owner_falls_back_to_user_only_for_org_404(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if url.startswith("/orgs/"):
                raise GitHubApiError("missing", status=404)
            return ([{"name": "demo"}], {})

        self.assertEqual(list(owner_repositories(fetch, "acme")), [{"name": "demo"}])
        self.assertEqual(len(calls), 2)

        def forbidden(url):
            raise GitHubApiError("forbidden", status=403)

        with self.assertRaises(GitHubApiError):
            list(owner_repositories(forbidden, "acme"))

        def server_error(url):
            raise GitHubApiError("server error", status=500)

        with self.assertRaises(GitHubApiError):
            list(owner_repositories(server_error, "acme"))

    def test_reviewer_pattern_is_exact_line_without_cross_line_whitespace(self):
        pattern = reviewer_pattern("Claude[bot]")
        self.assertTrue(pattern.search("note\n  FROM:\tclaude[bot]  \n"))
        self.assertTrue(pattern.search("from: Claude[bot]\r\nto: cursor"))
        self.assertTrue(pattern.search("x\r\nfrom: claude[bot]\r\n"))
        for value in (
            "quoted from: claude[bot] elsewhere",
            "from: claude[bot]-extra",
            "from: claude[bot] extra",
            "from:\nclaude[bot]",
        ):
            self.assertFalse(pattern.search(value))

    def test_unreviewed_checks_inline_comments_and_skips_410_repo(self):
        def fetch(url):
            if url.startswith("/orgs/acme/repos"):
                return ([{"name": "demo"}, {"name": "disabled"}], {})
            if url == "/repos/acme/disabled/issues?state=open&per_page=100":
                raise GitHubApiError("gone", status=410)
            if url == "/repos/acme/demo/issues?state=open&per_page=100":
                return (
                    [
                        {"number": 1, "title": "plain issue"},
                        {"number": 2, "title": "inline reviewed pr", "pull_request": {}},
                        {"number": 3, "title": "unreviewed bot-author pr", "pull_request": {}},
                    ],
                    {},
                )
            mapping = {
                "/repos/acme/demo/issues/1/comments?per_page=100": ([], {}),
                "/repos/acme/demo/issues/2/comments?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/2/reviews?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/2/comments?per_page=100": ([{"body": "from: bot"}], {}),
                "/repos/acme/demo/issues/3/comments?per_page=100": ([{"body": "", "user": {"login": "bot[bot]"}}], {}),
                "/repos/acme/demo/pulls/3/reviews?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/3/comments?per_page=100": ([], {}),
            }
            return mapping[url]

        self.assertEqual(
            list(unreviewed(fetch, "acme", "bot")),
            [("demo", "IS", 1, "plain issue"), ("demo", "PR", 3, "unreviewed bot-author pr")],
        )

    def test_item_404_does_not_abort_other_comment_surfaces(self):
        def fetch(url):
            if url.startswith("/orgs/acme/repos"):
                return ([{"name": "demo"}], {})
            if url == "/repos/acme/demo/issues?state=open&per_page=100":
                return ([{"number": 1, "title": "pr", "pull_request": {}}], {})
            if "/issues/1/comments" in url:
                raise GitHubApiError("missing", status=404)
            if "/pulls/1/reviews" in url:
                return ([{"body": "from: bot"}], {})
            return ([], {})

        self.assertEqual(list(unreviewed(fetch, "acme", "bot")), [])\n\n    def test_non_tagged_nonempty_issue_comment_does_not_count_as_reviewed(self):\n        def fetch(url):\n            if url.startswith("/orgs/acme/repos"):\n                return ([{"name": "demo"}], {})\n            if url == "/repos/acme/demo/issues?state=open&per_page=100":\n                return ([{"number": 1, "title": "pr", "pull_request": {}}], {})\n            if "/issues/1/comments" in url:\n                return ([{"body": "review failed; please retry"}], {})\n            return ([], {})\n\n        self.assertEqual(list(unreviewed(fetch, "acme", "bot")), [("demo", "PR", 1, "pr")])

    def test_fetcher_rejects_cross_origin_before_sending_token(self):
        fetch = make_fetcher(token="secret", api_root="https://api.github.test")
        with self.assertRaisesRegex(GitHubApiError, "cross-origin"):
            fetch("https://evil.example/items")

    def test_redirect_handler_rejects_cross_origin(self):\n        from scripts.unreviewed import _SameOriginRedirect\n\n        handler = _SameOriginRedirect(("https", "api.github.test"))\n        request = urllib.request.Request("https://api.github.test/items", headers={"Authorization": "Bearer secret"})\n        with self.assertRaisesRegex(GitHubApiError, "cross-origin redirect"):\n            handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/items")\n\n    def test_fetcher_timeout_and_rate_limit_diagnostics(self):
        response = io.BytesIO(json.dumps({"message": "secondary rate limit"}).encode())
        error = urllib.error.HTTPError(
            "https://api.github.test/items",
            403,
            "Forbidden",
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123", "Retry-After": "60"},
            response,
        )
        opener = mock.Mock()
        opener.open.side_effect = error
        with mock.patch("scripts.unreviewed.urllib.request.build_opener", return_value=opener):
            fetch = make_fetcher(token="secret", api_root="https://api.github.test", timeout=7)
            with self.assertRaises(GitHubApiError) as caught:
                fetch("/items")
        message = str(caught.exception)
        self.assertIn("secondary rate limit", message)
        self.assertIn("remaining=0", message)
        self.assertIn("retry-after=60", message)
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 7)


if __name__ == "__main__":
    unittest.main()
