"""Inspection rules shared by the handler, the CLI and the checklist runner (P2-INSP T00).

Pure functions over plain dicts (the JSON the record stores). No database, no clock. A question is
`{id, text, kind, required, unit, min, max, choices, fails_when}`; an answer is `{q, value, note}`.
Kinds: `yes_no_na`, `number`, `text`, `choice`.

The format 1 question rules are the core validators (`tl_core.forms.rules`, `fmt=1`; P2-FORMS T13)
and are re-exported here under the names T00 callers use. `failed_questions` and `result_of` are
the inspection's own: they carry what a failed answer means for the record.
"""

from __future__ import annotations

from typing import Any, Literal, TypeGuard

from tl_core.forms import rules as _rules
from tl_core.forms import types as _types

MAX_QUESTIONS = _types.MAX_FIELDS
MAX_QUESTION_TEXT = _types.MAX_FIELD_TEXT
MAX_CHOICES = _types.MAX_CHOICES
MAX_ANSWER_TEXT = _types.MAX_ANSWER_TEXT
MAX_NOTE = _types.MAX_NOTE

validate_questions = _rules.validate_questions  # called with the questions only: fmt defaults to 1
validate_answers = _rules.validate_answers  # called with questions and answers only


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fails(question: dict[str, Any], value: Any) -> bool:
    fails_when = question.get("fails_when")
    if fails_when == "no":
        return question.get("kind") == "yes_no_na" and value == "no"
    if fails_when == "out_of_range":
        if question.get("kind") != "number" or not _is_number(value):
            return False
        mn = question.get("min")
        mx = question.get("max")
        if _is_number(mn) and value < mn:
            return True
        if _is_number(mx) and value > mx:
            return True
    return False


def failed_questions(questions: list[dict], answers: list[dict]) -> list[str]:
    """Ids of the questions whose answer fails, in question order. Assumes valid input."""
    by_q = {answer["q"]: answer for answer in answers if isinstance(answer, dict) and "q" in answer}
    failed: list[str] = []
    for question in questions:
        answer = by_q.get(question["id"])
        if answer is None:
            continue
        if _fails(question, answer.get("value")):
            failed.append(question["id"])
    return failed


def result_of(
    questions: list[dict], answers: list[dict]
) -> Literal["accept", "reject", "conditional"]:
    """`reject` when a required question fails, `conditional` when only optional ones fail.

    Otherwise `accept`.
    """
    failed = failed_questions(questions, answers)
    if not failed:
        return "accept"
    required_ids = {question["id"] for question in questions if question.get("required") is True}
    if any(qid in required_ids for qid in failed):
        return "reject"
    return "conditional"
