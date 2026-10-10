"""`query_records` and `count_records` on the embedded client and on the FakeClient (O3, P0-I4).

The embedded client is checked against a real SQLite ledger. The fake must agree with it on the
same queries, because every screen test relies on the fake, and it must raise the same syntax
error with the same position.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeClient, keys
from tl_adapters.sqlite.uow import create_schema
from tl_core.query import QuerySyntaxError
from tl_core.services.commands import CommandResult, CreateRecord, UpdateRecord
from tl_tui.client import ClientInterface
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"


def _create(client: ClientInterface, key: str, title: str) -> CommandResult:
    return client.create_record(
        CreateRecord(
            actor="user:t",
            source="test",
            scope=SCOPE,
            record_type="core.Record",
            key=key,
            title=title,
        )
    )


@pytest.fixture
def embedded(tmp_path: Path) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    client = EmbeddedClient.for_sqlite(db)
    for key, title in [("A-1", "Bevel gauge"), ("A-2", "Pipe spool"), ("A-3", "Bevel plate")]:
        _create(client, key, title)
    return client


def seeded_fake() -> FakeClient:
    client = FakeClient()
    for key, title in [("A-1", "Bevel gauge"), ("A-2", "Pipe spool"), ("A-3", "Bevel plate")]:
        _create(client, key, title)
    return client


@pytest.fixture(params=["embedded", "fake"])
def client(request: pytest.FixtureRequest, embedded: EmbeddedClient) -> ClientInterface:
    return embedded if request.param == "embedded" else seeded_fake()


def test_blank_text_matches_every_record(client: ClientInterface) -> None:
    assert keys(client.query_records(SCOPE, "")) == ["A-1", "A-2", "A-3"]
    assert client.count_records(SCOPE, "  ") == 3


def test_text_and_field_terms_filter_and_count_agree(client: ClientInterface) -> None:
    assert keys(client.query_records(SCOPE, "title~bevel")) == ["A-1", "A-3"]
    assert client.count_records(SCOPE, "title~bevel") == 2
    assert keys(client.query_records(SCOPE, "bevel -key:A-3")) == ["A-1"]
    assert client.count_records(SCOPE, "nothing-like-this") == 0


def test_limit_offset_and_order_page_the_matches(client: ClientInterface) -> None:
    page = client.query_records(SCOPE, "title~bevel", limit=1, offset=1, order_by=[("key", "desc")])
    assert keys(page) == ["A-1"]
    assert client.count_records(SCOPE, "title~bevel") == 2  # the count ignores the page


def test_another_scope_is_not_searched(client: ClientInterface) -> None:
    assert client.query_records("project:OTHER", "") == []
    assert client.count_records("project:OTHER", "") == 0


def test_a_syntax_error_carries_the_position_of_the_bad_character(
    client: ClientInterface,
) -> None:
    with pytest.raises(QuerySyntaxError) as raised:
        client.query_records(SCOPE, "status:open )")
    assert raised.value.position == 12
    with pytest.raises(QuerySyntaxError) as counted:
        client.count_records(SCOPE, "nosuchfield:1")
    assert counted.value.position == 0


def test_a_changed_title_is_found_by_its_new_value(embedded: EmbeddedClient) -> None:
    record = embedded.get_record(SCOPE, "A-2")
    assert record is not None
    embedded.update_record(
        UpdateRecord(
            actor="user:t",
            source="test",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            changes={"title": "Renamed"},
        )
    )
    assert keys(embedded.query_records(SCOPE, "title:Renamed")) == ["A-2"]


def test_the_embedded_client_notes_the_events_of_its_own_commands(
    embedded: EmbeddedClient,
) -> None:
    result = _create(embedded, "A-9", "Mine")
    assert all(event.event_id in embedded.own_writes for event in result.events)
    assert len(embedded.own_writes) == 4  # the three seeded records and this one
