#!/usr/bin/env python3
"""A small, dependency-free arithmetic calculator.

Evaluates expressions made of numbers, the operators ``+ - * / % ^`` and
parentheses, respecting the usual precedence rules (``^`` is right-associative
and binds tighter than unary minus, so ``-2^2`` is ``-4``).

Usage:
    python3 calculator.py "2 + 3 * 4"
    python3 calculator.py "2 * (3 + 4)" --json
    python3 calculator.py            # interactive prompt
    echo "10 / 4" | python3 calculator.py
"""

from __future__ import annotations

import argparse
import json
import sys


class CalculatorError(ValueError):
    """Raised for malformed expressions or invalid arithmetic."""


_BINARY_OPERATORS = {"+", "-", "*", "/", "%", "^"}


def tokenize(expression: str) -> list[str]:
    """Split an expression into number and operator tokens."""
    tokens: list[str] = []
    i = 0
    length = len(expression)
    while i < length:
        char = expression[i]
        if char.isspace():
            i += 1
        elif char.isdigit() or char == ".":
            start = i
            seen_dot = False
            while i < length and (expression[i].isdigit() or expression[i] == "."):
                if expression[i] == ".":
                    if seen_dot:
                        raise CalculatorError(f"invalid number at position {start}")
                    seen_dot = True
                i += 1
            tokens.append(expression[start:i])
        elif char in _BINARY_OPERATORS or char in "()":
            tokens.append(char)
            i += 1
        else:
            raise CalculatorError(f"unexpected character {char!r} at position {i}")
    return tokens


class _Parser:
    """Recursive-descent parser for the supported grammar."""

    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> str:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def parse(self) -> float | int:
        if not self.tokens:
            raise CalculatorError("empty expression")
        value = self._expression()
        if self.pos != len(self.tokens):
            raise CalculatorError(f"unexpected token {self.tokens[self.pos]!r}")
        return value

    def _expression(self) -> float | int:
        value = self._term()
        while self._peek() in ("+", "-"):
            operator = self._advance()
            right = self._term()
            value = value + right if operator == "+" else value - right
        return value

    def _term(self) -> float | int:
        value = self._unary()
        while self._peek() in ("*", "/", "%"):
            operator = self._advance()
            right = self._unary()
            if operator == "*":
                value = value * right
            elif right == 0:
                raise CalculatorError("division by zero")
            elif operator == "/":
                value = value / right
            else:
                value = value % right
        return value

    def _unary(self) -> float | int:
        token = self._peek()
        if token in ("+", "-"):
            self._advance()
            value = self._unary()
            return value if token == "+" else -value
        return self._power()

    def _power(self) -> float | int:
        value = self._primary()
        if self._peek() == "^":
            self._advance()
            exponent = self._unary()
            value = value ** exponent
        return value

    def _primary(self) -> float | int:
        token = self._peek()
        if token is None:
            raise CalculatorError("unexpected end of expression")
        if token == "(":
            self._advance()
            value = self._expression()
            if self._peek() != ")":
                raise CalculatorError("missing closing parenthesis")
            self._advance()
            return value
        if token == ")":
            raise CalculatorError("unexpected ')'")
        self._advance()
        return _to_number(token)


def _to_number(token: str) -> float | int:
    if token.count(".") > 1:
        raise CalculatorError(f"invalid number {token!r}")
    if token == ".":
        raise CalculatorError(f"invalid number {token!r}")
    return float(token) if "." in token else int(token)


def _normalize(value: float | int) -> float | int:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def calculate(expression: str) -> float | int:
    """Evaluate an arithmetic expression and return the result.

    Raises ``CalculatorError`` for malformed input or division by zero.
    """
    result = _Parser(tokenize(expression)).parse()
    return _normalize(result)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description="Arithmetic calculator")
    parser.add_argument("--json", action="store_true", help="output JSON")

    if any(token in ("-h", "--help") for token in argv):
        parser.print_help()
        return 0

    # Flags are extracted by hand so that expressions beginning with a minus
    # sign (e.g. "-2^2") are not mistaken for command-line options.
    json_output = "--json" in argv
    tokens = [token for token in argv if token != "--json"]

    if tokens:
        return _run(" ".join(tokens), json_output)

    if not sys.stdin.isatty():
        return _run(sys.stdin.read().strip(), json_output)

    print("Arithmetic calculator. Type an expression or 'quit' to exit.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in ("quit", "exit"):
            return 0
        if line:
            _run(line, json_output)
    return 0


def _run(expression: str, as_json: bool) -> int:
    try:
        result = calculate(expression)
    except CalculatorError as error:
        if as_json:
            print(json.dumps({"expression": expression, "error": str(error)}))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps({"expression": expression, "result": result}))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
