"""EmbeddedClient and the TUI over the real pset services and the fixture packages (P0-I2).

No fake: a temporary SQLite ledger, `schema/fixtures` (co.acme.engineering 3.2.0, x.P123 1.4.0,
prj.P123 1.0.0), the real form metadata, conformance and `SetPsetValues`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from helpers import run_pilot, screen_text
from textual.pilot import Pilot
from textual.widgets import Input, TabbedContent
from tl_adapters.sqlite.uow import create_schema
from tl_core.schema_provider import DirectorySchemaProvider, get_provider, use_provider
from tl_core.services.commands import CreateRecord
from tl_core.services.psets import SetPsetValues
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.forms import save_record_edits
from tl_tui.paths import pset_value
from tl_tui.widgets.edit_form import EditForm, editor_id
from tl_tui.widgets.psets_tab import PsetsTab

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
SCOPE = "project:P123"


@pytest.fixture(autouse=True)
def fixture_schemas() -> Iterator[None]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        yield


@pytest.fixture
def client(tmp_path: Path) -> EmbeddedClient:
    db = tmp_path / "tl.db"
    create_schema(db)
    return EmbeddedClient.for_sqlite(db)


def _create(client: EmbeddedClient, key: str = "V-0001") -> dict[str, Any]:
    result = client.create_record(
        CreateRecord(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            record_type="core.Record",
            key=key,
            title="Valve 1",
        )
    )
    record = client.get_record_by_id(result.stream_id)
    assert record is not None
    return record


def test_form_metadata_comes_from_the_effective_schema(client: EmbeddedClient) -> None:
    meta = client.form_metadata(SCOPE, "core.Record")
    assert meta.effective_schema_hash == get_provider().effective(SCOPE).hash
    assert [g.name for g in meta.psets] == ["valve_data", "prj.shutdown_tie_in"]
    paths = [f.path for g in meta.psets for f in g.fields]
    assert "psets.valve_data.size_in" in paths and "psets.valve_data.x.fat_witness_by" in paths
    readonly = {f.path for f in meta.core_fields if f.readonly}
    assert readonly == {"key", "status"}


def test_setting_values_emits_pset_values_set_with_the_schema_hash(client: EmbeddedClient) -> None:
    record = _create(client)
    meta = client.form_metadata(SCOPE, "core.Record")
    standard = client.set_pset_values(
        SetPsetValues(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            pset="valve_data",
            layer="standard",
            values={"size_in": 4},
        )
    )
    custom = client.set_pset_values(
        SetPsetValues(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=standard.version,
            pset="valve_data",
            layer="custom",
            values={"x.fat_witness_by": "client"},
        )
    )
    events = client.history(record["id"])
    assert [e.event_type for e in events] == ["Record.Created", "Pset.ValuesSet", "Pset.ValuesSet"]
    assert all(e.payload["effective_schema_hash"] == meta.effective_schema_hash for e in events[1:])
    assert custom.version == 3
    saved = client.get_record_by_id(record["id"])
    assert saved is not None
    assert pset_value(saved["psets"], "psets.valve_data.size_in") == 4
    assert pset_value(saved["psets"], "psets.valve_data.x.fat_witness_by") == "client"


def test_a_missing_advisory_property_shows_a_warning(client: EmbeddedClient) -> None:
    record = _create(client)
    client.set_pset_values(
        SetPsetValues(
            actor="user:t",
            source="tui",
            scope=SCOPE,
            stream_id=record["id"],
            expected_version=record["version"],
            pset="valve_data",
            layer="standard",
            values={"size_in": 4},
        )
    )
    report = client.conformance(record["id"])
    assert report.status == "warning"
    assert {i.level for i in report.issues} == {"warning"}
    assert any(i.path.endswith("manufacturer") for i in report.issues)


def test_save_record_edits_over_the_real_services(client: EmbeddedClient) -> None:
    record = _create(client)
    meta = client.form_metadata(SCOPE, "core.Record")
    outcome = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=record,
        meta=meta,
        edits={
            "title": "Renamed",
            "psets.valve_data.size_in": 6.0,
            "psets.valve_data.x.fat_witness_by": "client",
            "psets.valve_data.manufacturer": "Acme",
        },
    )
    assert outcome.ok, outcome.error
    assert outcome.applied == ["core", "valve_data/standard", "valve_data/custom"]
    saved = client.get_record_by_id(record["id"])
    assert saved is not None and saved["title"] == "Renamed"
    assert saved["effective_schema_hash"] == meta.effective_schema_hash
    assert [e.event_type for e in client.history(record["id"])] == [
        "Record.Created",
        "Record.Updated",
        "Pset.ValuesSet",
        "Pset.ValuesSet",
    ]
    # Clearing a property sends None, which the real handler treats as "unset".
    cleared = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=saved,
        meta=meta,
        edits={"psets.valve_data.manufacturer": None},
    )
    assert cleared.ok, cleared.error
    after = client.get_record_by_id(record["id"])
    assert after is not None
    assert pset_value(after["psets"], "psets.valve_data.manufacturer") is None


def test_a_refused_part_of_a_save_leaves_the_record_untouched(client: EmbeddedClient) -> None:
    record = _create(client)
    meta = client.form_metadata(SCOPE, "core.Record")
    before = len(client.history(record["id"]))
    outcome = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=record,
        meta=meta,
        edits={
            "title": "Renamed",
            "psets.valve_data.manufacturer": "Acme",
            "psets.valve_data.size_in": "not a number",  # refused by the pset service
        },
    )
    assert not outcome.ok and outcome.applied == []
    assert outcome.version == record["version"]
    after = client.get_record_by_id(record["id"])
    assert after is not None
    assert after["title"] == "Valve 1" and after["version"] == record["version"]
    assert len(client.history(record["id"])) == before


def test_one_save_is_one_correlation(client: EmbeddedClient) -> None:
    record = _create(client)
    meta = client.form_metadata(SCOPE, "core.Record")
    outcome = save_record_edits(
        client,
        scope=SCOPE,
        actor="user:t",
        record=record,
        meta=meta,
        edits={"title": "Renamed", "psets.valve_data.manufacturer": "Acme"},
    )
    assert outcome.ok, outcome.error
    saved = client.history(record["id"])[1:]
    assert [e.event_type for e in saved] == ["Record.Updated", "Pset.ValuesSet"]
    assert len({e.correlation_id for e in saved}) == 1


def test_the_edit_form_saves_through_the_real_services_and_the_view_shows_it(
    client: EmbeddedClient,
) -> None:
    _create(client)
    app = TlApp(client, actor="user:t")

    async def scenario(pilot: Pilot[Any]) -> None:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("e")
        await pilot.pause()
        form = app.screen
        assert isinstance(form, EditForm)
        form.query_one(f"#{editor_id('psets.valve_data.size_in')} Input", Input).value = "4"
        witness = editor_id("psets.valve_data.x.fat_witness_by")
        form.query_one(f"#{witness} Input", Input).value = "client"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert not isinstance(app.screen, EditForm)
        app.query_one("#rv-tabs", TabbedContent).active = "tab-psets"
        await pilot.pause()
        tab = app.query_one(PsetsTab)
        assert (
            "Nominal size              4 in" in tab.text
            and "FAT witness               client" in tab.text
        )
        assert "Conformance: ! warning" in tab.text
        assert "V-0001" in screen_text(app)

    run_pilot(app, scenario, size=(160, 50))
    saved = client.get_record(SCOPE, "V-0001")
    assert saved is not None
    events = client.history(saved["id"])
    assert [e.event_type for e in events][-2:] == ["Pset.ValuesSet", "Pset.ValuesSet"]
    assert saved["conformance"] == "warning"
