"""The generated form of an extension type (form.yaml hints applied to the compiled class)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_core.extypes.compile import compile_type
from tl_core.extypes.forms import OTHER_GROUP, TypeForm, type_form
from tl_core.extypes.model import CompiledType
from tl_core.extypes.names import parse_type_ref

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types" / "co.acme"


def compiled(name: str) -> CompiledType:
    result, issues = compile_type(
        FIXTURES / name / "1.0.0", parse_type_ref(f"co.acme.{name}@1.0.0"), lint=False
    )
    assert issues == [] and result is not None
    return result


@pytest.fixture(scope="module")
def lift() -> TypeForm:
    return type_form(compiled("LiftPlan"))


@pytest.fixture(scope="module")
def observation() -> TypeForm:
    return type_form(compiled("SafetyObservation"))


def test_groups_follow_form_yaml_in_order(lift: TypeForm) -> None:
    assert [(g.name, g.label) for g in lift.groups] == [
        ("plan", "Lift plan"),
        ("method", "Method and crew"),
    ]
    assert [f.name for f in lift.groups[0].fields] == [
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
    ]
    assert [f.name for f in lift.fields()] == [
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
        "method_statement",
        "crew",
        "exclusion_zone_m",
    ]
    assert [f.order for f in lift.fields()] == list(range(7))


def test_index_fields_have_pset_paths_and_the_rest_have_body_paths(lift: TypeForm) -> None:
    paths = {f.name: f.path for f in lift.fields()}
    assert paths["crane"] == "psets.co_acme_lift_plan.crane"
    assert paths["risk_class"] == "psets.co_acme_lift_plan.risk_class"
    assert paths["method_statement"] == "body.method_statement"
    assert paths["crew"] == "body.crew"
    assert {f.name for f in lift.fields() if f.indexed} == {
        "lift_date",
        "crane",
        "load_tonnes",
        "risk_class",
    }


def test_a_managed_type_has_pset_paths_for_every_field(observation: TypeForm) -> None:
    assert all(f.path.startswith("psets.co_acme_safety_observation.") for f in observation.fields())
    assert observation.storage_mode == "managed"


def test_hints_set_labels_widgets_and_help(lift: TypeForm) -> None:
    crane = lift.field("crane")
    assert crane is not None
    assert crane.label == "Crane" and crane.help == "Tag as on the crane plate, for example CR-12."
    statement = lift.field("method_statement")
    assert statement is not None and statement.widget == "textarea"
    assert statement.kind == "text"


def test_widgets_default_from_the_kind(lift: TypeForm, observation: TypeForm) -> None:
    widgets = {f.name: f.widget for f in lift.fields()}
    assert widgets["lift_date"] == "date"
    assert widgets["risk_class"] == "select"
    assert widgets["load_tonnes"] == "input"
    assert widgets["crew"] == "input"  # a list of text: entered as one value per line by the client
    assert {f.name: f.widget for f in observation.fields()}["narrative"] == "textarea"


def test_field_metadata_comes_from_the_class(lift: TypeForm) -> None:
    load = lift.field("load_tonnes")
    assert load is not None
    assert (load.kind, load.unit, load.minimum, load.maximum, load.required) == (
        "decimal",
        "t",
        0.0,
        1000.0,
        True,
    )
    risk = lift.field("risk_class")
    assert risk is not None and [v.code for v in risk.enum_values or []] == [
        "low",
        "medium",
        "high",
    ]
    crane = lift.field("crane")
    assert crane is not None and crane.pattern == "^[A-Z]{2}-[0-9]{1,4}$"
    crew = lift.field("crew")
    assert crew is not None and crew.multivalued and not crew.required


def test_grid_columns_come_from_form_yaml(lift: TypeForm, observation: TypeForm) -> None:
    assert lift.grid_columns == ["lift_date", "crane", "load_tonnes", "risk_class"]
    assert observation.grid_columns == ["observed_on", "category", "severity", "location"]


def test_slots_form_yaml_does_not_place_go_in_an_other_group(tmp_path: Path) -> None:
    result = compiled("LiftPlan")
    trimmed = result.model_copy(
        update={
            "form": result.form.model_copy(
                update={
                    "groups": result.form.groups[:1],
                    "grid": result.form.grid.model_copy(update={"columns": []}),
                }
            )
        }
    )
    form = type_form(trimmed)
    assert [g.name for g in form.groups] == ["plan", OTHER_GROUP]
    assert [f.name for f in form.groups[1].fields] == [
        "method_statement",
        "crew",
        "exclusion_zone_m",
    ]
    assert form.grid_columns == result.index_fields  # no grid hint: the index fields


def test_a_type_without_form_hints_gets_one_group_named_for_the_type() -> None:
    from tl_core.extypes.model import FormHints

    result = compiled("LiftPlan").model_copy(update={"form": FormHints()})
    form = type_form(result)
    assert [(g.name, g.label) for g in form.groups] == [("fields", "LiftPlan")]
    assert len(form.fields()) == 7


def test_the_form_names_the_type_and_the_schema_it_was_built_from(lift: TypeForm) -> None:
    result = compiled("LiftPlan")
    assert (lift.type_ref, lift.type_name, lift.pset) == (
        "co.acme.LiftPlan@1.0.0",
        "co.acme.LiftPlan",
        "co_acme_lift_plan",
    )
    assert lift.schema_hash == result.schema_hash()
