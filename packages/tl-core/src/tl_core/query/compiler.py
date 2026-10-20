"""SQL compiler for the filter language (brief 10.2, 7.5, 5.4).

Turns a :class:`~tl_core.query.api.QuerySpec` into one ``SELECT`` over ``cur_core_record`` and a
dict of bound parameters. The security rules, which tests pin:

* Identifiers (columns, tables, aliases, operators) come only from the allow-lists in
  :mod:`tl_core.query.fields` and from counters this module generates. Nothing the caller wrote
  is spliced into the SQL text; every value, relation code, record type and pset path is a bound
  parameter.
* Every predicate is two-valued (never SQL ``NULL``), so ``NOT`` and ``!=`` behave: ``status!=open``
  also matches records with no status, exactly like ``-status:open``.
* Pset paths compile to ``id IN (SELECT record_id FROM cur_pset_values ...)`` when the test must
  hold and, for ``!=`` and for ``= null`` on a pset, to a correlated ``NOT EXISTS``; links to
  ``id IN`` over the link ends (both directions), ``missing(...)`` to a correlated ``NOT EXISTS``,
  and a count that may be zero to a correlated ``COUNT``. An explicit ``-x``, ``NOT`` or
  ``-linked(x)`` negates whatever ``x`` compiled to, so it is ``NOT (id IN (set))``: correct
  because the ids are never NULL, and a hashed SubPlan on Postgres that degrades only when the set
  outgrows ``work_mem``.
* The ``IN`` form is a set built once from ``cur_pset_values`` or ``cur_links`` (indexed by path
  and value, by relation and status), so a filter that matches few rows no longer probes the
  table once per record (P0-I8 D13: 150 ms to a few ms for a selective pset filter on SQLite at
  100k records).
* Only portable SQL: ``LIKE ... ESCAPE``, ``LOWER``, ``COALESCE``, ``EXISTS``, ``LIMIT/OFFSET``.

Text search is ``LIKE`` over key, title and description (case-insensitive; SQLite's ``LOWER``
folds ASCII only). FTS5 replaces it later.

An AST built by hand is validated here the same way parsed text is; a bad one raises
``QuerySyntaxError`` with ``position`` 0.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from tl_core import confidentiality
from tl_core.query.api import QuerySpec, QuerySyntaxError
from tl_core.query.ast import (
    And,
    Compare,
    CountLinked,
    Expr,
    Linked,
    MissingLink,
    Not,
    Or,
    RelativeDate,
    Text,
    Value,
)
from tl_core.query.clock import QueryClock, current_clock
from tl_core.query.fields import (
    ENVELOPE_FIELDS,
    LIVE_LINK_STATUSES,
    MAX_INT,
    NEVER_NULL_FIELDS,
    OPS_BY_KIND,
    PSET_OPS,
    PSET_PATH_RE,
    RELATION_RE,
    SORTABLE_FIELDS,
    SQL_OPS,
    TYPE_FULL_RE,
    Field,
)
from tl_core.query.temporal import (
    DayLiteral,
    InstantLiteral,
    iso_window,
    parse_literal,
    relative_day,
)

MAX_NODES = 300
MAX_DEPTH = 40
_NO_LIMIT = 2**63 - 1  # portable "no limit" so OFFSET can be used on its own

_ENVELOPE_COLUMNS = (
    "id",
    "key",
    "type",
    "scope",
    "title",
    "description",
    "status",
    "psets_json",
    "voided",
    "version",
    "last_seq",
    "effective_schema_hash",
    "conformance",
    "created_at",
    "updated_at",
)
_SELECT_LIST = ", ".join(f"r.{column}" for column in _ENVELOPE_COLUMNS)
_LIVE = "(" + ", ".join(f"'{status}'" for status in LIVE_LINK_STATUSES) + ")"
_ESCAPE = "ESCAPE '\\'"
#: What ``count(...) <op> n`` says about a record with no links at all (a count of 0).
_COUNT_TESTS: dict[str, Callable[[int, int], bool]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}
_SEARCH_COLUMNS = ("key", "title", "description")


@dataclass(frozen=True)
class Compiled:
    """SQL text with ``:name`` placeholders and the values to bind to them."""

    sql: str
    params: dict[str, Any]


def like_pattern(text: str, *, prefix: bool = True, suffix: bool = True) -> str:
    """A ``LIKE`` pattern for ``text`` (lower-cased, with ``\\``, ``%`` and ``_`` escaped)."""
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{'%' if prefix else ''}{escaped}{'%' if suffix else ''}"


def compile_query(
    spec: QuerySpec, *, count: bool = False, clock: QueryClock | None = None
) -> Compiled:
    """Compile ``spec`` to a record ``SELECT`` or, with ``count``, a ``SELECT COUNT(*)``."""
    if not spec.scope:
        raise ValueError("a query needs a scope")
    if spec.limit is not None and not 0 <= spec.limit <= _NO_LIMIT:
        raise ValueError(f"limit must be between 0 and {_NO_LIMIT}, got {spec.limit}")
    if not 0 <= spec.offset <= _NO_LIMIT:
        raise ValueError(f"offset must be between 0 and {_NO_LIMIT}, got {spec.offset}")
    builder = _Builder(clock if clock is not None else current_clock())
    clauses = [f"r.scope = {builder.bind(spec.scope)}"]
    if spec.record_type is not None:
        clauses.append(f"r.type = {builder.bind(spec.record_type)}")
    if not spec.include_voided:
        clauses.append(f"r.voided = {builder.bind(False)}")
    if spec.where is not None:
        clauses.append(builder.expr(spec.where, "r", 0))
    clauses.append(builder.visible("r.id"))  # a record the viewer may not read is not a result
    where = " AND ".join(clauses)
    if count:
        return Compiled(f"SELECT COUNT(*) FROM cur_core_record r WHERE {where}", builder.params)
    joins, order = builder.order(spec.order_by)
    sql = f"SELECT {_SELECT_LIST} FROM cur_core_record r{joins} WHERE {where} ORDER BY {order}"
    if spec.limit is not None or spec.offset:
        limit = _NO_LIMIT if spec.limit is None else spec.limit
        sql += f" LIMIT {builder.bind(limit)} OFFSET {builder.bind(spec.offset)}"
    return Compiled(sql, builder.params)


class _Builder:
    def __init__(self, clock: QueryClock) -> None:
        self.clock = clock
        self.params: dict[str, Any] = {}
        self._aliases = 0
        self._nodes = 0

    # --- bookkeeping --------------------------------------------------------------------------

    def bind(self, value: Any) -> str:
        name = f"q{len(self.params)}"
        self.params[name] = value
        return f":{name}"

    def alias(self, prefix: str) -> str:
        self._aliases += 1
        return f"{prefix}{self._aliases}"

    @staticmethod
    def fail(message: str) -> QuerySyntaxError:
        return QuerySyntaxError(message, 0)

    # --- expressions --------------------------------------------------------------------------

    def expr(self, node: Expr, rec: str, depth: int) -> str:
        """SQL for ``node`` evaluated against the record row aliased ``rec``."""
        self._nodes += 1
        if self._nodes > MAX_NODES:
            raise self.fail(f"query is too complex (more than {MAX_NODES} terms)")
        if depth > MAX_DEPTH:
            raise self.fail(f"query is nested more than {MAX_DEPTH} levels deep")
        if isinstance(node, Compare):
            return self.compare(node, rec)
        if isinstance(node, Text):
            return self.text(node, rec)
        if isinstance(node, And):
            return self.join("AND", node.items, rec, depth)
        if isinstance(node, Or):
            return self.join("OR", node.items, rec, depth)
        if isinstance(node, Not):
            return f"(NOT {self.expr(node.item, rec, depth + 1)})"
        if isinstance(node, Linked):
            return self.linked_exists(node, rec, depth)
        if isinstance(node, MissingLink):
            return self.linked_missing(Linked(node.relation, node.target_type, None), rec, depth)
        return self.count_linked(node, rec, depth)

    def join(self, word: str, items: tuple[Expr, ...], rec: str, depth: int) -> str:
        if not items:
            return "(1 = 1)" if word == "AND" else "(1 = 0)"
        parts = [self.expr(item, rec, depth + 1) for item in items]
        return "(" + f" {word} ".join(parts) + ")"

    def text(self, node: Text, rec: str) -> str:
        if not node.text:
            raise self.fail("search text must be a non-empty string")
        pattern = self.bind(like_pattern(node.text))
        terms = [
            f"LOWER(COALESCE({rec}.{c}, '')) LIKE {pattern} {_ESCAPE}" for c in _SEARCH_COLUMNS
        ]
        return "(" + " OR ".join(terms) + ")"

    # --- comparisons on envelope columns ------------------------------------------------------

    def compare(self, node: Compare, rec: str) -> str:
        if node.op not in SQL_OPS and node.op != "~":
            raise self.fail(f"unknown operator {node.op!r}")
        if node.path.startswith("psets."):
            return self.pset_compare(node, rec)
        found = ENVELOPE_FIELDS.get(node.path)
        if found is None:
            raise self.fail(f"unknown field {node.path!r}")
        if node.op not in OPS_BY_KIND[found.kind]:
            raise self.fail(f"operator {node.op!r} cannot be used with {found.name}")
        col = f"{rec}.{found.name}"
        if node.value is None:
            return self.null_test(found, col, node.op)
        if found.kind == "text":
            return self.text_compare(col, node.op, self.as_text(node.value))
        if found.kind == "int":
            return self.simple(col, node.op, self.as_number(node.value, found))
        if found.kind == "bool":
            if not isinstance(node.value, bool):
                raise self.fail(f"{found.name} takes true or false")
            return self.simple(col, node.op, node.value)
        return self.date_compare(col, node.op, node.value, found)

    def null_test(self, found: Field, col: str, op: str) -> str:
        if op not in ("=", "!="):
            raise self.fail("null can only be compared with '=' or '!='")
        empty = f"({col} IS NULL OR {col} = '')" if found.kind == "text" else f"{col} IS NULL"
        return empty if op == "=" else f"(NOT {empty})"

    def as_text(self, value: Value) -> str:
        if isinstance(value, bool) or isinstance(value, RelativeDate) or value is None:
            raise self.fail(f"cannot compare text with {value!r}")
        return str(value)

    def as_number(self, value: Value, found: Field) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise self.fail(f"{found.name} takes a number")
        if abs(value) > MAX_INT or value != value:
            raise self.fail("number out of range")
        return value

    def simple(self, col: str, op: str, value: Any) -> str:
        """A comparison that is false, not NULL, for a NULL column."""
        bound = self.bind(value)
        if op == "!=":
            return f"({col} IS NULL OR {col} <> {bound})"
        return f"({col} IS NOT NULL AND {col} {SQL_OPS[op]} {bound})"

    def text_compare(self, col: str, op: str, value: str) -> str:
        if op == "~":
            return f"(LOWER(COALESCE({col}, '')) LIKE {self.bind(like_pattern(value))} {_ESCAPE})"
        return self.simple(col, op, value)

    def date_compare(self, col: str, op: str, value: Value, found: Field) -> str:
        window = self.window(value, found.name)
        start, end = (self.bind(edge) for edge in window)
        if op == "=":
            return f"({col} IS NOT NULL AND {col} >= {start} AND {col} < {end})"
        if op == "!=":
            return f"({col} IS NULL OR {col} < {start} OR {col} >= {end})"
        if op == "<":
            return f"({col} IS NOT NULL AND {col} < {start})"
        if op == "<=":
            return f"({col} IS NOT NULL AND {col} < {end})"
        if op == ">":
            return f"({col} IS NOT NULL AND {col} >= {end})"
        return f"({col} IS NOT NULL AND {col} >= {start})"

    def window(self, value: Value, name: str) -> tuple[str, str]:
        """The ISO ``[start, end)`` window of a date value, in the stored column format."""
        try:
            if isinstance(value, RelativeDate):
                return iso_window(value, self.clock)
            if isinstance(value, str):
                literal = parse_literal(value)
                if isinstance(literal, (DayLiteral, InstantLiteral)):
                    return iso_window(literal, self.clock)
        except (ValueError, OverflowError) as exc:
            raise self.fail(f"{name}: not a usable date: {exc}") from exc
        raise self.fail(f"{name} takes a date such as 2026-10-09, +7d or today")

    # --- comparisons on pset values -----------------------------------------------------------

    def pset_compare(self, node: Compare, rec: str) -> str:
        if PSET_PATH_RE.match(node.path) is None:
            raise self.fail(f"not a pset path: {node.path!r}")
        if node.op not in PSET_OPS:
            raise self.fail(f"unknown operator {node.op!r}")
        pv = self.alias("pv")
        path = self.bind(node.path)
        value, op = node.value, node.op
        negate = op == "!="
        if value is None:
            if op not in ("=", "!="):
                raise self.fail("null can only be compared with '=' or '!='")
            # "has no value" is the negation of "has a row"; "!= null" is "has a row"
            return self.pset_rows(pv, path, None, rec, negated=op == "=")
        eq_op = "=" if negate else op
        cond = self.pset_condition(pv, eq_op, value)
        return self.pset_rows(pv, path, cond, rec, negated=negate)

    @staticmethod
    def pset_rows(pv: str, path: str, cond: str | None, rec: str, *, negated: bool) -> str:
        """Whether ``rec`` has a ``cur_pset_values`` row at ``path`` that satisfies ``cond``."""
        extra = f" AND {cond}" if cond is not None else ""
        if not negated:
            # An uncorrelated set: the planner builds it from the (path, value) index and then
            # either probes it per record or drives the record lookup from it, whichever is cheaper.
            return (
                f"{rec}.id IN (SELECT {pv}.record_id FROM cur_pset_values {pv} "
                f"WHERE {pv}.path = {path}{extra})"
            )
        return (
            f"(NOT EXISTS (SELECT 1 FROM cur_pset_values {pv} "
            f"WHERE {pv}.record_id = {rec}.id AND {pv}.path = {path}{extra}))"
        )

    def pset_condition(self, pv: str, op: str, value: Value) -> str:
        """The row-level test for one typed pset value (``op`` is never ``!=`` here)."""
        if op == "~":
            if isinstance(value, RelativeDate):
                raise self.fail("'~' cannot be used with a relative date")
            if isinstance(value, bool):
                text = "true" if value else "false"
            else:
                text = str(value)
            return f"LOWER({pv}.value_text) LIKE {self.bind(like_pattern(text))} {_ESCAPE}"
        sql_op = SQL_OPS[op]
        if isinstance(value, bool):
            if op != "=":
                raise self.fail("a true/false value can only be compared with '=' or '!='")
            return f"{pv}.value_bool = {self.bind(value)}"
        if isinstance(value, (int, float)):
            if abs(value) > MAX_INT or value != value:
                raise self.fail("number out of range")
            return f"{pv}.value_num {sql_op} {self.bind(float(value))}"
        if isinstance(value, RelativeDate):
            return self.pset_day(pv, op, value)
        return f"{pv}.value_text {sql_op} {self.bind(value)}"

    def pset_day(self, pv: str, op: str, value: RelativeDate) -> str:
        """A relative date against a pset value stored as ISO text (a date or a date-time)."""
        try:
            day = relative_day(value, self.clock)
            following: date = date.fromordinal(day.toordinal() + 1)
        except (ValueError, OverflowError) as exc:
            raise self.fail(f"not a usable date: {exc}") from exc
        col = f"{pv}.value_text"
        start, end = self.bind(day.isoformat()), self.bind(following.isoformat())
        return {
            "=": f"{col} >= {start} AND {col} < {end}",
            "<": f"{col} < {start}",
            "<=": f"{col} < {end}",
            ">": f"{col} >= {end}",
            ">=": f"{col} >= {start}",
        }[op]

    # --- links --------------------------------------------------------------------------------

    def visible(self, id_expr: str) -> str:
        """``id_expr`` is a record the viewer may read (ADR-0016); binds what the clause needs."""
        clause, params = confidentiality.not_hidden(id_expr)
        self.params.update(params)
        return clause

    def link_filter(self, node: Linked, link: str, other: str, depth: int) -> str:
        """The shared ``WHERE`` tail: live status, relation, type of the other end, condition.

        The other end must be readable too: a link to a hidden record does not exist for a viewer
        who may not read it (ADR-0016), so it can neither match nor be counted.
        """
        parts = [f"{link}.status IN {_LIVE}", self.visible(f"{other}.id")]
        if node.relation is not None:
            if RELATION_RE.match(node.relation) is None:
                raise self.fail(f"not a relation code: {node.relation!r}")
            parts.append(f"{link}.relation = {self.bind(node.relation)}")
        if node.target_type is not None:
            target = node.target_type
            if TYPE_FULL_RE.match(target) is None:
                raise self.fail(f"not a record type: {target!r}")
            exact = self.bind(target.lower())
            suffix = self.bind(like_pattern("." + target, prefix=True, suffix=False))
            parts.append(
                f"(LOWER({other}.type) = {exact} OR LOWER({other}.type) LIKE {suffix} {_ESCAPE})"
            )
        if node.where is not None:
            parts.append(self.expr(node.where, other, depth + 1))
        return " AND ".join(parts)

    def link_end(self, node: Linked, outbound: bool, depth: int) -> tuple[str, str]:
        """``(link alias, FROM and WHERE tail)`` of the live links that satisfy ``node``.

        ``outbound`` links leave the record, so the record is the ``from`` end. A link counts only
        when the record at its other end exists, as it always did, so that record is joined (by
        primary key) even when neither the type nor a nested condition looks at it.
        """
        link, other = self.alias("l"), self.alias("o")
        theirs = "to_id" if outbound else "from_id"
        tail = self.link_filter(node, link, other, depth)
        source = f"cur_links {link} JOIN cur_core_record {other} ON {other}.id = {link}.{theirs}"
        return link, f"FROM {source} WHERE {tail}"

    def linked_exists(self, node: Linked, rec: str, depth: int) -> str:
        """``rec`` has a live link that satisfies ``node``: a set of ids per direction."""
        out_link, out_tail = self.link_end(node, True, depth)
        in_link, in_tail = self.link_end(node, False, depth)
        return (
            f"({rec}.id IN (SELECT {out_link}.from_id {out_tail}) "
            f"OR {rec}.id IN (SELECT {in_link}.to_id {in_tail}))"
        )

    def linked_missing(self, node: Linked, rec: str, depth: int) -> str:
        """``rec`` has no such link; correlated, since ``NOT IN (big set)`` plans badly."""
        out_link, out_tail = self.link_end(node, True, depth)
        in_link, in_tail = self.link_end(node, False, depth)
        return (
            f"(NOT EXISTS (SELECT 1 {out_tail} AND {out_link}.from_id = {rec}.id) "
            f"AND NOT EXISTS (SELECT 1 {in_tail} AND {in_link}.to_id = {rec}.id))"
        )

    def count_linked(self, node: CountLinked, rec: str, depth: int) -> str:
        if node.op not in SQL_OPS:
            raise self.fail(f"count(...) cannot use the operator {node.op!r}")
        value = node.value
        if isinstance(value, bool) or abs(value) > MAX_INT:
            raise self.fail("count(...) is compared with a whole number")
        zero_matches = _COUNT_TESTS[node.op](0, value)
        out_link, out_tail = self.link_end(node.linked, True, depth)
        in_link, in_tail = self.link_end(node.linked, False, depth)
        if not zero_matches:
            # A record with no link cannot match, so group the link ends once instead of
            # counting per record: the ids whose number of links passes the test.
            grouped = self.alias("g")
            ends = (
                f"SELECT {out_link}.from_id AS rid {out_tail} "
                f"UNION ALL SELECT {in_link}.to_id AS rid {in_tail}"
            )
            return (
                f"{rec}.id IN (SELECT {grouped}.rid FROM ({ends}) {grouped} "
                f"GROUP BY {grouped}.rid HAVING COUNT(*) {SQL_OPS[node.op]} {self.bind(value)})"
            )
        out = f"SELECT COUNT(*) {out_tail} AND {out_link}.from_id = {rec}.id"
        inbound = f"SELECT COUNT(*) {in_tail} AND {in_link}.to_id = {rec}.id"
        return f"(((({out})) + (({inbound}))) {SQL_OPS[node.op]} {self.bind(value)})"

    # --- ordering -----------------------------------------------------------------------------

    def order(self, order_by: list[tuple[str, Literal["asc", "desc"]]]) -> tuple[str, str]:
        """``(joins, ORDER BY list)``: empty values sort last either way and ``id`` breaks ties."""
        joins: list[str] = []
        terms: list[str] = []
        for column, direction in order_by:
            if direction not in ("asc", "desc"):
                raise ValueError(f"direction must be 'asc' or 'desc', got {direction!r}")
            way = direction.upper()
            if column in SORTABLE_FIELDS:
                field = ENVELOPE_FIELDS[column]
                col = f"r.{column}"
                if column in NEVER_NULL_FIELDS:
                    terms.append(f"{col} {way}")
                    continue
                empty = f"{col} IS NULL OR {col} = ''" if field.kind == "text" else f"{col} IS NULL"
                terms.append(f"({empty}), {col} {way}")
            elif PSET_PATH_RE.match(column):
                sv = self.alias("sv")
                joins.append(
                    f" LEFT JOIN cur_pset_values {sv} ON {sv}.record_id = r.id "
                    f"AND {sv}.path = {self.bind(column)}"
                )
                for typed in ("value_num", "value_text", "value_bool"):
                    terms.append(f"({sv}.{typed} IS NULL), {sv}.{typed} {way}")
            else:
                allowed = sorted(SORTABLE_FIELDS)
                raise ValueError(
                    f"cannot order by {column!r}; allowed: {allowed} or psets.<pset>.<property>"
                )
        order = ", ".join([*terms, "r.id"]) if terms else "r.created_at, r.id"
        return "".join(joins), order
