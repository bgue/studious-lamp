"""Form metadata from an effective schema (P0-I2-T04b). Copied into place by the ticket."""

from __future__ import annotations

from tl_schema.effective import EffectiveSchema
from tl_schema.formgen import form_metadata
from tl_schema.forms import FieldMeta, FormMetadata

RECORD = "core.Record"


def by_path(meta: FormMetadata) -> dict[str, FieldMeta]:
    fields = [*meta.core_fields]
    for group in meta.psets:
        fields.extend(group.fields)
    return {f.path: f for f in fields}


def test_envelope_and_hash(effective: EffectiveSchema) -> None:
    meta = form_metadata(effective, RECORD)
    assert meta.record_type == RECORD
    assert meta.effective_schema_hash == effective.hash
    assert FormMetadata.model_validate(meta.model_dump()) == meta


def test_core_fields(effective: EffectiveSchema) -> None:
    fields = form_metadata(effective, RECORD).core_fields
    assert [f.path for f in fields] == ["title", "description", "key", "status"]
    assert [f.order for f in fields] == [0, 1, 2, 3]
    assert {f.group for f in fields} == {"details"}
    assert {f.layer for f in fields} == {"core"}
    assert [f.readonly for f in fields] == [False, False, True, True]
    assert [f.kind for f in fields] == ["string", "text", "string", "string"]
    assert [f.label for f in fields] == ["Title", "Description", "Key", "Status"]
    assert fields[0].required_in_states == ["*"]
    assert all(f.enforcement is None for f in fields)
    assert all(f.description for f in fields)


def test_groups_list_standard_psets_before_project_psets(effective: EffectiveSchema) -> None:
    meta = form_metadata(effective, RECORD)
    assert [(g.name, g.layer) for g in meta.psets] == [
        ("valve_data", "standard"),
        ("prj.shutdown_tie_in", "project"),
    ]
    valve = meta.psets[0]
    assert (valve.label, valve.package, valve.version) == (
        "Valve data",
        "co.acme.engineering",
        "3.2.0",
    )
    assert valve.enforcement == "required"
    project = meta.psets[1]
    assert (project.package, project.version) == ("prj.P123", "1.0.0")
    assert project.enforcement == "advisory"


def test_fields_in_order_standard_then_custom(effective: EffectiveSchema) -> None:
    valve = form_metadata(effective, RECORD).psets[0]
    assert [f.path for f in valve.fields] == [
        "psets.valve_data.size_in",
        "psets.valve_data.body_material",
        "psets.valve_data.fail_action",
        "psets.valve_data.tag_no",
        "psets.valve_data.manufacturer",
        "psets.valve_data.x.fat_witness_by",
        "psets.valve_data.x.tie_in_window",
    ]
    assert [f.order for f in valve.fields] == list(range(7))
    assert {f.group for f in valve.fields} == {"valve_data"}
    assert [f.layer for f in valve.fields] == ["standard"] * 5 + ["custom"] * 2
    assert not any(f.readonly for f in valve.fields)


def test_a_standard_field(effective: EffectiveSchema) -> None:
    size = by_path(form_metadata(effective, RECORD))["psets.valve_data.size_in"]
    assert size.label == "Nominal size"
    assert size.kind == "decimal"
    assert size.unit == "[in_i]"
    assert size.required_in_states == ["Design", "Installed"]
    assert size.enforcement == "required"
    assert size.enum_values is None
    assert size.description.startswith("Nominal pipe size")


def test_enum_fields_carry_values_and_crosswalks(effective: EffectiveSchema) -> None:
    fields = by_path(form_metadata(effective, RECORD))
    material = fields["psets.valve_data.body_material"]
    assert material.kind == "enum"
    assert material.enum_values is not None
    codes = [(v.code, v.crosswalk) for v in material.enum_values]
    assert codes[0] == ("CS", None)
    assert codes[-1] == ("SS316L-NACE", "SS316L")
    assert material.required_in_states == ["Design"]
    fail = fields["psets.valve_data.fail_action"]
    assert fail.enforcement == "locked"
    assert fail.enum_values is not None
    assert [v.code for v in fail.enum_values] == ["FC", "FO", "FL"]


def test_always_required_property(effective: EffectiveSchema) -> None:
    fields = by_path(form_metadata(effective, RECORD))
    maker = fields["psets.valve_data.manufacturer"]
    assert maker.required_in_states == ["*"]
    assert maker.enforcement == "advisory"


def test_custom_and_project_fields(effective: EffectiveSchema) -> None:
    fields = by_path(form_metadata(effective, RECORD))
    witness = fields["psets.valve_data.x.fat_witness_by"]
    assert witness.layer == "custom"
    assert witness.label == "FAT witness"
    assert witness.enforcement == "advisory"
    window = fields["psets.prj.shutdown_tie_in.window"]
    assert window.layer == "project"
    assert window.group == "prj.shutdown_tie_in"
    approved = fields["psets.prj.shutdown_tie_in.approved"]
    assert approved.kind == "bool"
    assert [f.order for f in form_metadata(effective, RECORD).psets[1].fields] == [0, 1]


def test_a_record_type_without_psets_still_has_core_fields(effective: EffectiveSchema) -> None:
    meta = form_metadata(effective, "piping.Weld")
    assert meta.psets == []
    assert [f.path for f in meta.core_fields] == ["title", "description", "key", "status"]


def test_metadata_is_deterministic(effective: EffectiveSchema) -> None:
    assert form_metadata(effective, RECORD) == form_metadata(effective, RECORD)
