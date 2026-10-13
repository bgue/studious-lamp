"""Replaying the ledger gives the tables the commands made (restore and rebuild, brief 24)."""

from __future__ import annotations

from typing import Any

from docworld import World
from tl_adapters.db import rebuild_projections

TABLES = (
    ("cur_documents_document", "id"),
    ("cur_documents_revision", "id"),
    ("cur_documents_rendition", "id"),
    ("cur_documents_transmittal", "id"),
    ("cur_documents_transmittal_item", "item_id"),
    ("cur_documents_review_cycle", "id"),
    ("cur_documents_reviewer", "reviewer_id"),
    ("cur_core_record", "id"),
    ("cur_links", "link_id"),
)


def snapshot(world: World) -> dict[str, list[dict[str, Any]]]:
    return {t: world.rows(f"SELECT * FROM {t} ORDER BY {order}") for t, order in TABLES}


def test_a_rebuild_reproduces_every_documents_table(world: World) -> None:
    world.issued_document()
    link = world.link(world.tag(), "ISO-1234", "A")
    world.create_revision(purpose="Second")
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue("ISO-1234", "B", "IFC")
    world.attach("ISO-1234", "B", slot="signed", data=b"%PDF signed", name="s.pdf")
    world.register("ISO-2000")
    assert world.link_status(link) == "stale"
    before = snapshot(world)
    assert before["cur_documents_revision"]  # the history is not empty
    rebuild_projections(world.db)
    assert snapshot(world) == before
