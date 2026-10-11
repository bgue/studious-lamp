"""Applying form edits to a stored body (P0-I8-T27)."""

from __future__ import annotations

from typing import Any

import pytest
from fakes import FakeClient
from tl_core.extypes.forms import TypeForm
from tl_tui.extension_body import body_values, merged_body

BODY: dict[str, Any] = {
    "crane": "CR-12",
    "crew": ["A. Okafor"],
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "risk_class": "medium",
    "legacy_note": "kept although the form does not show it",
}


@pytest.fixture
def form() -> TypeForm:
    client = FakeClient()
    client.add_example_type("co.acme.LiftPlan")
    detail = client.get_type("co.acme.LiftPlan@1.0.0")
    assert detail.form is not None
    return detail.form


def test_every_slot_of_the_form_has_an_initial_value_or_none(form: TypeForm) -> None:
    values = body_values(form, BODY)
    assert values["crane"] == "CR-12" and values["crew"] == ["A. Okafor"]
    assert values["method_statement"] is None and values["exclusion_zone_m"] is None
    assert set(values) == {slot.name for slot in form.fields()}
    assert "legacy_note" not in values


def test_an_edit_replaces_one_slot_and_keeps_the_rest(form: TypeForm) -> None:
    result = merged_body(form, BODY, {"crane": "CR-14"})
    assert result == {**BODY, "crane": "CR-14"}


def test_none_clears_a_slot(form: TypeForm) -> None:
    result = merged_body(form, BODY, {"crew": None, "method_statement": None})
    assert "crew" not in result and "method_statement" not in result
    assert result["crane"] == "CR-12"


def test_names_that_are_not_slots_are_ignored_but_unknown_body_keys_are_kept(
    form: TypeForm,
) -> None:
    result = merged_body(form, BODY, {"no_such_slot": 1, "legacy_note": None})
    assert result == BODY


def test_the_given_body_is_not_changed(form: TypeForm) -> None:
    before = dict(BODY)
    merged_body(form, BODY, {"crane": "X", "crew": None})
    assert BODY == before


def test_no_edits_give_an_equal_copy(form: TypeForm) -> None:
    result = merged_body(form, BODY, {})
    assert result == BODY and result is not BODY
