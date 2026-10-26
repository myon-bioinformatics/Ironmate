"""All truth tables, independent operator semantics and context controls."""
import unittest
from scripts import littlebit_jev_5way_survey as s

class TruthTables(unittest.TestCase):
    def test_all_functions(self):
        functions = (
            lambda a,b: False, lambda a,b: not(a or b),
            lambda a,b: not a and b, lambda a,b: not a,
            lambda a,b: a and not b, lambda a,b: not b,
            lambda a,b: a != b, lambda a,b: not(a and b),
            lambda a,b: a and b, lambda a,b: a == b,
            lambda a,b: b, lambda a,b: not a or b,
            lambda a,b: a, lambda a,b: not b or a,
            lambda a,b: a or b, lambda a,b: True)
        self.assertEqual(len(s.BOOLEAN_4BIT_LUT), 16)
        for code, fn in enumerate(functions):
            calls = []
            def oracle(board):
                calls.append(board)
                return fn(bool(board & 2), bool(board & 32))
            result = s.classify_pairwise_boolean_4bit_lut(130, 2, 32, oracle)
            self.assertEqual(result['tt_code'], code)
            self.assertEqual(result['formula'], s.BOOLEAN_4BIT_LUT[code])
            self.assertEqual(calls, [128, 160, 130, 162])
            self.assertEqual(result['queries_used'], len(calls))

    def test_context_dependence(self):
        def oracle(b):
            return bool(b & 4) or (bool(b & 1) != bool(b & 2))
        self.assertEqual(s.classify_pairwise_boolean_4bit_lut(0, 1, 2, oracle)['tt_code'], 6)
        self.assertEqual(s.classify_pairwise_boolean_4bit_lut(4, 1, 2, oracle)['tt_code'], 15)

    def test_invalid_inputs_before_oracle(self):
        def forbidden(b):
            self.fail('invalid input reached oracle')
        for args in ((-1,1,2), (True,1,2), (0,0,2), (0,3,4), (0,1,1), (0,True,2)):
            with self.assertRaises(ValueError):
                s.classify_pairwise_boolean_4bit_lut(*args, forbidden)

    def test_errors_propagate(self):
        with self.assertRaises(TypeError):
            s.classify_pairwise_boolean_4bit_lut(0,1,2,lambda b: 1)
        def broken(b):
            raise RuntimeError('oracle failed')
        with self.assertRaises(RuntimeError):
            s.classify_pairwise_boolean_4bit_lut(0,1,2,broken)
