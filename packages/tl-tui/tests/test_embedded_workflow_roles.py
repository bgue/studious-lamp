"""The embedded client derives workflow roles from the signed-in account (ADR-0013, P1-SEC1).

Over a real ledger, on every adapter: the fixture workflow lets only a document controller or an
admin `issue`. The client never takes roles from a caller or a command: a user, an actor with no
account, a disabled controller, an actor that only resembles a real one and a command that names
another actor than the client's all stay blocked; a controller and an admin pass. Taking the
derivation away blocks the controller (the guard of this file).
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from tl_adapters.db import DbTarget, make_uow_factory, open_uow
from tl_core.auth import accounts
from tl_core.auth.password import prepare_password
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import GuardFailedError
from tl_core.services.links import AddLink, handle_add_link
from tl_core.services.records import handle_create_record
from tl_core.services.workflow import TransitionWorkflow
from tl_tui import embedded
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"
GOOD = "correct horse battery"
PEOPLE = (
    ("boss", "person", ["admin"]),
    ("dora", "person", ["user", "document_controller"]),
    ("ursula", "person", ["user"]),
    ("gone", "person", ["user", "document_controller"]),
)


class Ledger:
    def __init__(self, target: DbTarget) -> None:
        self.target = target
        self.count = 0
        with open_uow(target) as uow:
            for name, kind, roles in PEOPLE:
                accounts.create_account(
                    uow, username=name, display_name=name, kind=kind,  # type: ignore[arg-type]
                    roles=roles, password=prepare_password(GOOD, username=name), by="svc:test",
                )  # fmt: skip
        with open_uow(target) as uow:
            found = (
                uow.conn()
                .exec_driver_sql("SELECT account_id FROM cur_account WHERE username = 'gone'")
                .scalar_one()
            )
            accounts.disable(uow, account_id=str(found), by="svc:test", reason="left")

    def client(self, actor: str) -> EmbeddedClient:
        return EmbeddedClient(make_uow_factory(self.target), actor=actor)

    def approved(self) -> tuple[str, int]:
        """A record in `Approved` (its `issue` is role-guarded): ``(id, version)``."""
        self.count += 1
        common: dict[str, Any] = {"actor": "user:ursula", "source": "test", "scope": SCOPE}
        ids: list[str] = []
        with open_uow(self.target) as uow:
            for letter in "AB":
                ids.append(
                    handle_create_record(
                        uow,
                        CreateRecord(
                            **common,
                            record_type="core.Record",
                            title="r",
                            key=f"EW-{self.count}{letter}",
                        ),
                    ).stream_id
                )
            handle_add_link(
                uow, AddLink(**common, from_id=ids[0], to_id=ids[1], relation="references")
            )
        client = self.client("user:ursula")
        version = 1
        for name in ("submit", "approve"):
            version = client.transition(self.command(client, ids[0], version, name)).version
        return ids[0], version

    @staticmethod
    def command(
        client: EmbeddedClient, sid: str, version: int, name: str, *, actor: str | None = None
    ) -> TransitionWorkflow:
        return TransitionWorkflow(
            actor=actor or client.actor,
            source="tui",
            scope=SCOPE,
            stream_id=sid,
            expected_version=version,
            transition=name,
        )

    def state(self, sid: str) -> str:
        return self.client("user:boss").workflow_status(sid).state


@pytest.fixture
def ledger(db: DbTarget) -> Ledger:
    return Ledger(db)


def can_issue(client: EmbeddedClient, sid: str) -> bool:
    return next(o for o in client.workflow_status(sid).options if o.transition == "issue").allowed


@pytest.mark.parametrize("actor", ["user:boss", "user:dora"])
def test_an_admin_and_a_controller_pass_the_roles_guard(ledger: Ledger, actor: str) -> None:
    sid, version = ledger.approved()
    client = ledger.client(actor)
    assert can_issue(client, sid) is True
    done = client.transition(ledger.command(client, sid, version, "issue"))
    assert done.events[0].actor == actor
    assert ledger.state(sid) == "Issued"


@pytest.mark.parametrize(
    "actor",
    [
        "user:ursula",  # a user
        "user:ghost",  # no such account
        "user:gone",  # a disabled controller
        "svc:dora",  # only resembles a real controller: not her actor string
        "user:DORA",  # folds to her name, but is not her actor string
    ],
)
def test_nobody_else_passes_and_nothing_is_written(ledger: Ledger, actor: str) -> None:
    sid, version = ledger.approved()
    client = ledger.client(actor)
    assert can_issue(client, sid) is False
    with pytest.raises(GuardFailedError, match="needs one of the roles: document_controller"):
        client.transition(ledger.command(client, sid, version, "issue"))
    assert ledger.state(sid) == "Approved"


def test_a_command_naming_another_actor_does_not_borrow_that_actors_roles(ledger: Ledger) -> None:
    sid, version = ledger.approved()
    client = ledger.client("user:ursula")
    with pytest.raises(GuardFailedError):
        client.transition(ledger.command(client, sid, version, "issue", actor="user:dora"))
    assert ledger.state(sid) == "Approved"


def test_a_roles_claim_on_a_command_is_dropped(ledger: Ledger) -> None:
    sid, version = ledger.approved()
    client = ledger.client("user:ursula")
    claimed = TransitionWorkflow.model_validate(
        {**ledger.command(client, sid, version, "issue").model_dump(),
         "actor_roles": ["document_controller", "admin"]}
    )  # fmt: skip
    with pytest.raises(GuardFailedError):
        client.transition(claimed)


def test_the_client_has_no_way_to_be_given_roles() -> None:
    assert "roles" not in inspect.signature(EmbeddedClient.workflow_status).parameters
    assert "roles" not in inspect.signature(EmbeddedClient.__init__).parameters


def test_the_derivation_is_what_lets_a_controller_pass(
    ledger: Ledger, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, version = ledger.approved()
    client = ledger.client("user:dora")
    monkeypatch.setattr(embedded, "workflow_roles", lambda _who: ())
    assert can_issue(client, sid) is False
    with pytest.raises(GuardFailedError):
        client.transition(ledger.command(client, sid, version, "issue"))
    monkeypatch.undo()
    assert can_issue(client, sid) is True
