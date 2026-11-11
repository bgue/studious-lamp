"""The two awp proposals (P2-I5-T12a): ``propose_progress`` and ``propose_week_commitment``.

An agent files a pending proposal and nothing changes; a person holding the word accepts it and the
command runs as that person. ``ClearConstraint`` and ``CloseWeek`` have no MCP tool and are not
proposable (an agent never waives a constraint or closes a week).
"""

# ruff: noqa: F811
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp_harness import McpHarness
from sqlalchemy import text
from test_mcp_week_tools import (  # noqa: F401
    PROJECT,
    call,
    env,
    hidden_iwp,
    refused,
    world,
)
from tl_adapters.db import open_uow
from tl_core.auth.module_roles import holder_for_actor
from tl_core.services import proposals
from tl_core.services.errors import ProposalAccessError
from tl_mcp.identity import MCP_ACTIONS
from tl_mcp.iwp_tools import IWP_MCP_ACTIONS
from tl_mcp.modes import resolve_tool_modes
from tl_mod_awp.module import PROPOSABLE
from tl_mod_awp.names import SCOPE_ITEM, SCOPE_ITEM_TABLE


def _key(env: McpHarness, record_id: str) -> str:
    with env.factory(True) as uow:
        from sqlalchemy import text

        return str(
            uow.conn()
            .execute(text("SELECT key FROM cur_core_record WHERE id = :i"), {"i": record_id})
            .scalar_one()
        )


def _accept(env: McpHarness, proposal_id: str, by: str) -> Any:
    with open_uow(env.db) as uow:
        holder = holder_for_actor(uow.conn(), f"user:{by}")
        return proposals.accept_proposal(
            uow, proposal_id=proposal_id, by=f"user:{by}", holder=holder
        )


def test_propose_progress_is_pending_then_a_person_accepts(env: McpHarness, world: Any) -> None:
    iwp, (item,) = world.pw.package(["10.0"])
    before = world.pw.pct(iwp)
    out = call(
        env,
        "propose_progress",
        project=PROJECT,
        iwp=_key(env, iwp),
        steps=[{"scope_item": _key(env, item), "step": "Material received", "done": True}],
    )
    proposal = out["proposal"]
    assert proposal["status"] == "pending"
    assert world.pw.pct(iwp) == before  # nothing recorded yet
    with pytest.raises(ProposalAccessError):
        _accept(env, proposal["proposal_id"], "vera")
    assert world.pw.pct(iwp) == before
    assert _accept(env, proposal["proposal_id"], "uma").status == "accepted"
    assert world.pw.pct(iwp) != before


def test_propose_week_commitment_is_pending_then_a_person_accepts(
    env: McpHarness,
    world: Any,
) -> None:
    plan = world.open("2026-11-16")
    iwp = world.issued()
    week = call(env, "list_weekly_plans", project=PROJECT)[0]["week"]
    out = call(
        env,
        "propose_week_commitment",
        project=PROJECT,
        week=week,
        iwp=_key(env, iwp),
        committed_hours="12.0",
    )
    proposal = out["proposal"]
    assert proposal["status"] == "pending"
    assert not world.commitments(plan)
    with pytest.raises(ProposalAccessError):
        _accept(env, proposal["proposal_id"], "vera")
    assert _accept(env, proposal["proposal_id"], "uma").status == "accepted"
    assert len(world.commitments(plan)) == 1


def test_an_unknown_week_or_iwp_is_one_refusal(env: McpHarness, world: Any) -> None:
    iwp = world.issued()
    world.open("2026-11-16")
    week = call(env, "list_weekly_plans", project=PROJECT)[0]["week"]
    assert "no weekly plan" in refused(
        env,
        "propose_week_commitment",
        project=PROJECT,
        week="2099-W01",
        iwp=_key(env, iwp),
        committed_hours="1.0",
    )
    assert "no record" in refused(
        env,
        "propose_week_commitment",
        project=PROJECT,
        week=week,
        iwp="P123-IWP-9999",
        committed_hours="1.0",
    )


def test_the_two_tools_are_listed_and_have_their_words(env: McpHarness) -> None:
    names = {t.name for t in asyncio.run(env.server.list_tools())}
    both = {"propose_progress", "propose_week_commitment"}
    assert both <= names
    assert {f"mcp.{n}" for n in both} <= IWP_MCP_ACTIONS <= MCP_ACTIONS
    assert both <= {p.tool for p in PROPOSABLE}


