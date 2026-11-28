"""All truth tables, independent operator semantics and context controls."""
import importlib.util
import sys
from pathlib import Path
import unittest
from research import littlebit_jev_5way_survey as s


def load_vendored(name, relpath):
    """Load a vendored file by path under a repo-unique name (cli_args README: Loading a vendored copy)."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / relpath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


run_cli = load_vendored("ironmate_cli_args", "vendor/cli_args.py").run_cli

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

class RadixConversion(unittest.TestCase):
    def test_roundtrip_without_width_loss(self):
        for value in (*range(256), (1 << 64) - 1, 1 << 64, (1 << 1024) + 15):
            octal = s.convert_bitboard_radix(hex(value), 16, 8)
            self.assertEqual(octal, oct(value))
            self.assertEqual(s.convert_bitboard_radix(octal, 8, 16), hex(value))
        self.assertEqual(s.convert_bitboard_radix(' FF ', 16, 8), '0o377')
        self.assertEqual(s.convert_bitboard_radix('0Xf_f', 16, 16), '0xff')

    def test_invalid_values(self):
        for args in (('8',8,16), ('',16,8), ('-1',16,8), ('-0',8,16),
                     ('0xff',8,16), ('1',10,8), ('1',16,True), (1,16,8)):
            with self.assertRaises(ValueError):
                s.convert_bitboard_radix(*args)

    def test_cli_converts_without_running_benchmark(self):
        for source, target, text, expected in (
            ('16','8','0xff','0o377'), ('8','16','377','0xff')):
            result = run_cli(s.__file__, '--convert', source, target, text, python_options=('-S',))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
        result = run_cli(s.__file__, '--convert', '8', '16', '89', python_options=('-S',))
        self.assertEqual(result.returncode, 2)

class ExactRadixNumbers(unittest.TestCase):
    def test_signed_points_fractions_and_exponents(self):
        from fractions import Fraction
        cases = [('0x1.8',16,Fraction(3,2)), ('-0o1.4',8,Fraction(-3,2)),
                 ('0x1@-2',16,Fraction(1,256)), ('0o1@-2',8,Fraction(1,64)),
                 ('0xe',16,Fraction(14)), ('0x1/0x3',16,Fraction(1,3)),
                 ('-0o1/-0o3',8,Fraction(1,3)), ('0x.8',16,Fraction(1,2)),
                 ('0o7@+2',8,Fraction(448))]
        for text, base, expected in cases:
            self.assertEqual(s.parse_radix_number(text,base), expected)
            for target in (8,16):
                rendered = s.convert_radix_number(text,base,target)
                self.assertEqual(s.parse_radix_number(rendered,target), expected)
        self.assertEqual(s.convert_radix_number('0x1.8',16,8), '0o1.4')
        self.assertEqual(s.convert_radix_number('0o1/0o3',8,16), '0x1/0x3')

    def test_many_exact_rational_roundtrips(self):
        from fractions import Fraction
        for n in range(-30,31):
            for d in range(1,35):
                text = hex(n) + '/' + hex(d)
                converted = s.convert_radix_number(text,16,8)
                self.assertEqual(s.parse_radix_number(converted,8), Fraction(n,d))
                back = s.convert_radix_number(converted,8,16)
                self.assertEqual(s.parse_radix_number(back,16), Fraction(n,d))

    def test_invalid_numbers(self):
        for text in ('0x1/0', '.', '0x1.2.3', '0x1@-4097', '0x1@2@3',
                     '0x1@0x2', '0x1@+-2', '--1.0', '0x1.g', 'NaN', 'inf'):
            with self.assertRaises(ValueError, msg=text):
                s.convert_radix_number(text,16,8)
