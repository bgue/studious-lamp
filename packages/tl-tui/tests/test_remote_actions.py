"""The remote client's record actions, module command runners and file fetch (P1-UX2-S1).

The API app of the harness serves the same ledger the embedded client reads. For the same record
and the same person the two clients agree on what is offered; the module command runners refuse a
name the module's table does not hold before anything is sent, and the server refuses an access the
person lacks; ``fetch_file`` writes a verified file in a safe place through the existing file route.
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
from tl_api.client import ApiClient
from tl_core.auth import accounts, sessions
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.password import prepare_password
from tl_core.files.types import object_key
from tl_core.services.errors import RecordNotFoundError, UnknownFileError, UploadVerificationError
from tl_mod_correspondence.confseed import Hidden, seed_hidden_world
from tl_mod_documents.handlers.documents import VoidDocument
from tl_mod_documents.handlers.revisions import IssueRevision, VoidRevision
from tl_mod_documents.testing import BASE, DocumentsWorld
from tl_mod_engineering.handlers.standards import RegisterCodeList
from tl_mod_engineering.handlers.tags import CreateTag, RenameTag
from tl_mod_engineering.testing import seed_registry
from tl_tui.embedded import EmbeddedClient
from tl_tui.remote import RemoteClient

FAKE_ID = "01J000000000000000000000"
PASSWORD = "correct horse battery"
ROLES = {"bob": ["user"], "ctl": ["document_controller"], "boss": ["admin"]}


class Ledger:
    def __init__(self, harness: Harness, hidden: Hidden, docs: DocumentsWorld) -> None:
        self.harness = harness
        self.hidden = hidden
        self.docs = docs
        self.tokens = {
            name: sessions.sign_in(harness.backend, username=name, password=PASSWORD)[1]
            for name in ROLES
        }

    def remote(self, name: str) -> RemoteClient:
        api = ApiClient("http://testserver", self.tokens[name], http=self.harness.client_for(None))
        return RemoteClient(api)

    def embedded(self, name: str) -> EmbeddedClient:
        return EmbeddedClient(
            SqliteUowFactory(self.harness.db),
            actor=f"user:{name}",
            files=self.harness.service,
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
                password=prepare_password(PASSWORD),
                by="svc:test",
            )
    seed_registry(harness.db)
    hidden = seed_hidden_world(harness.db, harness.service, tmp_path)
    docs = DocumentsWorld(harness.db, tmp_path / "docs")
    docs.create_revision("ISO-9002")  # revision B of the open document: a draft
    return Ledger(harness, hidden, docs)


# --- what a record offers ---------------------------------------------------------------------


@pytest.mark.parametrize("who", sorted(ROLES))
def test_embedded_and_remote_agree_on_what_a_record_offers(ledger: Ledger, who: str) -> None:
    ids = ledger.hidden.ids
    made = ledger.embedded("bob").engineering_command(
        "CreateTag",
        ledger.command(CreateTag, "bob", number="47-FV-1001", class_code="ControlValve"),
    )
    records = {
        "draft revision": ledger.docs.revision("ISO-9002", "B").id,
        "issued revision": ledger.docs.revision("ISO-9002", "A").id,
        "document": ids["open_document"],
        "answered rfi": ids["open_rfi"],
        "waiting rfi": ids["secret_rfi"],
        "early warning": ids["commercial"],
        "letter": ids["open"],
        "tag": made.stream_id,
        "transmittal": ledger.hidden.extra_ids["transmittal"],
    }
    embedded, remote = ledger.embedded(who), ledger.remote(who)
    for label, record_id in records.items():
        try:
            want = embedded.allowed_actions(record_id)
        except RecordNotFoundError as gone:
            with pytest.raises(RecordNotFoundError) as same:
                remote.allowed_actions(record_id)
            assert str(same.value) == str(gone), (who, label)
            continue
        assert remote.allowed_actions(record_id) == want, (who, label)


def test_a_record_the_person_may_not_read_is_not_found_remotely_too(ledger: Ledger) -> None:
    bob = ledger.remote("bob")
    with pytest.raises(RecordNotFoundError) as unknown:
        bob.allowed_actions(FAKE_ID)
    for kind in ("restricted", "privileged", "bogus", "document", "commercial", "secret_rfi"):
        record_id = ledger.hidden.ids[kind]
        with pytest.raises(RecordNotFoundError) as hidden:
            bob.allowed_actions(record_id)
        assert str(hidden.value).replace(record_id, FAKE_ID) == str(unknown.value), kind


# --- the module command runners ----------------------------------------------------------------


def test_a_name_that_is_not_in_the_modules_table_is_refused_before_anything_is_sent(
    ledger: Ledger,
) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    bob = ledger.remote("bob")
    void = ledger.command(VoidRevision, "bob", stream_id=draft, reason="in error")
    before = ledger.events()
    with pytest.raises(ForbiddenError, match="CloseCorrespondence is not a documents command"):
        bob.document_command("CloseCorrespondence", void)
    with pytest.raises(ForbiddenError, match="VoidDocument is not a documents command"):
        bob.document_command("VoidDocument", void)
    with pytest.raises(ForbiddenError, match="VoidRevision is not a engineering command"):
        bob.engineering_command("VoidRevision", void)
    assert ledger.events() == before


def test_the_server_refuses_an_access_the_person_lacks_and_runs_it_for_who_has_it(
    ledger: Ledger,
) -> None:
    draft = ledger.docs.revision("ISO-9002", "B").id
    other = ledger.docs.register("ISO-7001")
    before = ledger.events()
    bob = ledger.remote("bob")
    with pytest.raises(ForbiddenError):
        bob.document_command(
            "VoidDocument",
            ledger.command(VoidDocument, "bob", stream_id=other.stream_id, reason="x"),
        )
    with pytest.raises(ForbiddenError):
        bob.document_command(
            "IssueRevision",
            ledger.command(IssueRevision, "bob", stream_id=draft, issue_status="IFR"),
        )
    assert ledger.events() == before
    ctl = ledger.remote("ctl")
    done = ctl.document_command(
        "VoidDocument", ledger.command(VoidDocument, "ctl", stream_id=other.stream_id, reason="x")
    )
    assert ledger.docs.document("ISO-7001").state == "Void"
    assert all(ctl.own_writes.classify(event) == "own" for event in done.events)
    with pytest.raises(ForbiddenError):  # the admin registry is the admin's
        ledger.remote("ctl").engineering_command(
            "RegisterCodeList",
            ledger.command(
                RegisterCodeList,
                "ctl",
                scope="company",
                code="Colours",
                label="Colours",
                edition="co.acme.standards@1.0.0",
            ),
        )


def test_a_person_renames_a_tag_remotely_and_the_old_one_offers_nothing(ledger: Ledger) -> None:
    bob = ledger.remote("bob")
    made = bob.engineering_command(
        "CreateTag",
        ledger.command(CreateTag, "bob", number="47-FV-1001", class_code="ControlValve"),
    )
    assert [a.command for a in bob.allowed_actions(made.stream_id).actions] == [
        "ReclassifyTag",
        "RenameTag",
        "MergeTags",
    ]
    bob.engineering_command(
        "RenameTag",
        ledger.command(
            RenameTag, "bob", stream_id=made.stream_id, new_number="47-FV-1002", reason="r"
        ),
    )
    assert bob.allowed_actions(made.stream_id).actions == []


# --- fetching a file ---------------------------------------------------------------------------


def fetch_ready(ledger: Ledger, who: str = "bob") -> tuple[RemoteClient, str]:
    client = ledger.remote(who)
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    assert info.filename == "open.pdf" and info.slot == "original"
    return client, info.file_id


def test_a_file_is_written_in_the_destination_with_mode_0600_and_never_overwritten(
    ledger: Ledger, tmp_path: Path
) -> None:
    client, file_id = fetch_ready(ledger)
    dest = tmp_path / "sandbox" / "out"
    first = client.fetch_file(file_id, dest)
    assert first.parent == dest.resolve() and first.name == "open.pdf"
    assert stat.S_IMODE(first.stat().st_mode) == 0o600
    assert first.read_bytes() == b"OPENFILETEXT the original letter"
    first.write_bytes(b"my notes")
    second = client.fetch_file(file_id, dest)
    assert second.name == "open-1.pdf" and first.read_bytes() == b"my notes"


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
    path = client.fetch_file(file_id, dest)
    assert path.parent == dest.resolve()
    assert os.sep not in path.name and "\x00" not in path.name and not path.name.startswith("-")
    assert not path.name.startswith(".")
    assert [p for p in sandbox.rglob("*") if p.is_file()] == [path]


def test_a_tampered_object_raises_and_leaves_no_file(ledger: Ledger, tmp_path: Path) -> None:
    client, file_id = fetch_ready(ledger)
    (info,) = client.list_record_files(ledger.hidden.ids["open"])
    stored = ledger.harness.store.path_for(object_key(info.sha256))
    good = stored.read_bytes()
    dest = tmp_path / "sandbox"
    stored.write_bytes(good[:-1] + bytes([good[-1] ^ 1]))  # one byte flipped, the size the same
    with pytest.raises(UploadVerificationError):
        client.fetch_file(file_id, dest)
    assert list(dest.iterdir()) == []
    stored.write_bytes(good)
    assert client.fetch_file(file_id, dest).read_bytes() == good


def test_a_hidden_records_file_raises_the_error_a_missing_file_does(
    ledger: Ledger, tmp_path: Path
) -> None:
    bob = ledger.remote("bob")
    hidden_file = ledger.hidden.extra_ids["restricted_file"]
    dest = tmp_path / "sandbox"
    assert bob.list_record_files(ledger.hidden.ids["restricted"]) == []
    assert bob.list_record_files(FAKE_ID) == []
    with pytest.raises(UnknownFileError) as hidden:
        bob.fetch_file(hidden_file, dest)
    with pytest.raises(UnknownFileError) as missing:
        bob.fetch_file(FAKE_ID, dest)
    assert str(hidden.value).replace(hidden_file, FAKE_ID) == str(missing.value)
    api = bob._api  # pyright: ignore[reportPrivateUsage]
    api.__dict__.setdefault("_file_scopes", {})[hidden_file] = "project:P123"
    with pytest.raises(UnknownFileError) as known:  # the server answers a file it will not show
        bob.fetch_file(hidden_file, dest)
    assert str(known.value) == str(hidden.value)
    assert not dest.exists()
    ctl = ledger.remote("ctl")
    (info,) = ctl.list_record_files(ledger.hidden.ids["restricted"])
    assert ctl.fetch_file(info.file_id, dest).read_bytes().endswith(b"the original letter")


def test_the_embedded_and_the_remote_client_list_the_same_files(ledger: Ledger) -> None:
    for who in sorted(ROLES):
        for kind in ("open", "restricted"):
            record_id = ledger.hidden.ids[kind]
            assert ledger.remote(who).list_record_files(record_id) == ledger.embedded(
                who
            ).list_record_files(record_id), (who, kind)
