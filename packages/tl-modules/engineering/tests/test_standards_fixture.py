"""The acme standards fixture (P1-I1-T01): the file parses, and it holds what the demos need."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_mod_engineering.document import StandardsDoc, load_standards_file

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "schema"
    / "fixtures"
    / "standards"
    / "co.acme.standards@1.0.0.yaml"
)

# list name: (value_list_policy, minimum number of values, codes that must be present)
CODE_LISTS: dict[str, tuple[str, int, set[str]]] = {
    "Discipline": ("closed", 8, {"PIP", "MEC", "ELE", "INS", "CIV", "STR", "PRO", "HSE"}),
    "Area": ("extensible", 6, {"10", "20", "30", "47"}),
    "DocumentType": (
        "extensible",
        12,
        {"ISO", "PID", "GA", "DS", "LD", "SPC", "PRC", "CAL", "MTO"},
    ),
    "NdeMethod": ("closed", 6, {"RT", "UT", "MT", "PT", "VT", "PAUT"}),
    "WeldType": ("closed", 4, {"BW", "SW", "FW"}),
    "Craft": ("project_defined", 6, {"PF", "WLD", "ELC", "INT", "SCF", "RIG"}),
    "UnitOfMeasure": (
        "closed",
        10,
        {"mm", "in", "m", "bar", "psi", "degC", "degF", "kg", "lb", "m3"},
    ),
    "MaterialCode": ("extensible", 5, {"CS", "SS304", "SS316L", "DUPLEX", "other"}),
    "FailAction": ("closed", 3, {"FC", "FO", "FL"}),
}

MNEMONICS = {
    "FV", "PV", "LV", "TV", "HV", "XV", "PSV", "FT", "PT", "LT", "TT",
    "FIC", "PIC", "LIC", "TIC", "P", "E", "V", "K", "M", "HS", "TW",
}  # fmt: skip

# class code: (family, required psets, mnemonics that must be listed)
CLASSES: dict[str, tuple[str, list[str], set[str]]] = {
    "ControlValve": ("valve", ["valve_data"], {"FV", "PV", "LV", "TV"}),
    "ManualValve": ("valve", ["valve_data"], {"HV"}),
    "SafetyValve": ("valve", ["valve_data", "safety_data"], {"PSV"}),
    "Transmitter": ("instrument", [], {"FT", "PT", "LT", "TT"}),
    "Controller": ("instrument", [], {"FIC", "PIC", "LIC", "TIC"}),
    "Pump": ("pump", [], {"P"}),
    "Vessel": ("equipment", [], {"V"}),
    "HeatExchanger": ("equipment", [], {"E"}),
    "Compressor": ("equipment", [], {"K"}),
    "Motor": ("equipment", [], {"M"}),
}


@pytest.fixture(scope="module")
def doc() -> StandardsDoc:
    return load_standards_file(FIXTURE)


def test_the_file_is_the_first_edition_of_the_acme_standards(doc: StandardsDoc) -> None:
    assert doc.edition == "co.acme.standards@1.0.0"
    assert doc.owner == "role:standards-steward"
    assert doc.effective_from == "2026-01-01"
    assert doc.problems() == []


def test_it_defines_exactly_the_code_lists_the_demos_use(doc: StandardsDoc) -> None:
    assert set(doc.code_lists) == set(CODE_LISTS)


@pytest.mark.parametrize("name", sorted(CODE_LISTS))
def test_each_code_list_has_its_policy_and_enough_values(doc: StandardsDoc, name: str) -> None:
    policy, minimum, required = CODE_LISTS[name]
    code_list = doc.code_lists[name]
    codes = [value.code for value in code_list.values]
    assert code_list.value_list_policy == policy
    assert len(codes) >= minimum
    assert required <= set(codes)
    assert len(codes) == len(set(codes))
    assert all(value.label.strip() and value.label != value.code for value in code_list.values)


def test_a_unit_of_measure_carries_its_ucum_code_and_dimension(doc: StandardsDoc) -> None:
    for value in doc.code_lists["UnitOfMeasure"].values:
        assert isinstance(value.attributes.get("ucum"), str) and value.attributes["ucum"]
        assert isinstance(value.attributes.get("dimension"), str) and value.attributes["dimension"]
    by_code = {v.code: v.attributes for v in doc.code_lists["UnitOfMeasure"].values}
    assert by_code["in"] == {"ucum": "[in_i]", "dimension": "length"}
    assert by_code["bar"]["dimension"] == "pressure"
    assert by_code["degC"]["ucum"] == "Cel"


def test_the_material_and_fail_action_lists_mirror_the_pset_package(doc: StandardsDoc) -> None:
    assert [v.code for v in doc.code_lists["MaterialCode"].values] == [
        "CS",
        "SS304",
        "SS316L",
        "DUPLEX",
        "other",
    ]
    assert [v.code for v in doc.code_lists["FailAction"].values] == ["FC", "FO", "FL"]


def test_it_defines_the_mnemonics_with_a_meaning_each(doc: StandardsDoc) -> None:
    by_code = {m.code: m for m in doc.mnemonics}
    assert MNEMONICS <= set(by_code)
    assert all(m.label.strip() for m in doc.mnemonics)
    assert by_code["FV"].class_hint == "ControlValve"
    assert by_code["PSV"].class_hint == "SafetyValve"
    assert by_code["HS"].class_hint is None  # a hand switch has no class in this edition


def test_it_defines_the_tag_number_pattern(doc: StandardsDoc) -> None:
    (pattern,) = doc.numbering_patterns
    assert pattern.code == "tag"
    assert pattern.record_type == "engineering.Tag"
    assert pattern.template == "{area}-{mnemonic}-{seq:4}"
    assert pattern.allocate is False
    assert {n: (s.role, s.list, s.registry) for n, s in pattern.segments.items()} == {
        "area": ("area", "Area", None),
        "mnemonic": ("mnemonic", None, "mnemonic"),
        "seq": ("sequence", None, None),
    }


def test_it_defines_the_tag_classes_and_the_psets_they_require(doc: StandardsDoc) -> None:
    by_code = {c.code: c for c in doc.tag_classes}
    assert set(by_code) == set(CLASSES)
    for code, (family, psets, mnemonics) in CLASSES.items():
        tag_class = by_code[code]
        assert tag_class.family == family, code
        assert tag_class.required_psets == psets, code
        assert mnemonics <= set(tag_class.mnemonics), code
        assert tag_class.definition.strip(), code


def test_a_mnemonic_belongs_to_at_most_one_class(doc: StandardsDoc) -> None:
    seen: dict[str, str] = {}
    for tag_class in doc.tag_classes:
        for mnemonic in tag_class.mnemonics:
            assert mnemonic not in seen, (mnemonic, seen[mnemonic], tag_class.code)
            seen[mnemonic] = tag_class.code
