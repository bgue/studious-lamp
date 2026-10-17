"""Threading keys: subject, message ids, item numbers and the thread decision (P1-I5-T08a)."""

from __future__ import annotations

import pytest
from tl_mod_correspondence import threading as t
from tl_mod_correspondence.names import MATCHED_BY


@pytest.mark.parametrize(
    ("subject", "key"),
    [
        ("Revised programme", "revised programme"),
        ("RE: Revised programme", "revised programme"),
        ("Fwd: RE: Re[2]: Revised   Programme ", "revised programme"),
        ("AW: SV: Revised programme", "revised programme"),
        ("re:re:re:re:re:re:Hello world", "hello world"),
        ("Re: ", ""),
        ("", ""),
        ("Ｒｅｖｉｓｅｄ programme", "revised programme"),  # full-width letters
        ("Revised\tprogramme\r\nfor week 42", "revised programme for week 42"),
        ("Reference: the revised programme", "reference: the revised programme"),
        ("Regarding the programme", "regarding the programme"),  # "Re" without a colon stays
    ],
)
def test_the_subject_loses_prefixes_case_and_extra_space(subject: str, key: str) -> None:
    assert t.normalise_subject(subject) == key


def test_a_very_long_subject_is_cut_at_the_bound() -> None:
    assert len(t.normalise_subject("x" * 100_000)) == t.MAX_SUBJECT_CHARS


def test_a_prefix_chain_longer_than_the_loop_bound_still_ends() -> None:
    found = t.normalise_subject("re:" * 100_000 + "x")
    assert len(found) <= t.MAX_SUBJECT_CHARS and found.startswith("re:")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("<abc@mail.example>", "abc@mail.example"),
        ("  abc@mail.example ", "abc@mail.example"),
        ("<Abc.DEF@Mail.Example>", "Abc.DEF@Mail.Example"),  # case is kept
        (None, None),
        ("", None),
        ("<>", None),
        ("no-at-sign", None),
        ("two@at@signs", None),
        ("a b@c", None),
        ("<a@b><c@d>", None),
        ("a@" + "x" * 300, None),
        ("a@b\x00c", None),
        ("a@b‮c", None),  # a text-direction mark is a control-class character
    ],
)
def test_a_message_id_is_usable_or_none(raw: str | None, expected: str | None) -> None:
    assert t.normalise_message_id(raw) == expected


def test_references_come_out_in_order_without_brackets_or_repeats() -> None:
    header = "<a@x.example> <b@x.example>\n\t<a@x.example> junk <c@x.example>"
    assert t.parse_references(header) == ["a@x.example", "b@x.example", "c@x.example"]


def test_references_skip_unusable_tokens_and_empty_headers() -> None:
    assert t.parse_references(None) == []
    assert t.parse_references("") == []
    assert t.parse_references("no brackets here a@b") == []
    assert t.parse_references("<bad token@x> <ok@x.example>") == ["ok@x.example"]


def test_references_stop_at_the_count_bound() -> None:
    header = " ".join(f"<m{i}@x.example>" for i in range(t.MAX_REFERENCES + 20))
    found = t.parse_references(header)
    assert len(found) == t.MAX_REFERENCES and found[0] == "m0@x.example"


def test_references_read_only_the_first_part_of_a_huge_header() -> None:
    header = "<a@x.example> " + "z" * t.MAX_HEADER_CHARS + " <late@x.example>"
    assert t.parse_references(header) == ["a@x.example"]


def test_item_numbers_are_found_whatever_the_case_and_listed_once_in_order() -> None:
    text = "See p123-cor-0042, P123-TRN-0007 and again P123-COR-0042; also P124-COR-0001."
    assert t.find_item_numbers(text, "P123", ("COR", "TRN")) == ["P123-COR-0042", "P123-TRN-0007"]


def test_an_item_number_inside_a_longer_word_or_number_is_not_one() -> None:
    assert t.find_item_numbers("XP123-COR-0042", "P123", ("COR",)) == []
    assert t.find_item_numbers("P123-COR-004", "P123", ("COR",)) == []
    assert t.find_item_numbers("P123-COR-123456789", "P123", ("COR",)) == []
    assert t.find_item_numbers("(P123-COR-0042).", "P123", ("COR",)) == ["P123-COR-0042"]


