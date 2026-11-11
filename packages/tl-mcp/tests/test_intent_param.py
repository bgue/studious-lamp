"""The optional ``intent`` parameter of the propose tools (P2-INT-T03; ADR-0025 d6, ADR-0027 F9).

The tool passes the object to the command; ``proposals.submit`` checks it and stores it in the
Created event's ``intent`` column. An intent grants no authority and has no ``evidence`` key.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from tl_adapters.objectstore.fs import FsObjectStore
from tl_api.auth import Forbidden
from tl_core.files.service import FileService
from tl_core.intent import Intent
from tl_core.services import proposals
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world

ROOT = Path(__file__).resolve().parents[3]
ALICE = "user:alice"
FAKE_ID = "01J000000000000000000000"
INTENT: dict[str, Any] = {
    "why": "Weld failed inspection",
    "next": [{"text": "re-inspect the weld"}],
    "goal_ref": "ncr-42",
}
#: Every propose tool (ticket P2-INT-T03): the write tools, then one per module.
PROPOSE_TOOLS = (
    "create_record",
    "update_psets",
    "link_records",
    "transition_workflow",
    "propose_setting_change",
    "propose_cwp",
    "propose_triage",
    "start_extraction",
    "propose_import",
    "propose_iwp_scope",
    "propose_punch_item",  # P2-PUNCH-T05
    "propose_reservation",
    "propose_publish_schedule_snapshot",
    "propose_dispatch",
)


def events(env: McpHarness, event_type: str | None = None) -> list[Any]:
    with env.factory(True) as uow:
        found = uow.ledger.read_after(0, limit=1000)
    return [e for e in found if event_type is None or e.event_type == event_type]


def created_for(env: McpHarness, proposal_id: str) -> Any:
    (created,) = [e for e in events(env, "Proposal.Created") if e.stream_id == proposal_id]
    return created


def load_awp_world() -> ModuleType:
    """The S4 awp seed (``awp_world``), loaded by path as the awp tool tests do."""
    name = "awp_world"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "packages" / "tl-modules" / "awp" / "tests" / "awp_world.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def hidden_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[McpHarness, Hidden]]:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    store = FsObjectStore(tmp_path / "objects", secret=b"k")
    service = FileService(store, secret=b"s")
    env = McpHarness.build(tmp_path, object_store=store, files=service)
    try:
        yield env, seed_hidden_world(env.db, service, tmp_path)
    finally:
        env.close()


def test_create_record_stores_the_intent_in_the_created_column(env: McpHarness) -> None:
    out = env.structured(
        "create_record", scope=SCOPE, title="Weld NCR", key="P123-REC-0042", intent=INTENT
    )
    created = created_for(env, out["proposal"]["proposal_id"])
    assert created.intent is not None
    assert (created.intent.why, created.intent.goal_ref) == ("Weld failed inspection", "ncr-42")
    assert "intent" not in created.payload["command"]


def test_a_module_tool_stores_the_intent_in_the_created_column(env: McpHarness) -> None:
    world = load_awp_world().World(env.db)
    world.people()
    world.editions()
    world.seed()
    out = env.structured(
        "propose_cwp",
        project="P123",
        discipline="PIP",
        title="Proposed piping",
        cwa_code="A2",
        intent=INTENT,
    )
    created = created_for(env, out["proposal"]["proposal_id"])
    assert created.intent is not None and created.intent.why == "Weld failed inspection"
    assert "intent" not in created.payload["command"]


def test_a_person_accepting_appends_events_with_the_same_intent(env: McpHarness) -> None:
    out = env.structured(
        "create_record", scope=SCOPE, title="Weld NCR", key="P123-REC-0042", intent=INTENT
    )
    proposal_id = out["proposal"]["proposal_id"]
    proposals.accept_or_fail(env.factory, proposal_id=proposal_id, by=ALICE)
    proposed = created_for(env, proposal_id)
    (record,) = [e for e in events(env, "Record.Created")]
    assert proposed.intent is not None
    assert record.intent == proposed.intent
    assert record.intent == Intent.model_validate(INTENT)  # the appended event is the input
    assert "intent" not in record.payload


def test_a_bad_intent_is_refused_and_leaves_no_proposal(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="intent_invalid: .*longer than 500 characters"):
        env.call("create_record", scope=SCOPE, title="Weld NCR", intent={"why": "x" * 501})
    with pytest.raises(ToolError, match="evidence"):  # F9: refused by the schema (extra key)
        env.call("create_record", scope=SCOPE, title="Weld NCR", intent={"evidence": ["x"]})
    assert events(env, "Proposal.Created") == []


def test_a_hidden_and_an_unknown_toward_target_give_the_same_text(
    hidden_env: tuple[McpHarness, Hidden],
) -> None:
    env, hidden = hidden_env
    before = len(events(env, "Proposal.Created"))  # the seed world holds proposals of its own
    texts: list[str] = []
    for target in (hidden.ids["restricted"], FAKE_ID):
        with pytest.raises(ToolError) as refused:
            env.call(
                "create_record",
                scope=SCOPE,
                title="Weld NCR",
                intent={"toward": {"target": target, "condition": "closed"}},
            )
        texts.append(str(refused.value))
    assert texts[0] == texts[1]
    assert "intent_reference_unknown: intent reference not found" in texts[0]
    assert "not found" in texts[0]
    assert len(events(env, "Proposal.Created")) == before
    # a target the agent may read is accepted: the refusal above is the reference, not the tool
    env.structured(
        "create_record",
        scope=SCOPE,
        title="Weld NCR",
        intent={"toward": {"target": hidden.ids["open"], "condition": "closed"}},
    )


def test_an_agent_intent_does_not_change_an_access_refusal(tmp_path: Path) -> None:
    def deny(actor: str, action: str, resource: str) -> None:
        raise Forbidden("nobody may")

    env = McpHarness.build(tmp_path, authorize_hook=deny)
    try:
        with pytest.raises(ToolError) as plain:
            env.call("create_record", scope=SCOPE, title="Weld NCR")
        with pytest.raises(ToolError) as with_intent:
            env.call(
                "create_record",
                scope=SCOPE,
                title="Weld NCR",
                intent={"toward": {"target": FAKE_ID, "condition": "closed"}},
            )
        assert str(with_intent.value) == str(plain.value)
        assert "not allowed" in str(plain.value)
        assert events(env, "Proposal.Created") == []
    finally:
        env.close()


@pytest.mark.parametrize("tool", PROPOSE_TOOLS)
def test_every_propose_tool_takes_an_optional_intent(env: McpHarness, tool: str) -> None:
    tools = {t.name: t for t in asyncio.run(env.server.list_tools())}
    schema = tools[tool].input_schema
    assert "intent" in schema["properties"], tool
    assert "intent" not in (schema.get("required") or []), tool
    intent_def = schema["$defs"]["Intent"]["properties"]
    assert set(intent_def) == {"why", "next", "toward", "goal_ref"}  # F9: no evidence
