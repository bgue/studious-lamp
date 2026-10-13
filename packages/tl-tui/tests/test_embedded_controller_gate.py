"""The embedded client's gate for controlling acts (ADR-0013): who may `issue_transmittal`.

Over a real ledger: an admin, a document controller, a sim controller and a controller who also
holds `user` issue; a plain user, an actor with no account, a disabled controller, an agent and an
actor string that only folds to a real name are refused with `ForbiddenError` and nothing is
written. A command that names another actor than the client's is refused too.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_adapters.sqlite.uow import create_schema
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    handle_create_transmittal,
)
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_tui.embedded import EmbeddedClient

FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
GOOD = "correct horse battery"
PEOPLE = (
    ("boss", "person", ["admin"]),
    ("dora", "person", ["user", "document_controller"]),
    ("solo", "person", ["document_controller"]),
    ("sim-dc", "sim", ["user", "document_controller"]),
    ("ursula", "person", ["user"]),
    ("gone", "person", ["user", "document_controller"]),
)


class Ledger:
    def __init__(self, path: Path, transmittal_id: str) -> None:
        self.path = path
        self.transmittal_id = transmittal_id

    def client(self, actor: str) -> EmbeddedClient:
        return EmbeddedClient(SqliteUowFactory(self.path), actor=actor)

    def command(self, actor: str) -> IssueTransmittal:
        return IssueTransmittal(**{**BASE, "actor": actor}, stream_id=self.transmittal_id)

    def issued(self) -> int:
        with open_uow(self.path, readonly=True) as uow:
            return len(
                uow.conn()
                .exec_driver_sql("SELECT 1 FROM events WHERE event_type = 'Transmittal.Issued'")
                .all()
            )


@pytest.fixture
def ledger(tmp_path: Path) -> Iterator[Ledger]:
    with use_provider(DirectorySchemaProvider(FIXTURES)):
        path = tmp_path / "tl.db"
        create_schema(path)
        world = DocumentsWorld(path, tmp_path / "objects")
        world.issued_document("ISO-1234", "IFR")
        with open_uow(path) as uow:
            for name, kind, roles in PEOPLE:
                accounts.create_account(
                    uow, username=name, display_name=name, kind=kind,  # type: ignore[arg-type]
                    roles=roles, password=prepare_password(GOOD, username=name), by="svc:test",
                )  # fmt: skip
            bot = accounts.create_account(
                uow, username="bot", display_name="bot", kind="agent", roles=["user"],
                password=None, by="svc:test",
            )  # fmt: skip
            assert bot.kind == "agent"
        made = ledger_transmittal(path, world)
        yield Ledger(path, made)


def ledger_transmittal(path: Path, world: DocumentsWorld) -> str:
    with open_uow(path) as uow:
        return handle_create_transmittal(
            uow,
            CreateTransmittal(
                **BASE,
                subject="To site",
                purpose="for_construction",
                recipients=[Recipient(name="Site")],
                revision_ids=[world.revision("ISO-1234", "A").id],
            ),
        ).stream_id


def disable(ledger: Ledger, username: str) -> None:
    with open_uow(ledger.path) as uow:
        found = (
            uow.conn()
            .exec_driver_sql("SELECT account_id FROM cur_account WHERE username = ?", (username,))
            .scalar_one()
        )
        accounts.disable(uow, account_id=str(found), by="svc:test", reason="left")


@pytest.mark.parametrize("who", ["boss", "dora", "solo", "sim-dc"])
def test_an_admin_a_controller_and_a_sim_controller_may_issue(ledger: Ledger, who: str) -> None:
    actor = f"user:{who}"
    ledger.client(actor).issue_transmittal(ledger.command(actor))
    assert ledger.issued() == 1


def refused(
    ledger: Ledger,
    actor: str,
    command_actor: str | None = None,
    match: str = "document_controller or admin",
) -> None:
    with pytest.raises(ForbiddenError, match=match):
        ledger.client(actor).issue_transmittal(ledger.command(command_actor or actor))
    assert ledger.issued() == 0


def test_a_plain_user_is_refused(ledger: Ledger) -> None:
    refused(ledger, "user:ursula")


def test_an_actor_with_no_account_is_refused(ledger: Ledger) -> None:
    refused(ledger, "user:nobody")
    refused(ledger, "svc:root")


def test_a_disabled_controller_is_refused(ledger: Ledger) -> None:
    disable(ledger, "gone")
    refused(ledger, "user:gone")


def test_an_agent_actor_is_refused(ledger: Ledger) -> None:
    with pytest.raises(ValueError, match="agent_must_propose"):  # no client at all for an agent
        ledger.client("agent:bot")
    assert ledger.issued() == 0
    refused(ledger, "user:bot")  # the person string of an agent's name is not the agent's actor


def test_an_actor_that_only_folds_to_a_real_name_is_refused(ledger: Ledger) -> None:
    refused(ledger, "USER:DORA")
    refused(ledger, "svc:dora")


def test_a_command_naming_another_actor_is_refused(ledger: Ledger) -> None:
    """The gate vets the client's actor; the command must not record someone else's name."""
    refused(ledger, "user:dora", "user:boss", match="other than the signed-in person")
    refused(ledger, "user:dora", "user:ursula", match="other than the signed-in person")


def test_taking_the_role_away_closes_the_gate_for_the_same_client(ledger: Ledger) -> None:
    client = ledger.client("user:gone")
    with open_uow(ledger.path) as uow:
        found = (
            uow.conn()
            .exec_driver_sql("SELECT account_id FROM cur_account WHERE username = 'gone'")
            .scalar_one()
        )
        accounts.set_roles(uow, account_id=str(found), roles=["user"], by="svc:test", reason=None)
    with pytest.raises(ForbiddenError):
        client.issue_transmittal(ledger.command("user:gone"))
    assert ledger.issued() == 0


def test_the_other_writes_stay_open_to_a_plain_user(ledger: Ledger) -> None:
    """Only issuing is gated: drafting is anyone's work (ADR-0011, ADR-0013)."""
    client = ledger.client("user:ursula")
    made = client.create_transmittal(
        CreateTransmittal(
            **{**BASE, "actor": "user:ursula"},
            subject="Another",
            purpose="for_construction",
            recipients=[Recipient(name="Site")],
            revision_ids=[_first_revision(ledger)],
        )
    )
    assert made.key


def _first_revision(ledger: Ledger) -> str:
    with open_uow(ledger.path, readonly=True) as uow:
        return str(
            uow.conn().exec_driver_sql("SELECT id FROM cur_documents_revision LIMIT 1").scalar_one()
        )
