"""The hash of a file is not a way to learn that a hidden file exists (ADR-0016; review of P1-I5).

A file of a restricted item is stored once under its hash. A reader who cannot read that item must
get the answer they would get for bytes nobody ever stored: no shortcut by hash, no size of the
stored bytes, and the same text when the bytes are not sent.
"""

from __future__ import annotations

import hashlib
import io

import pytest
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.files.service import CompleteUpload, RegisterUpload
from tl_core.services.errors import UploadIncompleteError
from tl_mod_correspondence.testing import BASE, CorrWorld, frozen_today

MONDAY = "2026-10-19"
CONTROLLER = cf.Viewer(actor="user:ctl", level=1, account="user:ctl")
SECRET = b"%PDF-1.7 the restricted contract terms"


def declared(item_id: str, data: bytes, *, size: int | None = None) -> RegisterUpload:
    return RegisterUpload(
        **BASE,
        record_id=item_id,
        slot="attachment",
        filename="terms.pdf",
        content_type="application/pdf",
        size=len(data) if size is None else size,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def two_items(world: CorrWorld) -> tuple[str, str]:
    with frozen_today(MONDAY):
        secret = world.receive("Commercial terms")
        plain = world.receive("Programme")
    with cf.use_viewer(CONTROLLER):
        world.upload(secret.stream_id, "attachment", SECRET, "terms.pdf")
        world.set_class(secret.stream_id, "restricted")
    return secret.stream_id, plain.stream_id


def test_a_reader_who_cannot_see_the_file_gets_no_shortcut_by_its_hash(world: CorrWorld) -> None:
    assert world.files is not None
    _, plain = two_items(world)
    with open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, declared(plain, SECRET))
    assert ticket.exists is False and ticket.upload_url is not None
    unknown = b"%PDF-1.7 bytes nobody stored"
    with open_uow(world.db) as uow:
        other = world.files.register_upload(uow, declared(plain, unknown))
    assert other.exists is False


def test_attaching_by_hash_without_the_bytes_says_what_it_says_for_unknown_bytes(
    world: CorrWorld,
) -> None:
    assert world.files is not None
    _, plain = two_items(world)
    messages = []
    for data in (SECRET, b"%PDF-1.7 bytes nobody stored"):
        with open_uow(world.db) as uow:
            ticket = world.files.register_upload(uow, declared(plain, data))
        with pytest.raises(UploadIncompleteError) as caught, open_uow(world.db) as uow:
            world.files.complete_upload(uow, CompleteUpload(**BASE, upload_id=ticket.upload_id))
        messages.append(str(caught.value))
    assert messages[0] == messages[1]


def test_a_wrong_size_does_not_tell_the_size_of_the_hidden_bytes(world: CorrWorld) -> None:
    assert world.files is not None
    _, plain = two_items(world)
    lie = declared(plain, SECRET, size=len(SECRET) + 7)
    with open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, lie)
    with pytest.raises(Exception) as caught, open_uow(world.db) as uow:
        world.files.complete_upload(
            uow, CompleteUpload(**BASE, upload_id=ticket.upload_id), io.BytesIO(SECRET)
        )
    assert "stored for this hash" not in str(caught.value)


def test_a_controller_who_may_read_the_item_still_gets_the_shortcut(world: CorrWorld) -> None:
    assert world.files is not None
    _, plain = two_items(world)
    with cf.use_viewer(CONTROLLER), open_uow(world.db) as uow:
        ticket = world.files.register_upload(uow, declared(plain, SECRET))
    assert ticket.exists is True
