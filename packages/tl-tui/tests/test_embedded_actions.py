"""The embedded client's record actions, module command runners and file fetch (P1-UX2-S1).

A real ledger (the hidden world of ADR-0016, a document with a draft revision, a tag) and real
accounts: what a record offers follows the signed-in person's roles; ``document_command`` and
``engineering_command`` refuse a name the module's table does not hold and an access the person
lacks, as ``correspondence_command`` does; ``fetch_file`` writes a verified file in a safe place.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest
from harness import Harness
from sqlalchemy import text
from tl_adapters.db import open_uow
from tl_adapters.sqlite.factory import SqliteUowFactory
from tl_core.auth import accounts
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.extypes.errors import BodyStoreUnavailableError
from tl_core.files.types import object_key
from tl_core.services.errors import RecordNotFoundError, UnknownFileError, UploadVerificationError
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world
from tl_mod_documents.derivation import store as derivation_store
from tl_mod_documents.handlers.documents import VoidDocument
from tl_mod_documents.handlers.revisions import IssueRevision, VoidRevision
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_mod_engineering.handlers.standards import RegisterCodeList
from tl_mod_engineering.handlers.tags import CreateTag, RenameTag
from tl_mod_engineering.testing import seed_registry
from tl_tui.embedded import EmbeddedClient

SCOPE = "project:P123"
FAKE_ID = "01J000000000000000000000"
ROLES = {"bob": ["user"], "ctl": ["document_controller"], "boss": ["admin"]}


class Ledger:
    def __init__(self, harness: Harness, hidden: Hidden, docs: DocumentsWorld) -> None:
        self.harness = harness
        self.hidden = hidden
        self.docs = docs

    def client(self, name: str, *, files: bool = True) -> EmbeddedClient:
        return EmbeddedClient(
            SqliteUowFactory(self.harness.db),
            actor=f"user:{name}",
            files=self.harness.service if files else None,
        )

    def command(self, model: Any, name: str, **fields: Any) -> Any:
        return model(**{**BASE, "actor": f"user:{name}", **fields})

    def events(self) -> int:
        with open_uow(self.harness.db, readonly=True) as uow:
            return int(uow.conn().execute(text("SELECT count(*) FROM events")).scalar_one())


@pytest.fixture
def ledger(harness: Harness, tmp_path: Path) -> Ledger:
    with harness.backend(False) as uow:
        for name, roles in ROLES.items():
            accounts.create_account(
                uow,
                username=name,
                display_name=name.title(),
                kind="person",
                roles=roles,
                password=prepare_password("correct horse battery"),
                by="svc:test",
            )
    seed_registry(harness.db)
    hidden = seed_hidden_world(harness.db, harness.service, tmp_path)
    docs = DocumentsWorld(harness.db, tmp_path / "docs")
    docs.create_revision("ISO-9002")  # revision B of the open document: a draft
    return Ledger(harness, hidden, docs)


# --- what a record offers ---------------------------------------------------------------------


def test_what_a_draft_revision_offers_follows_the_roles_of_the_person(ledger: Ledger) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    offers = {
        who: [a.command for a in ledger.client(who).allowed_actions(draft).actions] for who in ROLES
    }
    assert offers == {
        "bob": ["VoidRevision"],
        "ctl": ["IssueRevision", "VoidRevision"],
        "boss": ["IssueRevision", "VoidRevision"],
    }
    found = ledger.client("bob").allowed_actions(draft)
    assert found.record_id == draft and found.state is None  # it has not moved from its start
    assert [a.label for a in found.actions] == ["Void"]


def test_a_record_the_person_may_not_read_answers_like_a_missing_one(ledger: Ledger) -> None:
    bob = ledger.client("bob")
    with pytest.raises(RecordNotFoundError) as unknown:
        bob.allowed_actions(FAKE_ID)
    for kind in ("restricted", "privileged", "bogus", "document", "commercial", "secret_rfi"):
        record_id = ledger.hidden.ids[kind]
        with pytest.raises(RecordNotFoundError) as hidden:
            bob.allowed_actions(record_id)
        assert str(hidden.value).replace(record_id, FAKE_ID) == str(unknown.value), kind
    # the controller reads the restricted ones, and the person named reads the privileged one
    assert ledger.client("ctl").allowed_actions(ledger.hidden.ids["commercial"]).actions
    assert ledger.client("ctl").allowed_actions(ledger.hidden.ids["secret_rfi"]).actions


def test_an_agent_cannot_use_the_embedded_client_at_all(ledger: Ledger) -> None:
    with pytest.raises(ValueError, match="agent"):
        EmbeddedClient(SqliteUowFactory(ledger.harness.db), actor="agent:bot")


# --- the module command runners ----------------------------------------------------------------


def test_document_command_refuses_a_name_the_documents_table_does_not_hold(
    ledger: Ledger,
) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    bob = ledger.client("bob")
    void = ledger.command(VoidRevision, "bob", stream_id=draft, reason="in error")
    before = ledger.events()
    with pytest.raises(ForbiddenError, match="CloseCorrespondence is not a documents command"):
        bob.document_command("CloseCorrespondence", void)
    with pytest.raises(ForbiddenError, match="VoidDocument is not a documents command"):
        bob.document_command("VoidDocument", void)  # the name and the class must agree
    with pytest.raises(ForbiddenError, match="VoidRevision is not a engineering command"):
        bob.engineering_command("VoidRevision", void)  # a documents command is not engineering's
    assert ledger.events() == before


def test_document_command_refuses_an_access_the_person_lacks_and_runs_it_for_who_has_it(
    ledger: Ledger,
) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    other = ledger.docs.register("ISO-7001")
    before = ledger.events()
    bob = ledger.client("bob")
    with pytest.raises(ForbiddenError, match="document_controller or admin"):
        bob.document_command(
            "VoidDocument",
            ledger.command(VoidDocument, "bob", stream_id=other.stream_id, reason="x"),
        )
    with pytest.raises(ForbiddenError, match="document_controller or admin"):
        bob.document_command(
            "IssueRevision",
            ledger.command(IssueRevision, "bob", stream_id=draft, issue_status="IFR"),
        )
    assert ledger.events() == before  # nothing was written
    ctl = ledger.client("ctl")
    done = ctl.document_command(
        "VoidDocument", ledger.command(VoidDocument, "ctl", stream_id=other.stream_id, reason="x")
    )
    assert ledger.events() > before
    assert all(ctl.own_writes.classify(event) == "own" for event in done.events)
    assert ledger.docs.document("ISO-7001").state == "Void"


def test_a_person_runs_a_command_of_their_own_access_and_not_as_somebody_else(
    ledger: Ledger,
) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    bob = ledger.client("bob")
    as_ctl = ledger.command(VoidRevision, "ctl", stream_id=draft, reason="in error")
    with pytest.raises(ForbiddenError, match="actor other than the signed-in person"):
        bob.document_command("VoidRevision", as_ctl)
    done = bob.document_command(
        "VoidRevision", ledger.command(VoidRevision, "bob", stream_id=draft, reason="in error")
    )
    assert done.stream_id == draft
    assert bob.allowed_actions(draft).actions == []


def test_engineering_command_gates_the_admin_registry_and_lets_a_person_rename_a_tag(
    ledger: Ledger,
) -> None:
    bob = ledger.client("bob")
    made = bob.engineering_command(
        "CreateTag",
        ledger.command(CreateTag, "bob", number="47-FV-1001", class_code="ControlValve"),
    )
    assert [a.command for a in bob.allowed_actions(made.stream_id).actions] == [
        "ReclassifyTag",
        "RenameTag",
        "MergeTags",
    ]
    before = ledger.events()
    with pytest.raises(ForbiddenError, match="admin role"):
        bob.engineering_command(
            "RegisterCodeList",
            ledger.command(
                RegisterCodeList,
                "bob",
                scope="company",
                code="Colours",
                label="Colours",
                edition="co.acme.standards@1.0.0",
            ),
        )
    assert ledger.events() == before
    bob.engineering_command(
        "RenameTag",
        ledger.command(
            RenameTag, "bob", stream_id=made.stream_id, new_number="47-FV-1002", reason="r"
        ),
    )
    assert bob.allowed_actions(made.stream_id).actions == []  # the old tag has left service


# --- fetching a file ---------------------------------------------------------------------------


def fetch_ready(ledger: Ledger, who: str = "bob") -> tuple[EmbeddedClient, str]:
    """A client for ``who`` that has listed the open item's file; returns it and the file's id."""
    client = ledger.client(who)
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    assert info.filename == "open.pdf" and info.slot == "original"
    return client, info.file_id


def test_a_file_is_written_in_the_destination_with_mode_0600(
    ledger: Ledger, tmp_path: Path
) -> None:
    client, file_id = fetch_ready(ledger)
    dest = tmp_path / "out"
    path = client.fetch_file(file_id, dest)
    assert path.parent == dest.resolve() and path.name == "open.pdf"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_bytes() == b"OPENFILETEXT the original letter"


def test_a_second_fetch_never_overwrites_the_first(ledger: Ledger, tmp_path: Path) -> None:
    client, file_id = fetch_ready(ledger)
    first = client.fetch_file(file_id, tmp_path)
    first.write_bytes(b"my notes")
    second = client.fetch_file(file_id, tmp_path)
    third = client.fetch_file(file_id, tmp_path)
    assert [p.name for p in (first, second, third)] == ["open.pdf", "open-1.pdf", "open-2.pdf"]
    assert first.read_bytes() == b"my notes"


@pytest.mark.parametrize(
    "hostile", ["../x", "../../etc/passwd", "/etc/passwd", "-rf", "--help.pdf", "a\x00b.pdf", ".."]
)
def test_a_hostile_filename_cannot_leave_the_destination(
    ledger: Ledger, tmp_path: Path, hostile: str
) -> None:
    client, file_id = fetch_ready(ledger)
    with open_uow(ledger.harness.db) as uow:
        uow.conn().execute(
            text("UPDATE cur_files SET filename = :n WHERE file_id = :f"),
            {"n": hostile, "f": file_id},
        )
    sandbox = tmp_path / "sandbox"
    dest = sandbox / "out"
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    assert info.filename == hostile
    path = client.fetch_file(file_id, dest)
    assert path.parent == dest.resolve()
    assert os.sep not in path.name and "\x00" not in path.name and not path.name.startswith("-")
    assert not path.name.startswith(".")
    assert [p for p in sandbox.rglob("*") if p.is_file()] == [path]  # nothing went anywhere else


def test_a_tampered_object_raises_and_leaves_no_file(ledger: Ledger, tmp_path: Path) -> None:
    client, file_id = fetch_ready(ledger)
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    stored = ledger.harness.store.path_for(object_key(info.sha256))
    good = stored.read_bytes()
    dest = tmp_path / "out"
    for bad in (good[:-1] + bytes([good[-1] ^ 1]), good[:-3]):  # a flipped byte; a short object
        stored.write_bytes(bad)
        with pytest.raises(UploadVerificationError, match="do not match"):
            client.fetch_file(file_id, dest)
        assert list(dest.iterdir()) == []
    stored.write_bytes(good)
    assert client.fetch_file(file_id, dest).read_bytes() == good


def test_a_hidden_records_file_raises_the_error_a_missing_file_does(
    ledger: Ledger, tmp_path: Path
) -> None:
    bob = ledger.client("bob")
    hidden_file = ledger.hidden.extra_ids["restricted_file"]
    assert bob.list_record_files(ledger.hidden.ids["restricted"]) == []
    assert bob.list_record_files(FAKE_ID) == []
    dest = tmp_path / "sandbox"
    with pytest.raises(UnknownFileError) as hidden:
        bob.fetch_file(hidden_file, dest)
    with pytest.raises(UnknownFileError) as missing:
        bob.fetch_file(FAKE_ID, dest)
    assert str(hidden.value).replace(hidden_file, FAKE_ID) == str(missing.value)
    # even when the scope of the file is known, the service answers the same
    bob._file_scopes[hidden_file] = SCOPE  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(UnknownFileError) as known:
        bob.fetch_file(hidden_file, dest)
    assert str(known.value) == str(hidden.value)
    assert not dest.exists()  # nothing was created for a file that is not there
    # the controller reads the restricted item and its file
    ctl = ledger.client("ctl")
    (info,) = ctl.list_record_files(ledger.hidden.ids["restricted"])
    assert ctl.fetch_file(info.file_id, dest).read_bytes().endswith(b"the original letter")


def test_without_a_file_service_the_error_says_so(ledger: Ledger, tmp_path: Path) -> None:
    client = ledger.client("bob", files=False)
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    dest = tmp_path / "sandbox"
    with derivation_store.use_files(None):  # the API app of the harness set one for the process
        with pytest.raises(BodyStoreUnavailableError, match="no file storage"):
            client.fetch_file(info.file_id, dest)
    assert not dest.exists()
