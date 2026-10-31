"""``record_types()`` on every client (OC-T1): embedded, remote (over the real API) and the fake."""

from __future__ import annotations

from pathlib import Path

from fakes import FakeClient
from harness import Harness
from tl_adapters.sqlite.uow import create_schema
from tl_core.offline import RecordTypeRow, record_type_rows
from tl_schema.generated.offline_classes import OFFLINE_CLASSES
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient
from tl_tui.remote import RemoteClient


def check_rows(rows: list[RecordTypeRow]) -> None:
    assert rows == record_type_rows()
    assert [r.record_type for r in rows] == sorted(OFFLINE_CLASSES)
    by_type = {r.record_type: r for r in rows}
    assert by_type["engineering.Tag"].offline == "full"
    assert by_type["documents.Revision"].offline == "draft_only"
    assert by_type["documents.Revision"].drafting_commands == ["CreateRevision", "VoidRevision"]
    assert by_type["cost.CostCode"].offline == "none"
    assert all(isinstance(r, RecordTypeRow) for r in rows)


def test_the_embedded_client_answers_the_core_rows(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db)
    check_rows(client.record_types())


def test_the_embedded_client_needs_no_ledger_content(tmp_path: Path) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db)
    assert client.record_types() == client.record_types()


def test_the_remote_client_returns_the_rows_from_the_route(harness: Harness) -> None:
    check_rows(RemoteClient(harness.api()).record_types())


def test_the_fake_returns_the_core_rows_and_records_the_call() -> None:
    fake = FakeClient()
    check_rows(fake.record_types())
    assert fake.calls.count("record_types") == 1  # type: ignore[attr-defined]
    fake.record_types()
    assert fake.calls.count("record_types") == 2  # type: ignore[attr-defined]


def test_the_fake_and_the_real_clients_have_the_method_on_the_interface() -> None:
    assert callable(getattr(ClientInterface, "record_types"))  # noqa: B009
    assert callable(FakeClient().record_types)
    assert callable(getattr(EmbeddedClient, "record_types"))  # noqa: B009
