"""The filter-language parser: grammar, precedence, typing of values and error positions."""

from __future__ import annotations

import pytest
from tl_core.query import (
    And,
    Compare,
    CountLinked,
    Linked,
    MissingLink,
    Not,
    Or,
    QuerySyntaxError,
    RelativeDate,
    Text,
    parse,
)
from tl_core.query.parser import MAX_DEPTH, MAX_NODES, MAX_QUERY_LENGTH


def eq(path: str, value: object) -> Compare:
    return Compare(path, "=", value)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["", "   ", "\t\n"])
def test_blank_text_parses_to_none(text: str) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("status:open", eq("status", "open")),
        ("status=open", eq("status", "open")),
        ("status!=open", Compare("status", "!=", "open")),
        ("title~bevel", Compare("title", "~", "bevel")),
        ("version>=2", Compare("version", ">=", 2)),
        ("version<10", Compare("version", "<", 10)),
        ("version>-1", Compare("version", ">", -1)),
        ("voided:true", eq("voided", True)),
        ("voided!=false", Compare("voided", "!=", False)),
        ("updated_at<+7d", Compare("updated_at", "<", RelativeDate(7))),
        ("updated_at>-3d", Compare("updated_at", ">", RelativeDate(-3))),
        ("created_at>=today", Compare("created_at", ">=", RelativeDate(0))),
        ("created_at>2026-10-09", Compare("created_at", ">", "2026-10-09")),
        ("created_at:2026-10-09T12:30:00Z", eq("created_at", "2026-10-09T12:30:00Z")),
        ("STATUS:Open", eq("status", "Open")),
        ("status:null", eq("status", None)),
        ("status!=NULL", Compare("status", "!=", None)),
        ('status:"null"', eq("status", "null")),
        ('title:"a b"', eq("title", "a b")),
        ("title:'a b'", eq("title", "a b")),
        (r'title:"say \"hi\" \\ done"', eq("title", 'say "hi" \\ done')),
        (r'title:"keep \n as is"', eq("title", "keep \\n as is")),
        ("key:007", eq("key", "007")),
        ("key:12.50", eq("key", "12.50")),
        ("key:true", eq("key", "true")),
        ("status:a:b", eq("status", "a:b")),
    ],
)
def test_envelope_terms(text: str, expected: object) -> None:
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("psets.nde.method=RT", eq("psets.nde.method", "RT")),
        ("psets.valve_data.size_in>=2", Compare("psets.valve_data.size_in", ">=", 2)),
        ("psets.a.b:1.5", eq("psets.a.b", 1.5)),
        ("psets.a.b:-3", eq("psets.a.b", -3)),
        ("psets.a.b:true", eq("psets.a.b", True)),
        ("psets.a.b:null", eq("psets.a.b", None)),
        ("psets.a.b:007", eq("psets.a.b", "007")),
        ("psets.a.b:1e5", eq("psets.a.b", "1e5")),
        ('psets.a.b:"12"', eq("psets.a.b", "12")),
        ("psets.a.b~12", Compare("psets.a.b", "~", "12")),
        ("psets.a.due<+7d", Compare("psets.a.due", "<", RelativeDate(7))),
        ("psets.a.x.c:1", eq("psets.a.x.c", 1)),
        ("psets.prj.tie_in.owner:Acme", eq("psets.prj.tie_in.owner", "Acme")),
        ("PSETS.a.b:1", eq("psets.a.b", 1)),
    ],
)
def test_pset_terms_infer_value_types(text: str, expected: object) -> None:
    assert parse(text) == expected


def test_terms_are_anded_and_flattened() -> None:
    assert parse("status:open type:task bevel") == And(
        (eq("status", "open"), eq("type", "task"), Text("bevel"))
    )
    assert parse("(a b) c AND d") == And((Text("a"), Text("b"), Text("c"), Text("d")))


def test_precedence_not_over_and_over_or() -> None:
    assert parse("a b OR c d") == Or((And((Text("a"), Text("b"))), And((Text("c"), Text("d")))))
    assert parse("a OR b c") == Or((Text("a"), And((Text("b"), Text("c")))))
    assert parse("-a b") == And((Not(Text("a")), Text("b")))
    assert parse("a or b or c") == Or((Text("a"), Text("b"), Text("c")))
    assert parse("(a OR b) c") == And((Or((Text("a"), Text("b"))), Text("c")))
    assert parse("not a OR b") == Or((Not(Text("a")), Text("b")))


