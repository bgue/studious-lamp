"""form_metadata and conformance services over a real SQLite ledger (P0-I2)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from tl_adapters.db import DbTarget, create_schema, open_uow
from tl_core.schema_provider import DirectorySchemaProvider, get_provider, use_provider
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.psets import conformance, form_metadata
from tl_core.services.records import handle_create_record
from tl_core.util import new_ulid

FIXTURES = Path(__file__).resolve().parents[2] / "schema" / "fixtures"
SCOPE = "project:P123"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def db(new_db: Callable[[], DbTarget]) -> DbTarget:
    path = new_db()
    create_schema(path)
    return path


def create(db: DbTarget, key: str, psets: dict[str, object]) -> str:
    with open_uow(db) as uow:
        result = handle_create_record(
            uow,
            CreateRecord(
                actor="user:u",
                source="test",
                scope=SCOPE,
                record_type="core.Record",
                title="Valve",
                key=key,
                psets=psets,
            ),
        )
    return result.stream_id


def test_form_metadata_describes_the_scope(db: DbTarget) -> None:
    with open_uow(db, readonly=True) as uow:
        meta = form_metadata(uow, SCOPE, "core.Record")
        again = form_metadata(uow, SCOPE, "core.Record")
        company = form_metadata(uow, "company", "core.Record")
    assert meta.effective_schema_hash == get_provider().effective(SCOPE).hash
    assert [g.name for g in meta.psets] == ["valve_data", "prj.shutdown_tie_in"]
    assert meta == again and meta is not again  # callers get their own copy
    assert [g.name for g in company.psets] == ["safety_data", "valve_data"]
    assert company.effective_schema_hash != meta.effective_schema_hash


def test_conformance_of_a_record(db: DbTarget) -> None:
    clean = create(db, "V-1", {})
    partial = create(db, "V-2", {"valve_data": {"size_in": 4}})
    broken = create(db, "V-3", {"valve_data": {"size_in": 500, "manufacturer": "A"}})
    with open_uow(db, readonly=True) as uow:
        ok = conformance(uow, clean)
        warn = conformance(uow, partial)
        bad = conformance(uow, broken)
    schema_hash = get_provider().effective(SCOPE).hash
    assert (ok.status, ok.issues, ok.effective_schema_hash) == ("ok", [], schema_hash)
    assert warn.status == "warning"
    assert [(i.path, i.rule) for i in warn.issues] == [
        ("psets.valve_data.manufacturer", "required_in_state")
    ]
    assert bad.status == "nonconformant"
    assert [(i.path, i.rule) for i in bad.issues] == [("psets.valve_data.size_in", "range")]


def test_conformance_of_an_unknown_record(db: DbTarget) -> None:
    with open_uow(db, readonly=True) as uow, pytest.raises(RecordNotFoundError):
        conformance(uow, new_ulid())
