"""The app opened on an extension type: its grid columns and its new-record form (P0-I8)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fakes import SCOPE, FakeClient
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_adapters.objectstore.fs import FsObjectStore
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.extypes import registry
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.widgets.extension_form import ExtensionRecordForm
from tl_tui.widgets.grid import RecordGrid
from tl_tui.widgets.new_record_form import NewRecordForm

LIFT = "co.acme.LiftPlan"
LIFT_PSET = "co_acme_lift_plan"


def _client() -> FakeClient:
    client = FakeClient()
    client.add_example_type(LIFT)
    client.create_instance(
        LIFT,
        scope=SCOPE,
        title="Skid lift",
        key="LP-1",
        body={
            "lift_date": "2026-11-03",
            "crane": "CR-12",
            "load_tonnes": 42.5,
            "risk_class": "medium",
        },
    )
    return client


def test_the_grid_of_an_extension_type_shows_the_columns_of_its_form() -> None:
    app = TlApp(_client(), scope=SCOPE, record_type=LIFT)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        grid = app.query_one("#grid", RecordGrid)
        assert [c.key for c in grid.columns] == [
            "key",
            "title",
            f"psets.{LIFT_PSET}.lift_date",
            f"psets.{LIFT_PSET}.crane",
            f"psets.{LIFT_PSET}.load_tonnes",
            f"psets.{LIFT_PSET}.risk_class",
            "status",
            "version",
        ]
        text = screen_text(app)
        assert "LP-1" in text and "CR-12" in text and "Crane" in text

    run_pilot(app, scenario, size=(160, 40))


def test_core_records_keep_the_default_columns() -> None:
    app = TlApp(FakeClient.with_valve_example(), scope=SCOPE)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        keys = [c.key for c in app.query_one("#grid", RecordGrid).columns]
        assert keys == ["key", "title", "status", "version", "conformance"]

    run_pilot(app, scenario, size=(120, 40))


def test_n_opens_the_generated_form_and_shows_the_new_record() -> None:
    client = _client()
    app = TlApp(client, scope=SCOPE, record_type=LIFT)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, ExtensionRecordForm)
        for name, text in {
            "new_key": "LP-2",
            "new_title": "Second lift",
            "ext_lift_date": "2026-12-01",
            "ext_crane": "CR-14",
            "ext_load_tonnes": "7",
        }.items():
            form.query_one(f"#{name} Input", Input).value = text
        form.query_one("#ext_risk_class Select", Select).value = "high"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert not isinstance(app.screen, ExtensionRecordForm)
        created = client.get_record(SCOPE, "LP-2")
        assert created is not None and created["type"] == LIFT
        assert client.get_record_body(created["id"]).body["crane"] == "CR-14"

    run_pilot(app, scenario, size=(160, 110))


def test_n_opens_the_plain_form_for_core_records() -> None:
    app = TlApp(FakeClient(), scope=SCOPE)

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, NewRecordForm)

    run_pilot(app, scenario, size=(120, 40))


def test_the_app_on_a_real_ledger_lists_opens_and_creates_records_of_a_type(
    tmp_path: Path,
) -> None:
    db = tmp_path / "tl.db"
    create_schema(db)
    root = tmp_path / "types"
    shutil.copytree(Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types", root)
    with use_provider(DirectorySchemaProvider()):
        client = EmbeddedClient.for_sqlite(
            db, object_store=FsObjectStore(tmp_path / "objects", secret=b"s")
        )
        registry.sync(SqliteUowFactory(db), root, actor="user:ops", source="test")
        client.create_instance(
            LIFT,
            scope=SCOPE,
            title="Skid lift",
            key="LP-1",
            body={
                "lift_date": "2026-11-03",
                "crane": "CR-12",
                "load_tonnes": 42.5,
                "risk_class": "medium",
            },
        )
        app = TlApp(client, scope=SCOPE, record_type=LIFT)

        async def scenario(pilot: Pilot[Any]) -> None:
            await pilot.pause()
            await pilot.pause()
            text = screen_text(app)
            assert "LP-1" in text and "CR-12" in text and "medium" in text
            await pilot.press("enter")
            await pilot.pause()
            await pilot.pause()
            assert "Skid lift" in screen_text(app)

        run_pilot(app, scenario, size=(160, 40))
