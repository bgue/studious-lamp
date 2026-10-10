"""One extension type, five surfaces, one ledger (P0-I8 workstream B, brief 31.3).

A package is registered with the CLI; an instance is created through the HTTP API; the MCP tools,
the embedded TUI client and the remote TUI (a real server on loopback) read and change the same
record. A body damaged on disk is refused everywhere, listed by the CLI, and healed by storing it
again. Nothing is mocked: a real SQLite ledger, a filesystem object store, the real app.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from helpers import run_pilot, screen_text
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult
from textual.pilot import Pilot
from textual.widgets import Input, Select
from tl_cli.main import app as cli
from tl_core.extypes.errors import (
    BodyHashMismatchError,
    BodyQuarantinedError,
    TypeNotActiveError,
)
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mcp.server import build_server
from tl_tui.app import TlApp
from tl_tui.embedded import EmbeddedClient
from tl_tui.remote import RemoteClient
from tl_tui.widgets.extension_form import ExtensionRecordForm
from typer.testing import CliRunner

SCOPE = "project:P123"
TYPES = Path(__file__).resolve().parents[2] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan"
LIFT_REF = "co.acme.LiftPlan@1.0.0"
BODY: dict[str, Any] = {
    "lift_date": "2026-11-03",
    "crane": "CR-12",
    "load_tonnes": 42.5,
    "risk_class": "medium",
    "crew": ["A. Okafor"],
}
runner = CliRunner()


@dataclass
class Stack:
    harness: Harness
    root: Path
    env: dict[str, str]

    def tl(self, *args: str, expect: int = 0) -> str:
        result = runner.invoke(cli, list(args), env=self.env)
        assert result.exit_code == expect, result.output
        return result.stdout

    def mcp(self, tool: str, **arguments: Any) -> Any:
        server = build_server(
            self.harness.backend,
            actor="agent:triage",
            lake_dir=self.root / "lake",
            object_store=self.harness.store,
        )
        result = asyncio.run(server.call_tool(tool, arguments))
        assert isinstance(result, CallToolResult)
        return result.structured_content

    def embedded(self) -> EmbeddedClient:
        return EmbeddedClient(self.harness.backend, object_store=self.harness.store)


@pytest.fixture
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Stack]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    types = tmp_path / "types"
    shutil.copytree(TYPES, types)
    (tmp_path / "h").mkdir()
    with use_provider(DirectorySchemaProvider()):
        harness = Harness.build(tmp_path / "h")
        env = {
            "TL_DB": str(harness.db),
            "TL_OBJECT_ROOT": str(tmp_path / "h" / "objects"),
            "TL_OBJECT_SECRET": "test",
        }
        built = Stack(harness, types, env)
        try:
            yield built
        finally:
            harness.close()


def _register_and_create(stack: Stack) -> str:
    out = stack.tl("types", "sync", str(stack.root))
    assert f"registered {LIFT_REF}" in out
    api = stack.harness.api()
    result = api.create_instance(LIFT, scope=SCOPE, title="Skid lift", key="LP-1", body=BODY)
    return result.stream_id


def test_the_cli_registers_and_every_surface_sees_the_type(stack: Stack) -> None:
    stack.tl("types", "sync", str(stack.root))
    assert LIFT_REF in stack.tl("types", "ls")
    assert LIFT_REF in {t.type_ref for t in stack.harness.api().list_types()}
    assert LIFT_REF in {t["type_ref"] for t in stack.mcp("list_record_types")["result"]}
    assert LIFT_REF in {t.type_ref for t in stack.embedded().list_types()}
    form = stack.harness.api().get_type(LIFT_REF).form
    assert form is not None
    assert stack.embedded().get_type(LIFT_REF).form == form  # one form, however it is asked
    assert stack.mcp("get_record_type", type_ref=LIFT_REF)["form"]["type_ref"] == LIFT_REF


def test_a_body_created_over_http_reads_the_same_everywhere(stack: Stack) -> None:
    record_id = _register_and_create(stack)
    via_api = stack.harness.api().get_record_body(record_id)
    assert via_api.body == BODY
    via_mcp = stack.mcp("get_record_body", record="LP-1", scope=SCOPE)
    assert via_mcp["body"] == BODY and via_mcp["pointer"]["hash"] == via_api.pointer.hash
    via_tui = stack.embedded().get_record_body(record_id)
    assert via_tui.body == BODY and via_tui.pointer == via_api.pointer


def test_an_embedded_edit_is_one_new_version_for_the_other_surfaces(stack: Stack) -> None:
    record_id = _register_and_create(stack)
    tui = stack.embedded()
    record = tui.get_record_by_id(record_id)
    assert record is not None
    changed = {**BODY, "risk_class": "high"}
    stored = tui.put_record_body(
        record_id, scope=SCOPE, body=changed, expected_version=int(record["version"])
    )
    api = stack.harness.api()
    assert api.get_record_body(record_id).body == changed
    assert stack.mcp("get_record_body", record="LP-1", scope=SCOPE)["body"] == changed
    row = api.get_record_by_id(record_id)
    assert row is not None
    assert row["version"] == stored.version
    assert row["psets"]["co_acme_lift_plan"]["risk_class"] == "high"  # the index field followed


def test_the_remote_tui_lists_and_creates_through_the_server(stack: Stack) -> None:
    _register_and_create(stack)
    with stack.harness.live() as server:
        client = RemoteClient.connect(server.base_url, server.token, timeout=5.0)
        tui = TlApp(client.as_client(), scope=SCOPE, record_type=LIFT, mode="remote")

        async def scenario(pilot: Pilot[Any]) -> None:
            for _ in range(100):  # the grid loads in a worker
                await pilot.pause(0.05)
                if "LP-1" in screen_text(tui):
                    break
            text = screen_text(tui)
            assert "LP-1" in text and "CR-12" in text and "Lift date" in text
            await pilot.press("n")
            await pilot.pause()
            form = tui.screen
            assert isinstance(form, ExtensionRecordForm)
            for name, value in {
                "new_key": "LP-2",
                "new_title": "Second lift",
                "ext_lift_date": "2026-12-01",
                "ext_crane": "CR-14",
                "ext_load_tonnes": "7",
            }.items():
                form.query_one(f"#{name} Input", Input).value = value
            form.query_one("#ext_risk_class Select", Select).value = "high"
            await pilot.pause()
            await pilot.press("ctrl+s")
            for _ in range(100):
                await pilot.pause(0.05)
                if not isinstance(tui.screen, ExtensionRecordForm):
                    break
            assert not isinstance(tui.screen, ExtensionRecordForm)

        try:
            run_pilot(tui, scenario, size=(160, 110))
        finally:
            client.close()
    created = stack.embedded().get_record(SCOPE, "LP-2")
    assert created is not None and created["type"] == LIFT
    assert stack.embedded().get_record_body(created["id"]).body["crane"] == "CR-14"


def test_a_damaged_body_is_refused_everywhere_listed_and_healed(stack: Stack) -> None:
    record_id = _register_and_create(stack)
    api = stack.harness.api()
    pointer = api.get_record_body(record_id).pointer
    stack.harness.store.path_for(pointer.uri).write_bytes(b'{"crane": "tampered"}')

    with pytest.raises(BodyHashMismatchError):
        api.get_record_body(record_id)
    with pytest.raises(BodyQuarantinedError):
        stack.embedded().get_record_body(record_id)
    with pytest.raises(ToolError):
        stack.mcp("get_record_body", record="LP-1", scope=SCOPE)
    report = stack.tl("types", "quarantine", "ls")
    assert record_id in report and "hash mismatch" in report
    assert "still failing" in stack.tl("types", "quarantine", "recheck", record_id, expect=1)

    stack.embedded().put_record_body(record_id, scope=SCOPE, body=BODY)  # store it again
    assert "restored" in stack.tl("types", "quarantine", "recheck", record_id)
    assert api.get_record_body(record_id).body == BODY
    assert "nothing quarantined" in stack.tl("types", "quarantine", "ls")


def test_a_deprecated_type_takes_no_new_records_on_any_surface(stack: Stack) -> None:
    _register_and_create(stack)
    stack.tl("types", "deprecate", LIFT_REF, "--reason", "replaced")
    with pytest.raises(TypeNotActiveError):
        stack.harness.api().create_instance(LIFT, scope=SCOPE, title="x", key="LP-9", body=BODY)
    with pytest.raises(TypeNotActiveError):
        stack.embedded().create_instance(LIFT, scope=SCOPE, title="x", key="LP-9", body=BODY)
    assert stack.embedded().get_record(SCOPE, "LP-9") is None
