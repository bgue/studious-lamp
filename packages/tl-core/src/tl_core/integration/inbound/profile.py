"""The profile ``jsonata-restricted@1`` as a pure check of a syntax tree (FANOUT D5).

This module imports the standard library and ``jsonata`` only, so the child process of the
ADR-0014 envelope can run it: **an expression is parsed and walked in the child, never in the
server**, under the envelope's memory limit and wall clock. The parent passes the allowed function
names in the header (``tl_core.integration.contract.MAPPING_ALLOWED_FUNCTIONS``); a problem is a
``(code, message)`` pair that never repeats the expression.

The caps are low on purpose: an expression a person writes for a payload is short. A 4000-step
path took seconds to parse; the caps and the envelope together bound that cost.
"""

# jsonata-python ships no type information; its objects are untyped here.
# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportArgumentType=false

from __future__ import annotations

from collections.abc import Collection, Iterator
from typing import Any

from jsonata import Jsonata
from jsonata.parser import Parser

#: The longest expression the profile accepts (the contract allows more; the check is stricter).
CHECK_MAX_CHARS = 2_000
MAX_AST_NODES = 500
MAX_AST_DEPTH = 60
#: Node types of the syntax tree a mapping may use. Everything else is refused by name.
ALLOWED_NODE_TYPES = frozenset(
    {
        "unary",  # an object or array constructor, or a minus sign
        "binary",
        "path",
        "name",
        "number",
        "string",
        "value",  # true, false, null
        "variable",
        "function",
        "condition",
        "filter",
        "block",  # parentheses
        "wildcard",
        "apply",  # a ~> $f()
        "sort",
        "group",
    }
)
_DESCRIPTIONS = {
    "lambda": "A function definition",
    "regex": "A regular expression",
    "partial": "Partial application",
    "bind": "Binding a variable",
    "transform": "A transform",
    "descendant": "The ** operator",
    "parent": "The % operator",
    "focus": "The @ operator",
    "index": "The # operator",
}

Problem = tuple[str, str]  # (code, message)


def _describe(kind: str) -> str:
    return _DESCRIPTIONS.get(kind, f"A {kind[:20]} expression")


def _node_children(node: Parser.Symbol) -> Iterator[Parser.Symbol]:
    """Every syntax node directly under ``node`` (the library keeps them in many fields)."""
    for value in vars(node).values():
        yield from _symbols(value, 0)


def _symbols(value: Any, depth: int) -> Iterator[Parser.Symbol]:
    if isinstance(value, Parser.Symbol):
        yield value
    elif isinstance(value, list | tuple) and depth < 4:
        for item in value:
            yield from _symbols(item, depth + 1)


def _called(node: Parser.Symbol) -> str | None:
    """The name of the function a call node calls, when it calls a named one."""
    procedure = getattr(node, "procedure", None)
    if isinstance(procedure, Parser.Symbol) and str(procedure.type) == "variable":
        return str(procedure.value)
    return None


def syntax_problems(tree: Parser.Symbol, allowed: Collection[str]) -> list[Problem]:
    """The reasons a syntax tree is outside the profile (the first few, deduplicated)."""
    problems: dict[str, Problem] = {}
    stack: list[tuple[Parser.Symbol, int]] = [(tree, 0)]
    seen = 0
    while stack:
        node, depth = stack.pop()
        seen += 1
        if seen > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            problems["size"] = ("too_complex", "The expression is too large or too deep.")
            break
        kind = str(node.type)
        if kind not in ALLOWED_NODE_TYPES:
            problems[f"node:{kind}"] = (
                "not_allowed",
                f"{_describe(kind)} is not allowed in a mapping.",
            )
            continue
        if kind == "function":
            name = _called(node)
            if name is None or f"${name}" not in allowed:
                shown = "that function" if name is None else f"${name[:40]}"
                problems[f"fn:{name}"] = (
                    "function_not_allowed",
                    f"{shown} is not allowed in a mapping.",
                )
                continue
        elif kind == "variable":
            name = str(node.value)
            if name not in ("", "$") and f"${name}" not in allowed:
                problems[f"var:{name}"] = (
                    "variable_not_allowed",
                    f"${name[:40]} is not allowed in a mapping.",
                )
                continue
        stack.extend((child, depth + 1) for child in _node_children(node))
    return list(problems.values())[:10]


def check_expression(expression: str, allowed: Collection[str]) -> list[Problem]:
    """Parse ``expression`` and walk its tree against the profile. Empty means it is inside."""
    if len(expression) > CHECK_MAX_CHARS:
        return [("too_long", f"A mapping is at most {CHECK_MAX_CHARS} characters.")]
    if not expression.strip() or "\x00" in expression:
        return [("empty", "A mapping is not empty and holds no NUL.")]
    try:
        tree = Jsonata(expression).ast
    except RecursionError:
        return [("too_complex", "The expression is nested too deeply.")]
    except Exception as exc:  # the library's own error: its code, never the expression
        code = str(getattr(exc, "error", "") or "")[:16]
        suffix = f" ({code})" if code else ""
        return [("syntax", f"The expression does not parse{suffix}.")]
    if tree is None:
        return [("empty", "A mapping is not empty and holds no NUL.")]
    return syntax_problems(tree, allowed)


__all__ = ["ALLOWED_NODE_TYPES", "CHECK_MAX_CHARS", "check_expression", "syntax_problems"]
