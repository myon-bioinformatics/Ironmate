import io
import json
from pathlib import Path
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError

from niconico_adapter import (
    build_search_url, classify_page, content_url, fetch_json, next_delay_seconds,
    normalize_item, snapshot_consistent, completion_state,
    export_with_snapshot_check, fetch_version, parse_version, VERSION_URL,
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
        for kwargs in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 100001}, {"context": "x" * 41}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_search_url(q="", sort="-startTime", context=kwargs.pop("context", "Ironmate"), **kwargs)
        with self.assertRaises(ValueError):
            build_search_url(q="", sort="-startTime", context="Ironmate", fields=("contentId", "userId"))
        for bad_filters in ({"fields": "contentId,userId,lastResBody"}, {"_context": "x" * 100}, {"_limit": 1000}, {"filtersX": 1}, {1: "x"}):
            with self.subTest(bad_filters=bad_filters), self.assertRaises(ValueError):
                build_search_url(q="", sort="-startTime", context="Ironmate", filters=bad_filters)

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
        self.assertEqual(item["provider"], "niconico")
        self.assertEqual(item["kind"], "video")
        self.assertEqual(item["source_url"], source)
        self.assertIsNone(normalize_item({"contentId": ""}, source_url=source)["html_url"])
        self.assertIsNone(normalize_item({"contentId": "so-1"}, source_url=source)["html_url"])

    def test_snapshot_consistency_and_pagination(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "niconico_snapshot_v2.json").read_text())
        self.assertTrue(snapshot_consistent(fixture["version_before"], fixture["version_after"]))
        self.assertFalse(snapshot_consistent(fixture["version_before"], {"last_modified": "changed"}))
        self.assertTrue(classify_page(fixture["search"], offset=0, limit=10)["complete"])
        state = classify_page({"meta": {"totalCount": 100001}, "data": [{}]}, offset=99999, limit=1)
        self.assertEqual(state["next_offset"], 100000)
        self.assertFalse(state["complete"])
        final = classify_page({"meta": {"totalCount": 100001}, "data": [{}]}, offset=100000, limit=1)
        self.assertTrue(final["complete"])
        self.assertFalse(final["truncated"])
        beyond = classify_page({"meta": {"totalCount": 100002}, "data": [{}]}, offset=100000, limit=1)
        self.assertTrue(beyond["truncated"])
        self.assertIsNone(beyond["next_offset"])
        self.assertTrue(completion_state(fixture["version_before"], fixture["version_after"], final)["complete"])
        self.assertFalse(completion_state(fixture["version_before"], {"last_modified": "changed"}, final)["complete"])
        stalled = classify_page({"meta": {"totalCount": 5}, "data": []}, offset=0, limit=10)
        self.assertEqual(stalled["status"], "stalled")
        self.assertIsNone(stalled["next_offset"])
        invalid = classify_page({}, offset=0, limit=10)
        self.assertEqual(invalid["status"], "invalid")
        self.assertFalse(invalid["complete"])
        for page in (beyond, stalled, invalid, {"status": "ok", "complete": False, "truncated": False}):
            with self.subTest(page=page):
                self.assertFalse(completion_state(fixture["version_before"], fixture["version_after"], page)["complete"])

    def test_invalid_meta_is_not_complete(self):
        for meta in ({"status": 500, "totalCount": 1}, {"status": 200, "totalCount": None}, {"totalCount": "1"}, {}):
            with self.subTest(meta=meta):
                state = classify_page({"meta": meta, "data": [{}]}, offset=0, limit=1)
                self.assertEqual(state["status"], "invalid")
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

def _page(total, n):
    return {"status": "detected", "elapsed_seconds": 0.5,
            "value": {"meta": {"status": 200, "totalCount": total}, "data": [{"contentId": "sm1"}] * n}}


def _ver(value, elapsed=0.25):
    return {"status": "detected", "elapsed_seconds": elapsed, "value": value}


