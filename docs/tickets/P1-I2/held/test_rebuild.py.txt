"""Replaying the ledger gives the tables the commands made (restore and rebuild, brief 24)."""

from __future__ import annotations

from typing import Any

from docworld import BASE, World
from tl_adapters.db import open_uow, rebuild_projections
from tl_mod_documents.handlers.reviews import (
    CloseReviewCycle,
    OpenReviewCycle,
    RecordReviewOutcome,
    ReviewerRequest,
    handle_close_review_cycle,
    handle_open_review_cycle,
    handle_record_review_outcome,
)
from tl_mod_documents.handlers.transmittals import (
    CreateTransmittal,
    IssueTransmittal,
    Recipient,
    handle_create_transmittal,
    handle_issue_transmittal,
)

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


def run(world: World, handler: Any, command: Any) -> Any:
    with open_uow(world.db) as uow:
        return handler(uow, command)


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
    world.create_revision("ISO-2000")
    world.attach("ISO-2000", "A", data=b"%PDF-1.7 other", name="o.pdf")
    review = run(
        world,
        handle_open_review_cycle,
        OpenReviewCycle(
            **BASE,
            revision_id=world.revision("ISO-2000", "A").id,
            reviewers=[ReviewerRequest(reviewer="user:ana")],
        ),
    )
    run(
        world,
        handle_record_review_outcome,
        RecordReviewOutcome(
            **BASE, review_cycle_id=review.stream_id, reviewer="user:ana", outcome="approved"
        ),
    )
    run(
        world, handle_close_review_cycle, CloseReviewCycle(**BASE, review_cycle_id=review.stream_id)
    )
    sent = run(
        world,
        handle_create_transmittal,
        CreateTransmittal(
            **BASE,
            number=None,
            subject="To site",
            purpose="for_construction",
            recipients=[Recipient(name="Site")],
            revision_ids=[world.revision("ISO-1234", "B").id],
        ),
    )
    run(world, handle_issue_transmittal, IssueTransmittal(**BASE, stream_id=sent.stream_id))
    assert world.link_status(link) == "stale"
    before = snapshot(world)
    assert before["cur_documents_revision"]  # the history is not empty
    assert before["cur_documents_transmittal_item"] and before["cur_documents_reviewer"]
    rebuild_projections(world.db)
    assert snapshot(world) == before
