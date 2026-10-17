"""Registering and retiring document schemas (ADR-0014): what is checked, and what is kept."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.services.errors import DuplicateKeyError
from tl_mod_documents.derivation import rows
from tl_mod_documents.derivation.schemas import (
    RetireDocumentSchema,
    handle_retire_document_schema,
)
from tl_mod_documents.errors import InvalidDocumentSchemaError, SchemaNotFoundError
from tl_mod_documents.testing import INDEX_MAPPING, INDEX_SCHEMA


def refused(world: World, **more: Any) -> list[str]:
    with pytest.raises(InvalidDocumentSchemaError) as caught:
        world.register_schema(**more)
    return caught.value.problems


def test_a_schema_version_is_registered_with_its_key_and_hash(world: World) -> None:
    made = world.register_schema(sample=[{"tag": "47-FV-1001", "type": "CV"}])
    assert made.key == "instrument-index@1.0.0"
    with open_uow(world.db, readonly=True) as uow:
        found = rows.get_schema(uow.conn(), made.stream_id)
    assert found is not None and found.scope == "company" and found.ordinal == 1
    assert found.is_active and found.target_kind == "tags" and found.key_column == "tag"
    assert found.json_schema == INDEX_SCHEMA and found.mapping == INDEX_MAPPING
    assert found.sample == [{"tag": "47-FV-1001", "type": "CV"}] and len(found.content_hash) == 64
    events = [e.event_type for e in made.events]
    assert events == ["Record.Created", "DocumentSchema.Defined"]


def test_the_hash_follows_what_decides_the_verdict(world: World) -> None:
    first = world.register_schema(semver="1.0.0")
    same = world.register_schema(semver="1.0.1")
    other = copy.deepcopy(INDEX_SCHEMA)
    other["properties"]["size_in"]["minimum"] = 1
    different = world.register_schema(semver="1.0.2", json_schema=other)
    with open_uow(world.db, readonly=True) as uow:
        found = [rows.get_schema(uow.conn(), m.stream_id) for m in (first, same, different)]
    hashes = [f.content_hash for f in found if f is not None]
    assert hashes[0] == hashes[1] != hashes[2]


def test_versions_are_ordered_and_must_rise(world: World) -> None:
    world.register_schema(semver="1.0.0")
    world.register_schema(semver="1.2.0")
    assert "must be higher than 1.2.0" in " ".join(refused(world, semver="1.1.9"))
    assert "must be higher than 1.2.0" in " ".join(refused(world, semver="1.2.0"))
    world.register_schema(semver="1.10.0")  # numbers, not text, are compared
    with open_uow(world.db, readonly=True) as uow:
        versions = rows.list_schemas(uow.conn(), "company", code="instrument-index")
    assert [(v.semver, v.ordinal) for v in versions] == [("1.0.0", 1), ("1.2.0", 2), ("1.10.0", 3)]


def test_a_project_can_have_its_own_variant_and_reads_its_own_first(world: World) -> None:
    world.register_schema()
    world.register_schema(semver="1.0.0", scope="project:P123", title="P123 index")
    with open_uow(world.db, readonly=True) as uow:
        mine = rows.resolve_schema(uow.conn(), "project:P123", "instrument-index")
        other = rows.resolve_schema(uow.conn(), "project:P999", "instrument-index")
    assert mine is not None and mine.scope == "project:P123"
    assert other is not None and other.scope == "company"


def test_every_problem_is_listed_at_once(world: World) -> None:
    problems = refused(
        world,
        code="Bad Code",
        semver="1.0",
        json_schema={"type": "object", "properties": {"tag": {"type": "string"}}},
        mapping=None,
        target_kind="tags",
        key_column="nowhere",
        doc_types=["A", "A"],
    )
    text = " | ".join(problems)
    for fragment in (
        "code must be",
        "semver must be",
        "mapping and target_kind go together",
        "key_column 'nowhere' is not a property",
        "doc_types must be distinct",
    ):
        assert fragment in text, text


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"json_schema": {"type": "object"}}, "type object with properties"),
        (
            {"json_schema": {"type": "array", "properties": {"a": {}}}},
            "type object with properties",
        ),
        (
            {"json_schema": {"type": "object", "properties": {"a": {"type": "nope"}}}},
            "not a valid JSON Schema",
        ),
        (
            {
                "json_schema": {
                    "type": "object",
                    "properties": {"a": {"$ref": "http://evil.example/x"}},
                }
            },
            "refer only to itself",
        ),
        ({"json_schema": {"type": "object", "properties": {" a": {}}}}, "blank or has spaces"),
        ({"sample": [{"tag": "bad", "type": "CV"}]}, "sample row 1"),
        (
            {"mapping": {**INDEX_MAPPING, "target": "documents"}, "target_kind": "documents"},
            "mapping:",
        ),
        ({"target_kind": None}, "go together"),
    ],
)
def test_a_schema_that_cannot_be_used_is_refused_with_the_reason(
    world: World, change: dict[str, Any], fragment: str
) -> None:
    assert fragment in " | ".join(refused(world, **change))


def test_a_huge_schema_is_refused_before_it_is_read(world: World) -> None:
    big = {
        "type": "object",
        "properties": {f"c{i}": {"description": "x" * 2000} for i in range(200)},
    }
    assert "larger than" in " | ".join(refused(world, json_schema=big))
    many = {"type": "object", "properties": {f"c{i}": {} for i in range(201)}}
    assert "more than 200 properties" in " | ".join(refused(world, json_schema=many))


def test_the_same_version_twice_is_a_duplicate_key(world: World) -> None:
    world.register_schema()
    with pytest.raises((DuplicateKeyError, InvalidDocumentSchemaError)):
        world.register_schema()


def test_a_schema_can_be_retired_once_and_is_then_not_picked(world: World) -> None:
    old = world.register_schema(semver="1.0.0")
    new = world.register_schema(semver="1.1.0")
    with open_uow(world.db) as uow:
        handle_retire_document_schema(
            uow,
            RetireDocumentSchema(
                **{**BASE, "scope": "company"}, stream_id=new.stream_id, reason="bad"
            ),
        )
    with open_uow(world.db, readonly=True) as uow:
        latest = rows.find_schema(uow.conn(), "company", "instrument-index")
        retired = rows.get_schema(uow.conn(), new.stream_id)
        exact = rows.find_schema(uow.conn(), "company", "instrument-index", "1.1.0")
    assert latest is not None and latest.id == old.stream_id  # the newest active one
    assert retired is not None and not retired.is_active and retired.retired_reason == "bad"
    assert exact is not None and exact.id == new.stream_id  # a retired version is still readable
    with (
        open_uow(world.db) as uow,
        pytest.raises(InvalidDocumentSchemaError, match="already retired"),
    ):
        handle_retire_document_schema(
            uow,
            RetireDocumentSchema(
                **{**BASE, "scope": "company"}, stream_id=new.stream_id, reason="again"
            ),
        )
    with open_uow(world.db) as uow, pytest.raises(SchemaNotFoundError):
        handle_retire_document_schema(
            uow, RetireDocumentSchema(**BASE, stream_id=new.stream_id, reason="wrong scope")
        )
