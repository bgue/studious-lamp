"""Psets bound to a record by its class (ADR-0010): schema, validation, forms and conformance."""

from __future__ import annotations

from datetime import date
from typing import Any

from tl_schema.conformance import evaluate
from tl_schema.effective import EffectiveSchema
from tl_schema.formgen import form_metadata
from tl_schema.validation import record_json_schema, validate_psets

TODAY = date(2026, 10, 9)
TAG = "engineering.Tag"  # applies_to of no fixture pset: only a class can bring psets to it


def summary(schema: EffectiveSchema, psets: dict[str, Any], **kwargs: Any) -> list[tuple[str, ...]]:
    report = evaluate(schema, TAG, psets, on=TODAY, **kwargs)
    return [(i.path, i.rule, i.level) for i in report.issues]


def test_psets_for_adds_the_bound_psets_to_those_of_the_type(effective: EffectiveSchema) -> None:
    # a tag's own pset is provenance (P1-I3); the bound ones come after it
    assert [p.name for p in effective.psets_for(TAG)] == ["provenance"]
    bound = effective.psets_for(TAG, ["valve_data"])
    assert [p.name for p in bound] == ["provenance", "valve_data"]
    # psets of the type itself keep applying; unknown names are ignored; no duplicates
    plain = [p.name for p in effective.psets_for("core.Record")]
    assert [p.name for p in effective.psets_for("core.Record", ["valve_data", "nope"])] == plain


def test_a_record_with_no_class_is_unchanged(effective: EffectiveSchema) -> None:
    report = evaluate(effective, TAG, {}, on=TODAY)
    assert report.status == "ok" and report.issues == []


def test_a_bound_pset_without_values_is_nonconformant_by_its_enforcement(
    effective: EffectiveSchema,
) -> None:
    report = evaluate(effective, TAG, {}, on=TODAY, bound=["valve_data"])
    assert report.status == "nonconformant"
    assert summary(effective, {}, bound=["valve_data"]) == [
        ("psets.valve_data", "class_required", "nonconformant"),
        ("psets.valve_data.manufacturer", "required_in_state", "warning"),
    ]
    assert report.issues[0].message == (
        "Valve data is required by the record's class and has no values"
    )


def test_a_bound_pset_with_values_reports_only_what_the_state_requires(
    effective: EffectiveSchema,
) -> None:
    psets = {"valve_data": {"manufacturer": "Acme"}}
    assert summary(effective, psets, bound=["valve_data"]) == []
    assert summary(effective, psets, state="Design", bound=["valve_data"]) == [
        ("psets.valve_data.body_material", "required_in_state", "nonconformant"),
        ("psets.valve_data.size_in", "required_in_state", "nonconformant"),
    ]


def test_an_advisory_bound_pset_is_only_a_warning(effective: EffectiveSchema) -> None:
    report = evaluate(effective, TAG, {}, on=TODAY, bound=["prj.shutdown_tie_in"])
    assert report.status == "warning"
    assert [(i.path, i.rule) for i in report.issues] == [
        ("psets.prj.shutdown_tie_in", "class_required")
    ]


def test_bound_values_are_validated_like_any_others(effective: EffectiveSchema) -> None:
    bad = {"valve_data": {"size_in": "wide"}}
    assert validate_psets(effective, TAG, bad) == []  # an unbound pset is not this record's
    issues = validate_psets(effective, TAG, bad, ["valve_data"])
    assert [(i.path, i.keyword) for i in issues] == [("psets.valve_data.size_in", "type")]


def test_the_json_schema_of_a_bound_record_includes_the_bound_psets(
    effective: EffectiveSchema,
) -> None:
    plain = record_json_schema(effective, TAG)
    bound = record_json_schema(effective, TAG, ["valve_data"])
    assert "valve_data" not in plain["properties"]
    assert "valve_data" in bound["properties"]
    # a different bound set is a different cached document; the same one is the same object
    assert record_json_schema(effective, TAG, ["valve_data"]) is bound
    assert record_json_schema(effective, TAG) is plain


def test_the_form_of_a_bound_record_lists_the_bound_psets(effective: EffectiveSchema) -> None:
    assert [g.name for g in form_metadata(effective, TAG).psets] == ["provenance"]
    groups = form_metadata(effective, TAG, ["valve_data"]).psets
    assert [g.name for g in groups] == ["provenance", "valve_data"]
    assert "psets.valve_data.size_in" in [f.path for f in groups[1].fields]
