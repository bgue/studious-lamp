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
from mcp_harness import SCOPE, McpHarness
from tl_core.services import proposals
from tl_mcp.server import build_server

OTHER_AGENT = "agent:other"
KEY = "walk-ncr-0042-r1"


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


def test_q3_b_keyed_retry_after_the_target_is_taken_is_replayed_not_refused(
    env: McpHarness,
) -> None:
    first = create(env, key="P123-REC-0042", idempotency_key=KEY)
    # the target record is created under the same key after the proposal was filed, so
    # precheck of the same command would now refuse
    env.create_record("P123-REC-0042")
    replay = create(env, key="P123-REC-0042", idempotency_key=KEY)
    assert replay["proposal"]["proposal_id"] == first["proposal"]["proposal_id"]
    assert len(proposal_events(env)) == 1
