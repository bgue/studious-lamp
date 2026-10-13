"""The five projectors: each event type into its table, replay twice to the same rows (T03)."""

from __future__ import annotations

from typing import Any

from docworld import Events, apply, as_json, install, table_rows
from sqlalchemy import Engine, text
from tl_core.projection.defaults import default_registry

DOC = "D1"
REV_A = "R-A"
REV_B = "R-B"
REND = "N1"
TR = "T1"
RC = "C1"


def journal(events: Events) -> list[Any]:
    """A small history: a document, two revisions, a rendition, a transmittal, a review."""
    out = [
        events.created(DOC, "documents.Document", "ISO-1234", title="Iso"),
        events.make(
            "Document.Defined",
            {
                "number": "ISO-1234",
                "doc_type": "ISO",
                "discipline": "PIP",
                "revision_scheme": "alpha",
            },
            stream_id=DOC,
            stream_type="documents.Document",
        ),
        events.created(REV_A, "documents.Revision", "ISO-1234@A"),
        events.make(
            "Revision.Defined",
            {
                "document_id": DOC,
                "document_number": "ISO-1234",
                "code": "A",
                "ordinal": 1,
                "purpose": "First issue",
                "intended_status": "IFR",
                "revision_date": "2026-10-13",
            },
            stream_id=REV_A,
            stream_type="documents.Revision",
        ),
        events.created(REND, "documents.Rendition", "ISO-1234@A/pdf-1"),
        events.make(
            "Rendition.Defined",
            {
                "revision_id": REV_A,
                "document_id": DOC,
                "kind": "pdf",
                "file_id": "F1",
                "filename": "a.pdf",
                "content_type": "application/pdf",
                "size": 10,
                "sha256": "ab" * 32,
                "page_count": 3,
            },
            stream_id=REND,
            stream_type="documents.Rendition",
        ),
        events.make(
            "Revision.Issued",
            {"issue_status": "IFR", "status_class": "review", "issued_on": "2026-10-14"},
            stream_id=REV_A,
            stream_type="documents.Revision",
        ),
        events.make(
            "Document.CurrentRevisionChanged",
            {
                "current_revision_id": REV_A,
                "current_revision_code": "A",
                "current_revision_status": "IFR",
                "current_revision_class": "review",
                "current_revision_issued_on": "2026-10-14",
                "reason": "issued",
            },
            stream_id=DOC,
            stream_type="documents.Document",
        ),
        events.created(TR, "documents.Transmittal", "TRN-0001", title="To site"),
        events.make(
            "Transmittal.Defined",
            {
                "number": "TRN-0001",
                "direction": "outgoing",
                "purpose": "for_review",
                "due_date": "2026-10-20",
                "recipients": [{"name": "Site", "organisation": "Acme", "email": None}],
                "items": [
                    {
                        "revision_id": REV_A,
                        "document_id": DOC,
                        "document_number": "ISO-1234",
                        "revision_code": "A",
                        "issue_status": "IFR",
                    }
                ],
            },
            stream_id=TR,
            stream_type="documents.Transmittal",
        ),
        events.make(
            "Transmittal.Issued",
            {"issued_on": "2026-10-15"},
            stream_id=TR,
            stream_type="documents.Transmittal",
        ),
        events.make(
            "Transmittal.ResponseRecorded",
            {"response_code": "approved", "response_note": "ok", "responded_on": "2026-10-16"},
            stream_id=TR,
            stream_type="documents.Transmittal",
        ),
        events.created(RC, "documents.ReviewCycle", "ISO-1234@A/RC1"),
        events.make(
            "ReviewCycle.Defined",
            {
                "revision_id": REV_A,
                "document_id": DOC,
                "round": 1,
                "due_date": "2026-10-20",
                "opened_on": "2026-10-13",
                "reviewers": [
                    {"reviewer": "user:ana", "due_date": None},
                    {"reviewer": "user:bo", "due_date": "2026-10-18"},
                ],
            },
            stream_id=RC,
            stream_type="documents.ReviewCycle",
        ),
        events.make(
            "ReviewCycle.OutcomeRecorded",
            {
                "reviewer": "user:ana",
                "outcome": "approved_with_comments",
                "comment": "see markup",
                "responded_on": "2026-10-15",
            },
            stream_id=RC,
            stream_type="documents.ReviewCycle",
        ),
        events.make(
            "ReviewCycle.Closed",
            {"outcome": "approved_with_comments", "closed_on": "2026-10-16"},
            stream_id=RC,
            stream_type="documents.ReviewCycle",
        ),
        events.created(REV_B, "documents.Revision", "ISO-1234@B"),
        events.make(
            "Revision.Defined",
            {
                "document_id": DOC,
                "document_number": "ISO-1234",
                "code": "B",
                "ordinal": 2,
                "previous_revision_id": REV_A,
            },
            stream_id=REV_B,
            stream_type="documents.Revision",
        ),
        events.make(
            "Revision.Superseded",
            {"superseded_by": REV_B, "status_class": "review"},
            stream_id=REV_A,
            stream_type="documents.Revision",
        ),
        events.created("N2", "documents.Rendition", "ISO-1234@A/pdf-2"),
        events.make(
            "Rendition.Defined",
            {
                "revision_id": REV_A,
                "document_id": DOC,
                "kind": "pdf",
                "file_id": "F2",
                "filename": "a2.pdf",
                "content_type": "application/pdf",
                "size": 12,
                "sha256": "cd" * 32,
            },
            stream_id="N2",
            stream_type="documents.Rendition",
        ),
        events.make(
            "Rendition.Superseded",
            {"superseded_by": "N2"},
            stream_id=REND,
            stream_type="documents.Rendition",
        ),
        events.make(
            "Document.Updated",
            {"changes": {"discipline": ["PIP", "MEC"], "originator": [None, "Acme"]}},
            stream_id=DOC,
            stream_type="documents.Document",
        ),
        events.make(
            "Document.Superseded",
            {"superseded_by": "D2", "reason": "merged"},
            stream_id=DOC,
            stream_type="documents.Document",
        ),
    ]
    return out