class VersionAndExportTest(unittest.TestCase):
    V = "2026-09-28T05:00:00+09:00"
    KW = {"q": "", "sort": "-startTime", "context": "Ironmate", "limit": 1}

    def run_export(self, responses, kw=None):
        calls, sleeps, queue = [], [], list(responses)

        def fetch(url, **k):
            calls.append((url, k))
            return queue.pop(0)
        result = export_with_snapshot_check(user_agent="Ironmate", search_kwargs=kw or self.KW,
                                            fetch=fetch, sleep=sleeps.append)
        return result, calls, sleeps

    def test_parse_version_rejects_bad_shapes(self):
        self.assertEqual(parse_version({"last_modified": self.V}), self.V)
        for bad in ([], None, {}, {"last_modified": None}, {"last_modified": ""}, {"last_modified": 5},
                    {"last_modified": "garbage"}, {"last_modified": "2026-09-28T05:00:00"}):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_version(bad))

    def test_fetch_version_ok_and_failures(self):
        seen = {}

        def fetch(url, **k):
            seen.update(url=url, **k)
            return _ver({"last_modified": self.V})
        ok = fetch_version(user_agent="Ironmate", timeout=7, fetch=fetch)
        self.assertEqual((ok["status"], ok["last_modified"]), ("ok", self.V))
        self.assertEqual((seen["url"], seen["user_agent"], seen["timeout"]), (VERSION_URL, "Ironmate", 7))
        bad = fetch_version(user_agent="x", fetch=lambda u, **k: _ver({"last_modified": ""}))
        self.assertEqual((bad["status"], bad["reason"]), ("parse_failed", "invalid_last_modified"))
        for status, http in (("invalid_request", 400), ("maintenance", 503), ("error", 500), ("error", None)):
            r = fetch_version(user_agent="x", fetch=lambda u, **k: {"status": status, "http_status": http})
            self.assertEqual((r["status"], r["reason"], r["last_modified"]), (status, "fetch_failed", None))

    def test_complete_only_with_matching_versions_and_all_pages(self):
        r, calls, sleeps = self.run_export([
            _ver({"last_modified": self.V}), _page(2, 1), _page(2, 1), _ver({"last_modified": self.V})])
        self.assertTrue(r["complete"])
        self.assertIsNone(r["reason"])
        self.assertEqual(len(r["items"]), 2)
        self.assertEqual([c[0] == VERSION_URL for c in calls], [True, False, False, True])
        self.assertEqual(sleeps, [0.25, 0.5, 0.5])
        self.assertTrue(all(c[1]["user_agent"] == "Ironmate" for c in calls))

    def test_snapshot_change_is_incomplete(self):
        r, _, _ = self.run_export([
            _ver({"last_modified": self.V}), _page(1, 1), _ver({"last_modified": "2026-09-29T05:00:00+09:00"})])
        self.assertFalse(r["complete"])
        self.assertEqual(r["reason"], "snapshot_changed")

    def test_observation_failures_never_complete(self):
        good = _ver({"last_modified": self.V})
        malformed = _ver({"last_modified": "bad"})
        fail = {"status": "error", "error_type": "TimeoutError", "elapsed_seconds": 1.0}
        r, calls, _ = self.run_export([fail])
        self.assertEqual((r["complete"], r["reason"], len(calls)), (False, "version_observation_failed", 1))
        r, _, _ = self.run_export([malformed])
        self.assertFalse(r["complete"])
        for after in (malformed, fail):
            r, _, _ = self.run_export([good, _page(1, 1), after])
            self.assertEqual((r["complete"], r["reason"]), (False, "version_observation_failed"))

    def test_page_problems_are_incomplete(self):
        good = _ver({"last_modified": self.V})
        r, calls, _ = self.run_export([good, {"status": "invalid_request", "http_status": 400, "elapsed_seconds": 0.1}])
        self.assertEqual((r["complete"], r["reason"], len(calls)), (False, "page_fetch_failed", 2))
        r, _, _ = self.run_export([good, _page(5, 0)])
        self.assertEqual(r["reason"], "page_stalled")
        r, _, _ = self.run_export([good, {"status": "detected", "value": {}, "elapsed_seconds": 0}])
        self.assertEqual(r["reason"], "page_invalid")

    def test_truncation_and_503_delay(self):
        good = _ver({"last_modified": self.V})
        r, _, _ = self.run_export([good, _page(100002, 1), good], kw=dict(self.KW, offset=100000))
        self.assertFalse(r["complete"])
        self.assertEqual(r["reason"], "provider_limit_truncated")
        maint = {"status": "maintenance", "http_status": 503, "elapsed_seconds": 0.1}
        r, calls, _ = self.run_export([maint])
        self.assertEqual(r["version_before"]["status"], "maintenance")
        self.assertEqual(len(calls), 1)
        r, _, sleeps = self.run_export([good, maint])
        self.assertEqual(r["reason"], "page_fetch_failed")
        self.assertEqual(sleeps, [0.25])


if __name__ == "__main__":
    unittest.main()
