"""Email in: an .eml file becomes a received item with its files (P1-I5-T11b)."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
from typing import BinaryIO

import pytest
from tl_adapters.db import open_uow
from tl_adapters.objectstore.fs import FsObjectStore
from tl_core.files.scan import ScanResult
from tl_core.files.service import FileService
from tl_mod_correspondence.errors import CorrespondenceScopeError, InvalidItemError
from tl_mod_correspondence.handlers.mail import IngestEmail, ingest_email, read_email
from tl_mod_correspondence.testing import BASE, CorrWorld, frozen_today
from tl_mod_documents.derivation import store

MONDAY = "2026-10-19"


def message(**headers: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Pat Jones <pat@meridian.example>"
    msg["To"] = "Project Manager <pm@acme.example>"
    msg["Subject"] = "Revised programme"
    msg["Date"] = "Fri, 16 Oct 2026 10:00:00 +0000"
    msg["Message-ID"] = "<abc123@mail.meridian.example>"
    for name, value in headers.items():
        del msg[name.replace("_", "-")]
        msg[name.replace("_", "-")] = value
    msg.set_content("Please confirm the revised programme.")
    return msg


def ingest(world: CorrWorld, msg: EmailMessage, **more: str):  # type: ignore[no-untyped-def]
    data = msg.as_bytes()
    parsed = read_email(data)
    with open_uow(world.db) as uow:
        return ingest_email(uow, IngestEmail(**{**BASE, **more}), parsed, data)


def files_of(world: CorrWorld, item_id: str) -> list[tuple[str, str, str]]:
    rows = world.rows(
        "SELECT slot, filename, status FROM cur_files WHERE record_id = :r ORDER BY slot, filename",
        r=item_id,
    )
    return [(r["slot"], r["filename"], r["status"]) for r in rows]


def test_an_email_becomes_a_received_item_in_a_thread_with_the_original_kept(
    world: CorrWorld,
) -> None:
    msg = message()
    msg.add_attachment(b"%PDF-1.7 spec", maintype="application", subtype="pdf", filename="spec.pdf")
    with frozen_today(MONDAY):
        made = ingest(world, msg)
    item = world.item(made.key or "")
    assert (item.state, item.direction, item.medium, item.received_via) == (
        "Received",
        "in",
        "email",
        "email",
    )
    assert (item.subject, item.from_name, item.sent_on, item.received_on) == (
        "Revised programme",
        "Pat Jones",
        "2026-10-16",
        MONDAY,
    )
    assert item.message_id == "abc123@mail.meridian.example"
    assert item.confidentiality == "internal" and item.thread_id is not None
    assert [(a["name"], a["email"]) for a in item.to] == [("Project Manager", "pm@acme.example")]
    assert item.body == "Please confirm the revised programme."
    assert files_of(world, made.stream_id) == [
        ("attachment", "spec.pdf", "available"),
        ("message", f"{made.key}.eml", "available"),
    ]


def test_a_known_party_is_matched_from_the_sender_and_the_recipients(world: CorrWorld) -> None:
    party = world.forge_party("MER", "Meridian Energy")  # owns meridian.example
    with frozen_today(MONDAY):
        made = ingest(world, message())
    item = world.item(made.key or "")
    assert item.from_party_id == party
    assert item.to[0]["party_id"] is None  # acme.example belongs to nobody yet


def test_a_reply_joins_the_thread_of_the_message_it_answers(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = ingest(world, message())
        reply = ingest(
            world,
            message(
                Subject="Something else",
                Message_ID="<def456@mail.meridian.example>",
                In_Reply_To="<abc123@mail.meridian.example>",
            ),
        )
        later = ingest(
            world,
            message(
                Subject="Third",
                Message_ID="<ghi789@mail.meridian.example>",
                References="<abc123@mail.meridian.example> <zzz@elsewhere.example>",
            ),
        )
    a, b, c = (world.item(m.key or "") for m in (first, reply, later))
    assert a.thread_id == b.thread_id == c.thread_id
    assert b.responds_to_id == first.stream_id and c.responds_to_id == first.stream_id


def test_a_message_received_twice_is_refused(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = ingest(world, message())
        with pytest.raises(InvalidItemError, match=f"already item {first.key}"):
            ingest(world, message())


def test_a_hostile_message_is_refused_and_nothing_is_written(world: CorrWorld) -> None:
    with pytest.raises(InvalidItemError, match="refused"):
        read_email(b"From: a@b.example\nSubject: bell\x07\n\nbody\n")
    with pytest.raises(InvalidItemError, match="larger than the limit"):
        read_email(b"x" * (11 * 1024 * 1024))
    assert world.rows("SELECT id FROM cur_core_record WHERE type LIKE 'correspondence.%'") == []


def test_an_attachment_the_scan_rejects_undoes_the_whole_ingest(
    world: CorrWorld, tmp_path: Path
) -> None:
    class Strict:
        def scan(self, data: BinaryIO, *, filename: str, content_type: str) -> ScanResult:
            found = b"EICAR" in data.read()
            return ScanResult(clean=not found, reason="test signature" if found else None)

    service = FileService(
        FsObjectStore(tmp_path / "strict", secret=b"k"), secret=b"s", scanner=Strict()
    )  # type: ignore[arg-type]
    msg = message()
    msg.add_attachment(b"EICAR test", maintype="application", subtype="pdf", filename="bad.pdf")
    with store.use_files(service), frozen_today(MONDAY):
        with pytest.raises(InvalidItemError, match="rejected by the scan"):
            ingest(world, msg)
    assert world.rows("SELECT id FROM cur_core_record WHERE type LIKE 'correspondence.%'") == []
    assert world.rows("SELECT file_id FROM cur_files") == []


def test_an_html_only_message_has_a_note_for_a_body(world: CorrWorld) -> None:
    msg = EmailMessage()
    msg["From"] = "a@b.example"
    msg["Subject"] = "Newsletter"
    msg["Message-ID"] = "<n1@b.example>"
    msg.set_content("<html><a href='http://evil.example'>x</a></html>", subtype="html")
    with frozen_today(MONDAY):
        made = ingest(world, msg)
    item = world.item(made.key or "")
    assert item.body is not None and "HTML part" in item.body and "evil" not in item.body
    assert [f[0] for f in files_of(world, made.stream_id)] == ["message"]


def test_a_message_without_a_subject_is_given_a_placeholder(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = ingest(world, message(Subject=""))
    assert world.item(made.key or "").subject == "(no subject)"


def test_an_email_needs_a_project_and_a_hidden_thread_is_not_joined(world: CorrWorld) -> None:
    from tl_core import confidentiality as cf

    with pytest.raises(CorrespondenceScopeError), frozen_today(MONDAY):
        ingest(world, message(), scope="company")
    with frozen_today(MONDAY):
        first = ingest(world, message())
        with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
            world.set_class(first.stream_id, "restricted")
        again = ingest(world, message(Message_ID="<other@x.example>"))
    with cf.use_viewer(cf.Viewer(actor="user:ctl", level=1, account="user:ctl")):
        a, b = world.item(first.key or ""), world.item(again.key or "")
        assert a.thread_id != b.thread_id  # the person could not see the restricted thread
