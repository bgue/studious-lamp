"""The triage suggestion engine: domain and subtype from the text (P1-I5-T07b)."""

from __future__ import annotations

import pytest
from corrworld import FIXTURES
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflows
from tl_mod_correspondence import domains as dm
from tl_mod_correspondence import suggest as sg


@pytest.fixture(scope="module")
def both() -> list[dm.DomainDefinition]:
    found = dm.load_domains(
        FIXTURES,
        workflows=load_workflows(FIXTURES / "workflows"),
        numbering=load_numbering(FIXTURES / "numbering" / "patterns.yaml"),
        sources={"documents.transmittal"},
    )
    return found.for_scope("project:P123")


def test_a_letter_with_no_keyword_goes_to_general_with_its_default_subtype(
    both: list[dm.DomainDefinition],
) -> None:
    got = sg.suggest(both, subject="Revised programme", body="Please confirm the dates.")
    assert (got.domain, got.subtype, got.score) == ("general", "letter", 0)
    assert got.reasons == ("no keyword matched; the default domain",)
    assert got.scores == {"document_control": 0, "general": 0}


def test_document_words_point_to_document_control_and_its_subtype(
    both: list[dm.DomainDefinition],
) -> None:
    got = sg.suggest(
        both,
        subject="Submittal of revision C",
        body="Attached are the drawings for review, as-built where marked.",
    )
    assert (got.domain, got.subtype) == ("document_control", "submittal")
    assert got.score >= 5
    assert "document_control: 'revision'" in got.reasons or any(
        "revision" in r for r in got.reasons
    )


def test_a_keyword_in_the_subject_counts_double_a_body_only_keyword_once(
    both: list[dm.DomainDefinition],
) -> None:
    in_subject = sg.suggest(both, subject="Transmittal 12", body=None)
    in_body = sg.suggest(both, subject="Hello", body="our transmittal follows")
    assert in_subject.scores["document_control"] == 2 * 2  # triage keyword and subtype keyword
    assert in_body.scores["document_control"] == 1 + 1


def test_the_same_word_counts_once_however_often_it_is_written(
    both: list[dm.DomainDefinition],
) -> None:
    once = sg.suggest(both, subject="x", body="memo")
    many = sg.suggest(both, subject="x", body="memo memo memo memo")
    assert once.scores == many.scores


def test_matching_is_on_whole_words_and_ignores_case(both: list[dm.DomainDefinition]) -> None:
    assert sg.suggest(both, subject="MEMO to all", body=None).subtype == "memo"
    assert sg.suggest(both, subject="memorable day", body=None).score == 0
    assert sg.suggest(both, subject="a revisionist view", body=None).score == 0
    assert sg.suggest(both, subject="Re: AS-BUILT drawings", body=None).domain == "document_control"


def test_the_subtype_is_the_one_with_the_most_keywords_and_a_tie_gives_the_default(
    both: list[dm.DomainDefinition],
) -> None:
    assert sg.suggest(both, subject="Minutes of the meeting", body=None).subtype == "minutes"
    tie = sg.suggest(both, subject="memo and minutes", body=None)
    assert (tie.domain, tie.subtype) == ("general", "letter")


def test_a_tie_between_domains_goes_to_general_and_never_depends_on_order(
    both: list[dm.DomainDefinition],
) -> None:
    text = {"subject": "transmittal memo", "body": None}  # 2+2 for document control, 2 for general
    forward = sg.suggest(both, **text)
    backward = sg.suggest(list(reversed(both)), **text)
    assert forward == backward
    even = sg.suggest(both, subject="memo and transmittal", body="memorandum for review code")
    assert even == sg.suggest(
        list(reversed(both)), subject="memo and transmittal", body="memorandum for review code"
    )


def test_no_domains_gives_an_empty_suggestion() -> None:
    got = sg.suggest([], subject="anything")
    assert (got.domain, got.subtype, got.score) == (None, None, 0)
    assert got.reasons == ("no domain is defined",)


def test_only_the_start_of_a_long_text_is_read(both: list[dm.DomainDefinition]) -> None:
    far = "x " * sg.MAX_BODY_CHARS + " transmittal"
    assert sg.suggest(both, subject="s", body=far).score == 0
    near = "transmittal " + "x " * sg.MAX_BODY_CHARS
    assert sg.suggest(both, subject="s", body=near).domain == "document_control"


def test_a_domain_without_general_falls_back_to_the_lowest_code(
    both: list[dm.DomainDefinition],
) -> None:
    only = [d for d in both if d.code == "document_control"]
    got = sg.suggest(only, subject="hello", body=None)
    assert (got.domain, got.subtype, got.score) == ("document_control", "transmittal", 0)
