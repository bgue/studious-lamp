"""The standards document model: what it accepts, and every way it refuses."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from tl_mod_engineering.document import StandardsDocError, parse_standards


def minimal() -> dict[str, Any]:
    return {
        "standards": "co.acme.standards",
        "version": "1.0.0",
        "description": "Test standards.",
        "owner": "role:steward",
        "code_lists": {
            "Area": {
                "label": "Areas",
                "definition": "Plant areas.",
                "value_list_policy": "extensible",
                "values": [{"code": "47", "label": "Unit 47"}, {"code": "10", "label": "Unit 10"}],
            },
            "Discipline": {
                "label": "Disciplines",
                "definition": "Disciplines.",
                "values": [{"code": "PIP", "label": "Piping"}],
            },
        },
        "mnemonics": [
            {"code": "FV", "label": "Flow control valve", "class_hint": "ControlValve"},
            {"code": "PT", "label": "Pressure transmitter", "discipline": "PIP"},
        ],
        "numbering_patterns": [
            {
                "code": "tag",
                "label": "Tag number",
                "definition": "Area, mnemonic and a four-digit sequence.",
                "record_type": "engineering.Tag",
                "template": "{area}-{mnemonic}-{seq:4}",
                "segments": {
                    "area": {"role": "area", "list": "Area"},
                    "mnemonic": {"role": "mnemonic", "registry": "mnemonic"},
                    "seq": {"role": "sequence"},
                },
            }
        ],
        "tag_classes": [
            {
                "code": "ControlValve",
                "label": "Control valve",
                "definition": "A valve that modulates flow.",
                "family": "valve",
                "required_psets": ["valve_data"],
                "mnemonics": ["FV"],
            }
        ],
    }


def parse(data: dict[str, Any]) -> Any:
    return parse_standards(yaml.safe_dump(data), source="test.yaml")


def refused(data: dict[str, Any]) -> str:
    with pytest.raises(StandardsDocError) as raised:
        parse(data)
    return str(raised.value)


def test_a_sound_document_parses_and_names_its_edition() -> None:
    doc = parse(minimal())
    assert doc.edition == "co.acme.standards@1.0.0"
    assert [m.code for m in doc.mnemonics] == ["FV", "PT"]
    assert doc.code_lists["Area"].value_list_policy == "extensible"
    assert doc.code_lists["Discipline"].value_list_policy == "closed"  # the default
    assert doc.numbering_patterns[0].allocate is False
    assert doc.problems() == []


def test_unknown_keys_are_refused_so_a_misspelling_cannot_be_ignored() -> None:
    data = minimal()
    data["mnemonics"][0]["clas_hint"] = "x"
    message = refused(data)
    assert message.startswith("test.yaml: mnemonics.0.clas_hint")


def test_invalid_yaml_and_a_non_mapping_are_refused_with_the_source_name() -> None:
    with pytest.raises(StandardsDocError, match=r"^broken.yaml: invalid YAML"):
        parse_standards("a: [1", source="broken.yaml")
    with pytest.raises(StandardsDocError, match="must be a YAML mapping"):
        parse_standards("- 1\n- 2\n", source="list.yaml")


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda d: d.update(standards="Acme"), "lower-case dotted words"),
        (lambda d: d.update(version="1.0"), "MAJOR.MINOR.PATCH"),
        (lambda d: d.update(effective_from="2026/01/01"), "ISO date"),
        (lambda d: d["code_lists"].update(area=d["code_lists"].pop("Area")), "UpperCamelCase"),
        (lambda d: d["mnemonics"][0].update(code="fv"), "upper-case"),
        (lambda d: d["code_lists"]["Area"]["values"][0].update(code="a b"), "letters, digits"),
        (lambda d: d["code_lists"]["Area"].update(values=[]), "values"),
        (lambda d: d["code_lists"]["Area"].update(definition=""), "definition"),
        (lambda d: d["tag_classes"][0].update(required_psets=["Valve Data"]), "lower snake case"),
        (lambda d: d["tag_classes"][0].update(family="boat"), "family"),
        (lambda d: d["numbering_patterns"][0].update(record_type="Tag"), "engineering.Tag"),
    ],
)
def test_a_field_that_does_not_validate_is_refused(change: Any, fragment: str) -> None:
    data = minimal()
    change(data)
    assert fragment in refused(data)


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda d: d["mnemonics"].append(dict(d["mnemonics"][0])), "duplicate mnemonic 'FV'"),
        (lambda d: d["tag_classes"].append(dict(d["tag_classes"][0])), "duplicate tag class"),
        (
            lambda d: d["code_lists"]["Area"]["values"].append({"code": "47", "label": "again"}),
            "duplicate value of Area '47'",
        ),
        (lambda d: d["tag_classes"][0].update(mnemonics=["ZZ"]), "mnemonic 'ZZ' is not defined"),
        (lambda d: d["mnemonics"][0].update(class_hint="Pump"), "class_hint 'Pump'"),
        (lambda d: d["mnemonics"][1].update(discipline="XYZ"), "not a value of Discipline"),
        (
            lambda d: d["numbering_patterns"][0]["segments"]["area"].update(list="Nowhere"),
            "names the code list 'Nowhere'",
        ),
        (lambda d: d["numbering_patterns"][0].update(template="{area}-{mnemonic}"), "exactly one"),
        (
            lambda d: d["numbering_patterns"][0]["segments"].pop("mnemonic"),
            "segment 'mnemonic' has no definition",
        ),
        (
            lambda d: d["numbering_patterns"][0]["segments"].update(extra={"role": "other"}),
            "segment 'extra' is not in the template",
        ),
        (
            lambda d: d["numbering_patterns"][0]["segments"]["seq"].update(role="other"),
            "'seq' must have the role sequence",
        ),
        (
            lambda d: d["numbering_patterns"][0]["segments"]["area"].update(role="sequence"),
            "only 'seq' may have the role sequence",
        ),
        (
            lambda d: d["numbering_patterns"][0]["segments"]["area"].update(registry="mnemonic"),
            "a list and a registry",
        ),
        (
            lambda d: d["code_lists"]["Area"]["values"][0].update(
                effective_from="2026-02-01", effective_to="2026-01-01"
            ),
            "effective_to is before effective_from",
        ),
    ],
)
def test_a_problem_across_the_document_is_named(change: Any, fragment: str) -> None:
    data = minimal()
    change(data)
    assert fragment in refused(data)


def test_every_problem_is_listed_not_only_the_first() -> None:
    data = minimal()
    data["tag_classes"][0]["mnemonics"] = ["ZZ"]
    data["mnemonics"][0]["class_hint"] = "Pump"
    lines = refused(data).splitlines()
    assert len(lines) == 2 and all(line.startswith("test.yaml: ") for line in lines)
