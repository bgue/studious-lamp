"""Pset compilation: what projects can do, and every rule they cannot break (brief 6.3)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError
from tl_schema.compile import SchemaCompileError, compile_psets
from tl_schema.effective import states_cover
from tl_schema.packages import PackageDoc

Build = Callable[..., list[PackageDoc]]
Raw = dict[str, dict[str, Any]]


def _entry(raw: Raw) -> dict[str, Any]:
    entry: dict[str, Any] = raw["x.P123"]["extends"][0]
    return entry


def _valve(raw: Raw) -> dict[str, Any]:
    props: dict[str, Any] = raw["co.acme.engineering"]["psets"]["valve_data"]["properties"]
    return props


def _expect(build: Build, mutate: Callable[[Raw], None], rule: str) -> SchemaCompileError:
    with pytest.raises(SchemaCompileError) as caught:
        compile_psets(build(mutate))
    assert caught.value.rule == rule, str(caught.value)
    return caught.value


def test_fixtures_compile_into_three_layers(build_docs: Build) -> None:
    psets = compile_psets(build_docs())
    assert list(psets) == ["prj.shutdown_tie_in", "safety_data", "valve_data"]
    valve = psets["valve_data"]
    assert valve.layer == "standard"
    assert valve.extension == "x.P123@1.4.0"
    assert list(valve.properties) == [
        "size_in",
        "body_material",
        "fail_action",
        "tag_no",
        "manufacturer",
    ]
    assert list(valve.custom) == ["fat_witness_by", "tie_in_window"]
    assert valve.custom["fat_witness_by"].layer == "custom"
    assert valve.custom["fat_witness_by"].relative_key() == "x.fat_witness_by"
    assert valve.find("x.tie_in_window") is valve.custom["tie_in_window"]
    assert valve.find("size_in") is valve.properties["size_in"]
    assert valve.find("nope") is None
    assert psets["prj.shutdown_tie_in"].layer == "project"


def test_resolved_property_details(build_docs: Build) -> None:
    valve = compile_psets(build_docs())["valve_data"]
    size = valve.properties["size_in"]
    assert (size.kind, size.unit, size.enforcement) == ("decimal", "[in_i]", "required")
    assert size.required_in_states == ["Design", "Installed"]
    assert size.materialize is True
    assert (size.minimum, size.maximum) == (0.25, 144)
    material = valve.properties["body_material"]
    assert material.kind == "enum"
    assert material.value_list_policy == "extensible"
    assert material.required_in_states == ["Design"]  # tightened by the project
    assert valve.properties["fail_action"].enforcement == "locked"  # property beats pset
    assert valve.properties["manufacturer"].required_in_states == ["*"]
    assert valve.properties["manufacturer"].enforcement == "advisory"
    assert [p.order for p in valve.all_properties()] == list(range(7))
    assert valve.custom_allowed and valve.custom_max == 10


def test_locked_pset_has_no_custom_section(build_docs: Build) -> None:
    safety = compile_psets(build_docs())["safety_data"]
    assert safety.custom_allowed is False
    assert safety.enforcement == "locked"
    assert safety.properties["sil_rating"].enforcement == "locked"


# --- projects can ----------------------------------------------------------------------------


def test_can_add_crosswalked_values_to_an_extensible_list(build_docs: Build) -> None:
    material = compile_psets(build_docs())["valve_data"].properties["body_material"]
    assert material.enum_values is not None
    added = [v for v in material.enum_values if v.code == "SS316L-NACE"]
    assert [(v.label, v.crosswalk) for v in added] == [("316L NACE MR0175", "SS316L")]


def test_can_crosswalk_to_other(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["add_values"]["MaterialCode"][0]["crosswalk"] = "other"

    compile_psets(build_docs(mutate))


def test_can_own_a_project_defined_list_outright(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _valve(raw)["body_material"]["value_list_policy"] = "project_defined"
        _entry(raw)["add_values"]["MaterialCode"] = [
            {"code": "INCONEL", "label": "Inconel 625"},
            {"code": "SS316L-NACE", "label": "316L NACE", "crosswalk": "SS316L"},
        ]

    material = compile_psets(build_docs(mutate))["valve_data"].properties["body_material"]
    assert material.enum_values is not None
    assert {"INCONEL", "SS316L-NACE"} <= {v.code for v in material.enum_values}


def test_can_define_a_project_list_for_a_custom_property(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["code_lists"] = {
            "WitnessParty": {
                "description": "Who witnesses factory tests on P123.",
                "value_list_policy": "project_defined",
                "values": [{"code": "CLIENT", "label": "Client"}, {"code": "TPI", "label": "TPI"}],
            }
        }
        _entry(raw)["custom"]["fat_witness_by"]["range"] = "WitnessParty"

    custom = compile_psets(build_docs(mutate))["valve_data"].custom["fat_witness_by"]
    assert custom.kind == "enum"
    assert custom.enum_values is not None
    assert [v.code for v in custom.enum_values] == ["CLIENT", "TPI"]
    assert custom.value_list_policy == "project_defined"


def test_can_tighten_required_states_and_narrow_ranges(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {
            "required_in_states": ["Design", "Installed", "Commissioned"],
            "minimum": 1,
            "maximum": 48,
        }
        _entry(raw)["tighten"]["tag_no"] = {"enforcement": "required"}
        _entry(raw)["tighten"]["manufacturer"] = {"enforcement": "required"}

    valve = compile_psets(build_docs(mutate))["valve_data"]
    size = valve.properties["size_in"]
    assert size.required_in_states == ["Design", "Installed", "Commissioned"]
    assert (size.minimum, size.maximum) == (1, 48)
    assert valve.properties["tag_no"].enforcement == "required"
    assert valve.properties["manufacturer"].enforcement == "required"


def test_can_add_a_pattern_where_the_company_has_none(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["manufacturer"] = {"pattern": "^[A-Za-z ]+$"}

    valve = compile_psets(build_docs(mutate))["valve_data"]
    assert valve.properties["manufacturer"].pattern == "^[A-Za-z ]+$"


def test_can_set_defaults_and_labels(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["defaults"] = {"size_in": 4, "body_material": "CS"}
        _entry(raw)["labels"] = {"size_in": "NPS (in)"}

    valve = compile_psets(build_docs(mutate))["valve_data"]
    assert valve.properties["size_in"].default == 4
    assert valve.properties["body_material"].default == "CS"
    assert valve.properties["size_in"].label == "NPS (in)"


def test_can_create_project_psets_bound_to_any_record_type(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["prj.P123"]["psets"]["shutdown_tie_in"]["applies_to"] = ["piping.Weld", "core.Record"]

    pset = compile_psets(build_docs(mutate))["prj.shutdown_tie_in"]
    assert pset.applies_to == ["piping.Weld", "core.Record"]
    assert pset.custom_allowed is False


# --- projects cannot -------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["remove", "rename", "rename_to", "range", "unit", "description"])
def test_cannot_remove_rename_or_redefine_a_company_property(build_docs: Build, key: str) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {key: "anything"}

    with pytest.raises(ValidationError):
        build_docs(mutate)


@pytest.mark.parametrize("key", ["remove", "rename", "properties"])
def test_cannot_use_unknown_extension_keys(build_docs: Build, key: str) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)[key] = {"size_in": "x"}

    with pytest.raises(ValidationError):
        build_docs(mutate)


def test_cannot_shadow_a_company_property_with_a_custom_one(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["custom"]["size_in"] = {"description": "my own size", "range": "string"}

    _expect(build_docs, mutate, "shadow")


def test_cannot_drop_a_required_state(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"required_in_states": ["Design"]}

    _expect(build_docs, mutate, "loosen")


def test_always_required_covers_every_state(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"required_in_states": ["*"]}

    size = compile_psets(build_docs(mutate))["valve_data"].properties["size_in"]
    assert size.required_in_states == ["*"]


def test_states_cover() -> None:
    assert states_cover(["*"], ["Design", "Installed"])
    assert states_cover(["*"], ["*"])
    assert states_cover(["Design", "Installed", "X"], ["Design"])
    assert not states_cover(["Design"], ["*"])
    assert not states_cover(["Design"], ["Design", "Installed"])
    assert states_cover([], [])


def test_cannot_drop_the_always_required_marker(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["manufacturer"] = {"required_in_states": ["Design"]}

    _expect(build_docs, mutate, "loosen")


def test_cannot_widen_a_range(build_docs: Build) -> None:
    def low(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"minimum": 0.1}

    def high(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"maximum": 200}

    _expect(build_docs, low, "loosen")
    _expect(build_docs, high, "loosen")


def test_cannot_replace_a_company_pattern(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["tag_no"] = {"pattern": "^.*$"}

    _expect(build_docs, mutate, "loosen")


def test_may_repeat_the_company_pattern(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["tag_no"] = {"pattern": "^[A-Z]{1,3}-[0-9]{3,5}$"}

    compile_psets(build_docs(mutate))


def test_cannot_lower_enforcement(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"enforcement": "advisory"}

    _expect(build_docs, mutate, "loosen")


def test_cannot_lock_a_property(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["tighten"]["size_in"] = {"enforcement": "locked"}

    _expect(build_docs, mutate, "loosen")


def test_cannot_add_values_to_a_closed_list(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["add_values"] = {"FailAction": [{"code": "FX", "label": "Fail exotic"}]}

    _expect(build_docs, mutate, "closed_list")


def test_cannot_add_an_extensible_value_without_a_crosswalk(build_docs: Build) -> None:
    def missing(raw: Raw) -> None:
        del _entry(raw)["add_values"]["MaterialCode"][0]["crosswalk"]

    def unknown(raw: Raw) -> None:
        _entry(raw)["add_values"]["MaterialCode"][0]["crosswalk"] = "NOPE"

    _expect(build_docs, missing, "crosswalk")
    _expect(build_docs, unknown, "crosswalk")


def test_cannot_add_a_value_twice(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["add_values"]["MaterialCode"][0]["code"] = "CS"

    _expect(build_docs, mutate, "duplicate")


def test_cannot_extend_a_locked_pset(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["extends"].append(
            {
                "ref": "co.acme.engineering@3.2.0#safety_data",
                "labels": {"sil_rating": "SIL"},
            }
        )

    _expect(build_docs, mutate, "locked")


@pytest.mark.parametrize("what", ["add_values", "custom", "defaults", "labels", "nothing"])
def test_a_locked_pset_cannot_be_extended_in_any_way(build_docs: Build, what: str) -> None:
    # Each variant is caught by the pset-level guard alone: no property-level check applies.
    entry: dict[str, Any] = {"ref": "co.acme.engineering@3.2.0#safety_data"}
    if what == "add_values":
        entry["add_values"] = {"FailAction": [{"code": "FX", "label": "Exotic"}]}
    elif what == "custom":
        entry["custom"] = {"note": {"description": "A custom note.", "range": "string"}}
    elif what == "defaults":
        entry["defaults"] = {"nope": 1}
    elif what == "labels":
        entry["labels"] = {"nope": "x"}

    def mutate(raw: Raw) -> None:
        raw["x.P123"]["extends"].append(entry)

    _expect(build_docs, mutate, "locked")


def test_cannot_touch_a_locked_property_of_an_open_pset(build_docs: Build) -> None:
    def tighten(raw: Raw) -> None:
        _entry(raw)["tighten"]["fail_action"] = {"required_in_states": ["Design"]}

    def default(raw: Raw) -> None:
        _entry(raw)["defaults"] = {"fail_action": "FC"}

    def label(raw: Raw) -> None:
        _entry(raw)["labels"] = {"fail_action": "Failure mode"}

    for mutate in (tighten, default, label):
        _expect(build_docs, mutate, "locked")


def test_cannot_lock_a_custom_property(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["custom"]["fat_witness_by"]["enforcement"] = "locked"

    _expect(build_docs, mutate, "locked")


def test_cannot_add_a_custom_section_to_a_pset_that_forbids_it(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["valve_data"]["custom_section"] = {"allowed": False}

    _expect(build_docs, mutate, "custom_not_allowed")


def test_cannot_exceed_the_custom_property_limit(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["valve_data"]["custom_section"] = {
            "allowed": True,
            "max_properties": 1,
        }

    _expect(build_docs, mutate, "custom_limit")


def test_cannot_promote_custom_or_project_properties(build_docs: Build) -> None:
    def custom(raw: Raw) -> None:
        _entry(raw)["custom"]["fat_witness_by"]["materialize"] = True

    def project(raw: Raw) -> None:
        raw["prj.P123"]["psets"]["shutdown_tie_in"]["properties"]["window"]["materialize"] = True

    _expect(build_docs, custom, "materialize")
    _expect(build_docs, project, "materialize")


def test_locked_pset_cannot_declare_a_custom_section(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["co.acme.engineering"]["psets"]["safety_data"]["custom_section"] = {"allowed": True}

    _expect(build_docs, mutate, "invalid")


# --- document consistency --------------------------------------------------------------------


def test_extension_must_target_an_adopted_version(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["ref"] = "co.acme.engineering@3.1.0#valve_data"

    _expect(build_docs, mutate, "unknown_target")


def test_extension_must_pin_what_it_extends(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["x.P123"]["depends"] = {}

    _expect(build_docs, mutate, "pin")


def test_extension_must_target_an_existing_pset(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["ref"] = "co.acme.engineering@3.2.0#no_such_pset"

    _expect(build_docs, mutate, "unknown_target")


def test_unknown_property_and_list_in_an_extension(build_docs: Build) -> None:
    def prop(raw: Raw) -> None:
        _entry(raw)["tighten"]["nope"] = {"enforcement": "required"}

    def listing(raw: Raw) -> None:
        _entry(raw)["add_values"] = {"NoSuchList": [{"code": "A", "label": "A"}]}

    _expect(build_docs, prop, "unknown_property")
    _expect(build_docs, listing, "unknown_list")


def test_unknown_range_is_rejected(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _valve(raw)["tag_no"]["range"] = "NoSuchList"

    _expect(build_docs, mutate, "unknown_range")


def test_two_extensions_of_one_pset_are_rejected(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        second = dict(raw["x.P123"])
        second["package"] = "x.P123b"
        raw["x.P123b"] = second

    _expect(build_docs, mutate, "duplicate")


def test_project_list_cannot_reuse_a_company_name(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        raw["prj.P123"]["code_lists"] = {
            "FailAction": {"description": "mine", "values": [{"code": "A", "label": "A"}]}
        }

    _expect(build_docs, mutate, "shadow")


def test_default_must_fit_the_kind(build_docs: Build) -> None:
    def mutate(raw: Raw) -> None:
        _entry(raw)["defaults"] = {"size_in": "four"}

    _expect(build_docs, mutate, "invalid")


def test_quantity_needs_a_unit_and_ranges_need_numbers(build_docs: Build) -> None:
    def quantity(raw: Raw) -> None:
        _valve(raw)["tag_no"] = {"description": "d", "range": "quantity"}

    def minimum(raw: Raw) -> None:
        _valve(raw)["tag_no"]["minimum"] = 1

    _expect(build_docs, quantity, "invalid")
    _expect(build_docs, minimum, "invalid")


def test_package_twice_is_rejected(build_docs: Build) -> None:
    docs = build_docs()
    with pytest.raises(SchemaCompileError) as caught:
        compile_psets([*docs, docs[0]])
    assert caught.value.rule == "duplicate"


@pytest.mark.parametrize(
    "mutate_text",
    [
        "company_with_project",
        "extension_without_project",
        "extension_with_psets",
        "bad_version",
        "bad_name",
        "bad_list_name",
        "missing_description",
        "reserved_pset_x",
        "reserved_pset_prj",
        "reserved_property_x",
    ],
)
def test_document_structure_errors(build_docs: Build, mutate_text: str) -> None:
    def mutate(raw: Raw) -> None:
        match mutate_text:
            case "company_with_project":
                raw["co.acme.engineering"]["project"] = "P123"
            case "extension_without_project":
                del raw["x.P123"]["project"]
            case "extension_with_psets":
                raw["x.P123"]["psets"] = raw["prj.P123"]["psets"]
            case "bad_version":
                raw["x.P123"]["version"] = "1.4"
            case "bad_name":
                _valve(raw)["Bad-Name"] = {"description": "d"}
            case "bad_list_name":
                raw["co.acme.engineering"]["code_lists"]["bad_list"] = {"description": "d"}
            case "missing_description":
                del _valve(raw)["size_in"]["description"]
            case "reserved_pset_x":
                raw["co.acme.engineering"]["psets"]["x"] = raw["co.acme.engineering"]["psets"][
                    "safety_data"
                ]
            case "reserved_pset_prj":
                raw["co.acme.engineering"]["psets"]["prj"] = raw["co.acme.engineering"]["psets"][
                    "safety_data"
                ]
            case "reserved_property_x":
                _valve(raw)["x"] = {"description": "Collides with the custom section."}

    with pytest.raises(ValidationError):
        build_docs(mutate)
