"""The Properties tab: the sets that apply to the record's type and class (P1-UX-S2)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.app import App, ComposeResult
from textual.pilot import Pilot
from tl_adapters.db import open_uow
from tl_adapters.sqlite.uow import create_schema
from tl_core.schema_provider import DirectorySchemaProvider, get_provider, use_provider
from tl_mod_engineering.handlers.tags import CreateTag, handle_create_tag
from tl_mod_engineering.testing import seed_registry
from tl_schema.formgen import form_metadata
from tl_tui.display import find_technical
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.psets_tab import PsetsTab
from tl_tui.widgets.record_view import RecordView

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"


@pytest.fixture
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


class Host(App[None]):
    def __init__(self, client: Any, key: str) -> None:
        super().__init__()
        self.client = client
        self.key = key

    def compose(self) -> ComposeResult:
        yield RecordView(self.client, SCOPE, self.key, id="record")


def test_the_tab_is_named_properties() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = screen_text(app)
        assert "Properties" in text and "Psets" not in text

    run_pilot(app, scenario, size=(120, 30))


def test_the_tab_asks_for_the_sets_of_the_record_by_its_id() -> None:
    client = FakeClient.with_valve_example()
    record = client.get_record(SCOPE, "FV-1002")
    assert record is not None
    app = Host(client, "FV-1002")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        assert client.form_metadata_ids[-1] == record["id"]

    run_pilot(app, scenario, size=(120, 30))


def test_the_rule_and_the_group_use_plain_words() -> None:
    client = FakeClient.with_valve_example()
    app = Host(client, "FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = app.query_one(PsetsTab).text
        assert "required at Design or Installed" in text and "▾ valve_data · required" in text
        assert find_technical(text) == []
        assert "3.2.0" not in text and "Effective schema" not in text

    run_pilot(app, scenario, size=(160, 40))


def test_a_tag_shows_the_sets_its_class_binds(tmp_path: Path, fixture_schemas: None) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    seed_registry(db)
    with open_uow(db) as uow:
        made = handle_create_tag(
            uow,
            CreateTag(
                actor="user:u",
                source="test",
                scope=SCOPE,
                number="47-FV-1001",
                class_code="ControlValve",
            ),
        )
    client = EmbeddedClient.for_sqlite(db)
    record = client.get_record(SCOPE, "47-FV-1001")
    assert record is not None and record["id"] == made.stream_id
    assert "valve_data" not in [g.name for g in client.form_metadata(SCOPE, record["type"]).psets]
    app = Host(client, "47-FV-1001")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = app.query_one(PsetsTab).text
        assert "▾ Valve data" in text, text  # only the record id tells the class

    run_pilot(app, scenario, size=(160, 40))


def test_a_document_shows_document_data(fixture_schemas: None) -> None:
    client = FakeClient.with_valve_example()
    client.metadata_by_type["documents.Document"] = form_metadata(
        get_provider().effective(SCOPE), "documents.Document"
    )
    client._seed("ISO-1234", "Isometric", "Issued")  # noqa: SLF001
    doc = client.get_record(SCOPE, "ISO-1234")
    assert doc is not None
    client._records[doc["id"]]["type"] = "documents.Document"  # noqa: SLF001
    app = Host(client, "ISO-1234")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        text = app.query_one(PsetsTab).text
        assert text.count("▾ Document data") == 1
        for label in ("Originator", "Native file format", "Review due"):
            assert label in text, label
        assert "document_data" not in text and find_technical(text) == []

    run_pilot(app, scenario, size=(160, 40))
