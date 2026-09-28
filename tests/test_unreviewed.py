"""Offline tests for the portable unreviewed GitHub diagnostics."""

import unittest

from scripts.unreviewed import _next_link, paged, reviewer_pattern, unreviewed


class UnreviewedDiagnosticsTest(unittest.TestCase):
    def test_next_link_extracts_next_relation(self):
        value = '<https://api.github.test/items?page=2>; rel="next", <https://api.github.test/items?page=3>; rel="last"'
        self.assertEqual(_next_link(value), "https://api.github.test/items?page=2")

    def test_paged_follows_link_header(self):
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

    def test_reviewer_pattern_is_line_scoped_and_case_insensitive(self):
        pattern = reviewer_pattern("Claude")
        self.assertTrue(pattern.search("note\nfrom: claude\n"))
        self.assertFalse(pattern.search("quoted from: claude elsewhere"))
        self.assertFalse(pattern.search("from: claude-extra"))

    def test_unreviewed_checks_issue_and_all_pr_comment_surfaces(self):
        def fetch(url):
            if url.startswith("/orgs/acme/repos"):
                return ([{"name": "demo"}], {})
            if url == "/repos/acme/demo/issues?state=open&per_page=100":
                return (
                    [
                        {"number": 1, "title": "plain issue"},
                        {"number": 2, "title": "reviewed issue"},
                        {"number": 3, "title": "reviewed pr", "pull_request": {}},
                        {"number": 4, "title": "unreviewed pr", "pull_request": {}},
                    ],
                    {},
                )
            mapping = {
                "/repos/acme/demo/issues/1/comments?per_page=100": ([], {}),
                "/repos/acme/demo/issues/2/comments?per_page=100": ([{"body": "from: bot"}], {}),
                "/repos/acme/demo/issues/3/comments?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/3/reviews?per_page=100": ([{"body": "FROM: BOT"}], {}),
                "/repos/acme/demo/pulls/3/comments?per_page=100": ([], {}),
                "/repos/acme/demo/issues/4/comments?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/4/reviews?per_page=100": ([], {}),
                "/repos/acme/demo/pulls/4/comments?per_page=100": ([], {}),
            }
            return mapping[url]

        self.assertEqual(
            list(unreviewed(fetch, "acme", "bot")),
            [
                ("demo", "IS", 1, "plain issue"),
                ("demo", "PR", 4, "unreviewed pr"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