def test_no_tool_clears_or_closes_and_neither_is_proposable(env: McpHarness) -> None:
    names = {t.name for t in asyncio.run(env.server.list_tools())}
    for forbidden in ("clear_constraint", "waive_constraint", "close_week", "close_weekly_plan"):
        assert forbidden not in names
    commands = {p.model.__name__ for p in PROPOSABLE}
    assert commands.isdisjoint({"ClearConstraint", "CloseWeek"})
    assert set(resolve_tool_modes()).isdisjoint(
        {"propose_clear_constraint", "propose_close_week", "clear_constraint", "close_week"}
    )


# --- a hidden record answers as one that never existed (ADR-0016) -------------------------------


def _hide_scope_item(env: McpHarness, item_id: str) -> Any:
    from contextlib import contextmanager

    from tl_core import confidentiality as cf
    from tl_core import modules as core_modules
    from tl_core.modules import ConfidentialSource

    @contextmanager
    def cm() -> Any:
        with open_uow(env.db) as uow:
            conn = uow.conn()
            conn.execute(text("CREATE TABLE IF NOT EXISTS t12a_si (id TEXT PRIMARY KEY, cls TEXT)"))
            conn.execute(text("DELETE FROM t12a_si"))
            ids = [r[0] for r in conn.execute(text(f"SELECT id FROM {SCOPE_ITEM_TABLE}")).all()]
            for rid in ids:
                conn.execute(
                    text("INSERT INTO t12a_si VALUES (:i, :c)"),
                    {"i": rid, "c": "restricted" if rid == item_id else "internal"},
                )
        source = ConfidentialSource(
            record_types=frozenset({SCOPE_ITEM}),
            table="t12a_si",
            id_column="id",
            class_column="cls",
        )
        real = core_modules.confidential_sources
        cf.confidential_sources = lambda: [*real(), source]  # type: ignore[attr-defined]
        try:
            yield
        finally:
            cf.confidential_sources = real  # type: ignore[attr-defined]

    return cm()


def test_progress_on_a_hidden_iwp_or_scope_item_reads_as_a_missing_record(
    env: McpHarness, world: Any, db: Any
) -> None:
    iwp, (item,) = world.pw.package(["10.0"])
    iwp_key, item_key = _key(env, iwp), _key(env, item)
    step = [{"scope_item": item_key, "step": "Material received", "done": True}]
    ghost = [{"scope_item": "P123-SI-9999", "step": "Material received", "done": True}]
    missing_iwp = refused(env, "propose_progress", project=PROJECT, iwp="P123-IWP-9999", steps=step)
    missing_item = refused(env, "propose_progress", project=PROJECT, iwp=iwp_key, steps=ghost)
    with hidden_iwp(db, iwp):
        hidden = refused(env, "propose_progress", project=PROJECT, iwp=iwp_key, steps=step)
    assert hidden == missing_iwp
    assert iwp_key not in hidden
    with _hide_scope_item(env, item):
        hidden_si = refused(env, "propose_progress", project=PROJECT, iwp=iwp_key, steps=step)
    assert hidden_si.replace(item_key, "X") == missing_item.replace("P123-SI-9999", "X")
    assert item_key not in hidden_si


def test_a_week_commitment_to_a_hidden_iwp_reads_as_a_missing_record(
    env: McpHarness, world: Any, db: Any
) -> None:
    world.open("2026-11-16")
    iwp = world.issued()
    key = _key(env, iwp)
    week = call(env, "list_weekly_plans", project=PROJECT)[0]["week"]
    args = {"project": PROJECT, "week": week, "committed_hours": "1.0"}
    missing = refused(env, "propose_week_commitment", iwp="P123-IWP-9999", **args)
    with hidden_iwp(db, iwp):
        hidden = refused(env, "propose_week_commitment", iwp=key, **args)
    assert hidden.replace(key, "X") == missing.replace("P123-IWP-9999", "X")
    assert key not in hidden


# --- the refusal of the two a person alone does, with its reason -------------------------------


def test_an_agent_proposing_a_clear_or_a_close_is_refused_with_the_reason(env: McpHarness) -> None:
    from tl_core.constraints.commands import ClearConstraint
    from tl_core.services.errors import InvalidProposalError
    from tl_mod_awp.commands import CloseWeek

    for tool, command in (
        ("propose_clear_constraint", ClearConstraint.model_construct()),
        ("propose_close_week", CloseWeek.model_construct()),
        ("propose_progress", CloseWeek.model_construct()),
        ("propose_week_commitment", ClearConstraint.model_construct()),
    ):
        with pytest.raises(InvalidProposalError) as why:
            proposals.submit(
                env.factory, tool=tool, agent="agent:triage", command=command, summary="x"
            )
        assert str(why.value), tool
    refusal = refused_text = str(why.value)
    assert "not a" in refusal or "does not propose" in refusal, refused_text