def test_a_type_code_that_was_not_asked_for_is_not_found() -> None:
    assert t.find_item_numbers("P123-NCR-0042", "P123", ("COR",)) == []


@pytest.mark.parametrize(
    ("project", "codes"),
    [("P 123", ("COR",)), ("P123|.*", ("COR",)), ("", ("COR",)), ("P123", ("C.R",)), ("P123", ())],
)
def test_a_project_or_code_that_is_not_plain_gives_nothing(
    project: str, codes: tuple[str, ...]
) -> None:
    assert t.find_item_numbers("P123-COR-0042", project, codes) == []


def test_a_project_or_code_that_is_not_plain_is_refused_even_when_the_text_has_it() -> None:
    assert t.find_item_numbers("P 123-COR-0042", "P 123", ("COR",)) == []
    assert t.find_item_numbers("P123-C.R-0042", "P123", ("C.R",)) == []
    assert t.find_item_numbers("P123-COR-0042", "P123", ("cor",)) == ["P123-COR-0042"]  # case only


def test_a_project_id_with_regex_characters_is_matched_literally() -> None:
    assert t.find_item_numbers("A.B-COR-0001 AxB-COR-0001", "A.B", ("COR",)) == ["A.B-COR-0001"]


def test_item_numbers_stop_at_the_count_bound_and_the_text_bound() -> None:
    many = " ".join(f"P123-COR-{i:04d}" for i in range(t.MAX_KEYS + 10))
    assert len(t.find_item_numbers(many, "P123", ("COR",))) == t.MAX_KEYS
    late = "x" * t.MAX_TEXT_CHARS + " P123-COR-0042"
    assert t.find_item_numbers(late, "P123", ("COR",)) == []


def facts(**more: object) -> t.ThreadFacts:
    base: dict[str, object] = {
        "in_reply_to": None,
        "references": [],
        "subject_key": "",
        "numbers": [],
    }
    base.update(more)
    return t.ThreadFacts(**base)  # type: ignore[arg-type]


def test_a_header_match_wins_and_names_the_item_answered() -> None:
    known = {"m1@x": t.KnownItem("I1", "T1"), "m2@x": t.KnownItem("I2", "T2")}
    match = t.match_thread(
        facts(in_reply_to="m1@x", numbers=["P123-COR-0001"], subject_key="programme"),
        known,
        {"P123-COR-0001": t.KnownItem("I9", "T9")},
        {"programme": "T3"},
    )
    assert match == t.ThreadMatch("T1", "I1", "header")


def test_references_are_tried_from_the_newest_back() -> None:
    known = {"old@x": t.KnownItem("I1", "T1"), "new@x": t.KnownItem("I2", "T2")}
    match = t.match_thread(facts(references=["old@x", "new@x"]), known, {}, {})
    assert match == t.ThreadMatch("T2", "I2", "header")


def test_an_unknown_header_falls_through_to_the_item_number() -> None:
    match = t.match_thread(
        facts(in_reply_to="gone@x", numbers=["P123-COR-0002", "P123-COR-0001"]),
        {},
        {"P123-COR-0001": t.KnownItem("I1", "T1")},
        {},
    )
    assert match == t.ThreadMatch("T1", "I1", "reference_key")


def test_the_subject_joins_an_open_thread_and_answers_no_item() -> None:
    match = t.match_thread(
        facts(subject_key="revised programme"), {}, {}, {"revised programme": "T7"}
    )
    assert match == t.ThreadMatch("T7", None, "subject")


def test_a_thin_subject_does_not_join_a_thread() -> None:
    assert t.match_thread(facts(subject_key="hi"), {}, {}, {"hi": "T7"}) is None
    assert t.match_thread(facts(subject_key=""), {}, {}, {"": "T7"}) is None


def test_an_item_with_no_thread_is_returned_for_the_caller_to_open_one() -> None:
    match = t.match_thread(facts(in_reply_to="m@x"), {"m@x": t.KnownItem("I1", None)}, {}, {})
    assert match == t.ThreadMatch(None, "I1", "header")


def test_nothing_matching_gives_none() -> None:
    assert t.match_thread(facts(), {}, {}, {}) is None


def test_every_way_of_matching_is_a_name_the_module_knows() -> None:
    assert {"header", "reference_key", "subject"} <= set(MATCHED_BY)
