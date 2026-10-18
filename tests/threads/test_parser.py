"""The dispatch parser: the frozen grammar (contract helper) and the edges it leaves open."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from test_dispatch_contract import PARSE_CASES, PROBLEM_CASES, check_parser_contract
from tl_core.threads.contract import (
    DISPATCH_VERBS,
    DispatchArgs,
    DispatchParser,
    LinkArgs,
    NotifyArgs,
    ParsedDispatch,
    ParseProblem,
    RaiseArgs,
    RemindArgs,
)
from tl_core.threads.parser import CommandLineParser

PARSER = CommandLineParser()


def parsed(text: str) -> ParsedDispatch:
    found = PARSER.parse(text)
    assert isinstance(found, ParsedDispatch), (text, found)
    return found


def problem(text: str) -> ParseProblem:
    found = PARSER.parse(text)
    assert isinstance(found, ParseProblem), (text, found)
    return found


def test_the_parser_keeps_the_frozen_grammar() -> None:
    assert isinstance(PARSER, DispatchParser)
    check_parser_contract(PARSER)


def test_every_verb_and_the_american_spelling_parse() -> None:
    assert {c[1] for c in PARSE_CASES} == set(DISPATCH_VERBS)
    assert parsed("/Summarize").verb == "summarise"
    assert parsed("/SUMMARISE").line == "/SUMMARISE"


def test_a_quoted_text_is_one_word_and_never_a_parameter_or_a_key() -> None:
    args = parsed('/dispatch x "qty=2" "#K-1" "@a b"').args
    assert isinstance(args, DispatchArgs)
    assert args.parameters == {}
    assert args.text == "qty=2 #K-1 @a b"


def test_a_quote_inside_a_token_is_an_ordinary_character() -> None:
    args = parsed('/status Closed 5" pipe').args
    assert args.model_dump()["text"] == '5" pipe'


def test_a_mention_or_key_left_in_text_keeps_its_sigil() -> None:
    notify = parsed("/notify @a see #K-1 now").args
    assert isinstance(notify, NotifyArgs)
    assert notify.who == ["a"] and notify.text == "see #K-1 now"
    raised = parsed("/raise record #A call @b").args
    assert isinstance(raised, RaiseArgs)
    assert raised.against == ["A"] and raised.text == "call @b"


def test_mentions_count_wherever_they_stand() -> None:
    remind = parsed("/remind @a +1d @b ring them").args
    assert isinstance(remind, RemindArgs)
    assert remind.who == ["a", "b"] and remind.when == "+1d" and remind.text == "ring them"


def test_a_note_is_everything_after_the_first_line() -> None:
    args = parsed("/link A\r\n\r\n  one\ntwo\t\n").args
    assert isinstance(args, LinkArgs) and args.note == "one\ntwo"
    assert parsed("/link A\n   \n").args.note is None


def test_bare_sigils_and_empty_names_are_words() -> None:
    assert parsed("/hold # @ x").args.model_dump()["text"] == "# @ x"
    assert problem("/notify @").code == "missing_argument"


def test_the_boundaries_of_dates_and_times() -> None:
    assert parsed("/due +3660d").verb == "due"
    assert problem("/due +3661d").code == "bad_date"
    assert parsed("/due +522w").verb == "due"
    assert problem("/due +523w").code == "bad_date"
    assert problem("/due 2026-02-30").code == "bad_date"
    assert problem("/due 2026-11-02 2026-11-03").code == "unexpected_arguments"
    assert parsed("/remind +527040m").verb == "remind"
    assert problem("/remind +527041m").code == "bad_time"
    assert problem("/remind 2026-11-02T25:00").code == "bad_time"
    assert parsed("/remind 2026-11-02T23:59").verb == "remind"
    assert problem("/remind").code == "missing_argument"
    assert problem("/remind @a").code == "missing_argument"


def test_the_bounds_of_the_command_line() -> None:
    assert problem("/hold " + "x" * 1995).code == "too_long"
    assert parsed("/hold " + "x" * 1990).verb == "hold"
    assert problem("/hold" + "\x7f").code == "control_character"
    assert parsed("/hold a\tb").verb == "hold"


def test_a_parameter_name_is_lower_case_and_a_value_may_hold_equals() -> None:
    args = parsed("/dispatch x a=b=c Qty=2").args
    assert isinstance(args, DispatchArgs)
    assert args.parameters == {"a": "b=c"} and args.text == "Qty=2"
    assert problem("/dispatch x " + " ".join(f"p{i}=1" for i in range(21))).code == "bad_parameter"


def test_a_problem_names_a_column_where_it_can() -> None:
    assert problem("/frobnicate").column == 1
    assert problem('/raise rfi "x').column == 11
    assert problem("/summarise now").column == 11


@given(st.text(max_size=300))
def test_the_parser_is_total(text: str) -> None:
    found = PARSER.parse(text)
    assert found is None or isinstance(found, ParsedDispatch | ParseProblem)
    if isinstance(found, ParseProblem):
        assert len(found.message) <= 500


@given(st.text(alphabet="/@#\"' \tabc=+1dwmh-:\n\x00\x7f", max_size=80))
def test_the_parser_is_total_on_grammar_characters(text: str) -> None:
    PARSER.parse("/" + text)
    PARSER.parse("/link " + text)
    PARSER.parse("/remind " + text)


def test_the_problem_cases_are_all_problems() -> None:
    for text, code in PROBLEM_CASES:
        assert problem(text).code == code
