"""The extension type tools and resources, and propose-only create for types (P0-I8-T22)."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp_harness import SCOPE, McpHarness
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.extypes import body, registry
from tl_core.extypes.lock import write_lock
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord

TYPES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "types"
LIFT = "co.acme.LiftPlan"
OBSERVATION = "co.acme.SafetyObservation"
OBSERVATION_PSET = "co_acme_safety_observation"
LIFT_BODY: dict[str, Any] = {
    "crane": "CR-12",
    "lift_date": "2026-11-03",
    "load_tonnes": 42.5,
    "risk_class": "medium",
}
OBSERVED: dict[str, Any] = {
    "observed_on": "2026-10-02",
    "category": "near_miss",
    "severity": "high",
    "location": "Unit 3 pipe rack",
}


class Env:
    def __init__(self, h: McpHarness, root: Path, store: FsObjectStore) -> None:
        self.h, self.root, self.store = h, root, store

    def sync(self) -> None:
        registry.sync(self.h.factory, self.root, actor="user:ops", source="test")

    def lift(self, key: str = "LP-1") -> str:
        cmd = CreateRecord(
            actor="user:alice",
            source="test",
            scope=SCOPE,
            record_type=LIFT,
            title="Lift",
            key=key,
        )
        with self.h.factory(False) as uow:
            return body.create_extension_record(uow, self.store, cmd, dict(LIFT_BODY)).stream_id


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    root = tmp_path / "types"
    shutil.copytree(TYPES, root)
    store = FsObjectStore(tmp_path / "objects", secret=b"k")
    with use_provider(DirectorySchemaProvider()):
        (tmp_path / "h").mkdir()
        harness = McpHarness.build(tmp_path / "h", object_store=store)
        try:
            yield Env(harness, root, store)
        finally:
            harness.close()


def test_the_type_tools_are_read_only_and_registered(env: Env) -> None:
    tools = {t.name: t for t in asyncio.run(env.h.server.list_tools())}
    for name in ("list_record_types", "get_record_type", "get_record_body"):
        assert name in tools
        annotations = tools[name].annotations
        assert annotations is not None and annotations.read_only_hint is True
        assert annotations.destructive_hint is False
        assert tools[name].description
    assert set(tools["list_record_types"].input_schema["properties"]) == {"status"}
    assert tools["get_record_type"].input_schema["required"] == ["type_ref"]
    assert tools["get_record_body"].input_schema["required"] == ["record"]


def test_list_record_types_is_empty_then_lists_the_registrations(env: Env) -> None:
    assert env.h.structured("list_record_types")["result"] == []
    env.sync()
    rows = env.h.structured("list_record_types")["result"]
    assert [r["type_ref"] for r in rows] == [f"{LIFT}@1.0.0", f"{OBSERVATION}@1.0.0"]
    lift = rows[0]
    assert lift["type_name"] == LIFT and lift["status"] == "active"
    assert lift["storage_mode"] == "object-backed"
    assert lift["index_fields"] == ["lift_date", "crane", "load_tonnes", "risk_class"]


def test_list_record_types_filters_by_status(env: Env) -> None:
    (env.root / "co.acme" / "LiftPlan" / "1.0.0" / "examples" / "bad.json").write_text("{}")
    write_lock(env.root / "co.acme" / "LiftPlan" / "1.0.0")
    env.sync()
    active = env.h.structured("list_record_types", status="active")["result"]
    assert [r["type_ref"] for r in active] == [f"{OBSERVATION}@1.0.0"]
    quarantined = env.h.structured("list_record_types", status="quarantined")["result"]
    assert [r["type_ref"] for r in quarantined] == [f"{LIFT}@1.0.0"]
    with pytest.raises(ToolError):
        env.h.call("list_record_types", status="bogus")


def test_get_record_type_returns_the_form(env: Env) -> None:
    env.sync()
    detail = env.h.structured("get_record_type", type_ref=f"{LIFT}@1.0.0")
    assert detail["registration"]["type_ref"] == f"{LIFT}@1.0.0"
    assert detail["unavailable"] is None and detail["report"] == []
    names = [f["name"] for g in detail["form"]["groups"] for f in g["fields"]]
    assert names[:4] == ["lift_date", "crane", "load_tonnes", "risk_class"] and "crew" in names


def test_get_record_type_of_a_quarantined_version_has_the_report(env: Env) -> None:
    (env.root / "co.acme" / "LiftPlan" / "1.0.0" / "examples" / "bad.json").write_text("{}")
    write_lock(env.root / "co.acme" / "LiftPlan" / "1.0.0")
    env.sync()
    detail = env.h.structured("get_record_type", type_ref=f"{LIFT}@1.0.0")
    assert detail["form"] is None and detail["registration"]["status"] == "quarantined"
    assert detail["report"][0]["kind"] == "example"


def test_get_record_type_unknown_is_a_tool_error(env: Env) -> None:
    with pytest.raises(ToolError, match="no registration"):
        env.h.call("get_record_type", type_ref="co.acme.Nope@1.0.0")


def test_get_record_body_by_id_and_by_key(env: Env) -> None:
    env.sync()
    record_id = env.lift()
    by_id = env.h.structured("get_record_body", record=record_id)
    assert by_id["record_id"] == record_id and by_id["body"] == LIFT_BODY
    assert by_id["pointer"]["uri"].startswith(f"records/{LIFT}/{record_id}/")
    by_key = env.h.structured("get_record_body", record="LP-1", scope=SCOPE)
    assert by_key == by_id


def test_get_record_body_errors_are_tool_errors(env: Env) -> None:
    env.sync()
    with pytest.raises(ToolError, match="no record"):
        env.h.call("get_record_body", record="LP-404", scope=SCOPE)
    plain = env.h.create_record("P-1")
    with pytest.raises(ToolError, match="no stored body"):
        env.h.call("get_record_body", record=plain.stream_id)


def test_a_damaged_body_is_never_returned_and_the_record_is_quarantined(env: Env) -> None:
    env.sync()
    record_id = env.lift()
    good = env.h.structured("get_record_body", record=record_id)
    env.store.path_for(good["pointer"]["uri"]).write_bytes(b'{"crane":"CR-99"}')
    with pytest.raises(ToolError, match="does not match its recorded hash"):
        env.h.call("get_record_body", record=record_id)
    with pytest.raises(ToolError, match="failed verification"):
        env.h.call("get_record_body", record=record_id)


def test_without_an_object_store_bodies_cannot_be_read(tmp_path: Path) -> None:
    with use_provider(DirectorySchemaProvider()):
        h = McpHarness.build(tmp_path)
        try:
            with pytest.raises(ToolError, match="no object store"):
                h.call("get_record_body", record="01J9Z6Q4W3X2Y1V0T9S8R7Q6P5")
        finally:
            h.close()


def test_the_type_resources(env: Env) -> None:
    env.sync()
    listing = json.loads(env.h.read("tl://types"))
    assert [r["type_ref"] for r in listing] == [f"{LIFT}@1.0.0", f"{OBSERVATION}@1.0.0"]
    one = json.loads(env.h.read(f"tl://types/{OBSERVATION}@1.0.0"))
    assert (
        one["registration"]["storage_mode"] == "managed" and one["form"]["pset"] == OBSERVATION_PSET
    )
    with pytest.raises(ResourceError):
        env.h.read("tl://types/co.acme.Nope@1.0.0")


# --- propose-only create --------------------------------------------------------------------


def test_create_record_of_a_managed_type_is_a_proposal_not_a_record(env: Env) -> None:
    env.sync()
    made = env.h.structured(
        "create_record",
        scope=SCOPE,
        title="Shackle pin",
        record_type=OBSERVATION,
        key="SO-1",
        psets={OBSERVATION_PSET: OBSERVED},
    )
    proposal = made["proposal"]
    assert proposal["status"] == "pending" and proposal["tool"] == "create_record"
    with env.h.factory(True) as uow:
        assert uow.conn().exec_driver_sql("SELECT COUNT(*) FROM cur_core_record").scalar() == 0
    # a person accepts; the record is then an instance of the type, made by that person
    result = proposals.accept_or_fail(
        env.h.factory, proposal_id=proposal["proposal_id"], by="user:alice", roles=[], source="cli"
    )
    assert result.status == "accepted"
    with env.h.factory(True) as uow:
        row = uow.conn().exec_driver_sql("SELECT type, key FROM cur_core_record").first()
    assert row is not None
    assert tuple(row) == (OBSERVATION, "SO-1")


def test_create_record_proposal_for_a_managed_type_checks_the_values_now(env: Env) -> None:
    env.sync()
    with pytest.raises(ToolError, match="observed_on"):
        env.h.call(
            "create_record",
            scope=SCOPE,
            title="x",
            record_type=OBSERVATION,
            key="SO-2",
            psets={OBSERVATION_PSET: {"observed_on": 5}},
        )


def test_create_record_of_an_object_backed_type_says_it_needs_a_body(env: Env) -> None:
    env.sync()
    with pytest.raises(ToolError, match="object-backed"):
        env.h.call("create_record", scope=SCOPE, title="Lift", record_type=LIFT, key="LP-9")
    with env.h.factory(True) as uow:
        assert uow.conn().exec_driver_sql("SELECT COUNT(*) FROM cur_core_record").scalar() == 0


def test_create_record_of_an_unregistered_type_is_still_refused(env: Env) -> None:
    with pytest.raises(ToolError, match="no extension type"):
        env.h.call("create_record", scope=SCOPE, title="x", record_type=OBSERVATION, key="SO-3")
