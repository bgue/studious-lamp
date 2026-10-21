"""Record-type display names and the example property sets of the company standard (P1-UX-S3)."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from tl_schema.compose import compose
from tl_schema.conformance import evaluate
from tl_schema.effective import EffectivePset, EffectiveSchema
from tl_schema.generated.type_labels import TYPE_LABELS
from tl_schema.generators import type_labels
from tl_schema.packages import PackageDoc

REPO = Path(__file__).resolve().parents[3]
TODAY = date(2026, 10, 21)
NEW_SETS = ("document_data", "rfi_data", "correspondence_data")
APPLIES_TO = {
    "document_data": {"documents.Document"},
    "rfi_data": {"correspondence.TechnicalItem"},
    "correspondence_data": {"correspondence.Correspondence", "correspondence.CommercialItem"},
}


def _module_record_types() -> set[str]:
    """Every string in a module's ``RECORD_TYPES`` constant, read from its ``names.py`` source."""
    found: set[str] = set()
    for path in sorted((REPO / "packages" / "tl-modules").glob("*/src/*/names.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants: dict[str, str] = {}
        members: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                constants[node.target.id] = value.value
            elif node.target.id == "RECORD_TYPES" and isinstance(value, ast.Call):
                members = [n.id for n in ast.walk(value.args[0]) if isinstance(n, ast.Name)]
        assert members, f"{path}: no RECORD_TYPES"
        found.update(constants[name] for name in members)
    return found


def test_every_record_type_has_a_title() -> None:
    types = _module_record_types()
    assert len(types) >= 30
    assert sorted(types - set(TYPE_LABELS)) == []
    assert TYPE_LABELS["core.Record"] == "Record"
    assert all(label.strip() for label in TYPE_LABELS.values())


def test_labels_are_plain_words() -> None:
    for record_type, label in TYPE_LABELS.items():
        assert "." not in label, record_type
        assert not re.search(r"[a-z][A-Z]", label), f"{record_type}: {label!r} looks like CamelCase"
        assert re.fullmatch(r"[A-Z][A-Za-z]*( [A-Za-z]+)*", label), f"{record_type}: {label!r}"


def test_the_committed_labels_are_what_the_generator_writes() -> None:
    assert dict(type_labels.labels(REPO / "schema" / "core")) == TYPE_LABELS


def test_a_record_type_without_a_title_stops_the_generator(tmp_path: Path) -> None:
    core = tmp_path / "core"
    core.mkdir()
    for source in (REPO / "schema" / "core").glob("*.yaml"):
        text = source.read_text(encoding="utf-8")
        if source.name == "record.yaml":
            assert text.count("    title: Record\n") == 1
            text = text.replace("    title: Record\n", "")
        (core / source.name).write_text(text, encoding="utf-8")
    with pytest.raises(type_labels.TypeLabelsError, match="core.Record"):
        type_labels.labels(core)


@pytest.fixture
def effective(build_docs: Callable[..., list[PackageDoc]]) -> EffectiveSchema:
    """The company standard alone, in company scope (an optional set is dropped from projects)."""
    return compose([d for d in build_docs() if d.kind == "company"], "company")


def _set(schema: EffectiveSchema, name: str) -> EffectivePset:
    return schema.psets[name]


def test_the_three_new_sets_have_labels_units_a_required_property_and_a_code_list(
    effective: EffectiveSchema,
) -> None:
    for name in NEW_SETS:
        pset = _set(effective, name)
        assert pset.label and pset.enforcement == "advisory" and pset.adoption == "optional"
        props = list(pset.properties.values())
        assert all(p.label and p.description for p in props), name
        required = [p for p in props if "*" in p.required_in_states]
        assert required and all(p.enforcement == "advisory" for p in required), name
        assert any(p.code_list and p.enum_values for p in props), name
    days = _set(effective, "rfi_data").properties["schedule_impact_days"]
    assert days.kind == "int" and days.unit == "d"
    estimate = _set(effective, "rfi_data").properties["cost_estimate"]
    assert estimate.kind == "decimal"
    assert [
        v.code for v in _set(effective, "rfi_data").properties["cost_currency"].enum_values or []
    ][:2] == ["USD", "EUR"]
    assert "cost_currency" in _set(effective, "rfi_data").properties


def test_the_new_sets_apply_to_the_module_record_types(effective: EffectiveSchema) -> None:
    for name, types in APPLIES_TO.items():
        assert set(_set(effective, name).applies_to) == types, name
        assert "core.Record" not in _set(effective, name).applies_to
    assert {p.name for p in effective.psets_for("correspondence.TechnicalItem")} >= {"rfi_data"}
    assert "rfi_data" not in {p.name for p in effective.psets_for("documents.Document")}
    assert "document_data" in {p.name for p in effective.psets_for("documents.Document")}


def test_an_existing_demo_record_stays_conformant_with_the_new_sets(
    effective: EffectiveSchema,
) -> None:
    # a document with the provenance values a publication wrote, and none of the new sets
    existing: dict[str, Any] = {"provenance": {"source": "src.doc.ISO-0101@C"}}
    for record_type in APPLIES_TO["document_data"]:
        report = evaluate(effective, record_type, existing, on=TODAY)
        assert report.status == "ok", report.issues
    for record_type in APPLIES_TO["rfi_data"] | APPLIES_TO["correspondence_data"]:
        assert evaluate(effective, record_type, {}, on=TODAY).status == "ok"


def test_a_partly_filled_example_set_warns_and_never_blocks(effective: EffectiveSchema) -> None:
    report = evaluate(
        effective, "documents.Document", {"document_data": {"area": "Unit 47"}}, on=TODAY
    )
    assert [(i.path, i.level) for i in report.issues] == [
        ("psets.document_data.originator", "warning")
    ]
    filled = {"document_data": {"originator": "ACME", "native_format": "DWG"}}
    assert evaluate(effective, "documents.Document", filled, on=TODAY).status == "ok"
    bad = {"document_data": {"originator": "ACME", "native_format": "ZZZ"}}
    assert evaluate(effective, "documents.Document", bad, on=TODAY).status != "ok"


def test_an_optional_set_is_left_out_of_a_project_that_does_not_adopt_it(
    build_docs: Callable[..., list[PackageDoc]],
) -> None:
    project = compose(build_docs(), "project:P123")
    assert not set(NEW_SETS) & set(project.psets)
