"""The pure inspection rules (P2-INSP T00).

Question and answer validation, failed questions, the result.
"""

from __future__ import annotations

from typing import Any

import pytest
from tl_mod_quality import insp_rules as r


def q(qid: str, kind: str = "yes_no_na", *, required: bool = True, **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": qid,
        "text": f"question {qid}",
        "kind": kind,
        "required": required,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
    }
    base.update(kw)
    return base


def a(qid: str, value: Any, note: str | None = None) -> dict[str, Any]:
    return {"q": qid, "value": value, "note": note}


# ---- validate_questions ----------------------------------------------------------------------


def test_good_questions_have_no_problems() -> None:
    questions = [
        q("q1", fails_when="no"),
        q("q2", "number", min=0, max=10, unit="bar", fails_when="out_of_range"),
        q("q3", "text", required=False),
        q("q4", "choice", choices=["a", "b"]),
    ]
    assert r.validate_questions(questions) == []


def test_empty_list_is_a_problem() -> None:
    assert r.validate_questions([]) != []


def test_more_than_sixty_questions_is_a_problem() -> None:
    assert r.validate_questions([q(f"q{i}") for i in range(1, 61)]) == []
    assert r.validate_questions([q(f"q{i}") for i in range(1, 62)]) != []


@pytest.mark.parametrize(
    "bad",
    [
        q("q1", id="x1"),  # id must be q<digits>
        q("q1", kind="essay"),
        q("q1", text=""),
        q("q1", text="x" * 201),
        q("q1", "number", fails_when="no"),  # "no" belongs to yes_no_na
        q("q1", fails_when="out_of_range"),  # out_of_range belongs to number
        q("q1", "number", fails_when="out_of_range"),  # needs min or max
        q("q1", "number", min=5, max=1),
        q("q1", "choice"),  # needs choices
        q("q1", "choice", choices=[]),
        q("q1", "choice", choices=[str(i) for i in range(9)]),
        q("q1", "choice", choices=["a", "a"]),
        q("q1", "text", fails_when="no"),
        q("q1", required="yes"),  # pyright: ignore[reportArgumentType]
    ],
)
def test_malformed_question_is_a_problem_naming_it(bad: dict[str, Any]) -> None:
    problems = r.validate_questions([bad])
    assert problems
    assert all(
        p.startswith("q1:") or p.startswith("x1:") or p.startswith("question") for p in problems
    )


def test_duplicate_question_ids_are_a_problem() -> None:
    assert r.validate_questions([q("q1"), q("q1")]) != []


def test_unknown_question_field_is_a_problem() -> None:
    assert r.validate_questions([q("q1", extra=1)]) != []


# ---- validate_answers ------------------------------------------------------------------------

QS = [
    q("q1", fails_when="no"),
    q("q2", "number", required=False, min=1, max=5, fails_when="out_of_range"),
    q("q3", "choice", required=False, choices=["red", "green"]),
    q("q4", "text", required=False),
]


def test_good_answers_have_no_problems() -> None:
    answers = [a("q1", "yes"), a("q2", 3), a("q3", "red"), a("q4", "fine", "ok")]
    assert r.validate_answers(QS, answers) == []


def test_required_unanswered_is_a_problem_optional_is_not() -> None:
    assert r.validate_answers(QS, []) == ["q1: answer required"]
    assert r.validate_answers(QS, [a("q1", "na")]) == []


@pytest.mark.parametrize(
    "answers",
    [
        [a("q1", "maybe")],
        [a("q1", True)],
        [a("q1", "yes"), a("q2", "3")],
        [a("q1", "yes"), a("q2", True)],
        [a("q1", "yes"), a("q3", "blue")],
        [a("q1", "yes"), a("q4", 5)],
        [a("q1", "yes"), a("q4", "x" * 1001)],
        [a("q1", "yes", "n" * 301)],
        [a("q1", "yes"), a("q1", "no")],
        [a("q1", "yes"), a("q9", "yes")],
        [a("q1", "yes"), {"q": "q2", "value": 1, "note": None, "extra": 1}],
    ],
)
def test_bad_answers_are_problems(answers: list[dict[str, Any]]) -> None:
    assert r.validate_answers(QS, answers) != []


def test_out_of_range_number_is_a_valid_answer_that_fails_not_a_problem() -> None:
    assert r.validate_answers(QS, [a("q1", "yes"), a("q2", 99)]) == []


# ---- failed_questions and result_of ----------------------------------------------------------


def test_no_fails_a_yes_no_question_with_fails_when_no() -> None:
    assert r.failed_questions(QS, [a("q1", "no")]) == ["q1"]
    assert r.failed_questions(QS, [a("q1", "yes")]) == []
    assert r.failed_questions(QS, [a("q1", "na")]) == []


def test_yes_no_without_fails_when_never_fails() -> None:
    assert r.failed_questions([q("q1")], [a("q1", "no")]) == []


@pytest.mark.parametrize(
    ("value", "fails"), [(0, True), (1, False), (5, False), (5.01, True), (3, False)]
)
def test_number_bounds_are_inclusive(value: float, fails: bool) -> None:
    got = r.failed_questions(QS, [a("q1", "yes"), a("q2", value)])
    assert got == (["q2"] if fails else [])


def test_one_sided_range() -> None:
    only_max = [q("q1", "number", max=10, fails_when="out_of_range")]
    assert r.failed_questions(only_max, [a("q1", -50)]) == []
    assert r.failed_questions(only_max, [a("q1", 11)]) == ["q1"]
    only_min = [q("q1", "number", min=10, fails_when="out_of_range")]
    assert r.failed_questions(only_min, [a("q1", 1000)]) == []
    assert r.failed_questions(only_min, [a("q1", 9)]) == ["q1"]


def test_unanswered_question_does_not_fail() -> None:
    assert r.failed_questions(QS, []) == []


def test_failed_ids_follow_question_order_not_answer_order() -> None:
    qs = [q("q1", fails_when="no"), q("q2", fails_when="no"), q("q3", fails_when="no")]
    assert r.failed_questions(qs, [a("q3", "no"), a("q1", "no"), a("q2", "yes")]) == ["q1", "q3"]


def test_result_accept_when_nothing_fails() -> None:
    assert r.result_of(QS, [a("q1", "yes"), a("q2", 3)]) == "accept"


def test_result_reject_when_a_required_question_fails() -> None:
    assert r.result_of(QS, [a("q1", "no")]) == "reject"


def test_result_conditional_when_only_an_optional_question_fails() -> None:
    assert r.result_of(QS, [a("q1", "yes"), a("q2", 9)]) == "conditional"


def test_result_reject_wins_over_conditional() -> None:
    assert r.result_of(QS, [a("q1", "no"), a("q2", 9)]) == "reject"


def test_inputs_are_not_modified() -> None:
    answers = [a("q1", "no"), a("q2", 9)]
    before = [dict(x) for x in answers]
    r.result_of(QS, answers)
    r.failed_questions(QS, answers)
    assert answers == before


def test_bounds_are_the_documented_ones() -> None:
    assert (r.MAX_QUESTIONS, r.MAX_QUESTION_TEXT, r.MAX_CHOICES, r.MAX_ANSWER_TEXT, r.MAX_NOTE) == (
        60,
        200,
        8,
        1000,
        300,
    )
