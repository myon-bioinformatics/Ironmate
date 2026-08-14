import unittest
from ironmate_mcp import _validate
class ValidateTest(unittest.TestCase):
 def test_validate(self): self.assertEqual(_validate(" Flutter ",5),("flutter",5))
 def test_invalid(self):
  with self.assertRaises(ValueError): _validate("",0)
