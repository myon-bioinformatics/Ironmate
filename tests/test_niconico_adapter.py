import io
import json
from pathlib import Path
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from niconico_adapter import (
    build_search_url, classify_page, content_url, fetch_json, next_delay_seconds,
    normalize_item, snapshot_consistent,
)


class NiconicoAdapterTest(unittest.TestCase):
    def test_search_url_exact_encoding(self):
        url = build_search_url(
            q="初音 ミク", targets="title,description", sort="+viewCounter",
            context="Ironmate", limit=100, offset=0,
            filters={"filters[viewCounter][gte]": 10},
        )
        self.assertEqual(
            url,
            "https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search"
            "?q=%E5%88%9D%E9%9F%B3+%E3%83%9F%E3%82%AF"
            "&targets=title%2Cdescription"
            "&fields=contentId%2Ctitle%2Cdescription%2Ctags%2CcategoryTags%2CviewCounter%2CmylistCounter%2ClikeCounter%2ClengthSeconds%2CstartTime%2ClastCommentTime%2CcommentCounter%2Cgenre"
            "&_sort=%2BviewCounter&_offset=0&_limit=100&_context=Ironmate"
            "&filters%5BviewCounter%5D%5Bgte%5D=10",
        )

    def test_empty_q_is_retained_and_keyword_search_requires_targets(self):
        url = build_search_url(q="", sort="-startTime", context="Ironmate")
        self.assertIn("?q=&", url)
        with self.assertRaises(ValueError):
            build_search_url(q="keyword", sort="-startTime", context="Ironmate")

    def test_bounds_context_and_excluded_fields(self):
        for kwargs in ({"limit": 101}, {"offset": 100001}, {"context": "x" * 41}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_search_url(q="", sort="-startTime", context=kwargs.pop("context", "Ironmate"), **kwargs)
        with self.assertRaises(ValueError):
            build_search_url(q="", sort="-startTime", context="Ironmate", fields=("contentId", "userId"))

    def test_content_url_is_conservative(self):
        self.assertEqual(content_url("sm12345"), "https://nico.ms/sm12345")
        for value in ("", "sm/1", "初音"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                content_url(value)

    def test_fixture_normalization_drops_excluded_fields(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "niconico_snapshot_v2.json").read_text())
        source = build_search_url(q="", sort="-startTime", context="Ironmate")
        item = normalize_item(fixture["search"]["data"][0], source_url=source)
        self.assertEqual(item["identifier"], "sm12345")
        self.assertEqual(item["html_url"], "https://nico.ms/sm12345")
        self.assertIsNone(item["api_url"])
        self.assertNotIn("userId", item["data"])
        self.assertNotIn("lastResBody", item["data"])

    def test_snapshot_consistency_and_pagination(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "niconico_snapshot_v2.json").read_text())
        self.assertTrue(snapshot_consistent(fixture["version_before"], fixture["version_after"]))
        self.assertFalse(snapshot_consistent(fixture["version_before"], {"last_modified": "changed"}))
        self.assertTrue(classify_page(fixture["search"], offset=0, limit=10)["complete"])
        state = classify_page({"meta": {"totalCount": 100001}, "data": [{}]}, offset=99999, limit=1)
        self.assertTrue(state["truncated"])
        self.assertFalse(state["complete"])

    def test_http_statuses_preserve_error_body_offline(self):
        headers = Message()
        for code, expected in ((400, "invalid_request"), (503, "maintenance")):
            error = HTTPError("https://example.test", code, "x", headers, io.BytesIO(b'{"meta":{"errorCode":"synthetic"}}'))
            with self.subTest(code=code), patch("niconico_adapter.time.monotonic", side_effect=[1.0, 1.25]):
                result = fetch_json("https://example.test", user_agent="Ironmate", opener=lambda *a, **k: (_ for _ in ()).throw(error))
            self.assertEqual(result["status"], expected)
            self.assertEqual(result["error"]["meta"]["errorCode"], "synthetic")
            self.assertEqual(result["elapsed_seconds"], 0.25)

    def test_rate_delay_is_testable_without_sleep(self):
        self.assertEqual(next_delay_seconds(1.25), 1.25)
        self.assertEqual(next_delay_seconds(0.1, http_status=503), 300.0)


    def test_required_negative_cases_and_user_agent_header(self):
        with self.assertRaises(ValueError):
            build_search_url(q="", sort="", context="Ironmate")
        with self.assertRaises(ValueError):
            build_search_url(q="", sort="-startTime", context="")
        with self.assertRaises(ValueError):
            fetch_json("https://example.test", user_agent="", opener=lambda *a, **k: None)

        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b'{}'

        seen = {}
        def opener(request, timeout):
            seen["ua"] = request.get_header("User-agent")
            return Response()
        with patch("niconico_adapter.time.monotonic", side_effect=[1.0, 1.1]):
            fetch_json("https://example.test", user_agent="Ironmate", opener=opener)
        self.assertEqual(seen["ua"], "Ironmate")
        self.assertFalse(snapshot_consistent({"last_modified": ""}, {"last_modified": ""}))

if __name__ == "__main__":
    unittest.main()
