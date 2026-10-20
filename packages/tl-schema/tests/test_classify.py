"""Classification of the change between two package versions (brief 27.5; P1-I8-T02)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from tl_schema.classify import (
    CLASS_ORDER,
    ClassificationReport,
    classify_packages,
)
from tl_schema.packages import PackageDoc

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "schema" / "fixtures"

Mutate = Callable[[dict[str, Any]], None]


def _raw(name: str) -> dict[str, Any]:
    path = next(FIXTURE_DIR.glob(f"{name}@*.yaml"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _pair(mutate: Mutate, name: str = "co.acme.engineering", version: str = "3.3.0"):
    old_raw = _raw(name)
    new_raw = copy.deepcopy(old_raw)
    new_raw["version"] = version
    mutate(new_raw)
    return PackageDoc.model_validate(old_raw), PackageDoc.model_validate(new_raw)


def _classify(mutate: Mutate, name: str = "co.acme.engineering") -> ClassificationReport:
    old, new = _pair(mutate, name, "9.0.0")
    return classify_packages(old, new)


def _codes(report: ClassificationReport) -> dict[str, str]:
    return {f"{c.path}|{c.code}": c.cls for c in report.changes}


def _valve(raw: dict[str, Any]) -> dict[str, Any]:
    return raw["psets"]["valve_data"]["properties"]


def test_a_first_version_is_additive() -> None:
    new = PackageDoc.model_validate(_raw("co.acme.engineering"))
    report = classify_packages(None, new)
    assert report.base is None and report.worst == "additive" and report.auto_adoptable
    assert not report.blocks_submit


def test_an_unchanged_package_has_no_changes_and_is_auto_adoptable() -> None:
    report = _classify(lambda raw: None)
    assert report.changes == ()
    assert report.worst == "additive" and report.auto_adoptable and not report.blocks_submit
    assert report.counts == {}


def test_a_higher_version_of_the_same_package_is_required() -> None:
    old, new = _pair(lambda raw: None, version="3.2.0")
    with pytest.raises(ValueError, match="higher version"):
        classify_packages(old, new)
    other = PackageDoc.model_validate(_raw("x.P123"))
    with pytest.raises(ValueError, match="different packages"):
        classify_packages(other, new)


def test_an_optional_property_is_additive() -> None:
    def add(raw: dict[str, Any]) -> None:
        _valve(raw)["seat_leak_class"] = {
            "description": "Seat leakage class of the valve.",
            "range": "string",
        }

    report = _classify(add)
    assert _codes(report) == {"psets.valve_data.seat_leak_class|property_added": "additive"}
    assert report.auto_adoptable


def test_a_required_property_is_constraining() -> None:
    def add(raw: dict[str, Any]) -> None:
        _valve(raw)["seat_leak_class"] = {
            "description": "Seat leakage class of the valve.",
            "range": "string",
            "required_in_states": ["Installed"],
        }

    report = _classify(add)
    assert report.worst == "constraining" and not report.auto_adoptable
    assert not report.blocks_submit
    assert "constraining" in report.handling


def test_a_property_that_becomes_required_is_constraining_and_one_that_stops_is_relaxing() -> None:
    def tighten(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["required"] = True

    assert _codes(_classify(tighten)) == {
        "psets.valve_data.tag_no.required_in_states|required_added": "constraining"
    }

    def relax(raw: dict[str, Any]) -> None:
        _valve(raw)["manufacturer"]["required"] = False

    report = _classify(relax)
    (change,) = report.changes
    assert change.code == "required_dropped" and change.relaxing and change.cls == "additive"


def test_required_in_states_grown_or_shrunk() -> None:
    def grow(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["required_in_states"] = ["Design", "Installed", "Commissioned"]

    assert _classify(grow).worst == "constraining"

    def shrink(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["required_in_states"] = ["Installed"]

    report = _classify(shrink)
    assert report.worst == "additive" and report.changes[0].relaxing


def test_enforcement_up_is_constraining_and_down_is_relaxing() -> None:
    def up(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["enforcement"] = "required"

    assert _codes(_classify(up)) == {
        "psets.valve_data.tag_no.enforcement|enforcement_tightened": "constraining"
    }

    def down(raw: dict[str, Any]) -> None:
        raw["psets"]["safety_data"]["enforcement"] = "required"

    report = _classify(down)
    assert report.worst == "additive" and report.changes[0].relaxing


def test_a_pset_level_enforcement_change_is_seen_on_properties_that_inherit_it() -> None:
    def down(raw: dict[str, Any]) -> None:
        raw["psets"]["valve_data"]["enforcement"] = "advisory"

    codes = _codes(_classify(down))
    assert "psets.valve_data.enforcement|enforcement_relaxed" in codes
    # size_in has no enforcement of its own, so it inherits the pset's: that is a change too
    assert "psets.valve_data.size_in.enforcement|enforcement_relaxed" in codes


def test_numeric_bounds_tighten_or_relax() -> None:
    def narrow(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["minimum"] = 0.5
        _valve(raw)["size_in"]["maximum"] = 100

    codes = _codes(_classify(narrow))
    assert codes["psets.valve_data.size_in.minimum|minimum_tightened"] == "constraining"
    assert codes["psets.valve_data.size_in.maximum|maximum_tightened"] == "constraining"

    def widen(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["minimum"] = 0.1
        _valve(raw)["size_in"]["maximum"] = 200

    codes = _codes(_classify(widen))
    assert codes["psets.valve_data.size_in.minimum|minimum_relaxed"] == "additive"
    assert codes["psets.valve_data.size_in.maximum|maximum_relaxed"] == "additive"

    def drop(raw: dict[str, Any]) -> None:
        del _valve(raw)["size_in"]["maximum"]

    assert _codes(_classify(drop)) == {
        "psets.valve_data.size_in.maximum|maximum_relaxed": "additive"
    }

    def add(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["minimum"] = 1

    assert _classify(add).worst == "constraining"


def test_a_pattern_added_or_changed_is_constraining_and_dropped_is_relaxing() -> None:
    def change(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["pattern"] = "^[A-Z]{1,3}-[0-9]{4}$"

    assert _classify(change).worst == "constraining"

    def add(raw: dict[str, Any]) -> None:
        _valve(raw)["manufacturer"]["pattern"] = "^[A-Za-z ]+$"

    assert _classify(add).worst == "constraining"

    def drop(raw: dict[str, Any]) -> None:
        del _valve(raw)["tag_no"]["pattern"]

    report = _classify(drop)
    assert report.worst == "additive" and report.changes[0].code == "pattern_dropped"


def test_a_changed_range_or_unit_is_breaking_and_blocks_a_submit() -> None:
    def retype(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["range"] = "int"

    report = _classify(retype)
    assert report.worst == "breaking" and report.blocks_submit and not report.auto_adoptable

    def reunit(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["unit"] = "mm"

    report = _classify(reunit)
    assert _codes(report) == {"psets.valve_data.size_in|unit_changed": "breaking"}

    def drop_unit(raw: dict[str, Any]) -> None:
        del _valve(raw)["size_in"]["unit"]

    assert _classify(drop_unit).blocks_submit


def test_a_removed_property_is_a_deprecation() -> None:
    def remove(raw: dict[str, Any]) -> None:
        del _valve(raw)["tag_no"]

    report = _classify(remove)
    assert _codes(report) == {"psets.valve_data.tag_no|property_removed": "deprecation"}
    assert not report.blocks_submit and not report.auto_adoptable


def test_a_property_that_returns_under_another_name_is_a_possible_rename() -> None:
    def rename(raw: dict[str, Any]) -> None:
        props = _valve(raw)
        props["tag_number"] = props.pop("tag_no")

    report = _classify(rename)
    assert _codes(report) == {"psets.valve_data.tag_no|property_renamed": "renaming"}
    assert "tag_number" in report.changes[0].detail


def test_a_renamed_property_with_a_new_description_is_a_removal_and_an_addition() -> None:
    def replace(raw: dict[str, Any]) -> None:
        props = _valve(raw)
        props["tag_number"] = {**props.pop("tag_no"), "description": "A different idea entirely."}

    codes = _codes(_classify(replace))
    assert codes == {
        "psets.valve_data.tag_no|property_removed": "deprecation",
        "psets.valve_data.tag_number|property_added": "additive",
    }


def test_two_removed_properties_do_not_both_claim_one_new_name() -> None:
    def twins(raw: dict[str, Any]) -> None:
        props = _valve(raw)
        a = {"description": "The same words twice over.", "range": "string"}
        props["twin_a"], props["twin_b"] = dict(a), dict(a)

    old, mid = _pair(twins, version="3.3.0")

    def drop_both(raw: dict[str, Any]) -> None:
        twins(raw)
        del _valve(raw)["twin_a"], _valve(raw)["twin_b"]
        _valve(raw)["twin_c"] = {"description": "The same words twice over.", "range": "string"}

    _, last = _pair(drop_both, version="3.4.0")
    report = classify_packages(mid, last)
    assert sorted(c.code for c in report.changes) == [
        "property_removed",
        "property_renamed",
    ]
    assert old.version == "3.2.0"


def test_a_changed_description_is_additive_but_needs_a_person() -> None:
    def reword(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["description"] = "Something that may mean another thing."

    report = _classify(reword)
    (change,) = report.changes
    assert change.cls == "additive" and change.review


def test_an_external_mapping_removed_or_replaced_is_forbidden() -> None:
    def replace(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["exact_mappings"] = ["cfihos:CFIHOS-99999999"]

    report = _classify(replace)
    assert report.worst == "forbidden" and report.blocks_submit
    assert "meaning" in report.handling["forbidden"]

    def drop(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["exact_mappings"] = []

    assert _classify(drop).worst == "forbidden"

    def extend(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["exact_mappings"].append("ifc:Pset_ValveTypeCommon.Size")

    report = _classify(extend)
    assert report.worst == "additive" and report.changes[0].code == "mapping_added"


def test_code_lists_values_and_policy() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["code_lists"]["MaterialCode"]["values"].append({"code": "TI", "label": "Titanium"})
        del raw["code_lists"]["MaterialCode"]["values"][0]  # CS goes away
        raw["code_lists"]["MaterialCode"]["value_list_policy"] = "closed"

    codes = _codes(_classify(edit))
    assert codes["code_lists.MaterialCode.values.TI|value_added"] == "additive"
    assert codes["code_lists.MaterialCode.values.CS|value_removed"] == "deprecation"
    assert codes["code_lists.MaterialCode.value_list_policy|value_list_policy_tightened"] == (
        "constraining"
    )


def test_a_value_meaning_that_changes_is_forbidden_and_one_that_appears_is_additive() -> None:
    def meaning(raw: dict[str, Any]) -> None:
        raw["code_lists"]["FailAction"]["values"][0]["meaning"] = "https://example.org/fc"

    assert _classify(meaning).worst == "additive"

    old_raw = _raw("co.acme.engineering")
    old_raw["code_lists"]["FailAction"]["values"][0]["meaning"] = "https://example.org/fc"
    new_raw = copy.deepcopy(old_raw)
    new_raw["version"] = "3.3.0"
    new_raw["code_lists"]["FailAction"]["values"][0]["meaning"] = "https://example.org/other"
    report = classify_packages(
        PackageDoc.model_validate(old_raw), PackageDoc.model_validate(new_raw)
    )
    assert report.worst == "forbidden"


def test_code_lists_added_and_removed() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["code_lists"]["Rating"] = {
            "description": "Pressure rating classes.",
            "values": [
                {"code": "150", "label": "Class 150"},
                {"code": "300", "label": "Class 300"},
            ],
        }
        del raw["code_lists"]["FailAction"]

    codes = _codes(_classify(edit))
    assert codes["code_lists.Rating|code_list_added"] == "additive"
    assert codes["code_lists.FailAction|code_list_removed"] == "deprecation"


def test_psets_added_removed_and_the_mandatory_pset_with_required_properties() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["psets"]["pump_data"] = {
            "description": "Pump data for rotating equipment.",
            "adoption": "mandatory",
            "properties": {
                "flow": {
                    "description": "Rated flow of the pump.",
                    "range": "decimal",
                    "required": True,
                }
            },
        }
        raw["psets"]["fan_data"] = {
            "description": "Fan data for rotating equipment.",
            "properties": {"rpm": {"description": "Rated speed of the fan.", "range": "int"}},
        }
        del raw["psets"]["safety_data"]

    codes = _codes(_classify(edit))
    assert codes["psets.pump_data|pset_added_required"] == "constraining"
    assert codes["psets.fan_data|pset_added"] == "additive"
    assert codes["psets.safety_data|pset_removed"] == "deprecation"


def test_pset_rules_applies_to_adoption_class_filter_and_custom_section() -> None:
    def edit(raw: dict[str, Any]) -> None:
        pset = raw["psets"]["valve_data"]
        pset["applies_to"] = ["core.Record", "engineering.Tag"]
        pset["class_filter"] = "class in (ControlValve)"
        pset["custom_section"] = {"allowed": True, "max_properties": 5}
        safety = raw["psets"]["safety_data"]
        safety["adoption"] = "mandatory"
        safety["custom_section"] = {"allowed": True}

    codes = _codes(_classify(edit))
    assert codes["psets.valve_data.applies_to|applies_to_added"] == "additive"
    assert codes["psets.valve_data.class_filter|class_filter_changed"] == "constraining"
    assert codes["psets.valve_data.custom_section|custom_limit_lowered"] == "constraining"
    assert codes["psets.safety_data.adoption|adoption_tightened"] == "constraining"
    assert codes["psets.safety_data.custom_section|custom_section_opened"] == "additive"

    def narrow(raw: dict[str, Any]) -> None:
        raw["psets"]["valve_data"]["applies_to"] = ["engineering.Tag"]
        raw["psets"]["valve_data"]["custom_section"] = {"allowed": False}

    codes = _codes(_classify(narrow))
    assert codes["psets.valve_data.applies_to|applies_to_removed"] == "deprecation"
    assert codes["psets.valve_data.custom_section|custom_section_closed"] == "constraining"


def test_materialize_on_and_off() -> None:
    def edit(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["materialize"] = False
        _valve(raw)["tag_no"]["materialize"] = True

    codes = _codes(_classify(edit))
    assert codes["psets.valve_data.size_in|materialize_removed"] == "deprecation"
    assert codes["psets.valve_data.tag_no|materialize_added"] == "additive"


def test_package_level_changes() -> None:
    def edit(raw: dict[str, Any]) -> None:
        raw["title"] = "Another title"
        raw["description"] = "A different description of the package."

    codes = _codes(_classify(edit))
    assert codes["(package)|title_changed"] == "additive"
    assert codes["(package)|description_changed"] == "additive"

    old = PackageDoc.model_validate(_raw("x.P123"))
    raw = _raw("x.P123")
    raw["version"] = "1.5.0"
    raw["kind"] = "project"
    raw["psets"] = {}
    raw["extends"] = []
    new = PackageDoc.model_validate(raw)
    report = classify_packages(old, new)
    assert report.blocks_submit and "kind_changed" in {c.code for c in report.changes}

    raw = _raw("x.P123")
    raw["version"] = "1.5.0"
    raw["project"] = "P999"
    assert classify_packages(old, PackageDoc.model_validate(raw)).blocks_submit


def test_depends_changes_are_additive() -> None:
    raw = _raw("x.P123")
    raw["version"] = "1.5.0"
    raw["depends"] = {}
    old = PackageDoc.model_validate(_raw("x.P123"))
    report = classify_packages(old, PackageDoc.model_validate(raw))
    assert _codes(report) == {"depends.co.acme.engineering|depends_removed": "additive"}


def test_extension_changes() -> None:
    raw = _raw("x.P123")
    raw["version"] = "1.5.0"
    ext = raw["extends"][0]
    ext["tighten"]["body_material"] = {"required_in_states": ["Design", "Installed"]}
    ext["tighten"]["size_in"] = {"minimum": 1}
    ext["add_values"]["MaterialCode"].append({"code": "TI", "label": "Titanium"})
    del ext["custom"]["tie_in_window"]
    ext["custom"]["rev"] = {"description": "Revision of the tie-in.", "range": "string"}
    ext["defaults"] = {"manufacturer": "Acme"}
    old = PackageDoc.model_validate(_raw("x.P123"))
    codes = _codes(classify_packages(old, PackageDoc.model_validate(raw)))
    base = "extends.co.acme.engineering@3.2.0#valve_data"
    assert (
        codes[f"{base}.tighten.body_material.required_in_states|required_added"] == "constraining"
    )
    assert codes[f"{base}.tighten.size_in|tighten_added"] == "constraining"
    assert codes[f"{base}.add_values.MaterialCode|value_added"] == "additive"
    assert codes[f"{base}.custom.tie_in_window|custom_removed"] == "deprecation"
    assert codes[f"{base}.custom.rev|custom_added"] == "additive"
    assert codes[f"{base}.defaults|defaults_changed"] == "additive"


def test_an_extension_that_stops_tightening_is_relaxing_and_a_removed_one_is_a_deprecation() -> (
    None
):
    raw = _raw("x.P123")
    raw["version"] = "1.5.0"
    raw["extends"][0]["tighten"] = {}
    old = PackageDoc.model_validate(_raw("x.P123"))
    (change,) = classify_packages(old, PackageDoc.model_validate(raw)).changes
    assert change.code == "tighten_removed" and change.relaxing

    raw["extends"] = []
    (change,) = classify_packages(old, PackageDoc.model_validate(raw)).changes
    assert change.code == "extension_removed" and change.cls == "deprecation"


def test_conformance_mode_period_and_waivers() -> None:
    old_raw = _raw("x.P123")
    old_raw["conformance"] = {
        "mode": "lenient",
        "lenient_until": "2027-06-30",
        "waivers": [
            {
                "path": "psets.valve_data.size_in",
                "reason": "Legacy data.",
                "approver": "lead",
            }
        ],
    }
    new_raw = copy.deepcopy(old_raw)
    new_raw["version"] = "1.5.0"
    new_raw["conformance"] = {
        "mode": "strict",
        "lenient_until": "2027-03-31",
        "waivers": [
            {
                "path": "psets.valve_data.fail_action",
                "reason": "Legacy data.",
                "approver": "lead",
            }
        ],
    }
    report = classify_packages(
        PackageDoc.model_validate(old_raw), PackageDoc.model_validate(new_raw)
    )
    codes = _codes(report)
    assert codes["conformance.mode|mode_tightened"] == "constraining"
    assert codes["conformance.lenient_until|lenient_until_changed"] == "constraining"
    assert codes["conformance.waivers.psets.valve_data.fail_action|waiver_added"] == "additive"
    assert codes["conformance.waivers.psets.valve_data.size_in|waiver_removed"] == "constraining"

    new_raw["conformance"]["mode"] = "lenient"
    new_raw["conformance"]["lenient_until"] = "2027-12-31"
    codes = _codes(
        classify_packages(PackageDoc.model_validate(old_raw), PackageDoc.model_validate(new_raw))
    )
    assert codes["conformance.lenient_until|lenient_until_changed"] == "additive"


def test_the_worst_class_decides_and_the_counts_add_up() -> None:
    def edit(raw: dict[str, Any]) -> None:
        _valve(raw)["size_in"]["range"] = "int"  # breaking
        _valve(raw)["tag_no"]["required"] = True  # constraining
        del _valve(raw)["manufacturer"]  # deprecation
        _valve(raw)["extra"] = {"description": "An extra optional property.", "range": "string"}

    report = _classify(edit)
    assert report.worst == "breaking"
    assert report.counts == {"additive": 1, "deprecation": 1, "constraining": 1, "breaking": 1}
    assert sum(report.counts.values()) == len(report.changes)
    assert set(report.handling) == set(report.counts)
    assert list(report.counts) == [c for c in CLASS_ORDER if c in report.counts]


def test_the_digest_is_stable_and_changes_with_the_changes() -> None:
    def edit(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["required"] = True

    first, second = _classify(edit), _classify(edit)
    assert first.digest == second.digest and len(first.digest) == 64
    assert _classify(lambda raw: None).digest != first.digest

    def other(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["enforcement"] = "required"

    assert _classify(other).digest != first.digest


def test_changes_are_sorted_by_path() -> None:
    def edit(raw: dict[str, Any]) -> None:
        _valve(raw)["tag_no"]["required"] = True
        _valve(raw)["size_in"]["maximum"] = 10
        raw["code_lists"]["FailAction"]["values"].append({"code": "X", "label": "X"})

    paths = [c.path for c in _classify(edit).changes]
    assert paths == sorted(paths)


def test_a_property_with_another_unit_is_not_taken_for_a_rename() -> None:
    def replace(raw: dict[str, Any]) -> None:
        props = _valve(raw)
        gone = props.pop("size_in")
        props["size_mm"] = {**gone, "unit": "mm"}

    codes = _codes(_classify(replace))
    assert codes == {
        "psets.valve_data.size_in|property_removed": "deprecation",
        "psets.valve_data.size_mm|property_added_required": "constraining",
    }


def test_an_optional_pset_with_required_properties_is_only_additive() -> None:
    def add(raw: dict[str, Any]) -> None:
        raw["psets"]["fan_data"] = {
            "description": "Fan data for rotating equipment.",
            "adoption": "optional",
            "properties": {
                "rpm": {"description": "Rated speed of the fan.", "range": "int", "required": True}
            },
        }

    assert _codes(_classify(add)) == {"psets.fan_data|pset_added": "additive"}
