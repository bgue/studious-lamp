"""EmbeddedClient over a real SQLite ledger (P0-I2-T11)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tl_adapters.sqlite.uow import create_schema
from tl_core.ledger import ConcurrencyError
from tl_core.services import psets
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_core.services.errors import DuplicateKeyError
from tl_core.services.psets import SetPsetValues
from tl_schema.forms import ConformanceReport, FormMetadata
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient
from tl_tui.errors import CLIENT_ERRORS, describe_error

SCOPE = "project:P123"


@pytest.fixture
def client(tmp_path: Path) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    return EmbeddedClient.for_sqlite(db)


def _create(client: ClientInterface, key: str, title: str = "t") -> str:
    result = client.create_record(
        CreateRecord(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            record_type="core.Record",
            title=title,
            key=key,
        )
    )
    return result.stream_id


def test_embedded_client_satisfies_the_protocol(client: EmbeddedClient) -> None:
    as_protocol: ClientInterface = client
    assert as_protocol.list_records(SCOPE) == []


def test_create_get_and_list(client: EmbeddedClient) -> None:
    first = _create(client, "R-1", "First")
    _create(client, "R-2", "Second")

    assert client.get_record(SCOPE, "R-1") is not None
    by_id = client.get_record_by_id(first)
    assert by_id is not None and by_id["title"] == "First"
    assert client.get_record_by_id("missing") is None
    assert client.get_record(SCOPE, "nope") is None
    assert [r["key"] for r in client.list_records(SCOPE)] == ["R-1", "R-2"]
    assert [r["key"] for r in client.list_records(SCOPE, limit=1, offset=1)] == ["R-2"]
    assert client.list_records(SCOPE, record_type="other.Type") == []
    assert client.list_records("project:other") == []


def test_update_record_and_history(client: EmbeddedClient) -> None:
    record_id = _create(client, "R-1", "Old")
    result = client.update_record(
        UpdateRecord(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id=record_id,
            expected_version=1,
            changes={"title": "New"},
        )
    )
    assert result.version == 2
    events = client.history(record_id)
    assert [e.event_type for e in events] == ["Record.Created", "Record.Updated"]
    record = client.get_record_by_id(record_id)
    assert record is not None and record["title"] == "New" and record["version"] == 2


def test_service_errors_propagate_and_are_described(client: EmbeddedClient) -> None:
    record_id = _create(client, "R-1")
    with pytest.raises(DuplicateKeyError) as dup:
        _create(client, "R-1")
    assert isinstance(dup.value, CLIENT_ERRORS)
    assert "R-1" in describe_error(dup.value)

    with pytest.raises(ConcurrencyError) as conflict:
        client.update_record(
            UpdateRecord(
                actor="user:t",
                source="tui",
                scope=SCOPE,
                stream_id=record_id,
                expected_version=7,
                changes={"title": "x"},
            )
        )
    assert "reload" in describe_error(conflict.value)


def test_pset_methods_delegate_to_the_pset_services(
    client: EmbeddedClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    report = ConformanceReport(status="ok", issues=[], effective_schema_hash="h")
    meta = FormMetadata(
        record_type="core.Record", effective_schema_hash="h", core_fields=[], psets=[]
    )

    def fake_set(uow: object, cmd: SetPsetValues) -> CommandResult:
        calls.append(f"set:{cmd.pset}")
        return CommandResult(stream_id=cmd.stream_id, key=None, version=2, events=[])

    monkeypatch.setattr(psets, "handle_set_pset_values", fake_set)
    monkeypatch.setattr(psets, "form_metadata", lambda uow, scope, rt: meta)
    monkeypatch.setattr(psets, "conformance", lambda uow, rid: report)

    result = client.set_pset_values(
        SetPsetValues(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id="s",
            expected_version=1,
            pset="valve_data",
            layer="standard",
            values={"size_in": 6.0},
        )
    )
    assert result.version == 2 and calls == ["set:valve_data"]
    assert client.form_metadata(SCOPE, "core.Record") is meta
    assert client.conformance("s") is report