def test_negation_forms() -> None:
    expected = Not(eq("status", "void"))
    assert parse("-status:void") == expected
    assert parse("not status:void") == expected
    assert parse("NOT status:void") == expected
    assert parse("not(status:void)") == expected
    assert parse("--a") == Not(Not(Text("a")))
    assert parse("-(a b)") == Not(And((Text("a"), Text("b"))))


def test_text_terms() -> None:
    assert parse("bevel") == Text("bevel")
    assert parse('"bevel weld"') == Text("bevel weld")
    assert parse("W-001") == Text("W-001")
    assert parse('"or"') == Text("or")
    assert parse('"linked"') == Text("linked")
    assert parse("count") == Text("count")
    assert parse("path") == Text("path")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("linked:NCR", Linked(None, "NCR", None)),
        ("linked:quality.NCR", Linked(None, "quality.NCR", None)),
        ("linked", Linked(None, None, None)),
        ("linked(raised_against)", Linked("raised_against", None, None)),
        ("linked(raised_against):NCR", Linked("raised_against", "NCR", None)),
        ("linked(*):NCR", Linked(None, "NCR", None)),
        (
            "linked(raised_against).status:open",
            Linked("raised_against", None, eq("status", "open")),
        ),
        ("linked:NCR.status:open", Linked(None, "NCR", eq("status", "open"))),
        (
            "linked:quality.NCR.status:open",
            Linked(None, "quality.NCR", eq("status", "open")),
        ),
        (
            "linked:quality.NCR.psets.a.b>3",
            Linked(None, "quality.NCR", Compare("psets.a.b", ">", 3)),
        ),
        ("linked.status:open", Linked(None, None, eq("status", "open"))),
        (
            "linked:NCR.(status:open type:x)",
            Linked(None, "NCR", And((eq("status", "open"), eq("type", "x")))),
        ),
        ("linked:NCR.-status:void", Linked(None, "NCR", Not(eq("status", "void")))),
        (
            "linked(a).linked(b).status:open",
            Linked("a", None, Linked("b", None, eq("status", "open"))),
        ),
        ("(linked:NCR)", Linked(None, "NCR", None)),
        ("LINKED:NCR", Linked(None, "NCR", None)),
    ],
)
def test_linked_terms(text: str, expected: object) -> None:
    assert parse(text) == expected


def test_where_stops_at_the_next_term() -> None:
    assert parse("linked:NCR.status:open title:x") == And(
        (Linked(None, "NCR", eq("status", "open")), eq("title", "x"))
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("count(linked:NCR)>0", CountLinked(Linked(None, "NCR", None), ">", 0)),
        ("count(linked:NCR)>=2", CountLinked(Linked(None, "NCR", None), ">=", 2)),
        ("count(linked:NCR)=1", CountLinked(Linked(None, "NCR", None), "=", 1)),
        ("count(linked:NCR):1", CountLinked(Linked(None, "NCR", None), "=", 1)),
        ("count(linked:NCR)!=0", CountLinked(Linked(None, "NCR", None), "!=", 0)),
        ("count( linked )<3", CountLinked(Linked(None, None, None), "<", 3)),
        (
            "count(linked(r).status:open)>=2",
            CountLinked(Linked("r", None, eq("status", "open")), ">=", 2),
        ),
        ("missing(link:permit)", MissingLink(None, "permit")),
        ("missing(link)", MissingLink(None, None)),
        ("missing(linked(requires):permit)", MissingLink("requires", "permit")),
        ("missing(link(requires))", MissingLink("requires", None)),
    ],
)
def test_count_and_missing(text: str, expected: object) -> None:
    assert parse(text) == expected


def test_the_brief_example_uses_only_fields_phase_0_has() -> None:
    parsed = parse("status:open psets.nde.method=RT updated_at<+7d linked:NCR")
    assert parsed == And(
        (
            eq("status", "open"),
            eq("psets.nde.method", "RT"),
            Compare("updated_at", "<", RelativeDate(7)),
            Linked(None, "NCR", None),
        )
    )


