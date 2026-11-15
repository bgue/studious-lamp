"""The agent stop routes over HTTP (P2-X2 T01; ADR-0029 decision 6; ADR-0016 for the list).

Stop, resume and the list of stopped agents are admin routes: a plain user, a document controller
and an agent get 403. A stop answers `changed: false` on a repeat. An unknown agent and one that
never filed get the same 404 body. The list counts only the held proposals the reader may see,
for five readers: an admin without clearance, a user, a controller, the lowest reader, and a
person named on the privileged item (full clearance for that record). Expectations come from the
spec and the seed, never from the code under test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from harness import Harness, ensure_agent
from tl_api.tokens import add_token
from tl_core import confidentiality as cf
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.services import agent_stop, proposals
from tl_mod_correspondence.confseed import seed_hidden_world
from tl_mod_documents.derivation.publish import PublishDerivedTags

PASSWORD = "correct horse battery"
SCOPE = "project:P123"
TRIAGE = "agent:triage"
PEOPLE = (
    ("ada", ("admin",)),
    ("uma", ("user",)),
    ("dora", ("user", "document_controller")),
    ("amy", ("user",)),
)


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


class Cast:
    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.clients: dict[str, TestClient] = {}
        for name, roles in PEOPLE:
            self.person(name, roles)
        with harness.backend() as uow:
            accounts.create_account(
                uow, username="triage", display_name="Triage", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            accounts.create_account(
                uow, username="idle", display_name="Idle", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
        token = add_token(harness.settings.tokens_path, TRIAGE)
        self.clients[TRIAGE] = self._client(token)

    def _client(self, token: str) -> TestClient:
        client = self.harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client

    def person(self, name: str, roles: tuple[str, ...]) -> None:
        with self.harness.backend() as uow:
            accounts.create_account(
                uow, username=name, display_name=name.title(), kind="person", roles=list(roles),
                password=prepare_password(PASSWORD, username=name), by="svc:test",
            )  # fmt: skip
        _, token = sessions.sign_in(self.harness.backend, username=name, password=PASSWORD)
        self.clients[name] = self._client(token)


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def file_proposal(harness: Harness, agent: str, derived_id: str) -> str:
    """File one pending proposal of ``agent`` that carries ``derived_id`` (nothing is checked)."""
    ensure_agent(harness, agent)  # S1: an agent files only under an explicit grant
    command = PublishDerivedTags(
        actor=agent, source="mcp:triage", scope=SCOPE, derived_id=derived_id, expected_content_rev=1
    )
    with harness.backend(readonly=False) as uow, cf.system_view():
        # the seed writes as the system: propose reads back what it wrote, and the lowest viewer
        # may not read a proposal that carries the privileged record
        return proposals.propose(
            uow, tool="propose_import_tags", agent=agent, command=command, summary="publish"
        ).proposal_id


def code(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.json()["error"])


# --- stop and resume ---------------------------------------------------------------------------


def test_an_admin_stops_then_a_second_stop_answers_changed_false(
    harness: Harness, cast: Cast
) -> None:
    file_proposal(harness, TRIAGE, "NOSUCH")
    ada = cast.clients["ada"]
    first = ada.post("/admin/agents/stop", json={"agent": TRIAGE, "reason": "breach"})
    assert first.status_code == 200 and first.json()["changed"] is True, first.text
    again = ada.post("/admin/agents/stop", json={"agent": TRIAGE})
    assert again.status_code == 200 and again.json()["changed"] is False, again.text
    assert again.json()["events"] == []


def test_an_admin_resumes_then_a_second_resume_answers_changed_false(
    harness: Harness, cast: Cast
) -> None:
    file_proposal(harness, TRIAGE, "NOSUCH")
    ada = cast.clients["ada"]
    assert ada.post("/admin/agents/resume", json={"agent": TRIAGE}).json()["changed"] is False
    ada.post("/admin/agents/stop", json={"agent": TRIAGE})
    done = ada.post("/admin/agents/resume", json={"agent": TRIAGE})
    assert done.status_code == 200 and done.json()["changed"] is True, done.text
    again = ada.post("/admin/agents/resume", json={"agent": TRIAGE})
    assert again.status_code == 200 and again.json()["changed"] is False, again.text


@pytest.mark.parametrize("who", ["uma", "dora", TRIAGE])
def test_every_agent_stop_route_is_403_for_a_user_a_controller_and_an_agent(
    harness: Harness, cast: Cast, who: str
) -> None:
    file_proposal(harness, TRIAGE, "NOSUCH")
    client = cast.clients[who]
    assert client.post("/admin/agents/stop", json={"agent": TRIAGE}).status_code == 403
    assert client.post("/admin/agents/resume", json={"agent": TRIAGE}).status_code == 403
    assert client.get("/admin/agents/stopped").status_code == 403
    still = cast.clients["ada"].get("/admin/agents/stopped").json()
    assert still == []  # nothing was written by the refused calls


def test_an_unknown_agent_and_a_never_filed_agent_get_the_same_404(cast: Cast) -> None:
    ada = cast.clients["ada"]
    unknown = ada.post("/admin/agents/stop", json={"agent": "agent:nosuch"})
    idle = ada.post("/admin/agents/stop", json={"agent": "agent:idle"})
    no_prefix = ada.post("/admin/agents/resume", json={"agent": "triage"})
    for response in (unknown, idle, no_prefix):
        assert response.status_code == 404 and code(response) == "account_not_found", response.text
    assert unknown.json() == idle.json() == no_prefix.json()


def test_a_stopped_agent_is_refused_a_filing_and_files_again_after_resume(
    harness: Harness, cast: Cast
) -> None:
    file_proposal(harness, TRIAGE, "NOSUCH")
    cast.clients["ada"].post("/admin/agents/stop", json={"agent": TRIAGE})
    with pytest.raises(ForbiddenError):
        file_proposal(harness, TRIAGE, "NOSUCH")
    cast.clients["ada"].post("/admin/agents/resume", json={"agent": TRIAGE})
    assert file_proposal(harness, TRIAGE, "NOSUCH")


def test_the_body_is_closed_and_the_list_limit_is_bounded(harness: Harness, cast: Cast) -> None:
    file_proposal(harness, TRIAGE, "NOSUCH")
    ada = cast.clients["ada"]
    extra = ada.post("/admin/agents/stop", json={"agent": TRIAGE, "actor": "user:uma"})
    assert extra.status_code == 422, extra.text
    assert ada.get("/admin/agents/stopped", params={"limit": 0}).status_code == 422
    assert ada.get("/admin/agents/stopped", params={"limit": 501}).status_code == 422


# --- the list and the held count, five readers ------------------------------------------------


def test_the_list_counts_only_the_held_proposals_each_reader_may_see(
    harness: Harness, cast: Cast, tmp_path: Path
) -> None:
    hidden = seed_hidden_world(harness.target or harness.db, harness.service, tmp_path)
    file_proposal(harness, TRIAGE, hidden.ids["open"])
    file_proposal(harness, TRIAGE, hidden.ids["privileged"])
    cast.clients["ada"].post("/admin/agents/stop", json={"agent": TRIAGE, "reason": "review"})

    # the world without the privileged proposal: one held proposal, the open one
    held_for = {}
    for name, actor in (
        ("admin", "user:ada"),  # admin, not named on the privileged item
        ("user", "user:uma"),
        ("controller", "user:dora"),
        ("lowest", None),
        ("named", "user:amy"),  # named on the privileged item: full clearance for it
    ):
        with harness.backend(readonly=True) as uow:
            viewer = cf.viewer_for_actor(uow.conn(), actor) if actor else cf.LOWEST
            rows = agent_stop.list_stopped(uow.conn(), viewer)
        (row,) = [r for r in rows if r.agent == TRIAGE]
        held_for[name] = row.held
    assert held_for == {"admin": 1, "user": 1, "controller": 1, "lowest": 1, "named": 2}

    body = cast.clients["ada"].get("/admin/agents/stopped")
    assert [(r["agent"], r["held"], r["reason"]) for r in body.json()] == [(TRIAGE, 1, "review")]
    assert set(body.json()[0]) == {"agent", "stopped_at", "stopped_by", "reason", "held"}
    assert hidden.ids["privileged"] not in body.text
