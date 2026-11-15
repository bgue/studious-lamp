"""Inspection rules shared by the handler, the CLI and the checklist runner (P2-INSP T00).

Pure functions over plain dicts (the JSON the record stores). No database, no clock, no import
from `tl_core` or any other module. A question is
`{id, text, kind, required, unit, min, max, choices, fails_when}`; an answer is `{q, value, note}`.
Kinds: `yes_no_na`, `number`, `text`, `choice`.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal, TypeGuard

MAX_QUESTIONS = 60
MAX_QUESTION_TEXT = 200
MAX_CHOICES = 8
MAX_ANSWER_TEXT = 1000
MAX_NOTE = 300

KINDS = frozenset({"yes_no_na", "number", "text", "choice"})
QUESTION_FIELDS = frozenset(
    {"id", "text", "kind", "required", "unit", "min", "max", "choices", "fails_when"}
)
ANSWER_FIELDS = frozenset({"q", "value", "note"})
YES_NO_NA = ("yes", "no", "na")

_ID_RE = re.compile(r"q[0-9]+")


def _is_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _label(position: int, question: Any) -> str:
    """The id when it is `q` plus digits, else `question <n>`."""
    qid = question.get("id") if isinstance(question, dict) else None
    if isinstance(qid, str) and _ID_RE.fullmatch(qid):
        return qid
    return f"question {position}"


def _question_problems(position: int, question: Any) -> list[str]:
    if not isinstance(question, dict):
        return [f"question {position}: not an object"]
    label = _label(position, question)
    problems: list[str] = []
    for key in sorted(set(question) - QUESTION_FIELDS, key=str):
        problems.append(f"{label}: unknown field {key}")
    for key in sorted(QUESTION_FIELDS - set(question)):
        problems.append(f"{label}: missing field {key}")

    qid = question.get("id")
    if not (isinstance(qid, str) and _ID_RE.fullmatch(qid)):
        problems.append(f"question {position}: id must be q followed by digits")

    kind = question.get("kind")
    kind_ok = isinstance(kind, str) and kind in KINDS
    if not kind_ok:
        problems.append(f"{label}: bad kind")

    text = question.get("text")
    if not isinstance(text, str):
        problems.append(f"{label}: text must be text")
    elif not text.strip():
        problems.append(f"{label}: text is empty")
    elif len(text) > MAX_QUESTION_TEXT:
        problems.append(f"{label}: text over {MAX_QUESTION_TEXT} characters")

    if not isinstance(question.get("required"), bool):
        problems.append(f"{label}: required must be true or false")

    mn = question.get("min")
    mx = question.get("max")
    for name, bound in (("min", mn), ("max", mx)):
        if bound is not None and not _is_number(bound):
            problems.append(f"{label}: {name} must be a number or null")
    if _is_number(mn) and _is_number(mx) and mn > mx:
        problems.append(f"{label}: min above max")

    fails_when = question.get("fails_when")
    if fails_when is None:
        pass
    elif fails_when == "no":
        if kind != "yes_no_na":
            problems.append(f'{label}: fails_when "no" needs kind yes_no_na')
    elif fails_when == "out_of_range":
        if kind != "number":
            problems.append(f'{label}: fails_when "out_of_range" needs kind number')
        elif mn is None and mx is None:
            problems.append(f'{label}: fails_when "out_of_range" needs min or max')
    else:
        problems.append(f"{label}: fails_when must be no, out_of_range or null")

    choices = question.get("choices")
    if kind == "choice":
        if not isinstance(choices, list) or not choices:
            problems.append(f"{label}: choice needs a non-empty choices list")
        elif len(choices) > MAX_CHOICES:
            problems.append(f"{label}: more than {MAX_CHOICES} choices")
        elif not all(isinstance(c, str) for c in choices):
            problems.append(f"{label}: choices must be text")
        elif len(set(choices)) != len(choices):
            problems.append(f"{label}: duplicate choices")
    elif choices is not None:
        problems.append(f"{label}: choices allowed only on kind choice")
    return problems


def validate_questions(questions: list[dict]) -> list[str]:
    """Problems with a checklist's question list; an empty list means it is publishable."""
    if not isinstance(questions, list):
        return ["questions: must be a list"]
    if not questions:
        return ["questions: at least one question is required"]
    problems: list[str] = []
    if len(questions) > MAX_QUESTIONS:
        problems.append(f"questions: more than {MAX_QUESTIONS}")
    seen: set[str] = set()
    for position, question in enumerate(questions, start=1):
        problems.extend(_question_problems(position, question))
        qid = question.get("id") if isinstance(question, dict) else None
        if isinstance(qid, str):
            if qid in seen:
                problems.append(f"{_label(position, question)}: duplicate id")
            seen.add(qid)
    return problems


def _value_problems(label: str, question: dict[str, Any], value: Any) -> list[str]:
    kind = question.get("kind")
    if kind == "yes_no_na":
        if not (isinstance(value, str) and value in YES_NO_NA):
            return [f"{label}: value must be yes, no or na"]
    elif kind == "number":
        if not _is_number(value) or (isinstance(value, float) and not math.isfinite(value)):
            return [f"{label}: value must be a number"]
    elif kind == "text":
        if not isinstance(value, str):
            return [f"{label}: value must be text"]
        if len(value) > MAX_ANSWER_TEXT:
            return [f"{label}: text over {MAX_ANSWER_TEXT} characters"]
    elif kind == "choice":
        choices = question.get("choices") or []
        if not (isinstance(value, str) and value in choices):
            return [f"{label}: value not in choices"]
    return []


def validate_answers(questions: list[dict], answers: list[dict]) -> list[str]:
    """Problems with answers to a checklist; each starts with the question id (or `answer <n>`)."""
    if not isinstance(answers, list):
        return ["answers: must be a list"]
    by_id: dict[str, dict[str, Any]] = {}
    for question in questions:
        qid = question.get("id") if isinstance(question, dict) else None
        if isinstance(qid, str):
            by_id.setdefault(qid, question)

    problems: list[str] = []
    answered: set[str] = set()
    for position, answer in enumerate(answers, start=1):
        if not isinstance(answer, dict):
            problems.append(f"answer {position}: not an object")
            continue
        aq = answer.get("q")
        label = aq if isinstance(aq, str) else f"answer {position}"
        for key in sorted(set(answer) - ANSWER_FIELDS, key=str):
            problems.append(f"{label}: unknown field {key}")
        for key in sorted(ANSWER_FIELDS - set(answer)):
            problems.append(f"{label}: missing field {key}")
        if not isinstance(aq, str) or aq not in by_id:
            problems.append(f"{label}: unknown question")
            continue
        if aq in answered:
            problems.append(f"{aq}: repeated answer")
            continue
        answered.add(aq)
        problems.extend(_value_problems(aq, by_id[aq], answer.get("value")))
        note = answer.get("note")
        if note is not None:
            if not isinstance(note, str):
                problems.append(f"{aq}: note must be text or null")
            elif len(note) > MAX_NOTE:
                problems.append(f"{aq}: note over {MAX_NOTE} characters")

    for question in questions:
        if not isinstance(question, dict):
            continue
        qid = question.get("id")
        if question.get("required") is True and isinstance(qid, str) and qid not in answered:
            problems.append(f"{qid}: answer required")
    return problems


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
