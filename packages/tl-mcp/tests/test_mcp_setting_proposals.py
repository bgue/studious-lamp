"""propose_setting_change: a setting change is proposed by an agent and made by a person (D3)."""

from __future__ import annotations

from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp_harness import ACTOR, SCOPE, McpHarness
from tl_core import settings
from tl_core.services import proposals

ALICE = "user:alice"
KEY = "feed.reactions.enabled"


def propose(env: McpHarness, **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {"key": KEY, "layer": SCOPE, "value": False}
    args.update(kw)
    out = env.structured("propose_setting_change", **args)
    assert isinstance(out, dict)
    return out


def value(env: McpHarness, key: str = KEY, **kw: Any) -> Any:
    with env.factory(True) as uow:
        return settings.value_of(uow.conn(), key, **kw)


def accept(env: McpHarness, proposal_id: str, **kw: Any) -> Any:
    return proposals.accept_or_fail(env.factory, proposal_id=proposal_id, by=ALICE, **kw)


def test_the_tool_files_a_pending_proposal_and_changes_nothing(env: McpHarness) -> None:
    out = propose(env, summary="Switch reactions off for P123")
    proposal = out["proposal"]
    assert (proposal["status"], proposal["tool"], proposal["agent"], proposal["scope"]) == (
        "pending",
        "propose_setting_change",
        ACTOR,
        SCOPE,
    )
    assert proposal["command_type"] == "ChangeSetting" and proposal["summary"].startswith("Switch")
    assert proposal["command"]["layer"] == SCOPE and proposal["command"]["value"] is False
    assert "Nothing has changed yet" in out["message"]
    assert value(env, project="P123") is True


def test_a_person_accepting_changes_the_setting_as_themselves(env: McpHarness) -> None:
    out = propose(env, reason="field pilot")
    assert accept(env, out["proposal"]["proposal_id"]).status == "accepted"
    assert value(env, project="P123") is False
    with env.factory(True) as uow:
        events = [
            e for e in uow.ledger.read_after(0, limit=100) if e.event_type == "Setting.Changed"
        ]
    (changed,) = events
    assert (changed.actor, changed.source) == (ALICE, "mcp:triage")
    assert changed.payload["layer"] == SCOPE and changed.payload["reason"] == "field pilot"


def test_the_summary_is_made_up_when_none_is_given(env: McpHarness) -> None:
    summary = propose(env)["proposal"]["summary"]
    assert KEY in summary and SCOPE in summary
    reset = propose(env, reset=True, value=None)["proposal"]["summary"]
    assert "reset" in reset


def test_a_reset_and_a_scheduled_change_are_proposed(env: McpHarness) -> None:
    out = propose(env, reset=True, value=None)
    assert out["proposal"]["command"]["reset"] is True
    later = propose(env, applies_at="2099-01-01T00:00:00Z")
    assert later["proposal"]["command"]["applies_at"].startswith("2099-01-01")


def test_what_could_never_apply_is_refused_when_proposing(env: McpHarness) -> None:
    for args, message in (
        ({"key": "no.such"}, "no setting"),
        ({"value": "yes"}, "takes a bool"),
        ({"layer": "elsewhere"}, "not a layer"),
        ({"key": "ui.tui.keymap", "layer": SCOPE, "value": "vim"}, "cannot be set"),
        ({"key": "webhooks.retry.max_hours", "layer": "company", "value": 48}, "say why"),
        ({"applies_at": "tomorrow"}, "ISO 8601"),
        ({"applies_at": "2001-01-01T00:00:00Z"}, "not in the future"),
    ):
        with pytest.raises(ToolError, match=message):
            env.call(
                "propose_setting_change", **{"key": KEY, "layer": SCOPE, "value": False, **args}
            )
    with env.factory(True) as uow:
        assert uow.ledger.head_seq() == 0


def test_a_locked_key_is_refused_now(env: McpHarness) -> None:
    with env.factory(False) as uow:
        settings.lock_setting(
            uow, key=KEY, locked=True, bounds=None, actor=ALICE, source="t", reason="policy"
        )
    with pytest.raises(ToolError, match="locked by the company"):
        env.call("propose_setting_change", key=KEY, layer=SCOPE, value=False)


def test_a_dangerous_key_is_proposed_and_the_person_takes_the_risk(env: McpHarness) -> None:
    out = propose(
        env,
        key="webhooks.egress.allowlist",
        layer="company",
        value=["hub.example.com"],
        reason="partner hub",
    )
    pid = out["proposal"]["proposal_id"]
    assert accept(env, pid).status == "failed"
    again = propose(
        env,
        key="webhooks.egress.allowlist",
        layer="company",
        value=["hub.example.com"],
        reason="partner hub",
    )["proposal"]["proposal_id"]
    assert accept(env, again, accept_risk=True).status == "accepted"
    assert value(env, "webhooks.egress.allowlist") == ["hub.example.com"]


def test_the_tool_cannot_carry_a_risk_acceptance(env: McpHarness) -> None:
    out = env.structured(
        "propose_setting_change",
        key="webhooks.egress.allowlist",
        layer="company",
        value=["x.example.com"],
        reason="r",
        accept_risk=True,  # not a parameter of the tool: ignored
    )
    assert isinstance(out, dict)
    assert out["proposal"]["command"]["accept_risk"] is False
    assert accept(env, out["proposal"]["proposal_id"]).status == "failed"
    assert value(env, "webhooks.egress.allowlist") == []


def test_a_value_is_bounded_in_size(env: McpHarness) -> None:
    with pytest.raises(ToolError, match="longer than"):
        env.call(
            "propose_setting_change",
            key="feed.signal_tags",
            layer="company",
            value=["x" * 60] * 1500,
        )
