"""Editor descriptions and value routing of an extension type's form (P0-I8-T25)."""

from __future__ import annotations

import pytest
from fakes import FakeClient
from tl_core.extypes.forms import TypeForm, TypeFormField
from tl_tui.extension_fields import field_meta, sections, split_values

LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"


@pytest.fixture
def fake() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    client.add_example_type(OBSERVATION)
    return client


def _form(fake: FakeClient, type_ref: str) -> TypeForm:
    form = fake.get_type(type_ref).form
    assert form is not None
    return form


def _slot(**changes: object) -> TypeFormField:
    base: dict[str, object] = {
        "name": "crane",
        "path": "psets.p.crane",
        "label": "Crane",
        "description": "The crane",
        "kind": "string",
        "widget": "input",
        "order": 3,
    }
    return TypeFormField.model_validate({**base, **changes})


def test_a_field_becomes_an_editor_description() -> None:
    meta = field_meta(_slot(required=True, help="Tag as on the plate"), "plan")
    assert (meta.path, meta.label, meta.kind, meta.group, meta.order) == (
        "psets.p.crane",
        "Crane",
        "string",
        "plan",
        3,
    )
    assert meta.description == "Tag as on the plate"
    assert meta.enforcement == "required"
    assert meta.layer == "standard" and not meta.readonly


def test_description_stands_in_for_missing_help_and_optional_means_no_enforcement() -> None:
    meta = field_meta(_slot(), "plan")
    assert meta.description == "The crane" and meta.enforcement is None


def test_a_multivalued_slot_is_edited_as_json() -> None:
    assert field_meta(_slot(multivalued=True), "g").kind == "json"


def test_kinds_the_editor_knows_pass_and_others_are_text() -> None:
    for kind in ("string", "text", "int", "decimal", "bool", "date", "datetime", "enum", "ref"):
        assert field_meta(_slot(kind=kind), "g").kind == kind
    assert field_meta(_slot(kind="geometry"), "g").kind == "string"


def test_unit_and_enum_values_come_along(fake: FakeClient) -> None:
    form = _form(fake, "co.acme.LiftPlan@1.0.0")
    risk = next(f for f in form.fields() if f.name == "risk_class")
    meta = field_meta(risk, "plan")
    assert meta.kind == "enum" and meta.enum_values
    assert {v.code for v in meta.enum_values} == {v.code for v in risk.enum_values or []}


def test_sections_follow_the_groups_of_the_form(fake: FakeClient) -> None:
    result = sections(_form(fake, "co.acme.LiftPlan@1.0.0"))
    assert [(s.name, s.label) for s in result] == [
        ("plan", "Lift plan"),
        ("method", "Method and crew"),
    ]
    assert [f.path.rsplit(".", 1)[1] for f in result[0].fields] == [
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
    ]
    assert all(f.group == s.name for s in result for f in s.fields)


def test_sections_skip_a_group_without_fields(fake: FakeClient) -> None:
    form = _form(fake, "co.acme.LiftPlan@1.0.0")
    empty = form.model_copy(
        update={"groups": [*form.groups[:1], form.groups[1].model_copy(update={"fields": []})]}
    )
    assert [s.name for s in sections(empty)] == ["plan"]


def test_an_object_backed_type_keeps_all_values_in_its_body(fake: FakeClient) -> None:
    form = _form(fake, "co.acme.LiftPlan@1.0.0")
    split = split_values(
        form,
        {"crane": "CR-12", "crew": ["A"], "load_tonnes": 4.5, "method_statement": None, "x": 1},
    )
    assert split.psets == {}
    assert split.body == {"crane": "CR-12", "crew": ["A"], "load_tonnes": 4.5}


def test_a_managed_type_keeps_its_values_in_its_pset(fake: FakeClient) -> None:
    form = _form(fake, "co.acme.SafetyObservation@1.0.0")
    split = split_values(form, {"severity": "high", "location": "Unit 3", "narrative": None})
    assert split.body is None
    assert split.psets == {"co_acme_safety_observation": {"severity": "high", "location": "Unit 3"}}
    assert split_values(form, {}).psets == {}
    assert split_values(form, {"unknown": 1}).psets == {}
