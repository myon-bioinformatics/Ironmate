import base64
import unittest

from studio_ingress import decode, parse_shelf

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


if __name__ == "__main__":
    unittest.main()
