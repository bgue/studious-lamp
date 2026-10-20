"""``${binding}`` placeholders: checked at authoring, filled with ``Template`` and nothing else."""

from __future__ import annotations

from typing import Any

import pytest
from tl_core.integration.contract import (
    RULE_BINDINGS,
    RULE_MAX_ARGS_BYTES,
    RULE_MAX_BINDING_CHARS,
)
from tl_core.integration.rules.placeholders import MAX_NODES, check_template, substitute

BINDINGS = {name: f"<{name}>" for name in RULE_BINDINGS}


def codes(args: dict[str, Any]) -> list[str]:
    return [p.code for p in check_template(args)]


def test_every_documented_binding_is_accepted() -> None:
    args = {"body": " ".join(f"${{{name}}}" for name in sorted(RULE_BINDINGS))}
    assert check_template(args) == []


def test_a_name_that_is_not_a_binding_is_refused_at_authoring() -> None:
    assert codes({"body": "${nope}"}) == ["unknown_binding"]
    assert codes({"body": "$nope"}) == ["unknown_binding"]
    assert codes({"body": "${__class__}"}) == ["unknown_binding"]
    assert codes({"body": "${event_id.__class__}"}) in (["bad_placeholder"], ["unknown_binding"])


def test_a_lone_dollar_is_refused_and_two_are_a_dollar() -> None:
    assert codes({"body": "costs $5"}) == ["bad_placeholder"]
    assert codes({"body": "costs $$5"}) == []
    assert substitute({"body": "costs $$5"}, BINDINGS)[0] == {"body": "costs $5"}


def test_placeholders_are_found_in_nested_values_and_not_in_names() -> None:
    assert codes({"a": [{"b": "${nope}"}]}) == ["unknown_binding"]
    assert codes({"${nope}": "fine"}) == []


def test_substitution_fills_strings_at_any_depth_and_leaves_other_values() -> None:
    args = {"a": "k=${subject_key}", "b": [1, True, None, {"c": "${event_type}!"}], "n": 3}
    out, problem = substitute(args, BINDINGS)
    assert problem is None
    assert out == {
        "a": "k=<subject_key>",
        "b": [1, True, None, {"c": "<event_type>!"}],
        "n": 3,
    }
    assert args["a"] == "k=${subject_key}", "the rule's own arguments are not changed"


def test_a_bound_value_is_inserted_once_and_never_read_again() -> None:
    bindings = {**BINDINGS, "subject_title": "${event_actor} and $subject_key"}
    out, _ = substitute({"body": "${subject_title}"}, bindings)
    assert out == {"body": "${event_actor} and $subject_key"}


def test_there_is_no_attribute_access_or_formatting() -> None:
    bindings = {**BINDINGS, "subject_key": "K-1"}
    out, _ = substitute({"body": "{subject_key.__class__} {0} ${subject_key}"}, bindings)
    assert out == {"body": "{subject_key.__class__} {0} K-1"}


def test_a_value_too_long_refuses_the_step_and_nothing_is_cut() -> None:
    bindings = {**BINDINGS, "subject_title": "t" * (RULE_MAX_BINDING_CHARS + 1)}
    out, problem = substitute({"body": "${subject_title}"}, bindings)
    assert problem is not None and problem.code == "binding_too_long"
    assert out == {"body": "${subject_title}"}
    exact = {**BINDINGS, "subject_title": "t" * RULE_MAX_BINDING_CHARS}
    assert substitute({"body": "${subject_title}"}, exact)[1] is None


def test_arguments_that_grow_past_the_limit_are_refused() -> None:
    half = RULE_MAX_ARGS_BYTES // 2 + 100
    args = {"a": "${subject_key}" * 1, "b": "x" * half}
    bindings = {**BINDINGS, "subject_key": "k" * 900}
    many = {f"f{n}": "${subject_key}" for n in range(30)}
    assert substitute(args, bindings)[1] is None
    out, problem = substitute(many, bindings)
    assert problem is not None and problem.code == "args_too_large"
    assert out == many


def test_stored_arguments_over_the_limit_are_refused_at_authoring() -> None:
    assert codes({"body": "x" * (RULE_MAX_ARGS_BYTES + 1)}) == ["args_too_large"]


def test_arguments_too_deep_or_too_wide_are_refused_not_walked_forever() -> None:
    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(60):
        nested: dict[str, object] = {}
        cursor["x"] = nested
        cursor = nested
    assert codes(deep) == ["args_too_large"]
    assert substitute(deep, BINDINGS)[1] is not None
    wide = {"items": ["a"] * (MAX_NODES + 1)}
    assert codes(wide) == ["args_too_large"]


@pytest.mark.parametrize("text", ["${subject_key}", "$subject_key", "a ${event_id} b"])
def test_the_two_forms_of_a_name_both_work(text: str) -> None:
    out, problem = substitute({"body": text}, BINDINGS)
    assert problem is None and "<" in out["body"]
