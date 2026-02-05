# -*- coding: utf-8 -*-
"""Safe evaluation of variable expressions.

Used by menu trigger conditions and other lightweight branching rules.

Expression rules (intentionally small & safe):
- Variables are referenced by bare identifiers, resolved from a provided dict.
- Supports: numbers/strings/bools, parentheses, comparisons, and/or/not,
  and basic arithmetic (+ - * / %).
- Disallows: attribute access, function calls, subscripts, comprehensions, etc.

On any parse/eval error, returns False.
"""

from __future__ import annotations

import ast
from typing import Any


class _UnsafeExpressionError(ValueError):
    pass


def _coerce_value(val: Any) -> Any:
    # Preserve booleans
    if isinstance(val, bool):
        return val
    # Pass through numbers/strings/None
    if isinstance(val, (int, float, str)) or val is None:
        return val
    # Fallback: stringification is safer than raising for unknown types
    return str(val)


def eval_var_expr(expr: str | None, variables: dict[str, Any] | None = None) -> bool:
    """Evaluate a boolean expression against variables.

    Returns False if expr is empty/None or if evaluation fails.
    """

    if expr is None:
        return False
    expr = str(expr).strip()
    if not expr:
        return False

    variables = variables or {}

    try:
        tree = ast.parse(expr, mode="eval")
    except Exception:
        return False

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)

        # constants
        if isinstance(node, ast.Constant):
            return node.value

        # variables
        if isinstance(node, ast.Name):
            return _coerce_value(variables.get(node.id, 0))

        # boolean ops
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    if not bool(_eval(v)):
                        return False
                return True
            if isinstance(node.op, ast.Or):
                for v in node.values:
                    if bool(_eval(v)):
                        return True
                return False
            raise _UnsafeExpressionError("unsupported boolean operator")

        # unary ops
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not bool(_eval(node.operand))
            if isinstance(node.op, ast.UAdd):
                return +float(_eval(node.operand))
            if isinstance(node.op, ast.USub):
                return -float(_eval(node.operand))
            raise _UnsafeExpressionError("unsupported unary operator")

        # arithmetic
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Mod):
                return left % right
            raise _UnsafeExpressionError("unsupported binary operator")

        # comparisons (including chained)
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comp in zip(node.ops, node.comparators, strict=False):
                right = _eval(comp)
                ok = False
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                else:
                    raise _UnsafeExpressionError("unsupported comparison operator")
                if not ok:
                    return False
                left = right
            return True

        # explicitly disallow everything else
        raise _UnsafeExpressionError(f"unsupported expression element: {type(node).__name__}")

    try:
        return bool(_eval(tree))
    except Exception:
        return False
