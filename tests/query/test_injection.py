"""Hostile input is data: values never reach the SQL text, and identifiers are allow-listed."""

from __future__ import annotations

from pathlib import Path

import pytest
from query_seed import SCOPE, create_record
from sqlalchemy import text
from tl_adapters.sqlite.uow import SqliteUnitOfWork, open_uow
from tl_core.query import (
    CountLinked,
    Linked,
    MissingLink,
    QuerySpec,
    QuerySyntaxError,
    Text,
    count_query,
    parse,
    run_query,
)
from tl_core.query.ast import Compare, Expr
from tl_core.query.compiler import compile_query
from tl_core.query.format import quote, to_text

HOSTILE = [
    "'; DROP TABLE events;--",
    '"; DROP TABLE events;--',
    "x' OR '1'='1",
    "x') OR 1=1 --",
    "'); DELETE FROM cur_core_record; --",
    "\\'; DROP TABLE events;--",
    "' UNION SELECT id, id, id, id, id, id, id, id, id, id, id, id, id, id, id FROM events --",
    "%' OR title LIKE '%",
    "100%_off\\",
    "Robert'); DROP TABLE cur_links;--",
    ":missing_param",
    "{{7*7}}",
    "‮́ ünï",
]


def table_counts(uow: SqliteUnitOfWork) -> dict[str, int]:
    return {
        name: int(uow.conn().execute(text(f"SELECT COUNT(*) FROM {name}")).scalar_one())
        for name in ("events", "cur_core_record", "cur_pset_values", "cur_links")
    }


@pytest.fixture
def hostile_db(db: Path) -> Path:
    """The seeded ledger plus one record per hostile string, used as title and as a pset value."""
    with open_uow(db) as uow:
        for n, payload in enumerate(HOSTILE):
            create_record(
                uow,
                f"H-{n:02d}",
                record_type="test.Hostile",
                title=payload,
                psets={"evil": {"value": payload}},
            )
    return db


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_values_are_found_as_data_everywhere_a_value_can_go(
    hostile_db: Path, payload: str
) -> None:
    n = HOSTILE.index(payload)
    key = f"H-{n:02d}"
    quoted = quote(payload)
    with open_uow(hostile_db, readonly=True) as uow:
        before = table_counts(uow)
        queries = [
            f"title:{quoted}",
            f"title~{quoted}",
            quoted,
            f"psets.evil.value:{quoted}",
            f"psets.evil.value~{quoted}",
            f"key:H-{n:02d} {quoted}",
        ]
        for query in queries:
            hits = {r["key"] for r in run_query(uow, QuerySpec(scope=SCOPE, where=parse(query)))}
            assert key in hits, query
            assert hits <= {key} | {f"H-{m:02d}" for m in range(len(HOSTILE))}, query
        # a hostile value that matches nothing returns nothing, and changes nothing
        miss = f"title:{quote(payload + 'zz')}"
        assert run_query(uow, QuerySpec(scope=SCOPE, where=parse(miss))) == []
        assert table_counts(uow) == before


@pytest.mark.parametrize("payload", HOSTILE)
def test_no_caller_text_appears_in_the_sql(uow: SqliteUnitOfWork, payload: str) -> None:
    quoted = quote(payload)
    for query in (
        f"title:{quoted}",
        f"title~{quoted}",
        quoted,
        f"psets.a.b:{quoted}",
        f"psets.a.b~{quoted}",
        f"linked:Weld.title:{quoted}",
        f"key>{quoted}",
    ):
        compiled = compile_query(QuerySpec(scope=SCOPE, where=parse(query)))
        assert payload not in compiled.sql, query
        for fragment in ("DROP", "UNION", "DELETE", "1=1", "--"):
            assert fragment not in compiled.sql, (query, fragment)
        count = compile_query(QuerySpec(scope=payload, where=parse(query)), count=True)
        assert payload not in count.sql
        assert payload in count.params.values()
        run_query(uow, QuerySpec(scope=payload, where=parse(query)))  # executes, finds nothing


@pytest.mark.parametrize("payload", HOSTILE)
def test_hostile_scope_and_record_type_are_bound_parameters(
    uow: SqliteUnitOfWork, payload: str
) -> None:
    assert run_query(uow, QuerySpec(scope=payload)) == []
    assert run_query(uow, QuerySpec(scope=SCOPE, record_type=payload)) == []
    assert count_query(uow, QuerySpec(scope=SCOPE, record_type=payload)) == 0


@pytest.mark.parametrize("payload", HOSTILE)
def test_identifiers_in_a_hand_built_ast_are_checked_not_spliced(
    uow: SqliteUnitOfWork, payload: str
) -> None:
    hostile_asts: list[Expr] = [
        Compare(payload, "=", "x"),
        Compare("title", payload, "x"),  # type: ignore[arg-type]
        Compare(f"psets.a.{payload}", "=", "x"),
        Compare(f"psets.{payload}", "=", "x"),
        Linked(payload, None, None),
        Linked(None, payload, None),
        Linked("requires", payload, None),
        MissingLink(payload, None),
        MissingLink(None, payload),
        CountLinked(Linked(payload, None, None), ">", 0),
        CountLinked(Linked(None, None, None), payload, 0),  # type: ignore[arg-type]
        Linked(None, None, Compare(payload, "=", "x")),
    ]
    before = table_counts(uow)
    for ast in hostile_asts:
        with pytest.raises(QuerySyntaxError):
            run_query(uow, QuerySpec(scope=SCOPE, where=ast))
        with pytest.raises(QuerySyntaxError):
            count_query(uow, QuerySpec(scope=SCOPE, where=ast))
    with pytest.raises(ValueError):
        run_query(uow, QuerySpec(scope=SCOPE, order_by=[(payload, "asc")]))
    assert table_counts(uow) == before


def test_hostile_text_in_a_hand_built_ast_is_a_parameter(uow: SqliteUnitOfWork) -> None:
    for payload in HOSTILE:
        compiled = compile_query(QuerySpec(scope=SCOPE, where=Text(payload)))
        assert payload not in compiled.sql
        assert run_query(uow, QuerySpec(scope=SCOPE, where=Text(payload))) == []


def test_unquoted_hostile_text_is_a_syntax_error_not_sql(uow: SqliteUnitOfWork) -> None:
    for query in ("'; DROP TABLE events;--", "title:x; DROP TABLE events", "x' OR '1'='1"):
        try:
            where = parse(query)
        except QuerySyntaxError:
            continue
        run_query(uow, QuerySpec(scope=SCOPE, where=where))  # parsed as data; must be harmless
    assert table_counts(uow)["events"] > 0


def test_quote_and_to_text_round_trip_hostile_strings() -> None:
    for payload in HOSTILE:
        assert parse(quote(payload)) == Text(payload)
        expr = Compare("title", "=", payload)
        assert parse(to_text(expr)) == expr
