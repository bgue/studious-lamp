"""The RFI escalation rule on the rules engine (P1-I6 T05, ADR-0019, ADR-0017).

``dev/seed/rules/rfi-escalation.json`` is a propose-mode rule: when an RFI moves from Awaiting
response to Answered, propose ``EscalateTechnical`` with ``require_impact``. A person with the
controller access accepts it; the rule's service actor reads as the lowest viewer, so a restricted
or privileged RFI never fires it, and acted by a rule the command is refused (it needs a controller
viewer).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from tl_core import confidentiality as cf
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.integration.rules.engine import RulesWorker
from tl_core.integration.rules.service import (
    CreateRule,
    EnableRule,
    ReviseRule,
    handle_create_rule,
    handle_enable_rule,
    handle_revise_rule,
)
from tl_core.services import proposals
from tl_core.services.errors import ProposalNotFoundError
from tl_mod_correspondence.names import COMMERCIAL_TABLE
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, frozen_today

RULE_FILE = Path(__file__).resolve().parents[3] / "dev" / "seed" / "rules" / "rfi-escalation.json"
SCOPE = "project:P123"
MONDAY = "2026-10-19"
DUE = "2026-11-02"
HOLDS = {"user", "controller"}.__contains__


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def parity_accounts(harness: Harness) -> None:
    """A document controller, a user and an admin (the rule's creator)."""
    with harness.backend(False) as uow:
        for name, role in (
            ("ctl", "document_controller"),
            ("bob", "user"),
            ("boss", "admin"),
            ("u", "user"),
        ):
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=[role],
                password=prepare_password("correct horse battery"), by="svc:test",
            )  # fmt: skip


@pytest.fixture
def corr(harness: Harness) -> CorrWorld:
    return CorrWorld(harness.target or harness.db)


def install(harness: Harness, *, mode: str = "propose") -> str:
    body: dict[str, Any] = json.loads(RULE_FILE.read_text())
    with harness.backend(False) as uow:
        made = handle_create_rule(
            uow, CreateRule(actor="user:boss", source="test", scope=SCOPE, **body)
        )
        if mode != "propose":
            handle_revise_rule(
                uow,
                ReviseRule(
                    actor="user:boss", source="test", scope=SCOPE, rule_id=made.stream_id,
                    changes={"mode": mode}, reason="test",
                ),
            )  # fmt: skip
        handle_enable_rule(
            uow, EnableRule(actor="user:boss", source="test", scope=SCOPE, rule_id=made.stream_id)
        )
    return made.stream_id


def answered(corr: CorrWorld, *, cost: str = "yes", restricted: bool = False) -> str:
    """An RFI issued on Monday and answered the same day."""
    with frozen_today(MONDAY):
        made = corr.raise_technical(required_by=DUE)
        corr.submit_technical(made.stream_id)
        if restricted:
            with cf.use_viewer(CONTROLLER):
                corr.set_class(made.stream_id, "restricted")
        with cf.use_viewer(CONTROLLER):
            corr.issue_technical(made.stream_id)
        with cf.use_viewer(CONTROLLER if restricted else cf.LOWEST):
            corr.answer_technical(made.stream_id, cost_impact=cost)
    return made.stream_id


def run_rules(harness: Harness) -> Any:
    from tl_api.commands import command_runner

    return RulesWorker(harness.backend, command_runner()).run_until_idle()


def pending(harness: Harness, viewer: Any = None) -> list[Any]:
    """The proposals the viewer reads (the plain user's viewer when none is given)."""
    with harness.backend(True) as uow, cf.use_viewer(viewer or cf.LOWEST):
        return proposals.list_proposals(uow.conn(), SCOPE, status=None)


def failure_events(corr: CorrWorld) -> list[str]:
    """Every stored `Proposal.Failed` payload, as text (what the event log shows)."""
    rows = corr.rows(
        "SELECT payload AS payload_json FROM events WHERE event_type = 'Proposal.Failed'"
    )
    return [str(r["payload_json"]) for r in rows]


def commercial_items(corr: CorrWorld) -> int:
    return int(corr.scalar(f"SELECT count(*) FROM {COMMERCIAL_TABLE}"))


