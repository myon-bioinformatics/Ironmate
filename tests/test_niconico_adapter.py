import io
import json
from pathlib import Path
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

from adapters.niconico_adapter import (
    build_search_url, classify_page, content_url, fetch_json, next_delay_seconds,
    normalize_item, snapshot_consistent, completion_state, fetch_version,
    paged_search, VERSION_URL,
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
            with self.subTest(code=code), patch("adapters.niconico_adapter.time.monotonic", side_effect=[1.0, 1.25]):
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
        with patch("adapters.niconico_adapter.time.monotonic", side_effect=[1.0, 1.1]):
            fetch_json("https://example.test", user_agent="Ironmate", opener=opener)
        self.assertEqual(seen["ua"], "Ironmate")
        self.assertFalse(snapshot_consistent({"last_modified": ""}, {"last_modified": ""}))

class VersionObservationTest(unittest.TestCase):
    # Independently authored timestamps and content; no live API requests.
    version = {"last_modified": "2026-10-01T05:00:00+09:00"}
    changed = {"last_modified": "2026-10-02T05:00:00+09:00"}

    def run_search(self, responses, **kwargs):
        seen, events, waits = [], [], []
        responses = iter(responses)

        def opener(request, timeout):
            seen.append(request)
            events.append(("request", request.full_url))
            self.assertEqual(request.get_header("User-agent"), "Ironmate-offline")
            self.assertEqual(timeout, 7)
            value = next(responses)
            if isinstance(value, Exception):
                raise value
            return io.BytesIO(value if isinstance(value, bytes) else json.dumps(value).encode())

        def sleeper(delay):
            waits.append(delay)
            events.append(("wait", delay))

        # Each HTTP request takes exactly 1.25s in this deterministic clock.
        with patch("adapters.niconico_adapter.time.monotonic", side_effect=[
            t for i in range(20) for t in (i * 10.0, i * 10.0 + 1.25)
        ]):
            result = paged_search(q="", sort="-startTime", context="Ironmate-offline",
                                  user_agent="Ironmate-offline", timeout=7,
                                  opener=opener, sleeper=sleeper, **kwargs)
        self.assertEqual([event[0] for event in events],
                         ["request"] + [v for _ in waits for v in ("wait", "request")])
        return result, seen, waits

    @staticmethod
    def page(ids, total):
        return {"meta": {"status": 200, "totalCount": total},
                "data": [{"contentId": ident, "title": "synthetic", "userId": 123}
                         for ident in ids]}

    @staticmethod
    def http_error(code):
        return HTTPError(VERSION_URL, code, "synthetic", Message(),
                         io.BytesIO(b'{"meta":{"errorCode":"synthetic"}}'))

    def test_same_version_surrounds_all_pages_and_preserves_provenance(self):
        result, requests, waits = self.run_search([
            self.version, self.page(["sm9001"], 2), self.page(["sm9002"], 2), self.version,
        ], limit=1)
        self.assertTrue(result["complete"])
        self.assertTrue(result["snapshot_consistent"])
        self.assertEqual(result["pages_fetched"], 2)
        self.assertEqual(requests[0].full_url, VERSION_URL)
        self.assertEqual(requests[-1].full_url, VERSION_URL)
        self.assertEqual(waits, [1.25] * 3)
        self.assertEqual(result["retry_delay_seconds"], 1.25)
        self.assertEqual(result["version_before"]["last_modified"], self.version["last_modified"])
        self.assertEqual(result["version_after"]["last_modified"], self.version["last_modified"])
        for i, record in enumerate(result["records"]):
            self.assertEqual(record["source_url"], requests[i + 1].full_url)
            self.assertEqual(parse_qs(urlsplit(record["source_url"]).query)["_offset"], [str(i)])
            self.assertNotIn("userId", record["data"])

    def test_version_change_is_incomplete_even_when_pages_complete(self):
        result, _, _ = self.run_search([self.version, self.page(["sm9001"], 1), self.changed])
        self.assertTrue(result["page"]["complete"])
        self.assertFalse(result["complete"])
        self.assertFalse(result["snapshot_consistent"])

    def test_http_version_failure_is_never_complete_before_or_after(self):
        for code, status in ((400, "invalid_request"), (503, "maintenance"), (500, "error")):
            for position in ("before", "after"):
                with self.subTest(code=code, position=position):
                    responses = [self.http_error(code)] if position == "before" else [
                        self.version, self.page([], 0), self.http_error(code),
                    ]
                    result, requests, _ = self.run_search(responses)
                    self.assertFalse(result["complete"])
                    self.assertFalse(result["snapshot_consistent"])
                    observation = result["version_" + position]
                    self.assertEqual(observation["status"], status)
                    self.assertEqual(observation["http_status"], code)
                    self.assertNotIn("last_modified", observation)
                    self.assertEqual(len(requests), 1 if position == "before" else 3)
                    self.assertEqual(result["retry_delay_seconds"], 300.0 if code == 503 else 1.25)

    def test_missing_last_modified_is_incomplete_before_or_after(self):
        for position in ("before", "after"):
            with self.subTest(position=position):
                responses = [{}] if position == "before" else [self.version, self.page([], 0), {}]
                result, _, _ = self.run_search(responses)
                self.assertFalse(result["complete"])
                self.assertEqual(result["version_" + position]["error_type"], "invalid_version")

    def test_malformed_json_and_network_failure_are_incomplete(self):
        for failure in (b'{', b'\xff', URLError("offline")):
            for position in ("before", "after"):
                with self.subTest(failure=failure, position=position):
                    responses = [failure] if position == "before" else [
                        self.version, self.page([], 0), failure,
                    ]
                    result, _, _ = self.run_search(responses)
                    self.assertFalse(result["complete"])
                    self.assertEqual(result["version_" + position]["status"], "error")

    def test_version_helper_rejects_invalid_shapes_types_and_dates(self):
        for payload in (None, [], "stamp", {"last_modified": None}, {"last_modified": 1},
                        {"last_modified": []}, {"last_modified": ""},
                        {"last_modified": "2026-02-30T05:00:00+09:00"},
                        {"last_modified": "2026-10-01"},
                        {"last_modified": "2026-10-01T05:00:00"}):
            with self.subTest(payload=payload):
                result = fetch_version(user_agent="offline", opener=lambda *a, **k:
                                       io.BytesIO(json.dumps(payload).encode()))
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error_type"], "invalid_version")
                self.assertNotIn("last_modified", result)

    def test_page_http_failure_keeps_classification_and_paces_final_version(self):
        for code, status in ((400, "invalid_request"), (503, "maintenance")):
            with self.subTest(code=code):
                result, requests, waits = self.run_search([
                    self.version, self.http_error(code), self.version,
                ])
                self.assertFalse(result["complete"])
                self.assertEqual(result["page"]["status"], status)
                self.assertEqual(result["page"]["fetch"]["http_status"], code)
                self.assertEqual(len(requests), 3)  # no search retry
                self.assertEqual(waits, [1.25, 300.0 if code == 503 else 1.25])

    def test_page_limit_and_invalid_pages_cannot_be_completed_by_matching_version(self):
        result, _, _ = self.run_search([
            self.version, self.page(["sm9001"], 2), self.version,
        ], limit=1, max_pages=1)
        self.assertFalse(result["complete"])
        self.assertTrue(result["page"]["truncated"])
        for payload in ([], {}, {"meta": {"totalCount": 1}, "data": [None]},
                        self.page([], 1)):
            with self.subTest(payload=payload):
                result, _, _ = self.run_search([self.version, payload, self.version])
                self.assertFalse(result["complete"])
                self.assertEqual(result["records"], [])

    def test_provider_offset_limit_is_still_truncated(self):
        result, _, _ = self.run_search([
            self.version, self.page(["sm9001"], 100002), self.version,
        ], offset=100000, limit=1)
        self.assertFalse(result["complete"])
        self.assertTrue(result["page"]["truncated"])


if __name__ == "__main__":
    unittest.main()
