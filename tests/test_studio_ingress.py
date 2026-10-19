import base64
import unittest
from unittest.mock import patch

import studio_ingress as ingress
from studio_ingress import MAX_BYTES, decode, parse_shelf

PNG = bytes.fromhex("89504e470d0a1a0a") + b"payload"


class PortableIngressTests(unittest.TestCase):
    def test_raw_and_uri(self):
        b64 = base64.b64encode(PNG).decode()
        self.assertEqual(decode(b64), ("image/png", PNG))
        self.assertEqual(decode("data:image/png;base64," + b64), ("image/png", PNG))

    def test_mismatch(self):
        with self.assertRaises(ValueError):
            decode("data:image/jpeg;base64," + base64.b64encode(PNG).decode())

    def test_limit(self):
        with self.assertRaises(ValueError):
            decode(base64.b64encode(PNG).decode(), max_bytes=len(PNG) - 1)

    def test_padding(self):
        with self.assertRaises(ValueError):
            decode(base64.b64encode(PNG + b"x").decode().rstrip("="))

    def test_parse_shelf(self):
        b64 = base64.b64encode(PNG).decode()
        items = [
            "data:image/png;base64," + b64,
            "plain text note",
            {"text": b64, "label": "Custom PNG"},
        ]
        parsed = parse_shelf(items)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["type"], "image")
        self.assertEqual(parsed[0]["mime"], "image/png")
        self.assertEqual(parsed[0]["data"], PNG)
        self.assertEqual(parsed[1]["type"], "text")
        self.assertIsNone(parsed[1]["data"])
        self.assertEqual(parsed[2]["type"], "image")
        self.assertEqual(parsed[2]["label"], "Custom PNG")

    def test_parse_shelf_limits(self):
        with self.assertRaises(ValueError):
            parse_shelf(["item"] * 21)

    def test_aggregate_inclusive_boundary_and_remaining_decode_budget(self):
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        for delta in (-1, 0, 1):
            with self.subTest(delta=delta), patch.object(ingress, "decode", wraps=decode) as spy:
                budget = 2 * len(PNG) + delta
                if delta < 0:
                    with self.assertRaises(ValueError):
                        parse_shelf([uri, uri], max_bytes=budget)
                else:
                    self.assertEqual(len(parse_shelf([uri, uri], max_bytes=budget)), 2)
                self.assertEqual([call.kwargs["max_bytes"] for call in spy.call_args_list],
                                 [budget, budget - len(PNG)])

    def test_refuses_before_base64_allocation_even_with_rounded_length(self):
        # All three sizes have the same encoded length: the exact byte check is required.
        for remaining in (len(PNG) - 1, len(PNG) - 2):
            with self.subTest(remaining=remaining), patch.object(ingress.base64, "b64decode") as decoder:
                with self.assertRaises(ValueError):
                    decode(base64.b64encode(PNG).decode(), max_bytes=remaining)
                decoder.assert_not_called()

    def test_real_32mib_aggregate_boundary(self):
        encoded = base64.b64encode(PNG).decode()
        note = "n" * (MAX_BYTES - len(PNG))
        self.assertEqual(len(parse_shelf([note, encoded])), 2)
        with self.assertRaises(ValueError):
            parse_shelf([note + "x", encoded])
        with self.assertRaises(ValueError):
            parse_shelf([note, encoded, encoded])

    def test_explicit_image_errors_never_become_notes(self):
        b64 = base64.b64encode(PNG).decode()
        cases = ["data:image/jpeg;base64," + b64,
                 "data:text/plain;base64," + b64,
                 "data:image/png;base64,%%%", "data:image/png,broken", "data:",
                 "data:image/png;base64,", b64[:-1] + "!",
                 {"type": "image", "text": "broken"}, {"type": "image", "data": ""},
                 {"mime": "image/jpeg", "text": b64}, {"mime": "image/gif", "text": b64}]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                parse_shelf(["existing note", item])
        with self.assertRaises(ValueError):
            parse_shelf([b64], max_bytes=len(PNG) - 1)

    def test_notes_count_utf8_and_full_shelf_rejects_more_images(self):
        self.assertEqual(parse_shelf(["🌱", "abc"], max_bytes=7)[1]["text"], "abc")
        with self.assertRaises(ValueError):
            parse_shelf(["🌱", "abcd"], max_bytes=7)
        uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        with self.assertRaises(ValueError):
            parse_shelf([uri, uri], max_bytes=len(PNG))
        self.assertEqual(len(parse_shelf(["note"] * 20)), 20)
        self.assertEqual(parse_shelf(["\ufeff " + uri])[0]["type"], "image")


if __name__ == "__main__":
    unittest.main()
