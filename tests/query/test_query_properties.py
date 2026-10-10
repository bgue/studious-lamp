"""Property tests: the parser never crashes, text round-trips, and compiled SQL always runs."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from query_seed import SCOPE, build_db
from tl_adapters._unit import BaseUnitOfWork
from tl_adapters.db import DbTarget, open_uow
from tl_core.query import (
    And,
    Compare,
    CountLinked,
    Expr,
    Linked,
    MissingLink,
    Not,
    Or,
    QuerySpec,
    QuerySyntaxError,
    RelativeDate,
    Text,
    count_query,
    parse,
    run_query,
)
from tl_core.query.ast import CompareOp
from tl_core.query.fields import ENVELOPE_FIELDS
from tl_core.query.format import to_text

# --- strategies ---------------------------------------------------------------------------------

SAFE_CHARS = st.characters(
    blacklist_categories=("Cs", "Cc"), blacklist_characters=["\x00"]
) | st.sampled_from(" \t\n")
SYNTAX_CHARS = st.sampled_from(
    list("()\"'\\:=!<>~-+.*_ \t\nabcxyzORANDNOTlinkedcountmissingpsets0123456789")
)
FRAGMENTS = [
    "status",
    "title",
    "key",
    "type",
    "version",
    "created_at",
    "updated_at",
    "voided",
    "psets.nde.method",
    "psets.a.b.c",
    "psets",
    "linked",
    "linked(",
    "count(",
    "missing(",
    "link",
    "path(",
    "OR",
    "AND",
    "NOT",
    "or",
    "not",
    "-",
    "(",
    ")",
    ":",
    "=",
    "!=",
    "~",
    "<",
    "<=",
    ">",
    ">=",
    ".",
    "*",
    '"',
    "'",
    "\\",
    "open",
    "NCR",
    "quality.NCR",
    "raised_against",
    "null",
    "true",
    "false",
    "0",
    "7",
    "-1",
    "1.5",
    "007",
    "+7d",
    "-3d",
    "today",
    "2026-10-09",
    "2026-13-45",
    "2026-10-09T12:00:00Z",
    "bevel",
    "%",
    "_",
    "'; DROP TABLE events;--",
    " ",
    "  ",
    "\t",
    "\n",
]
SOUP = st.lists(st.sampled_from(FRAGMENTS), max_size=14).map("".join)
ANY_TEXT = st.one_of(st.text(max_size=80), st.text(SYNTAX_CHARS, max_size=80), SOUP)

IDENT = st.from_regex(r"[A-Za-z_][A-Za-z0-9_-]{0,8}", fullmatch=True)
TYPE_NAME = st.lists(IDENT, min_size=1, max_size=3).map(".".join)
NON_BLANK = st.text(SAFE_CHARS, max_size=20).filter(lambda s: bool(s.strip()))
ANY_VALUE_TEXT = st.text(SAFE_CHARS, max_size=20)
INT64 = st.integers(min_value=-(2**63) + 1, max_value=2**63 - 1)
DAYS = st.integers(min_value=-36500, max_value=36500).map(RelativeDate)
DATES = st.dates().map(lambda d: d.isoformat())
FINITE = st.floats(allow_nan=False, allow_infinity=False)

TEXT_OPS = st.sampled_from(["=", "!=", "~", "<", "<=", ">", ">="])
ORD_OPS = st.sampled_from(["=", "!=", "<", "<=", ">", ">="])
EQ_OPS = st.sampled_from(["=", "!="])


def _envelope_compare(name: str) -> st.SearchStrategy[Compare]:
    kind = ENVELOPE_FIELDS[name].kind
    nullable = st.builds(Compare, st.just(name), EQ_OPS, st.none())
    if kind == "text":
        return st.one_of(nullable, st.builds(Compare, st.just(name), TEXT_OPS, ANY_VALUE_TEXT))
    if kind == "int":
        return st.one_of(nullable, st.builds(Compare, st.just(name), ORD_OPS, INT64))
    if kind == "bool":
        return st.one_of(nullable, st.builds(Compare, st.just(name), EQ_OPS, st.booleans()))
    return st.one_of(
        nullable,
        st.builds(Compare, st.just(name), ORD_OPS, DAYS),
        st.builds(Compare, st.just(name), ORD_OPS, DATES),
    )


PSET_PATH = st.lists(IDENT, min_size=2, max_size=4).map(lambda segs: "psets." + ".".join(segs))
PSET_COMPARE = st.one_of(
    st.builds(Compare, PSET_PATH, EQ_OPS, st.none()),
    st.builds(Compare, PSET_PATH, st.just("~"), ANY_VALUE_TEXT),
    st.builds(Compare, PSET_PATH, ORD_OPS, ANY_VALUE_TEXT),
    st.builds(Compare, PSET_PATH, ORD_OPS, INT64),
    st.builds(Compare, PSET_PATH, ORD_OPS, FINITE),
    st.builds(Compare, PSET_PATH, EQ_OPS, st.booleans()),
    st.builds(Compare, PSET_PATH, ORD_OPS, DAYS),
)
COMPARES = st.one_of(*(_envelope_compare(n) for n in ENVELOPE_FIELDS), PSET_COMPARE)
LEAVES = st.one_of(COMPARES, st.builds(Text, NON_BLANK))
LINK_OPS = st.sampled_from(["=", "!=", "<", "<=", ">", ">="])


def exprs(where: st.SearchStrategy[Expr] | None = None) -> st.SearchStrategy[Expr]:
    def extend(children: st.SearchStrategy[Expr]) -> st.SearchStrategy[Expr]:
        linked = st.builds(Linked, st.none() | IDENT, st.none() | TYPE_NAME, st.none() | children)
        return st.one_of(
            st.builds(Not, children),
            st.builds(lambda xs: And(tuple(xs)), st.lists(children, min_size=2, max_size=4)),
            st.builds(lambda xs: Or(tuple(xs)), st.lists(children, min_size=2, max_size=4)),
            linked,
            st.builds(CountLinked, linked, LINK_OPS, st.integers(-5, 50)),
            st.builds(MissingLink, st.none() | IDENT, st.none() | TYPE_NAME),
        )

    return st.recursive(where or LEAVES, extend, max_leaves=8)


def normalize(node: Expr) -> Expr:
    """The form the parser returns: nested And in And and Or in Or are flattened."""
    if isinstance(node, Not):
        return Not(normalize(node.item))
    if isinstance(node, (And, Or)):
        items: list[Expr] = []
        for item in node.items:
            inner = normalize(item)
            if type(inner) is type(node):
                items.extend(inner.items)  # type: ignore[union-attr]
            else:
                items.append(inner)
        return type(node)(tuple(items))
    if isinstance(node, Linked):
        return Linked(
            node.relation, node.target_type, None if node.where is None else normalize(node.where)
        )
    if isinstance(node, CountLinked):
        linked = normalize(node.linked)
        assert isinstance(linked, Linked)
        return CountLinked(linked, node.op, node.value)
    return node


# --- the parser ---------------------------------------------------------------------------------


@settings(max_examples=1500, deadline=None)
@given(ANY_TEXT)
def test_parse_returns_an_ast_or_raises_query_syntax_error(text: str) -> None:
    try:
        result = parse(text)
    except QuerySyntaxError as error:
        assert 0 <= error.position <= max(len(text), 2000)
        assert str(error)
        return
    assert result is None or to_text(result) is not None
    assert (result is None) == (not text.strip())


@settings(max_examples=300, deadline=None)
@given(st.text(st.characters(), max_size=300))
def test_parse_survives_arbitrary_unicode(text: str) -> None:
    try:
        parse(text)
    except QuerySyntaxError:
        pass


@settings(max_examples=800, deadline=None)
@given(exprs())
def test_to_text_round_trips(expr: Expr) -> None:
    text = to_text(expr)
    assert parse(text) == normalize(expr), text


@settings(max_examples=300, deadline=None)
@given(ANY_TEXT)
def test_whatever_parses_prints_and_parses_again(text: str) -> None:
    try:
        first = parse(text)
    except QuerySyntaxError:
        return
    if first is not None:
        assert parse(to_text(first)) == first


# --- the compiler runs on a real database ------------------------------------------------------


@pytest.fixture
def shared_uow(new_db: Callable[[], DbTarget]) -> Iterator[BaseUnitOfWork]:
    path = new_db()
    build_db(path)
    with open_uow(path, readonly=True) as opened:
        yield opened


@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(exprs())
def test_compiled_sql_always_runs_and_counts_agree(shared_uow: BaseUnitOfWork, expr: Expr) -> None:
    spec = QuerySpec(scope=SCOPE, where=expr, limit=None)
    try:
        rows = run_query(shared_uow, spec)
        count = count_query(shared_uow, spec)
    except QuerySyntaxError:
        return  # e.g. a date or number the compiler refuses
    assert count == len(rows)
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))


@settings(
    max_examples=500,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(SOUP | ANY_TEXT)
def test_any_parsed_text_compiles_and_runs(shared_uow: BaseUnitOfWork, text: str) -> None:
    try:
        where = parse(text)
        rows = run_query(shared_uow, QuerySpec(scope=SCOPE, where=where, limit=None))
        count = count_query(shared_uow, QuerySpec(scope=SCOPE, where=where))
    except QuerySyntaxError:
        return
    assert count == len(rows)


@settings(
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(exprs())
def test_not_partitions_the_result(shared_uow: BaseUnitOfWork, expr: Expr) -> None:
    """Two-valued logic: a record matches ``x`` or ``-x``, never both and never neither."""
    try:
        yes = {
            r["id"] for r in run_query(shared_uow, QuerySpec(scope=SCOPE, where=expr, limit=None))
        }
        no = {
            r["id"]
            for r in run_query(shared_uow, QuerySpec(scope=SCOPE, where=Not(expr), limit=None))
        }
        everything = {r["id"] for r in run_query(shared_uow, QuerySpec(scope=SCOPE, limit=None))}
    except QuerySyntaxError:
        return
    assert yes | no == everything
    assert not yes & no


_OPS: list[CompareOp] = ["=", "!=", "<", "<=", ">", ">="]
