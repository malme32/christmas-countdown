import io
import json
import unittest
from unittest import mock

import calculator as calc


class BasicOperationTests(unittest.TestCase):
    def test_addition_and_subtraction(self):
        self.assertEqual(calc.calculate("2 + 3 - 1"), 4)

    def test_multiplication_and_division(self):
        self.assertEqual(calc.calculate("2 * 3 / 4"), 1.5)

    def test_modulo(self):
        self.assertEqual(calc.calculate("10 % 3"), 1)

    def test_power_is_right_associative(self):
        self.assertEqual(calc.calculate("2 ^ 3 ^ 2"), 512)

    def test_operator_precedence(self):
        self.assertEqual(calc.calculate("2 + 3 * 4"), 14)

    def test_parentheses_override_precedence(self):
        self.assertEqual(calc.calculate("(2 + 3) * 4"), 20)

    def test_negative_result_is_normalised_to_int(self):
        result = calc.calculate("-2^2")
        self.assertEqual(result, -4)
        self.assertIsInstance(result, int)


class UnaryAndWhitespaceTests(unittest.TestCase):
    def test_unary_minus(self):
        self.assertEqual(calc.calculate("-5 + 3"), -2)

    def test_double_unary(self):
        self.assertEqual(calc.calculate("--5"), 5)

    def test_whitespace_is_ignored(self):
        self.assertEqual(calc.calculate("  2   +\t3 "), 5)

    def test_decimal_numbers(self):
        self.assertEqual(calc.calculate("0.1 + 0.2"), 0.30000000000000004)
        self.assertEqual(calc.calculate(".5 * 4"), 2)


class ErrorTests(unittest.TestCase):
    def test_empty_expression_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("")

    def test_division_by_zero_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("1 / 0")

    def test_modulo_by_zero_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("1 % 0")

    def test_mismatched_parenthesis_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("(1 + 2")

    def test_unexpected_character_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("1 + a")

    def test_trailing_operator_raises(self):
        with self.assertRaises(calc.CalculatorError):
            calc.calculate("1 +")


class CliTests(unittest.TestCase):
    def test_positional_expression(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            rc = calc.main(["2 + 3 * 4"])
        self.assertEqual(rc, 0)
        self.assertEqual(buffer.getvalue().strip(), "14")

    def test_json_output(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            rc = calc.main(["(2 + 3) * 4", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["expression"], "(2 + 3) * 4")
        self.assertEqual(payload["result"], 20)

    def test_error_returns_nonzero(self):
        with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            rc = calc.main(["1 / 0"])
        self.assertEqual(rc, 1)

    def test_reads_expression_from_stdin(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("10 / 4\n")), mock.patch("sys.stdout", buffer):
            rc = calc.main([])
        self.assertEqual(rc, 0)
        self.assertEqual(buffer.getvalue().strip(), "2.5")


if __name__ == "__main__":
    unittest.main()
