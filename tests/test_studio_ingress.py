import base64
import unittest

from studio_ingress import decode

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


if __name__ == "__main__":
    unittest.main()
