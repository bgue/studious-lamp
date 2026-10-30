"""Ad-hoc custom fields through ``SetPsetValues`` (P1-UX3 round 4).

A set whose ``custom_section.allowed`` is true takes a custom field its schema does not declare,
under ``x.<name>``, up to ``custom_section.max_properties`` names per record and set. The fixture
set ``valve_data`` allows ten; the P123 extension declares ``fat_witness_by`` and
``tie_in_window``; ``safety_data`` (company scope) allows none.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services.commands import CommandResult, CreateRecord
from tl_core.services.errors import (
    LayerError,
    NoChangesError,
    PsetValidationError,
    RecordNotFoundError,
)
from tl_core.services.psets import (
    CUSTOM_NAME_PATTERN,
    SetPsetValues,
    conformance,
    custom_name_problem,
    custom_value_problem,
    handle_set_pset_values,
    stored_custom_names,
)
from tl_core.services.records import handle_create_record

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"
MAX = 10  # valve_data: custom_section.max_properties


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    path = new_db()
    create_schema(path)
    return path


def make(db: DbTarget, key: str = "V-1", scope: str = SCOPE) -> CommandResult:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="user:u",
                source="test",
                scope=scope,
                record_type="core.Record",
                title="Valve",
                key=key,
            ),
        )


def put(
    db: DbTarget,
    record: CommandResult,
    values: dict[str, Any],
    *,
    pset: str = "valve_data",
    version: int | None = None,
    scope: str = SCOPE,
    layer: str = "custom",
) -> CommandResult:
    cmd = SetPsetValues(
        actor="user:u",
        source="test",
        scope=scope,
        stream_id=record.stream_id,
        expected_version=record.version if version is None else version,
        pset=pset,
        layer=layer,  # type: ignore[arg-type]
        values=values,
    )
    with open_uow(db) as uow:
        return handle_set_pset_values(uow, cmd)


def stored(db: DbTarget, record: CommandResult) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT psets_json FROM cur_core_record WHERE id = :id"),
            {"id": record.stream_id},
        )
        return json.loads(found.scalar_one())


def events(db: DbTarget) -> int:
    with open_uow(db, readonly=True) as uow:
        return uow.ledger.head_seq()


# --- the rule itself -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a", "fat_witness_by", "w2", "a" * 40, "k_9_z"])
def test_a_good_name_is_accepted(name: str) -> None:
    assert custom_name_problem(name) is None
    assert CUSTOM_NAME_PATTERN.fullmatch(name)


@pytest.mark.parametrize(
    "name",
    ["", "A", "Fat", "1abc", "_a", "a b", "a-b", "a.b", "é", "a" * 41, "a__b", "x", "x_note"]
    + ["prj", "prj_x", "enrich", "enrich_ai", "src", "src_ifc"],
)
def test_a_bad_or_reserved_name_is_refused(name: str) -> None:
    assert custom_name_problem(name) is not None


def test_a_name_that_only_looks_like_a_reserved_prefix_is_fine() -> None:
    for name in ("xray", "prjx", "source", "enriched"):
        assert custom_name_problem(name) is None, name


@pytest.mark.parametrize("value", [None, "text", "", 4, 2.5, 0, -1])
def test_a_text_or_number_value_is_accepted(value: Any) -> None:
    assert custom_value_problem(value) is None


@pytest.mark.parametrize("value", [True, [1], {"a": 1}, float("nan"), float("inf"), "z" * 2001])
def test_other_values_are_refused(value: Any) -> None:
    assert custom_value_problem(value) is not None


# --- the command -----------------------------------------------------------------------------


def test_an_undeclared_custom_field_is_kept_and_stays_conformant(db: DbTarget) -> None:
    record = make(db)
    done = put(db, record, {"x.inspector_note": "checked on site"})
    assert stored(db, record) == {"valve_data": {"x": {"inspector_note": "checked on site"}}}
    assert done.events[0].payload["layer"] == "custom"
    with open_uow(db, readonly=True) as uow:
        report = conformance(uow, record.stream_id)
    assert not [i for i in report.issues if ".x" in i.path]
    assert report.status != "nonconformant"


def test_a_number_stays_a_number_and_text_stays_text(db: DbTarget) -> None:
    record = make(db)
    put(db, record, {"x.lead_time_days": 14, "x.supplier_ref": "A-7", "x.due": "2026-12-01"})
    held = stored(db, record)["valve_data"]["x"]
    assert held == {"lead_time_days": 14, "supplier_ref": "A-7", "due": "2026-12-01"}
    assert isinstance(held["lead_time_days"], int)


def test_a_declared_custom_field_still_works_and_is_typed(db: DbTarget) -> None:
    record = make(db)
    put(db, record, {"x.fat_witness_by": "client"})
    with pytest.raises(PsetValidationError):
        put(db, record, {"x.tie_in_window": 5}, version=2)  # declared as text


@pytest.mark.parametrize("name", ["Bad", "1st", "a b", "a" * 41, "x", "prj_note", "enrich_a"])
def test_a_bad_name_is_refused_and_nothing_is_written(db: DbTarget, name: str) -> None:
    record = make(db)
    before = events(db)
    with pytest.raises(PsetValidationError):
        put(db, record, {f"x.{name}": "v"})
    assert events(db) == before


def test_a_name_that_collides_with_a_declared_property_is_refused(db: DbTarget) -> None:
    record = make(db)
    with pytest.raises(PsetValidationError) as caught:
        put(db, record, {"x.size_in": "4"})
    assert "already a property" in str(caught.value)


@pytest.mark.parametrize("value", [True, ["a"], {"a": 1}, "z" * 2001])
def test_a_value_that_is_not_text_or_a_number_is_refused(db: DbTarget, value: Any) -> None:
    record = make(db)
    with pytest.raises(PsetValidationError):
        put(db, record, {"x.note": value})


def test_the_limit_counts_distinct_names_per_record_and_set(db: DbTarget) -> None:
    record = make(db)
    other = make(db, key="V-2")
    done = put(db, record, {f"x.f{i}": i for i in range(MAX)})
    assert len(stored_custom_names(stored(db, record), "valve_data")) == MAX
    with pytest.raises(PsetValidationError) as caught:
        put(db, record, {"x.one_more": 1}, version=done.version)
    assert str(MAX) in str(caught.value)
    # an existing name can still change, and another record has its own room
    put(db, record, {"x.f3": 99}, version=done.version)
    put(db, other, {"x.one_more": 1})


def test_the_limit_includes_the_names_of_the_same_write(db: DbTarget) -> None:
    record = make(db)
    with pytest.raises(PsetValidationError):
        put(db, record, {f"x.f{i}": i for i in range(MAX + 1)})
    assert stored(db, record) == {}


def test_clearing_a_field_makes_room(db: DbTarget) -> None:
    record = make(db)
    done = put(db, record, {f"x.f{i}": i for i in range(MAX)})
    cleared = put(db, record, {"x.f0": None}, version=done.version)
    put(db, record, {"x.fresh": "v"}, version=cleared.version)
    assert "f0" not in stored(db, record)["valve_data"]["x"]


def test_clearing_a_name_that_was_never_there_changes_nothing(db: DbTarget) -> None:
    record = make(db)
    with pytest.raises(NoChangesError):
        put(db, record, {"x.never_set": None})


def test_a_set_with_no_custom_section_takes_none(db: DbTarget) -> None:
    record = make(db, scope="company")
    with pytest.raises(LayerError):
        put(db, record, {"x.note": "n"}, pset="safety_data", scope="company")


def test_a_custom_key_needs_the_custom_layer_and_a_plain_key_does_not(db: DbTarget) -> None:
    record = make(db)
    with pytest.raises(LayerError):
        put(db, record, {"x.note": "n"}, layer="standard")
    with pytest.raises(LayerError):
        put(db, record, {"note": "n"})


def test_a_project_set_takes_no_ad_hoc_field(db: DbTarget) -> None:
    record = make(db)
    with pytest.raises(LayerError):
        put(db, record, {"x.note": "n"}, pset="prj.shutdown_tie_in", layer="custom")


def test_a_missing_record_is_refused_before_the_name_is_looked_at(db: DbTarget) -> None:
    """The record is looked up first, so a bad name tells nothing about a record that is not
    there (or hidden): both answer ``RecordNotFoundError`` whatever the name."""
    record = make(db)
    gone = CommandResult(stream_id="01J000000000000000000000", key="X", version=1, events=[])
    for key in ("x.good_name", "x.Bad Name", "x.prj_x"):
        with pytest.raises(RecordNotFoundError):
            put(db, gone, {key: "v"})
    assert record.version == 1