# --- errors -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "position", "fragment"),
    [
        ("status:", 7, "expected a value"),
        ("status: open", 7, "expected a value"),
        ("(a", 2, "missing ')'"),
        ("a)", 1, "unmatched"),
        (")", 0, "unmatched"),
        ("()", 0, "empty"),
        ("a OR", 4, "after OR"),
        ("OR a", 0, "keyword"),
        ("a AND", 5, "after AND"),
        ("a AND OR b", 6, "after AND"),
        ("a OR OR b", 5, "keyword"),
        ("-", 1, "after '-'"),
        ("- a", 1, "after '-'"),
        ("not", 3, "after NOT"),
        ("foo:bar", 0, "unknown field"),
        ("stat:open", 0, "did you mean 'status'"),
        ("a status:open foo:bar", 14, "unknown field"),
        ("discipline:PIP", 0, "unknown field"),
        ("psets.a:1", 0, "pset path"),
        ("psets:1", 0, "pset path"),
        ("psets.a.b.c.d.e.f.g.h:1", 0, "pset path"),
        ("psets.a b:1", 8, "unknown field"),
        ("version:abc", 8, "whole number"),
        ("version:1.5", 8, "whole number"),
        ("version~1", 7, "cannot be used"),
        ("voided:maybe", 7, "true or false"),
        ("voided<true", 6, "cannot be used"),
        ("created_at>soon", 11, "expected a date"),
        ("created_at>2026-13-01", 11, "not a valid date"),
        ("created_at~2026", 10, "cannot be used"),
        ("created_at>+99999999d", 11, "expected a date"),
        ("created_at>+999999d", 11, "not a valid date"),
        ("title<null", 6, "null"),
        ("status==open", 7, "quote the value"),
        ("status!open", 6, "expected '='"),
        ("status:(a)", 7, "cannot start with '('"),
        ('"unterminated', 0, "unterminated"),
        ('title:"unterminated', 6, "unterminated"),
        ('""', 0, "empty search"),
        ("a(b)", 1, "expected a space"),
        ('"a"b', 3, "expected a space"),
        ('a"b"', 1, "expected a space"),
        (":a", 0, "field name"),
        ("=a", 0, "field name"),
        ("~", 0, "field name"),
        ('"a b":c', 5, "quoted text cannot"),
        ("path(a>b>c)", 0, "not supported"),
        ("path(a>b>c).rev:C", 0, "not supported"),
        ("linked(", 7, "relation code"),
        ("linked(x", 8, "expected ')'"),
        ("linked(a b)", 9, "expected ')'"),
        ("linked(!):x", 7, "relation code"),
        ("linked:", 7, "record type"),
        ("linked:1x", 7, "record type"),
        ("linked:NCR:x", 10, "unexpected ':'"),
        ("linked.", 7, "after '.'"),
        ("linked. a", 7, "after '.'"),
        ("count(linked:NCR)", 17, "comparison"),
        ("count(linked:NCR)~1", 17, "'~' cannot"),
        ("count(linked:NCR)>x", 18, "whole number"),
        ("count(linked:NCR)>1.5", 18, "whole number"),
        ("count(x)>1", 6, "linked term"),
        ("count(linked:NCR>1", 16, "unexpected '>'"),
        ("missing(permit)", 8, "link term"),
        ("missing(link:permit", 19, "expected ')'"),
        ("missing(link.status:open)", 12, "condition"),
        ("missing(link:NCR.status:open)", 23, "condition"),
        ("x\x00y", 1, "control"),
        ("x\ud800", 1, "control"),
    ],
)
def test_errors_carry_the_offending_position(text: str, position: int, fragment: str) -> None:
    with pytest.raises(QuerySyntaxError) as info:
        parse(text)
    assert fragment in str(info.value)
    assert info.value.position == position, (text, str(info.value))


def test_error_is_a_service_error() -> None:
    from tl_core.services.errors import ServiceError

    with pytest.raises(ServiceError):
        parse("status:")


def test_limits_bound_the_input() -> None:
    with pytest.raises(QuerySyntaxError, match="longer than"):
        parse("a " * MAX_QUERY_LENGTH)
    with pytest.raises(QuerySyntaxError, match="nested"):
        parse("(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1))
    with pytest.raises(QuerySyntaxError, match="nested"):
        parse("-" * (MAX_DEPTH + 1) + "a")
    with pytest.raises(QuerySyntaxError, match="too complex"):
        parse(" ".join(f"t{n}" for n in range(MAX_NODES + 1)))


def test_the_deepest_allowed_nesting_parses() -> None:
    depth = MAX_DEPTH - 1
    assert parse("(" * depth + "a" + ")" * depth) == Text("a")
    assert parse("-" * depth + "a") is not None
