"""``ChangeSetting`` and the proposal flow for settings (P0-I8 decision D3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from settings_world import ALICE, P1, SRC, World, future
from tl_adapters.db import open_uow
from tl_core.proposals.types import PROPOSABLE_TOOLS
from tl_core.services import proposals
from tl_core.services.errors import (
    BudgetExceededError,
    InvalidProposalError,
    InvalidSettingValueError,
    ProposalDeciderError,
    ReasonRequiredError,
    RiskNotAcceptedError,
    SettingLockedError,
    SettingScopeError,
    UnknownSettingError,
)
from tl_core.services.settings import ChangeSetting, handle_change_setting
from tl_core.settings.types import SETTING_CHANGED

AGENT = "agent:triage"
TOOL = "propose_setting_change"


def change(layer: str = "company", **kw: Any) -> ChangeSetting:
    scope = P1 if layer.startswith("project:") else "company"
    values: dict[str, Any] = {
        "actor": ALICE,
        "source": SRC,
        "scope": scope,
        "key": "t.limit",
        "layer": layer,
        "value": 20,
    }
    values.update(kw)
    return ChangeSetting(**values)


def run(world: World, cmd: ChangeSetting) -> Any:
    with open_uow(world.db) as uow:
        return handle_change_setting(uow, cmd)


def propose(world: World, cmd: ChangeSetting, **kw: Any) -> Any:
    return proposals.submit(
        world.factory,
        tool=TOOL,
        agent=AGENT,
        command=cmd.model_copy(update={"actor": AGENT, "source": "mcp:triage"}),
        summary=kw.pop("summary", "change a setting"),
        **kw,
    )


# --- the command --------------------------------------------------------------------------------


def test_the_command_runs_as_its_actor_and_names_the_stream(world: World) -> None:
    result = run(world, change(value=20, causation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"))
    assert (result.stream_id, result.version, result.key) == ("setting:company:t.limit", 1, None)
    (event,) = result.events
    assert event.event_type == SETTING_CHANGED and event.actor == ALICE
    assert event.causation_id == "01J9Z6Q4W3X2Y1V0T9S8R7Q6P5"
    assert world.value("t.limit") == 20


def test_a_project_layer_needs_that_projects_scope(world: World) -> None:
    run(world, change(P1, value=30))
    assert world.events()[0].scope == P1
    with pytest.raises(ValidationError, match="scope of layer"):
        change(P1, scope="company")
    with pytest.raises(ValidationError, match="scope of layer"):
        change("company", scope=P1)
    with pytest.raises(ValidationError, match="not a layer"):
        change("elsewhere")


def test_a_reset_command_takes_the_value_away(world: World) -> None:
    run(world, change(P1, value=30))
    result = run(world, change(P1, reset=True, value=None))
    assert result.version == 2 and result.events[0].payload["reset"] is True
    assert world.get("t.limit", project="P1").modified_here is False


def test_a_command_that_changes_nothing_has_no_events(world: World) -> None:
    run(world, change(value=20))
    result = run(world, change(value=20))
    assert result.events == [] and result.version == 1


def test_the_command_is_refused_with_the_services_errors(world: World) -> None:
    with pytest.raises(UnknownSettingError):
        run(world, change(key="no.such"))
    with pytest.raises(SettingScopeError):
        run(world, change(key="t.restart", layer=P1))
    with pytest.raises(ReasonRequiredError):
        run(world, change(key="t.advanced", value="b"))
    assert world.head() == 0


def test_a_scheduled_command_applies_later(world: World) -> None:
    when = future(3)
    run(world, change(value=20, applies_at=when))
    assert world.value("t.limit") == 10
    assert world.value("t.limit", at=when + timedelta(seconds=1)) == 20


# --- proposing ----------------------------------------------------------------------------------


def test_the_tool_is_one_of_the_proposable_tools() -> None:
    assert PROPOSABLE_TOOLS[TOOL] == "ChangeSetting"
    assert proposals.COMMANDS["ChangeSetting"][0] is ChangeSetting


def test_a_proposal_changes_nothing_until_a_person_accepts(world: World) -> None:
    view = propose(world, change(P1, value=30), summary="Raise the limit")
    assert (view.status, view.tool, view.command_type, view.scope) == (
        "pending",
        TOOL,
        "ChangeSetting",
        P1,
    )
    assert view.command["layer"] == P1 and view.command["value"] == 30
    assert world.value("t.limit", project="P1") == 10
    done = proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=ALICE)
    assert done.status == "accepted"
    assert world.value("t.limit", project="P1") == 30
    changed = [e for e in world.events() if e.event_type == SETTING_CHANGED][0]
    created = world.events()[0]
    assert (changed.actor, changed.source) == (ALICE, "mcp:triage")
    assert changed.causation_id == created.event_id
    assert changed.correlation_id == view.proposal_id


def test_a_proposal_that_could_never_apply_is_refused_when_it_is_made(world: World) -> None:
    with pytest.raises(UnknownSettingError):
        propose(world, change(key="no.such"))
    with pytest.raises(InvalidSettingValueError):
        propose(world, change(value=999))
    world.lock("t.limit")
    with pytest.raises(SettingLockedError):
        propose(world, change(P1, value=5))
    with pytest.raises(ReasonRequiredError):
        propose(world, change(key="t.advanced", value="b"))
    assert world.rows("cur_setting") == []
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.list_proposals(uow.conn(), P1) == []


def test_an_agent_cannot_bring_its_own_risk_acceptance(world: World) -> None:
    cmd = change(key="t.danger", value=["a"], reason="r", accept_risk=True)
    with pytest.raises(InvalidProposalError, match="cannot accept a risk"):
        propose(world, cmd)


def test_a_dangerous_change_is_proposed_with_a_reason_and_accepted_with_the_risk(
    world: World,
) -> None:
    cmd = change(key="t.danger", value=["a.example.com"], reason="partner hub")
    view = propose(world, cmd)  # not refused: the risk is the accepting person's to take
    head = world.head()
    with pytest.raises(RiskNotAcceptedError, match="accept the risk"):
        proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=ALICE)
    assert world.head() == head  # nothing recorded: no Proposal.Failed, no budget spent again
    assert world.value("t.danger") == []
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.get_proposal(uow.conn(), view.proposal_id).status == "pending"
    done = proposals.accept_or_fail(
        world.factory, proposal_id=view.proposal_id, by=ALICE, accept_risk=True
    )
    assert done.status == "accepted" and world.value("t.danger") == ["a.example.com"]
    changed = [e for e in world.events() if e.event_type == SETTING_CHANGED][0]
    assert changed.payload["accept_risk"] is True and changed.payload["reason"] == "partner hub"
    with open_uow(world.db, readonly=True) as uow:
        stored = proposals.get_proposal(uow.conn(), view.proposal_id)
    assert stored.command["accept_risk"] is False  # the stored command never carried it


def test_a_setting_proposal_shows_what_it_changes_from_the_definition(world: World) -> None:
    world.set("t.danger", "company", ["old.example.com"], reason="r", accept_risk=True)
    cmd = change(key="t.danger", value=["new.example.com"], reason="partner hub")
    view = propose(world, cmd)
    info = view.setting
    assert info is not None
    assert (info.key, info.layer, info.owner) == ("t.danger", "company", None)
    assert (info.risk, info.effect) == ("dangerous", "live")
    assert info.current_value == ["old.example.com"]
    assert info.proposed_value == ["new.example.com"] and info.reset is False
    with open_uow(world.db, readonly=True) as uow:
        listed = proposals.list_proposals(uow.conn(), "company")
        assert listed[0].setting == info


def test_the_layer_owner_of_a_user_setting_is_shown(world: World) -> None:
    cmd = change(key="ui.t.pref", layer="user:bob", value="b")
    info = propose(world, cmd).setting
    assert info is not None and info.owner == "bob" and info.current_value == "a"
    reset = propose(world, change(key="ui.t.pref", layer="user:bob", reset=True, value=None))
    assert reset.setting is not None and reset.setting.reset is True
    assert reset.setting.proposed_value is None


def test_a_proposal_for_a_key_that_is_gone_still_shows_and_says_unknown(world: World) -> None:
    from tl_core.settings.registry import use_definitions

    view = propose(world, change(value=20))
    with use_definitions([]), open_uow(world.db, readonly=True) as uow:
        shown = proposals.get_proposal(uow.conn(), view.proposal_id)
    assert shown.setting is not None
    assert (shown.setting.risk, shown.setting.effect) == ("unknown", "unknown")


def test_other_proposals_have_no_setting_info(world: World) -> None:
    from tl_core.services.commands import CreateRecord

    command = CreateRecord(
        actor=AGENT, source="mcp:triage", scope=P1, record_type="core.Record", title="t", key="K-1"
    )
    shown = proposals.submit(
        world.factory, tool="create_record", agent=AGENT, command=command, summary="x"
    )
    assert shown.setting is None


def test_an_agent_cannot_decide_a_setting_proposal(world: World) -> None:
    view = propose(world, change(value=20))
    with pytest.raises(ProposalDeciderError):
        proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=AGENT)
    assert world.value("t.limit") == 10


def test_a_proposal_that_went_stale_fails_on_accept(world: World) -> None:
    view = propose(world, change(P1, value=30))
    world.lock("t.limit")  # the company locks the key before a person looks at the queue
    done = proposals.accept_or_fail(world.factory, proposal_id=view.proposal_id, by=ALICE)
    assert done.status == "failed" and (done.reason or "").startswith("SettingLockedError")
    assert world.value("t.limit", project="P1") == 10


# --- the budget is a setting --------------------------------------------------------------------


def test_the_daily_budget_comes_from_the_setting(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(proposals.BUDGET_ENV, raising=False)
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.daily_budget(uow.conn()) == 500
    world.set("ai.agents.daily_proposals", "company", 1, reason="spend")
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.daily_budget(uow.conn()) == 1
    propose(world, change(value=20))
    with pytest.raises(BudgetExceededError, match="1 proposals"):
        propose(world, change(value=21))


def test_the_environment_variable_still_overrides_the_setting(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.set("ai.agents.daily_proposals", "company", 1, reason="spend")
    monkeypatch.setenv(proposals.BUDGET_ENV, "3")
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.daily_budget(uow.conn()) == 3
    monkeypatch.setenv(proposals.BUDGET_ENV, "lots")
    with open_uow(world.db, readonly=True) as uow:
        assert proposals.daily_budget(uow.conn()) == 1
    assert proposals.daily_budget() == 500


def test_a_unicode_digit_in_the_budget_variable_is_ignored(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(proposals.BUDGET_ENV, "\u00b2")  # "²".isdigit() is true, int() fails
    assert proposals.daily_budget() == 500
    monkeypatch.setenv(proposals.BUDGET_ENV, "\u0663")  # an Arabic-Indic digit
    assert proposals.daily_budget() == 500


def test_a_dangerous_proposal_with_a_past_time_is_refused_when_it_is_made(world: World) -> None:
    # the dry run lets a missing risk acceptance pass, but not the checks after it
    past = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(InvalidSettingValueError, match="not in the future"):
        propose(world, change(key="t.danger", value=["a"], reason="r", applies_at=past))
