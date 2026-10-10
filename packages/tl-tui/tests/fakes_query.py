"""Query-language behaviour of `FakeClient` (P0-I4), kept apart like `fakes_links.py`.

The fake parses with the real `tl_core.query.parse`, so a syntax error carries the real message and
position, and evaluates the envelope comparisons, text search and and/or/not over its in-memory
records. Link terms (`linked`, `count`, `missing`) are not simulated and raise
`NotImplementedError`, so a test that needs them uses a real ledger.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any, Literal

from tl_core.query import parse
from tl_core.query.ast import And, Compare, Expr, Not, Or, Text
from tl_tui.paths import pset_value


def _value(record: dict[str, Any], path: str) -> Any:
    if path.startswith("psets."):
        return pset_value(record.get("psets") or {}, path)
    return record.get(path)


def matches(expr: Expr | None, record: dict[str, Any]) -> bool:
    """Whether ``record`` satisfies ``expr`` (two-valued: a missing value never equals)."""
    if expr is None:
        return True
    if isinstance(expr, And):
        return all(matches(item, record) for item in expr.items)
    if isinstance(expr, Or):
        return any(matches(item, record) for item in expr.items)
    if isinstance(expr, Not):
        return not matches(expr.item, record)
    if isinstance(expr, Text):
        needle = expr.text.lower()
        return any(
            needle in str(record.get(f) or "").lower() for f in ("key", "title", "description")
        )
    if isinstance(expr, Compare):
        have = _value(record, expr.path)
        want = expr.value
        if expr.op == "~":
            return have is not None and str(want).lower() in str(have).lower()
        if expr.op == "=":
            return have is not None and have == want
        if expr.op == "!=":
            return not (have is not None and have == want)
        if have is None or want is None:
            return False
        ordered: dict[str, Callable[[Any, Any], bool]] = {
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }
        return ordered[expr.op](have, want)
    raise NotImplementedError(f"the fake does not evaluate {type(expr).__name__} terms")


class FakeQuerySupport:
    """Mixin: ``query_records`` and ``count_records`` over ``self._records``."""

    _records: dict[str, dict[str, Any]]
    calls: list[str]

    def _matching(self, scope: str, q: str) -> list[dict[str, Any]]:
        expr = parse(q)  # raises QuerySyntaxError(message, position)
        return [
            r
            for r in self._records.values()
            if r["scope"] == scope and not r["voided"] and matches(expr, r)
        ]

    def query_records(
        self,
        scope: str,
        q: str,
        *,
        limit: int = 500,
        offset: int = 0,
        order_by: list[tuple[str, Literal["asc", "desc"]]] | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append("query_records")
        rows = self._matching(scope, q)
        for column, direction in reversed(order_by or []):
            rows.sort(key=lambda r, c=column: (r[c] is None, r[c] if r[c] is not None else 0))
            if direction == "desc":
                rows.reverse()
        return [deepcopy(r) for r in rows[offset : offset + limit]]

    def count_records(self, scope: str, q: str) -> int:
        self.calls.append("count_records")
        return len(self._matching(scope, q))
