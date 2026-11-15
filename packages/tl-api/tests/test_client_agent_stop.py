"""The HTTP client's agent stop calls round-trip (P2-X2 T01), with the admin error mapping."""

from __future__ import annotations

import pytest
from harness import Harness, ensure_agent
from tl_api.client import ApiClient
from tl_api.client.auth import sign_in
from tl_core.auth import accounts
from tl_core.auth.errors import AccountNotFoundError, ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.services import proposals
from tl_core.services.agent_stop import StoppedAgent
from tl_mod_documents.derivation.publish import PublishDerivedTags

PASSWORD = "correct horse battery"
BASE = "http://testserver"
TRIAGE = "agent:triage"


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    """These tests run on every adapter (`just test-parity`): the ledger is the parity `db`."""
    return parity_harness


@pytest.fixture
def filed(harness: Harness) -> None:
    """An admin and a user; a triage agent that has filed one proposal."""
    with harness.backend() as uow:
        for name, roles in (("boss", ["admin"]), ("bob", ["user"])):
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=roles,
                password=prepare_password(PASSWORD), by="svc:test",
            )  # fmt: skip
    ensure_agent(harness, TRIAGE)  # the agent's account, and S1's explicit filing grant
    command = PublishDerivedTags(
        actor=TRIAGE, source="mcp:triage", scope="project:P123", derived_id="NOSUCH",
        expected_content_rev=1,
    )  # fmt: skip
    with harness.backend(readonly=False) as uow:
        proposals.propose(
            uow, tool="propose_import_tags", agent=TRIAGE, command=command, summary="publish"
        )


def client_for(harness: Harness, username: str) -> ApiClient:
    out = sign_in(BASE, username, PASSWORD, http=harness.client_for(None))
    return ApiClient(BASE, out.token, http=harness.client_for(None))


def test_the_three_methods_round_trip_through_the_admin_client(
    harness: Harness, filed: None
) -> None:
    admin = client_for(harness, "boss")
    stopped = admin.stop_agent(TRIAGE, reason="breach")
    assert stopped.changed is True and stopped.events
    assert admin.stop_agent(TRIAGE).changed is False
    listed = admin.list_stopped_agents()
    assert [(a.agent, a.reason, a.held) for a in listed] == [(TRIAGE, "breach", 1)]
    assert isinstance(listed[0], StoppedAgent)
    assert admin.list_stopped_agents(limit=1) == listed
    resumed = admin.resume_agent(TRIAGE)
    assert resumed.changed is True
    assert admin.resume_agent(TRIAGE).changed is False
    assert admin.list_stopped_agents() == []


def test_a_user_is_forbidden_from_every_agent_stop_call(harness: Harness, filed: None) -> None:
    bob = client_for(harness, "bob")
    calls = [
        lambda: bob.stop_agent(TRIAGE),
        lambda: bob.resume_agent(TRIAGE),
        lambda: bob.list_stopped_agents(),
    ]
    for call in calls:
        with pytest.raises(ForbiddenError):
            call()


def test_an_unknown_agent_raises_account_not_found(harness: Harness, filed: None) -> None:
    admin = client_for(harness, "boss")
    with pytest.raises(AccountNotFoundError):
        admin.stop_agent("agent:nosuch")
    with pytest.raises(AccountNotFoundError):
        admin.resume_agent("agent:nosuch")
