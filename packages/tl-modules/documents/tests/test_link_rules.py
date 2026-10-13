"""Links to and from documents: the reserved relation, rule links, who may re-pin (P1-I2)."""

from __future__ import annotations

import pytest
from docworld import BASE, World
from tl_adapters.db import open_uow
from tl_core.services.errors import UnsupportedRecordTypeError
from tl_core.services.links import (
    AddLink,
    FlagLink,
    RetractLink,
    handle_add_link,
    handle_flag_link,
    handle_retract_link,
)
from tl_mod_documents.handlers.documents import SupersedeDocument, handle_supersede_document
from tl_mod_documents.resolver import RepinDocumentLink, handle_repin_document_link


def test_nobody_claims_that_a_record_supersedes_a_document_with_a_generic_link(
    world: World,
) -> None:
    world.issued_document("ISO-1234")
    tag = world.tag()
    doc = world.document("ISO-1234")
    with (
        open_uow(world.db) as uow,
        pytest.raises(UnsupportedRecordTypeError, match="supersedes link to a documents.Document"),
    ):
        handle_add_link(uow, AddLink(**BASE, from_id=tag, to_id=doc.id, relation="supersedes"))


def test_the_supersedes_link_of_a_supersession_is_kept_by_the_module(world: World) -> None:
    world.issued_document("ISO-1234")
    world.issued_document("ISO-2000")
    old, new = world.document("ISO-1234"), world.document("ISO-2000")
    with open_uow(world.db) as uow:
        handle_supersede_document(
            uow,
            SupersedeDocument(**BASE, stream_id=old.id, superseded_by_id=new.id, reason="re-drawn"),
        )
    (row,) = world.rows(
        "SELECT link_id, source FROM cur_links WHERE from_id = :f AND to_id = :t",
        f=new.id,
        t=old.id,
    )
    assert row["source"] == "rule"
    with (
        open_uow(world.db) as uow,
        pytest.raises(UnsupportedRecordTypeError, match="written by a rule of the module"),
    ):
        handle_retract_link(uow, RetractLink(**BASE, link_id=row["link_id"], reason="no"))
    with (
        open_uow(world.db) as uow,
        pytest.raises(UnsupportedRecordTypeError, match="written by a rule of the module"),
    ):
        handle_flag_link(uow, FlagLink(**BASE, link_id=row["link_id"], status="stale", reason="no"))


def test_a_link_that_starts_at_a_record_which_may_not_be_re_pinned_is_not_re_pinned(
    world: World,
) -> None:
    world.issued_document("ISO-1234")
    rendition = world.attach("ISO-1234", "A", slot="markup", data=b"%PDF m", name="m.pdf")
    link = world.link_from(rendition.stream_id, world.document("ISO-1234").id)
    with (
        open_uow(world.db) as uow,
        pytest.raises(
            UnsupportedRecordTypeError, match="RepinLink cannot change a documents.Rendition"
        ),
    ):
        handle_repin_document_link(uow, RepinDocumentLink(**BASE, link_id=link, pin="A"))
