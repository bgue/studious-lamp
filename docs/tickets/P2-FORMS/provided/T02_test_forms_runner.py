"""Runner model (P2-FORMS T02): one field per step, back, skip, hidden fields, review, confirm."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.forms import rules
from tl_core.forms import runner as rn


def f(fid: str, kind: str = "text", *, required: bool = True, **kw: Any) -> dict[str, Any]:
    """A format 2 field with every key; keyword arguments override."""
    base: dict[str, Any] = {
        "id": fid,
        "text": f"Field {fid}",
        "kind": kind,
        "required": required,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
        "section": None,
        "help": None,
        "visible_when": None,
    }
    base.update(kw)
    return base


FIELDS = [
    f("name", section="Who", help="Full name"),
    f("fit", "choice", choices=["yes", "no"]),
    f("why", visible_when={"q": "fit", "is": "no"}),
    f("extra", required=False),
]


def at(state: rn.RunnerState, fields: list[dict[str, Any]] = FIELDS) -> str | None:
    step = rn.step(state, fields)
    return None if step is None else step.id


def test_start_shows_the_first_field_with_its_numbers_and_texts() -> None:
    state = rn.start(FIELDS)
    step = rn.step(state, FIELDS)
    assert step is not None
    assert (step.id, step.text, step.kind, step.required) == ("name", "Field name", "text", True)
    assert (step.section, step.help, step.value, step.note) == ("Who", "Full name", None, None)
    assert (step.number, step.total) == (1, 3)  # "why" is hidden: three visible fields
    assert state.phase == "fill"


def test_answer_moves_on_and_a_hidden_field_is_skipped() -> None:
    state, problems = rn.answer(rn.start(FIELDS), FIELDS, "Ana")
    assert problems == [] and at(state) == "fit"
    state, problems = rn.answer(state, FIELDS, "yes")
    assert problems == [] and at(state) == "extra"  # "why" is hidden by fit=yes
    step = rn.step(state, FIELDS)
    assert step is not None and (step.number, step.total) == (3, 3)


def test_a_condition_shows_the_field_and_the_total_follows() -> None:
    state, _ = rn.answer(rn.start(FIELDS), FIELDS, "Ana")
    state, _ = rn.answer(state, FIELDS, "no")
    step = rn.step(state, FIELDS)
    assert step is not None and (step.id, step.number, step.total) == ("why", 3, 4)


def test_a_bad_value_is_refused_and_the_state_is_unchanged() -> None:
    start = rn.start(FIELDS)
    state, problems = rn.answer(start, FIELDS, 42)
    assert state == start
    assert problems and all(p.startswith("name:") for p in problems)
    state, problems = rn.answer(rn.answer(start, FIELDS, "Ana")[0], FIELDS, "maybe")
    assert at(state) == "fit" and problems


def test_skip_is_for_optional_fields_only() -> None:
    start = rn.start(FIELDS)
    state, problems = rn.skip(start, FIELDS)
    assert state == start and problems == ["name: answer required"]
    last = rn.answer(rn.answer(start, FIELDS, "Ana")[0], FIELDS, "yes")[0]
    state, problems = rn.skip(last, FIELDS)
    assert problems == [] and state.phase == "review" and at(state) is None


def test_back_returns_to_the_previous_visible_field_and_keeps_the_answer() -> None:
    state, _ = rn.answer(rn.start(FIELDS), FIELDS, "Ana")
    state, _ = rn.answer(state, FIELDS, "yes")
    state = rn.back(state, FIELDS)
    assert at(state) == "fit"  # "why" is hidden, so back skips it
    step = rn.step(state, FIELDS)
    assert step is not None and step.value == "yes"
    assert at(rn.back(rn.back(state, FIELDS), FIELDS)) == "name"  # stays at the first field


def test_back_from_review_returns_to_the_last_visible_field() -> None:
    state, _ = rn.answer(rn.start(FIELDS), FIELDS, "Ana")
    state, _ = rn.answer(state, FIELDS, "yes")
    state, _ = rn.skip(state, FIELDS)
    assert state.phase == "review"
    assert at(rn.back(state, FIELDS)) == "extra"


def test_changing_an_answer_that_hides_a_field_drops_its_answer() -> None:
    state, _ = rn.answer(rn.start(FIELDS), FIELDS, "Ana")
    state, _ = rn.answer(state, FIELDS, "no")
    state, _ = rn.answer(state, FIELDS, "Late")  # why
    state = rn.back(rn.back(state, FIELDS), FIELDS)  # at "fit"
    assert at(state) == "fit"
    state, _ = rn.answer(state, FIELDS, "yes")
    state, _ = rn.skip(state, FIELDS)
    assert [line.id for line in rn.review(state, FIELDS).lines] == ["name", "fit", "extra"]
    assert [a["q"] for a in rn.confirm(state, FIELDS)] == ["name", "fit"]


def test_review_lists_visible_fields_in_order_and_names_missing_required() -> None:
    state = rn.start(FIELDS, answers=[{"q": "fit", "value": "yes"}])
    state = rn.RunnerState(state.fmt, state.values, state.notes, None, "review")
    view = rn.review(state, FIELDS)
    assert [(line.id, line.value) for line in view.lines] == [
        ("name", None),
        ("fit", "yes"),
        ("extra", None),
    ]
    assert view.missing == ("name",)
    with pytest.raises(rn.RunnerError) as err:
        rn.confirm(state, FIELDS)
    assert err.value.problems == ["name: answer required"]


def test_confirm_returns_answers_that_validate_in_field_order() -> None:
    state = rn.start(FIELDS)
    for value in ("Ana", "yes"):
        state, _ = rn.answer(state, FIELDS, value)
    state, _ = rn.answer(state, FIELDS, "n/a", note="checked")
    answers = rn.confirm(state, FIELDS)
    assert answers == [
        {"q": "name", "value": "Ana"},
        {"q": "fit", "value": "yes"},
        {"q": "extra", "value": "n/a", "note": "checked"},
    ]
    assert rules.validate_answers(FIELDS, answers, fmt=2) == []


def test_confirm_before_the_end_is_refused() -> None:
    with pytest.raises(rn.RunnerError) as err:
        rn.confirm(rn.start(FIELDS), FIELDS)
    assert err.value.problems == ["not finished"]


def test_resume_prefills_values_and_prunes_hidden_ones() -> None:
    saved = [
        {"q": "name", "value": "Ana"},
        {"q": "fit", "value": "yes"},
        {"q": "why", "value": "stale"},
    ]
    state = rn.start(FIELDS, answers=saved)
    assert at(state) == "name"
    step = rn.step(state, FIELDS)
    assert step is not None and step.value == "Ana"
    assert "why" not in state.values


def test_format_one_answers_carry_a_note_key() -> None:
    q = [
        {
            "id": "q1",
            "text": "Guard fitted?",
            "kind": "yes_no_na",
            "required": True,
            "unit": None,
            "min": None,
            "max": None,
            "choices": None,
            "fails_when": None,
        }
    ]
    state, problems = rn.answer(rn.start(q, fmt=1), q, "yes")
    assert problems == []
    answers = rn.confirm(state, q)
    assert answers == [{"q": "q1", "value": "yes", "note": None}]
    assert rules.validate_answers(q, answers, fmt=1) == []


def test_inputs_are_not_mutated_and_an_empty_form_goes_straight_to_review() -> None:
    fields = [dict(x) for x in FIELDS]
    saved = [{"q": "name", "value": "Ana"}]
    before = (repr(fields), repr(saved))
    rn.answer(rn.start(fields, answers=saved), fields, "Bo")
    assert (repr(fields), repr(saved)) == before
    empty = rn.start([])
    assert empty.phase == "review" and rn.step(empty, []) is None
    assert rn.confirm(empty, []) == []
