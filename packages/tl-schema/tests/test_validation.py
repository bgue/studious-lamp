"""JSON Schema and validator for psets (P0-I2-T04). Copied into place by the ticket; do not edit."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tl_schema.effective import EffectiveSchema
from tl_schema.validation import ValueIssue, record_json_schema, validate_psets

RECORD = "core.Record"


def paths(issues: list[ValueIssue]) -> list[tuple[str, str]]:
    return [(i.path, i.keyword) for i in issues]


# --- the generated schema ----------------------------------------------------------------------


def test_schema_is_valid_draft_2020_12_and_names_the_hash(effective: EffectiveSchema) -> None:
    document = record_json_schema(effective, RECORD)
    Draft202012Validator.check_schema(document)
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["$id"] == f"urn:tl:effective:{effective.hash}:{RECORD}"
    assert document["type"] == "object"
    assert document["additionalProperties"] is True


def test_schema_has_one_object_per_pset(effective: EffectiveSchema) -> None:
    document = record_json_schema(effective, RECORD)
    assert sorted(document["properties"]) == ["prj", "valve_data"]
    valve = document["properties"]["valve_data"]
    assert valve["type"] == "object"
    assert valve["additionalProperties"] is False
    assert list(valve["properties"]) == [
        "size_in",
        "body_material",
        "fail_action",
        "tag_no",
        "manufacturer",
        "x",
    ]
    custom = valve["properties"]["x"]
    assert list(custom["properties"]) == ["fat_witness_by", "tie_in_window"]
    assert custom["additionalProperties"] is False
    project = document["properties"]["prj"]
    assert list(project["properties"]) == ["shutdown_tie_in"]
    assert project["additionalProperties"] is False


def test_property_schemas_follow_the_kind(effective: EffectiveSchema) -> None:
    props = record_json_schema(effective, RECORD)["properties"]["valve_data"]["properties"]
    assert props["size_in"]["type"] == "number"
    assert props["size_in"]["minimum"] == 0.25
    assert props["size_in"]["maximum"] == 144
    assert props["size_in"]["x-unit"] == "[in_i]"
    assert props["size_in"]["title"] == "Nominal size"
    assert props["size_in"]["description"].startswith("Nominal pipe size")
    assert props["body_material"]["type"] == "string"
    assert props["body_material"]["enum"] == [
        "CS",
        "SS304",
        "SS316L",
        "DUPLEX",
        "other",
        "SS316L-NACE",
    ]
    assert props["tag_no"]["pattern"] == "^[A-Z]{1,3}-[0-9]{3,5}$"
    assert props["manufacturer"]["type"] == "string"
    assert "minimum" not in props["manufacturer"]
    approved = record_json_schema(effective, RECORD)["properties"]["prj"]["properties"]
    assert approved["shutdown_tie_in"]["properties"]["approved"]["type"] == "boolean"


def test_schema_for_a_record_type_without_psets_accepts_anything_at_the_root(
    effective: EffectiveSchema,
) -> None:
    document = record_json_schema(effective, "piping.Weld")
    assert document["properties"] == {}
    assert validate_psets(effective, "piping.Weld", {"anything": {"goes": 1}}) == []


def test_schema_is_cached_by_hash(effective: EffectiveSchema) -> None:
    assert record_json_schema(effective, RECORD) is record_json_schema(effective, RECORD)
    copy_of = effective.model_copy()
    assert record_json_schema(copy_of, RECORD) is record_json_schema(effective, RECORD)


def test_other_kinds_map_as_documented(effective: EffectiveSchema) -> None:
    # Build a schema with one property per remaining kind by editing a copy of the valve pset.
    data: dict[str, Any] = copy.deepcopy(effective.model_dump(mode="json"))
    template = data["psets"]["valve_data"]["properties"]["manufacturer"]
    extra: dict[str, Any] = {}
    for kind in ("text", "int", "decimal", "bool", "date", "datetime", "quantity", "ref", "json"):
        prop = copy.deepcopy(template)
        prop.update({"name": f"k_{kind}", "kind": kind, "pattern": None, "unit": None})
        extra[f"k_{kind}"] = prop
    data["psets"]["valve_data"]["properties"] = extra
    data["hash"] = "kinds"
    schema = EffectiveSchema.model_validate(data)
    props = record_json_schema(schema, RECORD)["properties"]["valve_data"]["properties"]
    assert props["k_text"]["type"] == "string"
    assert props["k_int"]["type"] == "integer"
    assert props["k_decimal"]["type"] == "number"
    assert props["k_quantity"]["type"] == "number"
    assert props["k_bool"]["type"] == "boolean"
    assert props["k_ref"]["type"] == "string"
    assert props["k_date"]["pattern"] == r"^\d{4}-\d{2}-\d{2}$"
    assert "type" in props["k_datetime"] and "pattern" in props["k_datetime"]
    assert "type" not in props["k_json"]
    ok = {"valve_data": {"k_date": "2026-10-09", "k_datetime": "2026-10-09T12:30:00Z"}}
    assert validate_psets(schema, RECORD, ok) == []
    bad = {"valve_data": {"k_date": "09/10/2026"}}
    assert paths(validate_psets(schema, RECORD, bad)) == [("psets.valve_data.k_date", "pattern")]
    json_any = {"valve_data": {"k_json": {"nested": [1, 2, {"a": None}]}}}
    assert validate_psets(schema, RECORD, json_any) == []


# --- the validator -----------------------------------------------------------------------------


def test_valid_values_give_no_issues(effective: EffectiveSchema) -> None:
    psets = {
        "valve_data": {
            "size_in": 4,
            "body_material": "SS316L-NACE",
            "fail_action": "FC",
            "tag_no": "FV-1001",
            "manufacturer": "Acme Valves",
            "x": {"fat_witness_by": "client", "tie_in_window": "SD-1"},
        },
        "prj": {"shutdown_tie_in": {"window": "SD-2027-03", "approved": True}},
    }
    assert validate_psets(effective, RECORD, psets) == []
    assert validate_psets(effective, RECORD, {}) == []


def test_unknown_root_keys_are_allowed(effective: EffectiveSchema) -> None:
    psets = {"enrich": {"ai_classifier": {"valve_type": "ball"}}, "src": {"ifc": {"A": 1}}}
    assert validate_psets(effective, RECORD, psets) == []


def test_type_errors(effective: EffectiveSchema) -> None:
    psets = {
        "valve_data": {"size_in": "four", "manufacturer": 7, "x": {"fat_witness_by": False}},
        "prj": {"shutdown_tie_in": {"approved": "yes"}},
    }
    assert paths(validate_psets(effective, RECORD, psets)) == [
        ("psets.prj.shutdown_tie_in.approved", "type"),
        ("psets.valve_data.manufacturer", "type"),
        ("psets.valve_data.size_in", "type"),
        ("psets.valve_data.x.fat_witness_by", "type"),
    ]


def test_a_boolean_is_not_a_number(effective: EffectiveSchema) -> None:
    issues = validate_psets(effective, RECORD, {"valve_data": {"size_in": True}})
    assert paths(issues) == [("psets.valve_data.size_in", "type")]


def test_range_pattern_and_enum_errors(effective: EffectiveSchema) -> None:
    psets = {
        "valve_data": {
            "size_in": 0.1,
            "tag_no": "bad tag",
            "body_material": "UNOBTAINIUM",
            "fail_action": "XX",
        }
    }
    assert paths(validate_psets(effective, RECORD, psets)) == [
        ("psets.valve_data.body_material", "enum"),
        ("psets.valve_data.fail_action", "enum"),
        ("psets.valve_data.size_in", "minimum"),
        ("psets.valve_data.tag_no", "pattern"),
    ]
    over = validate_psets(effective, RECORD, {"valve_data": {"size_in": 500}})
    assert paths(over) == [("psets.valve_data.size_in", "maximum")]


def test_unknown_properties_are_reported_one_per_key(effective: EffectiveSchema) -> None:
    psets = {
        "valve_data": {"nope": 1, "size_in": 4, "x": {"other": 2, "fat_witness_by": "c"}},
        "prj": {"shutdown_tie_in": {"zzz": 1}, "another_pset": {"a": 1}},
    }
    issues = validate_psets(effective, RECORD, psets)
    assert paths(issues) == [
        ("psets.prj.another_pset", "additionalProperties"),
        ("psets.prj.shutdown_tie_in.zzz", "additionalProperties"),
        ("psets.valve_data.nope", "additionalProperties"),
        ("psets.valve_data.x.other", "additionalProperties"),
    ]
    assert "nope" in issues[2].message


def test_a_pset_that_is_not_an_object(effective: EffectiveSchema) -> None:
    issues = validate_psets(effective, RECORD, {"valve_data": 5})
    assert paths(issues) == [("psets.valve_data", "type")]


def test_issues_are_sorted_and_deterministic(effective: EffectiveSchema) -> None:
    psets = {"valve_data": {"tag_no": "x", "size_in": "y", "nope": 1}}
    first = validate_psets(effective, RECORD, psets)
    assert first == validate_psets(effective, RECORD, psets)
    assert paths(first) == sorted(paths(first))


def test_a_custom_section_is_unknown_when_the_pset_has_none(
    effective: EffectiveSchema,
) -> None:
    data: dict[str, Any] = effective.model_dump(mode="json")
    data["psets"]["valve_data"]["custom"] = {}
    data["hash"] = "no-custom"
    schema = EffectiveSchema.model_validate(data)
    issues = validate_psets(schema, RECORD, {"valve_data": {"x": {"fat_witness_by": "c"}}})
    assert paths(issues) == [("psets.valve_data.x", "additionalProperties")]


@pytest.mark.parametrize("record_type", ["core.Record"])
def test_validation_does_not_mutate_its_input(effective: EffectiveSchema, record_type: str) -> None:
    psets: dict[str, Any] = {"valve_data": {"size_in": 4, "x": {"fat_witness_by": "c"}}}
    before = copy.deepcopy(psets)
    validate_psets(effective, record_type, psets)
    assert psets == before
