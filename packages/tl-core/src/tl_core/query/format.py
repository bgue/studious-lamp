"""Render an AST back to query text (the inverse of :func:`tl_core.query.api.parse`).

The filter bar's structured builder and saved views store an AST and show or save its text.
``parse(to_text(expr))`` gives back an equivalent AST (nested ``And``/``Or`` come back flattened).
Text is quoted only where needed, so output stays readable.
"""

from __future__ import annotations

from decimal import Decimal

from tl_core.query.ast import (
    And,
    Compare,
    CompareOp,
    Expr,
    Linked,
    MissingLink,
    Not,
    Or,
    RelativeDate,
    Text,
    Value,
)
from tl_core.query.fields import ENVELOPE_FIELDS, OP_CHARS, QUOTES
from tl_core.query.temporal import parse_literal, parse_relative

_KEYWORDS = frozenset({"or", "and", "not", "linked"})
_SYMBOL: dict[CompareOp, str] = {
    "=": ":",
    "!=": "!=",
    "~": "~",
    "<": "<",
    "<=": "<=",
    ">": ">",
    ">=": ">=",
}


def to_text(expr: Expr | None) -> str:
    """Query text for ``expr``; ``None`` gives the empty string."""
    return "" if expr is None else _render(expr, 0)


def quote(text: str) -> str:
    """``text`` as a double-quoted string the parser reads back unchanged."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bare_ok(text: str) -> bool:
    return (
        bool(text)
        and not any(ch.isspace() or ch in "()" + QUOTES for ch in text)
        and text[0] not in OP_CHARS
    )


def _word(text: str) -> str:
    lower = text.lower()
    ok = _bare_ok(text) and not any(ch in OP_CHARS for ch in text) and text[0] != "-"
    if lower in _KEYWORDS or lower.startswith("linked."):
        ok = False
    return text if ok else quote(text)


def _number(value: float) -> str:
    text = repr(value)
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    return text if "." in text else text + ".0"


def _value(path: str, value: Value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, RelativeDate):
        return "today" if value.days == 0 else f"{value.days:+d}d"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _number(value)
    field = ENVELOPE_FIELDS.get(path)
    if field is None:  # a pset value: the parser infers types from bare text, so keep strings safe
        inferred = (
            value.lower() in ("null", "true", "false")
            or _relative_like(value)
            or _looks_numeric(value)
        )
        return quote(value) if inferred or not _bare_ok(value) else value
    if field.kind == "text":
        return quote(value) if value.lower() == "null" or not _bare_ok(value) else value
    return value if _bare_ok(value) and _is_date(value) else quote(value)


def _relative_like(value: str) -> bool:
    try:
        return parse_relative(value) is not None
    except ValueError:
        return True


def _looks_numeric(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _is_date(value: str) -> bool:
    try:
        return parse_literal(value) is not None
    except ValueError:
        return False


def _linked(node: Linked) -> str:
    out = "linked"
    if node.relation is not None:
        out += f"({node.relation})"
    if node.target_type is not None:
        out += f":{node.target_type}"
    if node.where is not None:
        out += f".({_render(node.where, 0)})"
    return out


def _render(node: Expr, parent: int) -> str:
    if isinstance(node, Or):
        text = " OR ".join(_render(item, 0) for item in node.items)
        return f"({text})" if parent > 0 else text
    if isinstance(node, And):
        text = " ".join(_render(item, 1) for item in node.items)
        return f"({text})" if parent > 1 else text
    if isinstance(node, Not):
        return "-" + _render(node.item, 2)
    if isinstance(node, Compare):
        return f"{node.path}{_SYMBOL[node.op]}{_value(node.path, node.value)}"
    if isinstance(node, Text):
        return _word(node.text)
    if isinstance(node, Linked):
        return _linked(node)
    if isinstance(node, MissingLink):
        inner = _linked(Linked(node.relation, node.target_type, None))
        return "missing(link" + inner.removeprefix("linked") + ")"
    return f"count({_linked(node.linked)}){_SYMBOL[node.op].replace(':', '=')}{node.value}"
