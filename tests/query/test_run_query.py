"""run_query and count_query over the seeded ledger: every operator of the language."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from query_seed import SCOPE
from tl_adapters._unit import BaseUnitOfWork
from tl_core.query import QuerySpec, QuerySyntaxError, count_query, parse, run_query
from tl_core.query.ast import Compare, Expr
from tl_core.query.clock import use_clock

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
ALL = {"W-001", "W-002", "W-003", "NCR-001", "NCR-002", "PRM-001", "V-0001"}  # W-099 is voided


def keys(uow: BaseUnitOfWork, text: str, **spec: object) -> list[str]:
    where = parse(text)
    with use_clock(NOW):
        rows = run_query(uow, QuerySpec(scope=SCOPE, where=where, **spec))  # type: ignore[arg-type]
        counted = count_query(uow, QuerySpec(scope=SCOPE, where=where, **spec))  # type: ignore[arg-type]
    if not spec.get("limit") and not spec.get("offset"):
        assert counted == len(rows), "count_query must agree with run_query"
    return [str(row["key"]) for row in rows]


def found(uow: BaseUnitOfWork, text: str) -> set[str]:
    return set(keys(uow, text))


def test_blank_query_returns_every_live_record_of_the_scope(uow: BaseUnitOfWork) -> None:
    assert found(uow, "") == ALL


def test_results_are_envelope_dicts_like_list_records(uow: BaseUnitOfWork) -> None:
    from tl_core.services.queries import list_records

    rows = run_query(uow, QuerySpec(scope=SCOPE))
    assert rows == list_records(uow, SCOPE)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("status:open", {"W-001", "NCR-001", "PRM-001", "V-0001"}),
        ("status=closed", {"W-002", "NCR-002"}),
        ("-status:open", {"W-002", "W-003", "NCR-002"}),
        ("not status:open", {"W-002", "W-003", "NCR-002"}),
        ("status!=open", {"W-002", "W-003", "NCR-002"}),
        ("status:null", {"W-003"}),
        ("status!=null", ALL - {"W-003"}),
        ("type:piping.Weld", {"W-001", "W-002", "W-003"}),
        ("key:W-001", {"W-001"}),
        ("key>=W-002 key<=W-003", {"W-002", "W-003"}),
        ("version:1", ALL),
        ("version>1", set()),
        ("version!=1", set()),
        ("voided:false", ALL),
        ("voided:true", set()),
        ("conformance:ok", ALL),
        ("scope:project:P123", ALL),
        ("scope:project:P999", set()),
        ("description:null", ALL - {"W-002"}),
        ("description~CHECK", {"W-002"}),
    ],
)
def test_envelope_comparisons(uow: BaseUnitOfWork, text: str, expected: set[str]) -> None:
    assert found(uow, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("title~BEVEL", {"W-001"}),
        ("title~weld", {"W-001", "W-003", "NCR-001"}),
        ("bevel", {"W-001", "W-002"}),
        ("BEVEL", {"W-001", "W-002"}),
        ("W-00", {"W-001", "W-002", "W-003"}),
        ('"hot work"', {"PRM-001"}),
        ("bevel check", {"W-002"}),
        ("bevel -check", {"W-001"}),
        ("100%", {"V-0001"}),
        ("%", {"V-0001"}),
        ("1_0", set()),
        ("_off", {"V-0001"}),
        ("100%_off", {"V-0001"}),
        ("\\", set()),
        ('"nothing like this"', set()),
    ],
)
def test_text_search_covers_key_title_and_description_with_escaping(
    uow: BaseUnitOfWork, text: str, expected: set[str]
) -> None:
    assert found(uow, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("psets.nde.method=RT", {"W-001"}),
        ("psets.nde.method:ut", set()),
        ("psets.nde.method~u", {"W-002"}),
        ("psets.nde.method!=RT", ALL - {"W-001"}),
        ("-psets.nde.method:RT", ALL - {"W-001"}),
        ("psets.nde.method:null", ALL - {"W-001", "W-002"}),
        ("psets.nde.method!=null", {"W-001", "W-002"}),
        ("psets.nde.count>=4", {"W-002"}),
        ("psets.nde.count<4", {"W-001"}),
        ("psets.nde.count:3", {"W-001"}),
        ("psets.nde.count>2 psets.nde.count<=5", {"W-001", "W-002"}),
        ("psets.nde.count!=3", ALL - {"W-001"}),
        ("psets.valve_data.size_in:4", {"V-0001"}),
        ("psets.valve_data.size_in>=4.0", {"V-0001"}),
        ("psets.valve_data.size_in>4", set()),
        ("psets.valve_data.tested:true", {"V-0001"}),
        ("psets.valve_data.tested:false", set()),
        ("psets.valve_data.tested!=true", ALL - {"V-0001"}),
        ("psets.valve_data.manufacturer~acm", {"V-0001"}),
        ('psets.valve_data.manufacturer:"Acme"', {"V-0001"}),
        ("psets.valve_data.size_in:Acme", set()),
        ("psets.nde.method:RT OR psets.nde.method:UT", {"W-001", "W-002"}),
        ("psets.nde.method:RT psets.nde.count:5", set()),
    ],
)
def test_pset_paths_compile_to_typed_exists(
    uow: BaseUnitOfWork, text: str, expected: set[str]
) -> None:
    assert found(uow, text) == expected


def test_boolean_logic_and_precedence(uow: BaseUnitOfWork) -> None:
    assert found(uow, "status:open OR status:closed") == ALL - {"W-003"}
    assert found(uow, "type:piping.Weld status:open OR key:PRM-001") == {"W-001", "PRM-001"}
    assert found(uow, "type:piping.Weld (status:open OR key:PRM-001)") == {"W-001"}
    assert found(uow, "(status:open OR status:closed) -type:piping.Weld") == {
        "NCR-001",
        "NCR-002",
        "PRM-001",
        "V-0001",
    }
    assert found(uow, "-(status:open OR status:closed)") == {"W-003"}
    assert found(uow, "status:open AND NOT type:piping.Weld") == {"NCR-001", "PRM-001", "V-0001"}


# --- dates --------------------------------------------------------------------------------------
# created_at: W-001 Oct 1 10:00Z, NCR-001 Oct 3, NCR-002 Oct 4, W-002 Oct 5 23:30Z, PRM-001 Oct 6,
# W-003 Oct 8, V-0001 Oct 9 08:00Z (W-099 voided). The fixed "now" is 2026-10-09 12:00Z.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("created_at=2026-10-05", {"W-002"}),
        ("created_at:2026-10-05", {"W-002"}),
        ("created_at!=2026-10-05", ALL - {"W-002"}),
        ("created_at<2026-10-03", {"W-001"}),
        ("created_at<=2026-10-03", {"W-001", "NCR-001"}),
        ("created_at>2026-10-08", {"V-0001"}),
        ("created_at>=2026-10-08", {"W-003", "V-0001"}),
        ("created_at>=2026-10-05 created_at<2026-10-07", {"W-002", "PRM-001"}),
        ("created_at<2026-10-05T23:30:00Z", {"W-001", "NCR-001", "NCR-002"}),
        ("created_at<=2026-10-05T23:30:00Z", {"W-001", "NCR-001", "NCR-002", "W-002"}),
        ("created_at=2026-10-05T23:30:00Z", {"W-002"}),
        ("created_at=2026-10-05T23:30:01Z", set()),
        ("created_at=2026-10-05T23:30Z", {"W-002"}),
        ("created_at<2026-10-06T01:30:00+02:00", {"W-001", "NCR-001", "NCR-002"}),
        ("created_at=today", {"V-0001"}),
        ("created_at>=today", {"V-0001"}),
        ("created_at<today", ALL - {"V-0001"}),
        ("created_at<=-1d", ALL - {"V-0001"}),
        ("created_at>-3d", {"W-003", "V-0001"}),
        ("created_at>=-3d", {"PRM-001", "W-003", "V-0001"}),
        ("created_at<-5d", {"W-001", "NCR-001"}),
        ("created_at>=-8d created_at<=-6d", {"W-001", "NCR-001"}),
        ("created_at<+1d", ALL),
        ("created_at>+1d", set()),
        ("updated_at>=today", {"V-0001"}),
    ],
)
def test_date_windows(uow: BaseUnitOfWork, text: str, expected: set[str]) -> None:
    assert found(uow, text) == expected


def test_relative_dates_follow_the_project_time_zone(uow: BaseUnitOfWork) -> None:
    # 2026-10-09 01:00Z is still Oct 8 in New York (UTC-4): "today" starts at 2026-10-08 04:00Z.
    where = parse("created_at>=today")
    moment = datetime(2026, 10, 9, 1, 0, tzinfo=UTC)
    with use_clock(moment, tz="America/New_York"):
        rows = run_query(uow, QuerySpec(scope=SCOPE, where=where))
    assert {r["key"] for r in rows} == {"W-003", "V-0001"}
    with use_clock(moment, tz="UTC"):
        rows = run_query(uow, QuerySpec(scope=SCOPE, where=where))
    assert {r["key"] for r in rows} == {"V-0001"}
    with use_clock(moment, tz="Pacific/Auckland"):  # already Oct 9, 14:00 local
        rows = run_query(uow, QuerySpec(scope=SCOPE, where=parse("created_at>=today")))
    assert {r["key"] for r in rows} == {"V-0001"}


def test_relative_dates_apply_to_pset_dates_stored_as_text(uow: BaseUnitOfWork) -> None:
    # valve_data.due is "2026-10-20"; today is 2026-10-09
    assert found(uow, "psets.valve_data.due<+7d") == set()
    assert found(uow, "psets.valve_data.due<=+11d") == {"V-0001"}
    assert found(uow, "psets.valve_data.due=+11d") == {"V-0001"}
    assert found(uow, "psets.valve_data.due>+10d") == {"V-0001"}
    assert found(uow, "psets.valve_data.due>+11d") == set()
    assert found(uow, "psets.valve_data.due>=+11d") == {"V-0001"}
    assert found(uow, "psets.valve_data.due!=+11d") == ALL - {"V-0001"}
    assert found(uow, 'psets.valve_data.due>"2026-10-19"') == {"V-0001"}


def test_a_clock_can_be_a_callable(uow: BaseUnitOfWork) -> None:
    calls: list[int] = []

    def tick() -> datetime:
        calls.append(1)
        return NOW

    with use_clock(tick):
        run_query(uow, QuerySpec(scope=SCOPE, where=parse("created_at>=today")))
    assert calls


# --- links --------------------------------------------------------------------------------------
# Live links (retracted and suggested do not count): NCR-001-W-001, NCR-001-W-002, NCR-002-W-002
# (stale), W-002-PRM-001.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("linked", {"W-001", "W-002", "NCR-001", "NCR-002", "PRM-001"}),
        ("linked:NCR", {"W-001", "W-002"}),
        ("linked:ncr", {"W-001", "W-002"}),
        ("linked:quality.NCR", {"W-001", "W-002"}),
        ("linked:quality.ncr", {"W-001", "W-002"}),
        ("linked:permit", {"W-002"}),
        ("linked:Weld", {"NCR-001", "NCR-002", "PRM-001"}),
        ("linked:piping.Weld", {"NCR-001", "NCR-002", "PRM-001"}),
        ("linked:iping.Weld", set()),
        ("linked:Wel", set()),
        ("linked(raised_against)", {"W-001", "W-002", "NCR-001", "NCR-002"}),
        ("linked(requires)", {"W-002", "PRM-001"}),
        ("linked(requires):permit", {"W-002"}),
        ("linked(requires):NCR", set()),
        ("linked(nope)", set()),
        ("linked(raised_against).status:open", {"W-001", "W-002", "NCR-001"}),
        ("linked(raised_against).status:closed", {"W-002", "NCR-001", "NCR-002"}),
        ("linked:NCR.status:open", {"W-001", "W-002"}),
        ("linked:NCR.status:closed", {"W-002"}),
        ("linked:quality.NCR.status:closed", {"W-002"}),
        ("linked:NCR.-status:open", {"W-002"}),
        ("linked:NCR.(status:open key:NCR-001)", {"W-001", "W-002"}),
        ("linked:NCR.(status:open key:NCR-002)", set()),
        ("linked:NCR.(key:NCR-002 OR key:NCR-009)", {"W-002"}),
        ("linked.key:W-001", {"NCR-001"}),
        ("linked.linked:permit", {"NCR-001", "NCR-002", "PRM-001"}),
        ("linked(raised_against).linked(requires)", {"NCR-001", "NCR-002"}),
        ("linked:NCR.bevel", set()),  # "NCR.bevel" is read as a dotted type name
        ("linked:NCR.(Crack)", {"W-001", "W-002"}),
        ("linked:NCR.(crack OR porosity)", {"W-001", "W-002"}),
        ("linked:NCR.(porosity)", {"W-002"}),
        ("linked(raised_against):NCR.psets.nde.count>2", set()),
        ("linked(raised_against):weld.psets.nde.count>2", {"NCR-001", "NCR-002"}),
        ("linked:Weld.psets.nde.method:RT", {"NCR-001"}),
    ],
)
def test_linked_counts_live_links_in_both_directions(
    uow: BaseUnitOfWork, text: str, expected: set[str]
) -> None:
    assert found(uow, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("count(linked:NCR)>0", {"W-001", "W-002"}),
        ("count(linked:NCR)>1", {"W-002"}),
        ("count(linked:NCR)=1", {"W-001"}),
        ("count(linked:NCR)=0", ALL - {"W-001", "W-002"}),
        ("count(linked:NCR)!=0", {"W-001", "W-002"}),
        ("count(linked:NCR)<2", ALL - {"W-002"}),
        ("count(linked:NCR)>=2", {"W-002"}),
        ("count(linked:NCR)<=1", ALL - {"W-002"}),
        ("count(linked)>=2", {"W-002", "NCR-001"}),
        ("count(linked)=0", {"W-003", "V-0001"}),
        ("count(linked(raised_against).status:open)>=1", {"W-001", "W-002", "NCR-001"}),
        ("count(linked(raised_against).status:closed)>=1", {"W-002", "NCR-001", "NCR-002"}),
        ("count(linked(raised_against).status:closed)>=2", set()),
        ("count(linked:NCR)>-1", ALL),
    ],
)
def test_count_linked(uow: BaseUnitOfWork, text: str, expected: set[str]) -> None:
    assert found(uow, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("missing(link:permit)", ALL - {"W-002"}),
        ("missing(link:NCR)", ALL - {"W-001", "W-002"}),
        ("missing(link)", {"W-003", "V-0001"}),
        ("missing(link(requires))", ALL - {"W-002", "PRM-001"}),
        ("missing(link(requires):permit)", ALL - {"W-002"}),
        ("type:piping.Weld missing(link:NCR)", {"W-003"}),
        ("-missing(link:NCR)", {"W-001", "W-002"}),
    ],
)
def test_missing_link(uow: BaseUnitOfWork, text: str, expected: set[str]) -> None:
    assert found(uow, text) == expected


# --- the spec: scope, type, voided, order, paging ----------------------------------------------


def test_scope_record_type_and_voided(uow: BaseUnitOfWork) -> None:
    assert [r["key"] for r in run_query(uow, QuerySpec(scope="project:P999"))] == ["W-001"]
    assert run_query(uow, QuerySpec(scope="project:nope")) == []
    weld = {r["key"] for r in run_query(uow, QuerySpec(scope=SCOPE, record_type="piping.Weld"))}
    assert weld == {"W-001", "W-002", "W-003"}
    with_voided = QuerySpec(scope=SCOPE, record_type="piping.Weld", include_voided=True)
    assert {r["key"] for r in run_query(uow, with_voided)} == {"W-001", "W-002", "W-003", "W-099"}
    only_voided = QuerySpec(scope=SCOPE, where=parse("voided:true"), include_voided=True)
    assert [r["key"] for r in run_query(uow, only_voided)] == ["W-099"]
    assert count_query(uow, with_voided) == 4


def test_default_order_is_creation_time_then_id(uow: BaseUnitOfWork) -> None:
    assert keys(uow, "") == [
        "W-001",
        "NCR-001",
        "NCR-002",
        "W-002",
        "PRM-001",
        "W-003",
        "V-0001",
    ]


def test_order_by_envelope_columns_puts_empty_values_last(uow: BaseUnitOfWork) -> None:
    asc = keys(uow, "", order_by=[("status", "asc"), ("key", "asc")])
    assert asc == ["NCR-002", "W-002", "NCR-001", "PRM-001", "V-0001", "W-001", "W-003"]
    desc = keys(uow, "", order_by=[("status", "desc"), ("key", "desc")])
    assert desc == ["W-001", "V-0001", "PRM-001", "NCR-001", "W-002", "NCR-002", "W-003"]
    titles = keys(uow, "", order_by=[("title", "asc")])
    assert titles == ["W-001", "W-003", "NCR-001", "V-0001", "PRM-001", "NCR-002", "W-002"]


def test_order_by_a_pset_path_sorts_numbers_then_text_then_missing(uow: BaseUnitOfWork) -> None:
    rows = keys(uow, "", order_by=[("psets.nde.count", "desc")])
    assert rows[:2] == ["W-002", "W-001"]
    assert rows[2:] == ["NCR-001", "NCR-002", "PRM-001", "V-0001", "W-003"]  # no value: by id
    asc = keys(uow, "", order_by=[("psets.nde.method", "asc")])
    assert asc[:2] == ["W-001", "W-002"]  # RT before UT; the rest have no value
    asc = keys(uow, "", order_by=[("psets.nde.method", "desc")])
    assert asc[:2] == ["W-002", "W-001"]


def test_limit_offset_and_count_ignore_each_other(uow: BaseUnitOfWork) -> None:
    spec = QuerySpec(scope=SCOPE, order_by=[("key", "asc")], limit=3)
    assert [r["key"] for r in run_query(uow, spec)] == ["NCR-001", "NCR-002", "PRM-001"]
    paged = QuerySpec(scope=SCOPE, order_by=[("key", "asc")], limit=2, offset=3)
    assert [r["key"] for r in run_query(uow, paged)] == ["V-0001", "W-001"]
    tail = QuerySpec(scope=SCOPE, order_by=[("key", "asc")], limit=None, offset=5)
    assert [r["key"] for r in run_query(uow, tail)] == ["W-002", "W-003"]
    assert count_query(uow, paged) == 7
    assert run_query(uow, QuerySpec(scope=SCOPE, limit=0)) == []


@pytest.mark.parametrize(
    "spec",
    [
        QuerySpec(scope=SCOPE, limit=-1),
        QuerySpec(scope=SCOPE, offset=-1),
        QuerySpec(scope=SCOPE, order_by=[("psets_json", "asc")]),
        QuerySpec(scope=SCOPE, order_by=[("key; DROP TABLE events", "asc")]),
        QuerySpec(scope=SCOPE, order_by=[("voided", "asc")]),
        QuerySpec(scope=SCOPE, order_by=[("psets.a", "asc")]),
        QuerySpec(scope=""),
    ],
)
def test_bad_specs_raise_value_error(uow: BaseUnitOfWork, spec: QuerySpec) -> None:
    with pytest.raises(ValueError):
        run_query(uow, spec)


def test_bad_direction_raises_value_error(uow: BaseUnitOfWork) -> None:
    spec = QuerySpec(scope=SCOPE, order_by=[("key", "up")])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        run_query(uow, spec)


# --- hand-built ASTs are validated like parsed text --------------------------------------------


@pytest.mark.parametrize(
    "where",
    [
        Compare("nope", "=", "x"),
        Compare("title; DROP TABLE events", "=", "x"),
        Compare("title", "LIKE", "x"),  # type: ignore[arg-type]
        Compare("psets.a", "=", "x"),
        Compare("psets.a.b; DROP", "=", "x"),
        Compare("version", "~", 1),
        Compare("version", "=", "one"),
        Compare("version", "=", True),
        Compare("voided", "=", 1),
        Compare("voided", "<", True),
        Compare("created_at", "=", "yesterday"),
        Compare("created_at", "~", "2026"),
        Compare("title", "=", True),
        Compare("status", "<", None),
    ],
)
def test_invalid_comparisons_raise_query_syntax_error(uow: BaseUnitOfWork, where: Expr) -> None:
    with pytest.raises(QuerySyntaxError) as info:
        run_query(uow, QuerySpec(scope=SCOPE, where=where))
    assert info.value.position == 0
