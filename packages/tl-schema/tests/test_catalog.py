"""The event catalog generator: schemas, samples, AsyncAPI, and agreement with the code."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tl_schema import generate
from tl_schema.generators import catalog

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def events() -> list[Any]:
    return catalog.build_events(generate.SCHEMA_DIR)


def validator(schema: dict[str, Any]) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def test_every_event_class_is_in_the_catalog_with_a_stable_name(events: list[Any]) -> None:
    names = [e.event_type for e in events]
    assert names == sorted(names) and len(set(names)) == len(names)
    assert {"Record.Created", "Workflow.Transitioned", "File.Uploaded", "Link.Added"} <= set(names)
    for e in events:
        assert e.ce_type == f"tl.core.{e.event_type}.v{e.version}"
        assert re.fullmatch(r"[A-Z]\w*\.[A-Z]\w*", e.event_type)
        assert e.title.endswith(".") and e.payload_class.endswith("Payload")


#: String literals shaped like an event type that are not catalog events, each with its reason.
NOT_EVENTS = {
    "Test.Bumped": "event type of the test-only counter projector (projection/testing.py)",
    # P0-I6 contract only (tl_core/proposals/types.py): WS-B adds schema/core/proposals.yaml with
    # these catalog classes and removes these four entries in the same change.
    "Proposal.Created": "P0-I6 WS-B contract; catalog class pending",
    "Proposal.Accepted": "P0-I6 WS-B contract; catalog class pending",
    "Proposal.Rejected": "P0-I6 WS-B contract; catalog class pending",
    "Proposal.Failed": "P0-I6 WS-B contract; catalog class pending",
}
EVENT_LITERAL = re.compile(r"[A-Z]\w*\.[A-Z]\w*")


def event_like_literals(packages: Path) -> set[str]:
    """Every string literal in ``packages/*/src`` shaped ``Class.Verb``, generated code excluded.

    A literal anywhere counts (an ``event_type=`` argument, a frozenset of handled types, a handler
    comparison), so an event type cannot slip past the catalog by being named in a new way.
    """
    found: set[str] = set()
    for path in packages.glob("*/src/**/*.py"):
        if "generated" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if EVENT_LITERAL.fullmatch(node.value):
                    found.add(node.value)
    return found


def uncatalogued(packages: Path, catalogued: set[str]) -> set[str]:
    return event_like_literals(packages) - catalogued - set(NOT_EVENTS)


def test_every_event_type_the_code_names_is_in_the_catalog(events: list[Any]) -> None:
    """Add a class to schema/core/events.yaml in the same change that adds an event type."""
    missing = uncatalogued(REPO / "packages", {e.event_type for e in events})
    assert not missing, f"event types without a catalog class: {sorted(missing)}"


def test_the_coverage_scan_sees_an_unknown_type_and_ignores_generated_code(
    tmp_path: Path, events: list[Any]
) -> None:
    source = tmp_path / "demo" / "src" / "demo"
    source.mkdir(parents=True)
    (source / "handlers.py").write_text(
        'HANDLED = frozenset({"Record.Created", "Fake.Thing"})\n'
        'def handle(event_type):\n    return event_type == "Other.Unknown"\n'
    )
    generated = source / "generated"
    generated.mkdir()
    (generated / "models.py").write_text('X = "Generated.Noise"\n')
    catalogued = {e.event_type for e in events}
    assert uncatalogued(tmp_path, catalogued) == {"Fake.Thing", "Other.Unknown"}


def test_the_catalog_coverage_scan_catches_a_removed_event_class(events: list[Any]) -> None:
    without_link_added = {e.event_type for e in events} - {"Link.Added"}
    assert "Link.Added" in uncatalogued(REPO / "packages", without_link_added)


def test_samples_validate_against_their_own_schemas(events: list[Any]) -> None:
    for e in events:
        payload_errors = list(validator(e.payload_schema).iter_errors(e.sample_payload))
        assert not payload_errors, (e.event_type, payload_errors[:1])
        envelope_errors = list(validator(e.envelope_schema).iter_errors(e.sample_envelope))
        assert not envelope_errors, (e.event_type, envelope_errors[:1])
        assert e.sample_envelope["data"]["detail"] == e.sample_payload


def test_the_envelope_schema_pins_type_and_rejects_other_events(events: list[Any]) -> None:
    created = next(e for e in events if e.event_type == "Record.Created")
    other = next(e for e in events if e.event_type == "Record.Voided")
    assert validator(created.envelope_schema).is_valid(created.sample_envelope)
    assert not validator(created.envelope_schema).is_valid(other.sample_envelope)
    broken = json.loads(json.dumps(created.sample_envelope))
    del broken["tlseq"]
    assert not validator(created.envelope_schema).is_valid(broken)
    broken = json.loads(json.dumps(created.sample_envelope))
    broken["data"]["detail"]["title"] = 7
    assert not validator(created.envelope_schema).is_valid(broken)


def test_payloads_are_open_and_any_json_is_really_any(events: list[Any]) -> None:
    transitioned = next(e for e in events if e.event_type == "Workflow.Transitioned")
    assert transitioned.payload_schema["additionalProperties"] is True
    payload = {**transitioned.sample_payload, "future_field": 1, "guards_evaluated": [1, 2]}
    assert validator(transitioned.payload_schema).is_valid(payload)
    assert not validator(transitioned.payload_schema).is_valid({"workflow": "x"})


def test_the_asyncapi_document_covers_every_event_type(events: list[Any]) -> None:
    files = catalog.generate(generate.SCHEMA_DIR)
    doc = json.loads(files["catalog/asyncapi.json"])
    assert doc["asyncapi"] == "3.0.0"
    assert set(doc["channels"]) == {e.event_type for e in events}
    index = json.loads(files["catalog/index.json"])["events"]
    assert [i["event_type"] for i in index] == [e.event_type for e in events]
    assert "## Record.Created" in files["docs/event-catalog.md"]


def test_the_output_is_deterministic() -> None:
    assert catalog.generate(generate.SCHEMA_DIR) == catalog.generate(generate.SCHEMA_DIR)
