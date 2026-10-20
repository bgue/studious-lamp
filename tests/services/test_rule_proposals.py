"""A rule in propose mode proposes as ``svc:rule-<slug>``; a person accepts it (FANOUT D3, D7)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from tl_adapters.db import create_schema, make_uow_factory, open_uow
from tl_core.services import proposals
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import (
    BudgetExceededError,
    InvalidProposalError,
    ProposalDeciderError,
    ReservedIdentifierError,
)
from tl_core.services.feed import PostToFeed

SCOPE = "project:P123"
RULE = "svc:rule-hse-notify"
TRIGGER = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PB"
CORR = "01J9Z6Q4W3X2Y1V0T9S8R7Q6PC"


@pytest.fixture
def db(new_db: Callable[[], str | Path]) -> str | Path:
    target = new_db()
    create_schema(target)
    return target


def post(body: str = "HSE notified", **extra: object) -> PostToFeed:
    return PostToFeed(actor=RULE, source="proposal", scope=SCOPE, body=body, **extra)  # type: ignore[arg-type]


def propose(db: str | Path, command: object = None, **kw: object):  # noqa: ANN201
    with open_uow(db) as uow:
        return proposals.propose_for_rule(
            uow,
            proposer=kw.pop("proposer", RULE),  # type: ignore[arg-type]
            command=command or post(),  # type: ignore[arg-type]
            summary="Post HSE notice",
            trigger_event_id=TRIGGER,
            correlation_id=CORR,
            **kw,  # type: ignore[arg-type]
        )


def test_a_rule_proposal_is_pending_and_stamped_with_the_rule(db: str | Path) -> None:
    view = propose(db)
    assert view.status == "pending" and view.tool == "rule" and view.agent == RULE
    assert view.command["actor"] == RULE and view.command["source"] == "rule:hse-notify"
    assert view.command["correlation_id"] == CORR and view.command["causation_id"] == TRIGGER


def test_a_person_accepts_and_the_command_runs_as_that_person_with_the_rules_source(
    db: str | Path,
) -> None:
    view = propose(db)
    done = proposals.accept_or_fail(
        make_uow_factory(db), proposal_id=view.proposal_id, by="user:mlee"
    )
    assert done.status == "accepted"
    with open_uow(db, readonly=True) as uow:
        from sqlalchemy import text

        row = (
            uow.conn()
            .execute(
                text("SELECT actor, source FROM events WHERE stream_id = :s ORDER BY seq"),
                {"s": done.result_stream_id},
            )
            .first()
        )
    assert row is not None and (row.actor, row.source) == ("user:mlee", "rule:hse-notify")


def test_only_a_person_decides(db: str | Path) -> None:
    view = propose(db)
    with open_uow(db) as uow, pytest.raises(ProposalDeciderError):
        proposals.accept_proposal(uow, proposal_id=view.proposal_id, by=RULE)


@pytest.mark.parametrize(
    "proposer", ["svc:inbound-x", "svc:rule-", "svc:rule-X", "agent:triage", "user:mlee", "rule-x"]
)
def test_only_a_rule_proposes_this_way(db: str | Path, proposer: str) -> None:
    with pytest.raises(InvalidProposalError):
        propose(db, proposer=proposer)


def test_a_command_a_rule_may_not_propose_is_refused(db: str | Path) -> None:
    from tl_core.services.settings import ChangeSetting

    change = ChangeSetting(
        actor=RULE, source="proposal", scope="company", key="integration.kill_switch",
        layer="company", value=True,
    )  # fmt: skip
    with pytest.raises(InvalidProposalError):
        propose(db, change)


def test_a_server_set_identifier_in_the_command_is_refused(db: str | Path) -> None:
    with pytest.raises(ReservedIdentifierError):
        propose(db, post(correlation_id="rule:x"))


def test_a_rule_has_a_daily_budget_like_an_agent(db: str | Path) -> None:
    propose(db, budget=1)
    with pytest.raises(BudgetExceededError):
        propose(db, budget=1)


def test_an_agent_tool_cannot_reach_the_rule_path(db: str | Path) -> None:
    """``rule`` is not an MCP tool and the new command types have no tool."""
    assert "rule" not in proposals.proposable_tools()
    assert not {"UpdateRecord", "SuggestLink", "PostToFeed"} & set(
        proposals.proposable_tools().values()
    )
    command = CreateRecord(
        actor="agent:triage", source="mcp:triage", scope=SCOPE, record_type="core.Record", title="t"
    )
    with open_uow(db) as uow, pytest.raises(InvalidProposalError):
        proposals.propose(uow, tool="rule", agent="agent:triage", command=command, summary="s")
