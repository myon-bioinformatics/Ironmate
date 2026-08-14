import io
import unittest
from unittest.mock import patch
from ironmate_mcp import _validate, list_portfolio_repositories
class ValidateTest(unittest.TestCase):
 def test_validate(self): self.assertEqual(_validate(" Flutter ",5),("flutter",5))
 def test_invalid(self):
  with self.assertRaises(ValueError): _validate("",0)
 def test_filters_fixture(self):
  with patch("ironmate_mcp.urlopen",return_value=io.BytesIO(b'[{"name":"Flutter"},{"name":"Python"}]')): result=list_portfolio_repositories("flutter",1)
  self.assertEqual(result["items"],[{"name":"Flutter"}])
 def test_failure_is_safe(self):
  with patch("ironmate_mcp.urlopen",side_effect=OSError("private detail")): result=list_portfolio_repositories()
  self.assertEqual(result["error"],"source_fetch_failed")
 def test_bad_shape_is_safe(self):
  with patch("ironmate_mcp.urlopen",return_value=io.BytesIO(b'null')): result=list_portfolio_repositories()
  self.assertEqual(result["error"],"source_payload_invalid")
 def test_missing_repository_key_is_safe(self):
  with patch("ironmate_mcp.urlopen",return_value=io.BytesIO(b'{}')): result=list_portfolio_repositories()
  self.assertEqual(result["error"],"source_payload_invalid")
