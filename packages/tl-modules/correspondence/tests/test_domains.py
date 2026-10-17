"""Domain definitions: parse, check against the system, look up by scope (P1-I5-T05)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from corrworld import FIXTURES
from tl_core.numbering.config import load_numbering
from tl_core.workflow.loader import load_workflows
from tl_mod_correspondence import domains as dm

SCHEMA_JSON = (
    Path(__file__).resolve().parents[4]
    / "packages/tl-schema/src/tl_schema/generated/json_schema/correspondence.domain.schema.json"
)
SOURCES = {"documents.transmittal"}


def systems() -> tuple[Any, Any]:
    return load_workflows(FIXTURES / "workflows"), load_numbering(
        FIXTURES / "numbering" / "patterns.yaml"
    )


def good() -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / "correspondence/domains/general.yaml").read_text())


def parse(data: dict[str, Any]) -> dm.DomainDefinition:
    return dm.parse_domain(yaml.safe_dump(data), source="t.yaml")


def problems(definition: dm.DomainDefinition) -> list[str]:
    workflows, numbering = systems()
    return dm.check_domain(
        definition, workflows=workflows, numbering=numbering, sources=SOURCES, source="t.yaml"
    )


def test_the_two_committed_domains_load_and_check_clean() -> None:
    workflows, numbering = systems()
    found = dm.load_domains(FIXTURES, workflows=workflows, numbering=numbering, sources=SOURCES)
    assert found.codes() == ["document_control", "general"]
    general = found.find("general", "project:P123")
    assert general is not None
    clock = general.subtype("letter").clocks[0]  # type: ignore[union-attr]
    assert (clock.trigger, clock.kind, clock.duration_days, clock.day_type) == (
        "issue",
        "response_from_them",
        14,
        "calendar",
    )
    assert clock.warn_days == (7, 3, 1)
    doc_control = found.find("document_control", "project:P123")
    assert doc_control is not None and doc_control.item_source == "documents.transmittal"


def test_the_committed_files_validate_against_the_generated_json_schema() -> None:
    schema = json.loads(SCHEMA_JSON.read_text())
    for name in ("general", "document-control"):
        data = yaml.safe_load((FIXTURES / f"correspondence/domains/{name}.yaml").read_text())
        jsonschema.validate(data, schema)


def test_the_model_and_the_linkml_class_have_the_same_fields() -> None:
    defs = json.loads(SCHEMA_JSON.read_text())["$defs"]
    pairs = {
        "CorrespondenceDomain": dm.DomainDefinition,
        "DomainSubtype": dm.DomainSubtype,
        "ClockTemplate": dm.ClockTemplate,
        "DomainRouting": dm.DomainRouting,
        "DomainIntegration": dm.DomainIntegration,
        "LetterTemplate": dm.LetterTemplate,
    }
    for name, model in pairs.items():
        assert set(defs[name]["properties"]) == set(model.model_fields), name


def test_a_bad_value_is_refused_with_the_source_and_the_path() -> None:
    data = good()
    data["subtypes"][0]["clocks"][0]["duration_days"] = 0
    with pytest.raises(dm.DomainError, match=r"t.yaml: subtypes.0.clocks.0.duration_days"):
        parse(data)


@pytest.mark.parametrize(
    "change",
    [
        {"code": "General"},
        {"code": "1x"},
        {"semver": "1.0"},
        {"semver": "1.0.0-rc1"},
        {"scope": "everywhere"},
        {"confidentiality_default": "secret"},
        {"feed_policy": "loud"},
        {"subtypes": []},
        {"extra_key": 1},
        {"required_psets": ["Bad Name"]},
        {"required_psets": ["a", "a"]},
        {"triage_keywords": ["UPPER"]},
        {"triage_keywords": ["a", "a"]},
        {"triage_keywords": ["x" * 80]},
        {"name": ""},
        {"item_source": 5},
        {"workflow_ref": ""},
    ],
)
def test_a_definition_that_breaks_the_format_is_refused(change: dict[str, Any]) -> None:
    data = good()
    data.update(change)
    with pytest.raises(dm.DomainError, match="t.yaml"):
        parse(data)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["subtypes"][0]["clocks"][0].update(day_type="weekly"),
        lambda d: d["subtypes"][0]["clocks"][0].update(warn_days=[3, 3]),
        lambda d: d["subtypes"][0]["clocks"][0].update(warn_days=[0]),
        lambda d: d["subtypes"][0]["clocks"][0].update(duration_days=3651),
        lambda d: d["subtypes"][0]["clocks"][0].update(duration_days="14"),
        lambda d: d["subtypes"][0]["clocks"][0].update(clause="no slash"),
        lambda d: d["subtypes"][0].update(code="Letter"),
        lambda d: d["subtypes"][0].update(clocks=[d["subtypes"][0]["clocks"][0]] * 6),
        lambda d: d["templates"][0].update(code="Bad Code"),
        lambda d: d["templates"][0].update(header="x" * 3000),
        lambda d: d["integration"].update(webhook_modes=["raw"]),
        lambda d: d.update(routing={"receive_roles": ["a"], "surprise": []}),
    ],
)
def test_a_nested_value_that_breaks_the_format_is_refused(mutate: Any) -> None:
    data = good()
    mutate(data)
    with pytest.raises(dm.DomainError):
        parse(data)


def test_booleans_are_not_taken_for_numbers_or_the_other_way_round() -> None:
    data = good()
    data["subtypes"][0]["response_required"] = "yes"
    with pytest.raises(dm.DomainError):
        parse(data)
    data = good()
    data["subtypes"][0]["clocks"][0]["duration_days"] = True
    with pytest.raises(dm.DomainError):
        parse(data)


def test_a_sound_definition_has_no_problems() -> None:
    assert problems(parse(good())) == []


def test_meaning_errors_are_all_reported() -> None:
    data = good()
    data["subtypes"].append(dict(data["subtypes"][0]))  # a repeated subtype
    data["default_subtype"] = "nothing"
    data["templates"][0]["subtype"] = "ghost"
    data["templates"].append(dict(data["templates"][0]))
    data["subtypes"][0]["clocks"][0]["warn_days"] = [20]
    data["workflow_ref"] = "no.such.workflow"
    data["numbering_pattern"] = "no.such.pattern"
    data["item_source"] = "other.source"
    found = problems(parse(data))
    text = "\n".join(found)
    for expected in (
        "subtype 'letter' is defined twice",
        "default_subtype 'nothing'",
        "unknown subtype 'ghost'",
        "template 'general-letter' is defined twice",
        "warns earlier than it is long",
        "no workflow 'no.such.workflow'",
        "no numbering pattern 'no.such.pattern'",
        "no register source 'other.source'",
    ):
        assert expected in text, expected
    assert all(line.startswith("t.yaml:") for line in found)


def test_text_that_is_not_a_domain_file_is_refused() -> None:
    for text in ("- a\n", "plain", "a: [", "&a [*a]"):
        with pytest.raises(dm.DomainError):
            dm.parse_domain(text, source="x")


def test_a_file_over_the_size_bound_is_refused_before_it_is_parsed() -> None:
    started = time.perf_counter()
    with pytest.raises(dm.DomainError, match="larger"):
        dm.parse_domain("a: " + "x" * dm.MAX_FILE_BYTES, source="big")
    assert time.perf_counter() - started < 1.0


def definition(code: str, scope: str, semver: str) -> dm.DomainDefinition:
    data = good()
    data.update(code=code, scope=scope, semver=semver)
    return parse(data)


def test_a_project_override_beats_the_company_default_and_the_newest_version_wins() -> None:
    found = dm.DomainSet(
        [
            definition("general", "company", "1.9.0"),
            definition("general", "company", "1.10.0"),
            definition("general", "project:P123", "1.0.0"),
            definition("other", "company", "2.0.0"),
        ]
    )
    best = found.find("general", "project:P123")
    assert best is not None and best.scope == "project:P123"
    company = found.find("general", "project:P999")
    assert company is not None and company.semver == "1.10.0"  # numbers, not text: 10 > 9
    assert found.find("general", "company") is not None
    assert found.find("nothing", "company") is None
    assert [d.code for d in found.for_scope("project:P123")] == ["general", "other"]


def test_a_definition_added_twice_is_refused() -> None:
    found = dm.DomainSet([definition("general", "company", "1.0.0")])
    with pytest.raises(dm.DomainError, match="twice"):
        found.add(definition("general", "company", "1.0.0"))


def test_loading_reads_the_domains_folder_and_names_the_bad_file(tmp_path: Path) -> None:
    folder = tmp_path / "correspondence" / "domains"
    folder.mkdir(parents=True)
    workflows, numbering = systems()
    assert (
        dm.load_domains(
            tmp_path / "nowhere", workflows=workflows, numbering=numbering, sources=SOURCES
        ).all()
        == []
    )
    (folder / "a.yaml").write_text(yaml.safe_dump(good()))
    (folder / "z.yaml").write_text(
        yaml.safe_dump({**good(), "workflow_ref": "nope", "code": "zed"})
    )
    with pytest.raises(dm.DomainError, match=r"z.yaml: no workflow 'nope'"):
        dm.load_domains(tmp_path, workflows=workflows, numbering=numbering, sources=SOURCES)
    (folder / "z.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(dm.DomainError, match="z.yaml: cannot read"):
        dm.load_domains(tmp_path, workflows=workflows, numbering=numbering, sources=SOURCES)