TABLES = [
    "cur_documents_document",
    "cur_documents_revision",
    "cur_documents_rendition",
    "cur_documents_transmittal",
    "cur_documents_transmittal_item",
    "cur_documents_review_cycle",
    "cur_documents_reviewer",
]
ORDER = {
    "cur_documents_transmittal_item": "item_id",
    "cur_documents_reviewer": "reviewer_id",
}


def snapshot(engine: Engine) -> dict[str, list[dict[str, Any]]]:
    return {t: table_rows(engine, t, ORDER.get(t, "id")) for t in TABLES}


def test_the_whole_journal_projects_and_a_second_database_gets_the_same_rows(
    engine: Engine, new_engine: Any, dialect: str
) -> None:
    events = journal(Events())
    apply(engine, *events)
    first = snapshot(engine)
    other = new_engine()
    install(other, dialect)
    apply(other, *events)
    assert snapshot(other) == first
    other.dispose()


def test_a_document_row_follows_its_events(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    (doc,) = table_rows(engine, "cur_documents_document")
    assert doc["number"] == "ISO-1234"
    assert doc["discipline"] == "MEC" and doc["originator"] == "Acme"  # Document.Updated
    assert doc["current_revision_code"] == "A" and doc["current_revision_status"] == "IFR"
    assert doc["current_revision_class"] == "review"
    assert doc["superseded_by"] == "D2"
    assert doc["last_seq"] > 0


def test_a_revision_is_current_only_between_issue_and_supersession(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    a, b = table_rows(engine, "cur_documents_revision", "ordinal")
    assert a["code"] == "A" and a["issue_status"] == "IFR" and a["issued_on"] == "2026-10-14"
    assert not a["is_current"] and a["superseded_by"] == REV_B
    assert b["code"] == "B" and b["previous_revision_id"] == REV_A
    assert b["issue_status"] is None and not b["is_current"]


def test_a_newer_rendition_of_a_kind_supersedes_the_older(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    rows = {r["id"]: r for r in table_rows(engine, "cur_documents_rendition")}
    assert not rows[REND]["is_current"] and rows[REND]["superseded_by"] == "N2"
    assert rows["N2"]["is_current"] and rows["N2"]["page_count"] is None
    assert rows[REND]["page_count"] == 3


def test_a_transmittal_lists_its_items_and_keeps_its_answer(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    (tr,) = table_rows(engine, "cur_documents_transmittal")
    assert tr["item_count"] == 1 and tr["issued_on"] == "2026-10-15"
    assert tr["response_code"] == "approved" and tr["responded_on"] == "2026-10-16"
    assert as_json(tr["recipients_json"]) == [
        {"name": "Site", "organisation": "Acme", "email": None}
    ]
    (item,) = table_rows(engine, "cur_documents_transmittal_item", "item_id")
    assert item["item_id"] == f"{TR}:001" and item["revision_code"] == "A"


def test_a_review_cycle_collects_outcomes_and_closes(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    (cycle,) = table_rows(engine, "cur_documents_review_cycle")
    assert cycle["state"] == "closed" and cycle["outcome"] == "approved_with_comments"
    assert cycle["closed_on"] == "2026-10-16" and cycle["round"] == 1
    ana, bo = table_rows(engine, "cur_documents_reviewer", "reviewer_id")
    assert ana["reviewer"] == "user:ana" and ana["outcome"] == "approved_with_comments"
    assert ana["due_date"] == "2026-10-20"  # the cycle's date when the reviewer has none
    assert bo["due_date"] == "2026-10-18" and bo["outcome"] is None


def test_every_event_moves_the_envelope_row(engine: Engine) -> None:
    events = Events()
    apply(engine, *journal(events))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT version, last_seq FROM cur_core_record WHERE id = :i"), {"i": DOC}
        ).one()
    assert row.version == events.versions[DOC]
    assert row.last_seq > 0


def test_the_flat_views_join_the_envelope_to_the_typed_columns(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    with engine.connect() as conn:
        doc = conn.execute(
            text(
                "SELECT key, title, record_type, doc_type, current_revision_code "
                "FROM v_documents_document"
            )
        ).one()
        rev = conn.execute(
            text("SELECT key, title, code FROM v_documents_revision ORDER BY ordinal")
        ).all()
    assert tuple(doc) == ("ISO-1234", "Iso", "documents.Document", "ISO", "A")
    assert [r.key for r in rev] == ["ISO-1234@A", "ISO-1234@B"]


def test_reset_empties_every_table(engine: Engine) -> None:
    apply(engine, *journal(Events()))
    with engine.begin() as conn:
        for projector in default_registry().all():
            if projector.name.startswith("documents_"):
                projector.reset(conn)
    assert all(not rows for rows in snapshot(engine).values())


def test_an_event_without_its_record_is_an_error_not_a_silent_gap(engine: Engine) -> None:
    import pytest

    events = Events()
    orphan = events.make(
        "Revision.Issued",
        {"issue_status": "IFR", "status_class": "review", "issued_on": "2026-10-14"},
        stream_id="nope",
        stream_type="documents.Revision",
    )
    with pytest.raises(LookupError):
        apply(engine, orphan)
