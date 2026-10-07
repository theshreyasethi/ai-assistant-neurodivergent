"""Verified micro-step math decomposition + conceptual/procedural error
typing for dyscalculia (roadmap P4-07).

Two independent pieces:

  1. safe_eval()/verify_steps() — an LLM proposes a step-by-step breakdown of
     a problem (one operation per step, which is the whole point for a
     dyscalculia student), and EVERY step is re-checked by a restricted AST
     evaluator before a child ever sees it. The LLM never gets to just assert
     a number is right; eval()/sympify() on model output is never used —
     only a hand-written evaluator over a tiny, fixed operator set.

  2. classify_math_error() — deterministic checks first, applied directly to
     the student's wrong numeric answer against the correct one, with no LLM
     involved in the typing itself (an LLM may later be asked to EXPLAIN the
     type in friendly words, but never to DECIDE it).
"""

from __future__ import annotations

import ast
import operator as op
from fractions import Fraction
from typing import Any, Dict, List, Optional

_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv}
# No Pow: an LLM-proposed exponent on untrusted input could produce an
# astronomically large number cheaply (a classic AST-evaluator DoS); nothing
# in a single-operation micro-step for a dyscalculia student needs it anyway.

MAX_EXPR_LEN = 60

PLACE_VALUE = "PLACE_VALUE"
OPERATION_CONFUSION = "OPERATION_CONFUSION"
CARRY_BORROW = "CARRY_BORROW"
FACT_RECALL = "FACT_RECALL"
SEQUENCING = "SEQUENCING"
ERROR_TYPES = [PLACE_VALUE, OPERATION_CONFUSION, CARRY_BORROW, FACT_RECALL, SEQUENCING]


class UnsafeExpression(ValueError):
    pass


def safe_eval(expr: str) -> Fraction:
    """Evaluate a tiny arithmetic expression with a restricted AST walk —
    never Python's eval()/sympify() on model output. Fraction (not float)
    throughout so equality checks below are exact, never off-by-epsilon."""
    if not isinstance(expr, str) or len(expr) > MAX_EXPR_LEN:
        raise UnsafeExpression("expression missing or too long")

    def _ev(node: ast.AST) -> Fraction:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return Fraction(str(node.value))
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](_ev(node.left), _ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_ev(node.operand)
        raise UnsafeExpression(f"unsupported syntax: {ast.dump(node)[:80]}")

    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise UnsafeExpression(str(exc)) from exc
    return _ev(tree)


def verify_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """steps: [{"op": "add", "expr": "12+7", "result": "19", "say": "..."}].

    Each step's `expr` must evaluate (via safe_eval, never the model's own
    claim) to its stated `result`. An unverifiable step is DROPPED, never
    shown to a child — a missing step the caller falls back to a template
    for is strictly better than a confidently wrong one.
    """
    verified = []
    for step in steps:
        try:
            if safe_eval(step["expr"]) == safe_eval(str(step["result"])):
                verified.append(step)
        except (UnsafeExpression, ZeroDivisionError, KeyError, TypeError):
            continue
    return verified


# ─────────────────────── deterministic error typing ───────────────────────


def _digits_reversed(n: int) -> List[int]:
    return [int(d) for d in str(abs(int(n)))[::-1]]


def classify_math_error(
    *, expression: str, correct_answer: float, student_answer: float, operation: Optional[str] = None,
) -> str:
    """Deterministic checks only — no LLM in the decision, ever. Order
    matters: more specific checks run before the catch-all FACT_RECALL.
    """
    try:
        correct = Fraction(str(correct_answer))
        given = Fraction(str(student_answer))
    except (ValueError, ZeroDivisionError):
        return SEQUENCING  # not even a parseable number: treat as a process failure

    # ── OPERATION_CONFUSION: the given answer matches what a DIFFERENT
    # operation on the same two operands would produce (e.g. subtracted
    # instead of added). Only checkable when we can parse two operands.
    operands = _parse_two_operands(expression)
    if operands:
        a, b = operands
        alternates = {
            "add": a + b, "sub": a - b, "mul": a * b,
            "div": (a / b) if b != 0 else None,
        }
        for alt_op, alt_result in alternates.items():
            if alt_result is not None and alt_op != (operation or "") and given == alt_result:
                return OPERATION_CONFUSION

    # ── PLACE_VALUE: same digits, different magnitude (off by a power of 10) —
    # classic place-value slip ("12" written/read as "120" or "1.2").
    if correct != 0 and given != 0:
        ratio = given / correct
        if ratio in (Fraction(10), Fraction(1, 10), Fraction(100), Fraction(1, 100)):
            return PLACE_VALUE

    # ── SEQUENCING: expression has MORE THAN ONE operation and the given
    # answer matches evaluating it in the WRONG order (no operator
    # precedence applied) — a process/ordering failure. Checked before
    # CARRY_BORROW below since CARRY_BORROW's "close in magnitude" heuristic
    # is a much weaker, more easily-coincidental signal than an exact match
    # against a specific wrong evaluation order.
    operator_count = sum(expression.count(s) for s in "+-*/") - (1 if expression.startswith("-") else 0)
    if operator_count >= 2:
        naive = _eval_left_to_right(expression)
        if naive is not None and naive == given and naive != correct:
            return SEQUENCING

    # ── CARRY_BORROW: for a SINGLE addition/subtraction, a wrong answer
    # that's off by a small amount with different digits in some position is
    # the signature of a dropped/duplicated carry or borrow — distinguished
    # from a wild guess (FACT_RECALL) by being close in magnitude.
    if operation in ("add", "sub") and operator_count <= 1 and correct == correct.__floor__() and given == given.__floor__():
        diff = abs(int(correct) - int(given))
        if 0 < diff < max(10, int(correct) * 0.2 + 1):
            correct_digits = _digits_reversed(int(correct))
            given_digits = _digits_reversed(int(given))
            if correct_digits != given_digits:
                return CARRY_BORROW

    # ── Default: no structural pattern matched — treat as a fact-recall gap.
    return FACT_RECALL


def _parse_two_operands(expression: str) -> Optional[tuple]:
    """Best-effort: only handles the simple `a <op> b` shape micro-steps use.
    Anything more complex returns None rather than guessing."""
    for symbol in ("+", "-", "*", "/"):
        if symbol in expression[1:]:  # skip a leading unary sign
            idx = expression.index(symbol, 1)
            left, right = expression[:idx], expression[idx + 1:]
            try:
                return Fraction(str(safe_eval(left))), Fraction(str(safe_eval(right)))
            except (UnsafeExpression, ZeroDivisionError):
                return None
    return None


def _eval_left_to_right(expression: str) -> Optional[Fraction]:
    """Evaluates strictly left-to-right, ignoring normal precedence — the
    exact mistake SEQUENCING is meant to catch (e.g. "2+3*4" computed as
    (2+3)*4 instead of 2+(3*4))."""
    import re

    tokens = re.findall(r"\d+\.?\d*|[+\-*/]", expression)
    if len(tokens) < 3:
        return None
    try:
        result = Fraction(tokens[0])
        for i in range(1, len(tokens), 2):
            operator_token, value = tokens[i], Fraction(tokens[i + 1])
            if operator_token == "+":
                result += value
            elif operator_token == "-":
                result -= value
            elif operator_token == "*":
                result *= value
            elif operator_token == "/":
                if value == 0:
                    return None
                result /= value
        return result
    except (ValueError, IndexError, ZeroDivisionError):
        return None
