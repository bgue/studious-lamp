"""The document controller over HTTP, on every adapter (ADR-0013).

A user, a document controller, an admin and an agent call every documents command with an empty
body, so only the access check can decide: the ten controlling commands are refused to the user
(403 `forbidden`, naming `control.command.<Name>`), pass for the controller and the admin, and are
`agent_must_propose` for the agent. The controller has no `admin.*` route and cannot recover a link
or change a role. `test_api_documents.py` pins the table; this file runs it as a matrix, on SQLite
and (under `just test-parity`) on Postgres.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from harness import Harness
from tl_api.commands import controller_actions
from tl_api.tokens import add_token
from tl_core.auth import accounts, sessions
from tl_core.auth.password import prepare_password
from tl_mod_correspondence.commands import API_COMMANDS as CORRESPONDENCE_COMMANDS
from tl_mod_documents.commands import API_COMMANDS
from tl_mod_schedule.commands import API_COMMANDS as SCHEDULE_COMMANDS

PASSWORD = "correct horse battery"
SCOPE = "project:P123"
CONTROLLING = {c.model.__name__ for c in API_COMMANDS if c.access == "controller"}


class Cast:
    def __init__(self, harness: Harness) -> None:
        with harness.backend() as uow:
            for name, roles in (
                ("boss", ["admin"]),
                ("dora", ["user", "document_controller"]),
                ("solo", ["document_controller"]),
                ("bob", ["user"]),
            ):
                accounts.create_account(
                    uow, username=name, display_name=name, kind="person", roles=roles,
                    password=prepare_password(PASSWORD), by="svc:test",
                )  # fmt: skip
            accounts.create_account(
                uow, username="sim-dc", display_name="sim", kind="sim",
                roles=["user", "document_controller"], password=prepare_password(PASSWORD),
                by="svc:test",
            )  # fmt: skip
        self.clients = {n: self._client(harness, n) for n in ("boss", "dora", "solo", "bob")}
        self.clients["sim-dc"] = self._client(harness, "sim-dc")
        self.agent = TestClient(harness.app, raise_server_exceptions=False)
        token = add_token(harness.settings.tokens_path, "agent:triage")
        self.agent.headers.update({"Authorization": f"Bearer {token}"})

    @staticmethod
    def _client(harness: Harness, name: str) -> TestClient:
        _, token = sessions.sign_in(harness.backend, username=name, password=PASSWORD)
        client = harness.client_for(None)
        client.headers.update({"Authorization": f"Bearer {token}"})
        return client


@pytest.fixture
def harness(parity_harness: Harness) -> Harness:
    return parity_harness


@pytest.fixture
def cast(harness: Harness) -> Cast:
    return Cast(harness)


def run(client: TestClient, name: str) -> tuple[int, str]:
    response = client.post(f"/commands/{name}", json={"scope": SCOPE})
    return response.status_code, str(response.json().get("message", ""))


def test_the_controlling_set_is_the_twelve_and_the_actions_follow() -> None:
    assert len(CONTROLLING) == 12  # the ten acts of document control, PublishDerivedDocuments, void
    scheduling = {c.model.__name__ for c in SCHEDULE_COMMANDS if c.access == "controller"}
    assert scheduling == {"DefineSchedule", "PublishScheduleSnapshot", "VoidScheduleSnapshot"}
    correspondence = {c.model.__name__ for c in CORRESPONDENCE_COMMANDS if c.access == "controller"}
    assert len(correspondence) == 24  # P1-I5: 13; P1-I6: issue + escalate an RFI, 9 Commercial
    assert controller_actions() == {
        f"control.command.{n}" for n in CONTROLLING | scheduling | correspondence
    }


def test_a_user_is_refused_every_controlling_command_naming_its_action(cast: Cast) -> None:
    for name in sorted(CONTROLLING):
        status, message = run(cast.clients["bob"], name)
        assert status == 403 and f"control.command.{name}" in message, (name, status, message)


def test_a_document_controller_an_admin_and_a_sim_controller_pass_the_access_check(
    cast: Cast,
) -> None:
    for who in ("dora", "solo", "sim-dc", "boss"):  # `solo` holds the role and nothing else
        for name in sorted(CONTROLLING):
            status, _ = run(cast.clients[who], name)
            assert status != 403, (who, name, status)


def test_the_user_commands_are_open_to_everyone_with_a_role(cast: Cast) -> None:
    prepare = {c.model.__name__ for c in API_COMMANDS if c.access == "user"}
    assert len(prepare) == 18  # 14 of document control, 4 of the derivation pipeline
    for who in ("bob", "dora", "solo", "boss"):
        for name in sorted(prepare):
            assert run(cast.clients[who], name)[0] != 403, (who, name)


def test_an_agent_gets_agent_must_propose_for_every_documents_command(cast: Cast) -> None:
    for command in API_COMMANDS:
        response = cast.agent.post(f"/commands/{command.model.__name__}", json={"scope": SCOPE})
        assert response.status_code == 403
        assert response.json()["error"] == "agent_must_propose", command.model.__name__


def test_the_controller_has_no_admin_route_and_cannot_recover_a_link(cast: Cast) -> None:
    for who in ("dora", "solo"):
        client = cast.clients[who]
        assert client.get("/admin/accounts").status_code == 403
        assert client.post("/admin/accounts", json={"username": "e"}).status_code == 403
        assert (
            client.post("/admin/tokens", json={"account_id": "x", "label": "x"}).status_code == 403
        )
        assert run(client, "AdminFlagLink")[0] == 403
        assert run(client, "AdminRetractLink")[0] == 403
        me = client.get("/auth/me").json()
        mine = client.put(f"/admin/accounts/{me['account_id']}/roles", json={"roles": ["admin"]})
        assert mine.status_code == 403
    assert cast.clients["boss"].get("/admin/accounts").status_code == 200


def test_taking_the_role_away_closes_the_commands_at_once(cast: Cast) -> None:
    dora = cast.clients["dora"]
    me = dora.get("/auth/me").json()
    assert run(dora, "IssueRevision")[0] != 403
    took = cast.clients["boss"].put(
        f"/admin/accounts/{me['account_id']}/roles", json={"roles": ["user"], "reason": "moved"}
    )
    assert took.status_code == 200, took.text
    assert dora.get("/auth/me").json()["roles"] == ["user"]  # the same session, no new sign-in
    assert run(dora, "IssueRevision")[0] == 403
    gave = cast.clients["boss"].put(
        f"/admin/accounts/{me['account_id']}/roles", json={"roles": ["user", "document_controller"]}
    )
    assert gave.status_code == 200
    assert run(dora, "IssueRevision")[0] != 403
