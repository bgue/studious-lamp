"""Guards on the forms rules: bounded recursion, malformed input, format 1 key parity."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.forms import rules as r
from tl_core.forms.registry import FormSourceLoadError, load_form_sources
from tl_core.forms.types import MAX_SOURCES


def q1(qid: str = "q1", **kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": qid,
        "text": "t",
        "kind": "yes_no_na",
        "required": False,
        "unit": None,
        "min": None,
        "max": None,
        "choices": None,
        "fails_when": None,
    }
    base.update(kw)
    return base


def q2(qid: str, **kw: Any) -> dict[str, Any]:
    return {**q1(qid), "section": None, "help": None, "visible_when": None, **kw}


def deep_not(levels: int) -> dict[str, Any]:
    node: dict[str, Any] = {"q": "a", "answered": True}
    for _ in range(levels):
        node = {"not": node}
    return node


def deep_form(levels: int) -> list[dict[str, Any]]:
    return [q2("a"), q2("b", visible_when=deep_not(levels))]


def test_a_very_deep_condition_is_a_problem_not_an_exception() -> None:
    problems = r.validate_questions(deep_form(2000), fmt=2)
    assert any("nested deeper" in p for p in problems)


def test_the_depth_limit_is_three_combinators() -> None:
    assert r.validate_questions(deep_form(3), fmt=2) == []
    assert any("nested deeper" in p for p in r.validate_questions(deep_form(4), fmt=2))


def test_a_very_deep_condition_does_not_break_visibility_or_answers() -> None:
    fields = deep_form(2000)
    answers = [{"q": "a", "value": "yes", "note": None}]
    assert r.visible_ids(fields, answers) == ["a"]
    assert r.validate_answers(fields, answers, fmt=2) == []


@pytest.mark.parametrize("bad", [None, "x", {"q": "q1"}, 3])
def test_answers_that_are_not_a_list(bad: Any) -> None:
    assert r.validate_answers([q1()], bad) == ["answers: must be a list"]
    assert r.visible_ids([q1()], bad) == ["q1"]


def test_fields_without_a_text_id_are_skipped() -> None:
    fields: list[Any] = ["x", None, {"text": "no id"}, {"id": 5}, q1()]
    ans = [{"q": "q1", "value": "yes", "note": None}]
    assert r.visible_ids(fields, ans) == ["q1"]
    assert r.validate_answers(fields, ans) == []
    assert r.intake_problems(fields, purpose="x", accepts_as=["SubmitForm"]) != []


def test_format1_answers_need_all_three_keys() -> None:
    for key in ("q", "value", "note"):
        ans = {"q": "q1", "value": "yes", "note": None}
        del ans[key]
        assert r.validate_answers([q1()], [ans], partial=True) != []
    ok = {"q": "q1", "value": "yes", "note": None}
    assert r.validate_answers([q1()], [ok]) == []
    assert any(
        "missing key 'note'" in p for p in r.validate_answers([q1()], [{"q": "q1", "value": "yes"}])
    )


def test_a_duplicate_id_is_flagged_even_when_the_id_is_malformed() -> None:
    problems = r.validate_questions([q1("bad"), q1("bad")])
    assert any("duplicate id" in p for p in problems)


class Boom:
    name = "a"

    def load(self) -> Any:
        raise AssertionError("must not load")


def test_too_many_sources_are_refused_before_any_is_loaded() -> None:
    entries = [Boom() for _ in range(MAX_SOURCES + 1)]
    with pytest.raises(FormSourceLoadError, match="more than"):
        load_form_sources(entries)  # type: ignore[arg-type]
