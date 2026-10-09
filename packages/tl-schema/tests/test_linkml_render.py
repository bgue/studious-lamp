"""The LinkML rendering of an effective schema: pset classes merged into core (brief 27.3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tl_schema.compose import compose
from tl_schema.linkml_render import build_view, linkml_yaml, pascal
from tl_schema.packages import PackageDoc

Build = Callable[..., list[PackageDoc]]


def test_pascal() -> None:
    assert pascal("valve_data") == "ValveData"
    assert pascal("prj.shutdown_tie_in") == "PrjShutdownTieIn"
    assert pascal("core.Record") == "CoreRecord"


def test_pset_classes_merge_into_core(build_docs: Build) -> None:
    view: Any = build_view(compose(build_docs(), "project:P123"))
    classes = set(view.all_classes())
    assert {"Record", "Event", "ValveData", "ValveData_P123_x", "PrjShutdownTieIn"} <= classes
    assert {"CoreRecordPsets", "CoreRecordProjectPsets"} <= classes
    assert {"MaterialCode", "FailAction", "ConformanceStatus"} <= set(view.all_enums())


def test_record_psets_slot_points_at_the_container(build_docs: Build) -> None:
    view: Any = build_view(compose(build_docs(), "project:P123"))
    assert view.induced_slot("psets", "Record").range == "CoreRecordPsets"
    container = {s.name: s.range for s in view.class_induced_slots("CoreRecordPsets")}
    assert container == {"valve_data": "ValveData", "prj": "CoreRecordProjectPsets"}


def test_slots_carry_constraints_and_annotations(build_docs: Build) -> None:
    view: Any = build_view(compose(build_docs(), "project:P123"))
    size = view.induced_slot("size_in", "ValveData")
    assert size.range == "decimal"
    assert (size.minimum_value, size.maximum_value) == (0.25, 144)
    assert size.unit.ucum_code == "[in_i]"
    assert size.annotations["tl:enforcement"].value == "required"
    assert size.annotations["tl:materialize"].value is True
    manufacturer = view.induced_slot("manufacturer", "ValveData")
    assert manufacturer.required is True
    assert view.induced_slot("tag_no", "ValveData").pattern == "^[A-Z]{1,3}-[0-9]{3,5}$"
    assert view.induced_slot("x", "ValveData").range == "ValveData_P123_x"
    assert view.induced_slot("fat_witness_by", "ValveData_P123_x").range == "string"


def test_project_values_keep_their_crosswalk(build_docs: Build) -> None:
    view: Any = build_view(compose(build_docs(), "project:P123"))
    values = view.get_enum("MaterialCode").permissible_values
    assert "SS316L-NACE" in values
    assert values["SS316L-NACE"].annotations["tl:crosswalk"].value == "SS316L"
    assert set(view.get_enum("FailAction").permissible_values) == {"FC", "FO", "FL"}


def test_company_scope_has_no_custom_classes(build_docs: Build) -> None:
    company = [d for d in build_docs() if d.kind == "company"]
    view: Any = build_view(compose(company, "company"))
    classes = set(view.all_classes())
    assert "ValveData" in classes and "SafetyData" in classes
    assert not any(name.endswith("_x") for name in classes)


def test_yaml_is_deterministic_and_carries_the_hash(build_docs: Build) -> None:
    schema = compose(build_docs(), "project:P123")
    text = linkml_yaml(schema)
    assert text == linkml_yaml(schema)
    assert schema.hash in text
