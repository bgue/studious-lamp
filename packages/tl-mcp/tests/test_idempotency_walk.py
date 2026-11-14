"""Idempotency keys on the MCP proposing tools, walked across agents and the cap (P2-X1-T07).

Q3 (T03 author): ``proposals.submit`` runs ``_check_proposal``, the daily budget check and
``precheck`` before ``propose``, which holds the idempotency replay. A keyed retry may then be
refused instead of replayed. The two Q3 cases below state the expected behaviour (replay, no
error). They are not xfail and not skipped: a red one is a finding, reported as Q3 RED.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import SCOPE, McpHarness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core import modules as core_modules
from tl_core.modules import ConfidentialSource
from tl_core.services import proposals
from tl_core.services.commands import VoidRecord
from tl_core.services.records import handle_void_record
from tl_mcp.server import build_server

OTHER_AGENT = "agent:other"
KEY = "walk-ncr-0042-r1"
FAKE_ID = "01J000000000000000000000"
CLASS_TABLE = "walk_idem_mcp_class"
RECORD_KEY = "P123-REC-0042"
TITLE = "Weld NCR walk title 3c9e"
UPDATE: dict[str, Any] = {
    "record": RECORD_KEY,
    "scope": SCOPE,
    "pset": "valve_data",
    "values": {"size_in": 4},
}


def proposal_events(env: McpHarness) -> list[Any]:
    with env.factory(True) as uow:
        found = uow.ledger.read_after(0, limit=1000)
    return [e for e in found if e.event_type == "Proposal.Created"]


def create(
    env: McpHarness, title: str = "Weld NCR", key: str = "P123-REC-0042", **extra: Any
) -> dict[str, Any]:
    out = env.structured("create_record", scope=SCOPE, title=title, key=key, **extra)
    assert isinstance(out, dict)
    return out


def test_the_same_key_from_two_agents_files_two_proposals(env: McpHarness, tmp_path: Path) -> None:
    mine = create(env, idempotency_key=KEY)
    other_server = build_server(env.factory, actor=OTHER_AGENT, lake_dir=tmp_path / "lake")
    other = McpHarness(env.db, env.factory, other_server)
    theirs = create(other, key="P123-REC-0043", idempotency_key=KEY)
    assert mine["proposal"]["agent"] != theirs["proposal"]["agent"]
    assert theirs["proposal"]["agent"] == OTHER_AGENT
    assert theirs["proposal"]["proposal_id"] != mine["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 2


def test_q3_a_keyed_retry_after_the_daily_cap_is_replayed_not_refused(
    env: McpHarness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(proposals.BUDGET_ENV, "2")
    first = create(env, key="P123-REC-0001", idempotency_key=KEY)
    create(env, key="P123-REC-0002")  # the second proposal of the day: the cap is reached
    # the cap is now reached; a retry of the first call must answer with the first answer
    replay = create(env, key="P123-REC-0001", idempotency_key=KEY)
    assert replay == first
    assert len(proposal_events(env)) == 2


def test_q3_b_keyed_retry_after_the_target_key_is_taken_is_replayed_not_refused(
    env: McpHarness,
) -> None:
    first = create(env, key="P123-REC-0042", idempotency_key=KEY)
    # the target record is created under the same key after the proposal was filed, so
    # precheck of the same command would now refuse
    env.create_record("P123-REC-0042")
    replay = create(env, key="P123-REC-0042", idempotency_key=KEY)
    assert replay["proposal"]["proposal_id"] == first["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 1


def test_q3_b_voided_target_retry_is_replayed_not_refused(env: McpHarness) -> None:
    target = env.create_record("P123-REC-0042")
    update: dict[str, Any] = {
        "record": "P123-REC-0042",
        "scope": SCOPE,
        "pset": "valve_data",
        "values": {"size_in": 4},
    }
    first = env.structured("update_psets", idempotency_key=KEY, **update)
    # the target is voided after the proposal was filed: precheck of the same command now refuses
    with env.factory(False) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="user:seed",
                source="test",
                scope=SCOPE,
                stream_id=target.stream_id,
                expected_version=target.version,
                reason="walk: target voided after the first filing",
            ),
        )
    with pytest.raises(ToolError):  # a fresh filing without the key is refused now
        env.structured("update_psets", **update)
    replay = env.structured("update_psets", idempotency_key=KEY, **update)
    assert replay == first
    assert len(proposal_events(env)) == 1


@pytest.fixture
def classed(env: McpHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    """``core.Record`` rows carry a class in ``CLASS_TABLE`` (a test-only source, as seed_week)."""
    with open_uow(env.db) as uow:
        uow.conn().execute(
            text(f"CREATE TABLE {CLASS_TABLE} (id TEXT PRIMARY KEY, cls TEXT NOT NULL)")
        )
    source = ConfidentialSource(
        record_types=frozenset({"core.Record"}),
        table=CLASS_TABLE,
        id_column="id",
        class_column="cls",
    )
    real = core_modules.confidential_sources
    monkeypatch.setattr(cf, "confidential_sources", lambda: [*real(), source])


def set_class(env: McpHarness, record_id: str, cls: str) -> None:
    with open_uow(env.db) as uow:
        uow.conn().execute(text(f"DELETE FROM {CLASS_TABLE} WHERE id = :i"), {"i": record_id})
        uow.conn().execute(
            text(f"INSERT INTO {CLASS_TABLE} (id, cls) VALUES (:i, :c)"),
            {"i": record_id, "c": cls},
        )


def test_an_agent_replay_after_its_clearance_drops_answers_as_a_missing_record(
    env: McpHarness, classed: None
) -> None:
    """The agent files K about a record it can read; the record then rises above its clearance.
    The replay of K answers what a call naming an id that never existed answers: same error type
    and text, and neither the record's id nor its title. The agent names the record by its key, so
    the comparison swaps that key for an id that never existed."""
    record_id = str(env.create_record(RECORD_KEY, TITLE).stream_id)
    set_class(env, record_id, "internal")  # the agent may read the record while K is filed
    first = env.structured("update_psets", idempotency_key=KEY, **UPDATE)
    assert first["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 1

    set_class(env, record_id, "privileged")  # the agent's clearance no longer reaches it
    with pytest.raises(ToolError) as replayed:
        env.call("update_psets", idempotency_key=KEY, **UPDATE)
    with pytest.raises(ToolError) as missing:
        env.call("update_psets", **{**UPDATE, "record": FAKE_ID})

    assert type(replayed.value) is type(missing.value)
    assert record_id not in str(replayed.value)
    assert TITLE not in str(replayed.value)
    assert str(replayed.value).replace(RECORD_KEY, FAKE_ID) == str(missing.value)
    assert len(proposal_events(env)) == 1