def test_an_answered_rfi_makes_one_proposal_and_a_controller_accepts_it(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    install(harness)
    item_id = answered(corr)
    run_rules(harness)
    [proposal] = pending(harness)
    assert (proposal.tool, proposal.agent) == ("rule", "svc:rule-rfi-escalation")
    assert proposal.command_type == "EscalateTechnical" and proposal.status == "pending"
    assert proposal.command["stream_id"] == item_id and proposal.command["require_impact"] is True
    assert proposal.command["source"] == "rule:rfi-escalation"
    assert commercial_items(corr) == 0

    with cf.use_viewer(CONTROLLER):  # the entry point sets the viewer of the signed-in person
        done = proposals.accept_or_fail(
            harness.backend, proposal_id=proposal.proposal_id, by="user:ctl", holds=HOLDS
        )
    assert done.status == "accepted", done.reason
    with cf.use_viewer(CONTROLLER):
        notice = corr.commercial("P123-EW-0001")
        assert notice.item.state == "Draft" and notice.item.confidentiality == "restricted"
        assert notice.data.aware_on == MONDAY
        link = corr.rows(
            "SELECT relation, from_id, to_id FROM cur_links WHERE from_id = :n", n=notice.item.id
        )
        assert [(r["relation"], r["to_id"]) for r in link] == [("derived_from", item_id)]
        [bar] = [c for c in corr.clocks("P123-EW-0001") if c.kind == "time_bar"]
        assert bar.due_on == "2026-11-02"  # 14 calendar days from the answer
        sources = {
            r["source"]
            for r in corr.rows("SELECT source FROM events WHERE stream_id = :s", s=notice.item.id)
        }
        assert sources == {"rule:rfi-escalation"}


def test_an_answer_with_no_impact_is_proposed_but_cannot_be_accepted(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    install(harness)
    answered(corr, cost="no")
    run_rules(harness)
    [proposal] = pending(harness)
    with cf.use_viewer(CONTROLLER):  # the entry point sets the viewer of the signed-in person
        done = proposals.accept_or_fail(
            harness.backend, proposal_id=proposal.proposal_id, by="user:ctl", holds=HOLDS
        )
    # a module's refusal is stored as its class and a fixed sentence, never its free text
    assert done.status == "failed" and done.reason == (
        "InvalidItemError: the module refused the command"
    )
    assert commercial_items(corr) == 0


def test_a_user_cannot_accept_it(harness: Harness, corr: CorrWorld, parity_accounts: None) -> None:
    from tl_core.services.errors import ProposalAccessError

    install(harness)
    answered(corr)
    run_rules(harness)
    [proposal] = pending(harness)
    with pytest.raises(ProposalAccessError):
        proposals.accept_or_fail(
            harness.backend,
            proposal_id=proposal.proposal_id,
            by="user:bob",
            holds={"user"}.__contains__,
        )
    assert pending(harness)[0].status == "pending"


def test_a_restricted_rfi_never_fires_the_rule(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    install(harness)
    answered(corr, restricted=True)
    stats = run_rules(harness)
    assert pending(harness) == []
    assert stats.hidden >= 1


def test_acted_by_the_rule_the_command_is_refused(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    """A service actor reads as the lowest viewer, so it holds no controller viewer."""
    install(harness, mode="act")
    answered(corr)
    run_rules(harness)
    assert pending(harness) == []
    assert commercial_items(corr) == 0
    blocked = corr.rows("SELECT event_type FROM events WHERE event_type = 'Rule.Blocked'")
    assert blocked


def test_raise_rfi_in_a_thread_previews_a_real_rfi_of_the_module(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    """With the module installed the core placeholder is replaced (T05b): `/raise rfi` plans a
    `RaiseTechnical`, not a labelled core record."""
    from tl_adapters.db import open_uow
    from tl_api.commands import command_runner
    from tl_core import settings
    from tl_core.threads.contract import DispatchPreview
    from tl_core.threads.planner import ThreadPlanner

    with harness.backend(False) as uow, cf.system_view():
        for key, value in (
            ("threads.enabled", True),
            ("threads.enabled_types", ["correspondence.TechnicalItem"]),
        ):
            settings.set_setting(
                uow,
                key=key,
                layer="company",
                value=value,
                actor="user:boss",
                source="t",
                reason="t",
            )
    with frozen_today(MONDAY):
        first = corr.raise_technical()
    planner = ThreadPlanner(
        factory=lambda readonly=False: open_uow(harness.target or harness.db, readonly=readonly)
    )
    with open_uow(harness.target or harness.db, readonly=True) as uow:
        found = planner.preview(
            uow,
            record_id=first.stream_id,
            text=f"/raise rfi #{first.key} Clash with line 47",
            actor="user:bob",
            holds={"user"}.__contains__,
            runner=command_runner(),
        )
    assert isinstance(found, DispatchPreview), found
    assert found.problems == [] and found.can_dispatch
    assert [p.command_type for p in found.planned] == ["RaiseTechnical"]


def accept(harness: Harness, proposal_id: str) -> Any:
    with cf.use_viewer(CONTROLLER):
        return proposals.accept_or_fail(
            harness.backend, proposal_id=proposal_id, by="user:ctl", holds=HOLDS
        )


def propose_again(harness: Harness, item_id: str) -> str:
    """A second proposal for the same RFI, as the rule would make after a reissue."""
    from tl_core.integration.automation import wants_current_version  # noqa: F401
    from tl_mod_correspondence.handlers.escalate import EscalateTechnical

    with harness.backend(False) as uow:
        made = proposals.propose_for_rule(
            uow,
            proposer="svc:rule-rfi-escalation",
            command=EscalateTechnical(
                actor="svc:rule-rfi-escalation", source="proposal", scope=SCOPE,
                stream_id=item_id, require_impact=True,
            ),
            summary="Again",
            trigger_event_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6PB",
            correlation_id="01J9Z6Q4W3X2Y1V0T9S8R7Q6PC",
        )  # fmt: skip
    return made.proposal_id


def test_a_failed_escalation_names_no_restricted_number_and_no_result_id_to_a_user(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    """F1 and F2 of the security review: the early warning is restricted; a plain user reads the
    proposals, their reasons and the failure events and finds neither its number nor its id."""
    install(harness)
    item_id = answered(corr)
    run_rules(harness)
    [first] = pending(harness)
    done = accept(harness, first.proposal_id)
    assert done.status == "accepted" and done.result_stream_id is not None
    notice_id, notice_number = done.result_stream_id, "P123-EW-0001"

    second = propose_again(harness, item_id)
    failed = accept(harness, second)
    assert failed.status == "failed"
    assert failed.reason == "InvalidItemError: the module refused the command"

    seen = json.dumps([v.model_dump(mode="json") for v in pending(harness)])
    assert "was escalated already" not in seen  # a module's text is not stored at all
    for secret in (notice_number, notice_id):
        assert secret not in seen
        assert all(secret not in event for event in failure_events(corr))
    # the controller reads the id of what the accepted proposal made
    [accepted] = [v for v in pending(harness, CONTROLLER) if v.proposal_id == first.proposal_id]
    assert accepted.result_stream_id == notice_id
    # and the plain user still sees that the proposal was accepted, without the id
    [plain] = [v for v in pending(harness) if v.proposal_id == first.proposal_id]
    assert plain.status == "accepted" and plain.result_stream_id is None


def test_the_escalation_message_of_the_command_names_no_other_number(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    from tl_mod_correspondence.errors import InvalidItemError

    item_id = answered(corr)
    with cf.use_viewer(CONTROLLER):
        corr.escalate(item_id)
        with pytest.raises(InvalidItemError) as raised:
            corr.escalate(item_id)
    assert "P123-EW-0001" not in str(raised.value) and "escalated already" in str(raised.value)


def test_a_privileged_rfi_never_fires_the_rule(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    install(harness)
    with frozen_today(MONDAY):
        made = corr.raise_technical(required_by=DUE)
        corr.submit_technical(made.stream_id)
        with cf.use_viewer(CONTROLLER):
            corr.set_class(made.stream_id, "privileged", grant=["user:ctl"])
            corr.issue_technical(made.stream_id)
            corr.answer_technical(made.stream_id, cost_impact="yes")
    stats = run_rules(harness)
    assert pending(harness, CONTROLLER) == [] and stats.hidden >= 1


def test_an_rfi_reclassified_after_its_proposal_hides_the_proposal_from_a_user(
    harness: Harness, corr: CorrWorld, parity_accounts: None
) -> None:
    install(harness)
    item_id = answered(corr)
    run_rules(harness)
    [proposal] = pending(harness)  # internal when the rule fired: a user reads it
    with frozen_today(MONDAY), cf.use_viewer(CONTROLLER):
        corr.set_class(item_id, "restricted")
    assert pending(harness) == []  # it carries the id of a record the user may no longer read
    with harness.backend(True) as uow, cf.use_viewer(cf.LOWEST):
        with pytest.raises(ProposalNotFoundError):
            proposals.get_proposal(uow.conn(), proposal.proposal_id)
    [seen] = pending(harness, CONTROLLER)
    assert seen.proposal_id == proposal.proposal_id and seen.status == "pending"
    assert accept(harness, proposal.proposal_id).status == "accepted"
