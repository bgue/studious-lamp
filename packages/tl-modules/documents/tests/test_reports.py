"""The base reports (T11a): register, history, overdue reviews, transmittal log, stale pins.

Documents, revisions and links are made with the commands of the base; transmittals and review
cycles are written with raw events (``forge``), so these tests do not depend on the commands that
make them.
"""

from __future__ import annotations

from datetime import date

import pytest
from docworld import World, forge
from tl_adapters.db import open_uow
from tl_mod_documents import reports
from tl_mod_documents.errors import DocumentNotFoundError

SCOPE = "project:P123"
TODAY = date(2026, 10, 20)


def transmittal_events(
    number: str, revision: str, doc: str, **more: object
) -> list[tuple[str, dict]]:
    base = {
        "number": number,
        "direction": "outgoing",
        "purpose": "for_construction",
        "due_date": None,
        "recipients": [{"name": "Site"}],
        "items": [
            {
                "revision_id": revision,
                "document_id": doc,
                "document_number": "ISO-1234",
                "revision_code": "A",
                "issue_status": "IFR",
            }
        ],
    }
    return [("Transmittal.Defined", {**base, **more})]


def review_events(
    revision: str, doc: str, reviewers: list[dict], due: str | None
) -> list[tuple[str, dict]]:
    return [
        (
            "ReviewCycle.Defined",
            {
                "revision_id": revision,
                "document_id": doc,
                "round": 1,
                "due_date": due,
                "opened_on": "2026-10-01",
                "reviewers": reviewers,
            },
        )
    ]


@pytest.fixture
def busy(world: World) -> World:
    """ISO-1234 A issued (IFR) and B issued (IFC); SPC-0001 registered; PID-0001 void."""
    world.issued_document("ISO-1234", "IFR")
    world.create_revision("ISO-1234", purpose="Construction issue", change_note="Weld map added")
    world.attach("ISO-1234", "B", data=b"%PDF-1.7 b", name="b.pdf")
    world.issue(
        "ISO-1234", "B", "IFC", issued_on="2026-10-12", date_reason="issued the day before entry"
    )
    world.register("SPC-0001", doc_type="SPC", discipline="MEC", title="Piping specification")
    world.register("PID-0001", doc_type="PID", title="P&ID, unit 47")
    from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document

    doc = world.document("PID-0001")
    with open_uow(world.db) as uow:
        handle_void_document(
            uow,
            VoidDocument(
                actor="user:u", source="test", scope=SCOPE, stream_id=doc.id, reason="in error"
            ),
        )
    return world


def conn_of(world: World):  # noqa: ANN201 - a context manager of a connection
    return open_uow(world.db, readonly=True)


def test_the_register_lists_documents_by_number_without_the_void_ones(busy: World) -> None:
    with conn_of(busy) as uow:
        lines = reports.document_register(uow.conn(), SCOPE)
    assert [line.number for line in lines] == ["ISO-1234", "SPC-0001"]
    iso, spc = lines
    assert (iso.state, iso.current_code, iso.current_status, iso.current_class) == (
        "Issued",
        "B",
        "IFC",
        "construction",
    )
    assert iso.revisions == 2 and iso.open_code is None and iso.doc_type == "ISO"
    assert iso.discipline == "PIP" and iso.current_issued_on == "2026-10-12"
    assert (spc.state, spc.current_code, spc.revisions) == ("Registered", None, 0)


def test_the_register_filters_and_shows_the_open_revision_and_stale_links(busy: World) -> None:
    busy.create_revision("ISO-1234")  # C is a draft
    tag = busy.tag()
    link = busy.link(tag, "ISO-1234", "A")
    # A is behind B, but the link is only flagged when a revision is issued afterwards
    assert busy.link_status(link) == "active"
    busy.attach("ISO-1234", "C", data=b"%PDF-1.7 c", name="c.pdf")
    busy.issue("ISO-1234", "C", "IFC")
    busy.create_revision("ISO-1234")
    with conn_of(busy) as uow:
        by_type = reports.document_register(uow.conn(), SCOPE, doc_type="ISO")
        by_discipline = reports.document_register(uow.conn(), SCOPE, discipline="MEC")
        by_state = reports.document_register(uow.conn(), SCOPE, state="Registered")
        everything = reports.document_register(uow.conn(), SCOPE)
        none = reports.document_register(uow.conn(), "project:P999")
    assert [x.number for x in by_type] == ["ISO-1234"]
    assert [x.number for x in by_discipline] == ["SPC-0001"]
    assert [x.number for x in by_state] == ["SPC-0001"]
    iso = everything[0]
    assert iso.open_code == "D" and iso.stale_links == 1 and iso.revisions == 4
    assert none == []


def test_the_history_shows_every_revision_with_what_belongs_to_it(busy: World) -> None:
    a, b = busy.revision("ISO-1234", "A"), busy.revision("ISO-1234", "B")
    doc = busy.document("ISO-1234")
    forge(
        busy,
        "TR1",
        "documents.Transmittal",
        "TRN-0001",
        transmittal_events("TRN-0001", a.id, doc.id),
    )
    forge(
        busy,
        "RC1",
        "documents.ReviewCycle",
        "ISO-1234@A/RC1",
        review_events(a.id, doc.id, [{"reviewer": "user:ana", "due_date": None}], "2026-10-05")
        + [
            (
                "ReviewCycle.OutcomeRecorded",
                {
                    "reviewer": "user:ana",
                    "outcome": "approved",
                    "comment": None,
                    "responded_on": "2026-10-04",
                },
            ),
            ("ReviewCycle.Closed", {"outcome": "approved", "closed_on": "2026-10-04"}),
        ],
    )
    with conn_of(busy) as uow:
        history = reports.revision_history(uow.conn(), SCOPE, "ISO-1234")
    first, second = history
    assert (first.code, first.ordinal, first.issue_status, first.status_class) == (
        "A",
        1,
        "IFR",
        "review",
    )
    assert (
        first.is_current
        and first.transmittals == ["TRN-0001"]
        and first.review_outcome == "approved"
    )
    assert first.renditions == 1 and first.superseded_by is None
    assert (second.code, second.is_current, second.purpose) == ("B", True, "Construction issue")
    assert (
        second.change_note == "Weld map added"
        and second.transmittals == []
        and second.review_outcome is None
    )
    assert b.id and second.state == "Issued"


def test_the_history_of_an_unknown_document_is_an_error(busy: World) -> None:
    with conn_of(busy) as uow, pytest.raises(DocumentNotFoundError):
        reports.revision_history(uow.conn(), SCOPE, "NOPE-1")
    with conn_of(busy) as uow, pytest.raises(DocumentNotFoundError):
        reports.revision_history(uow.conn(), "project:P999", "ISO-1234")


def test_a_superseded_and_a_void_revision_are_told_apart(busy: World) -> None:
    busy.create_revision("ISO-1234")
    from tl_mod_documents.handlers.revisions import VoidRevision, handle_void_revision

    c = busy.revision("ISO-1234", "C")
    with open_uow(busy.db) as uow:
        handle_void_revision(
            uow,
            VoidRevision(actor="user:u", source="test", scope=SCOPE, stream_id=c.id, reason="x"),
        )
    busy.create_revision("ISO-1234")
    busy.attach("ISO-1234", "D", data=b"%PDF-1.7 d", name="d.pdf")
    busy.issue("ISO-1234", "D", "IFR")  # D supersedes A in the review class
    with conn_of(busy) as uow:
        history = {h.code: h for h in reports.revision_history(uow.conn(), SCOPE, "ISO-1234")}
    assert history["A"].state == "Superseded" and history["A"].superseded_by == "D"
    assert history["C"].state == "Void"
    assert history["D"].is_current and not history["A"].is_current


def test_overdue_reviews_are_open_unanswered_and_past_their_date(busy: World) -> None:
    a = busy.revision("ISO-1234", "A")
    doc = busy.document("ISO-1234")
    forge(
        busy,
        "RC1",
        "documents.ReviewCycle",
        "ISO-1234@A/RC1",
        review_events(
            a.id,
            doc.id,
            [
                {"reviewer": "user:ana", "due_date": None},  # the cycle's date: 2026-10-10
                {"reviewer": "user:bo", "due_date": "2026-10-18"},
                {"reviewer": "user:cy", "due_date": "2026-10-25"},  # not yet due
                {"reviewer": "user:di", "due_date": None},
            ],
            "2026-10-10",
        )
        + [
            (
                "ReviewCycle.OutcomeRecorded",
                {
                    "reviewer": "user:di",
                    "outcome": "approved",
                    "comment": None,
                    "responded_on": "2026-10-09",
                },
            ),
        ],
    )
    forge(  # a closed cycle is never overdue
        busy,
        "RC2",
        "documents.ReviewCycle",
        "ISO-1234@A/RC2",
        review_events(
            a.id, doc.id, [{"reviewer": "user:ed", "due_date": "2026-01-01"}], "2026-01-01"
        )
        + [
            (
                "ReviewCycle.Closed",
                {"outcome": "approved", "closed_on": "2026-01-02", "reason": "withdrawn"},
            )
        ],
    )
    with conn_of(busy) as uow:
        late = reports.overdue_reviews(uow.conn(), SCOPE, on=TODAY)
        early = reports.overdue_reviews(uow.conn(), SCOPE, on=date(2026, 10, 10))
        other = reports.overdue_reviews(uow.conn(), "project:P999", on=TODAY)
    assert [(x.reviewer, x.due_date, x.days_overdue) for x in late] == [
        ("user:ana", "2026-10-10", 10),
        ("user:bo", "2026-10-18", 2),
    ]
    assert late[0].document_number == "ISO-1234" and late[0].revision_code == "A"
    assert late[0].cycle_key == "ISO-1234@A/RC1"
    assert early == [] and other == []  # due today is not yet overdue


def test_the_reviewers_of_a_void_document_are_not_overdue(busy: World) -> None:
    from tl_mod_documents.handlers.documents import VoidDocument, handle_void_document

    a = busy.revision("ISO-1234", "A")
    doc = busy.document("ISO-1234")
    forge(
        busy,
        "RC1",
        "documents.ReviewCycle",
        "ISO-1234@A/RC1",
        review_events(a.id, doc.id, [{"reviewer": "user:ana", "due_date": "2026-10-01"}], None),
    )
    with conn_of(busy) as uow:
        assert len(reports.overdue_reviews(uow.conn(), SCOPE, on=TODAY)) == 1
    with open_uow(busy.db) as uow:
        handle_void_document(
            uow,
            VoidDocument(
                actor="user:u", source="test", scope=SCOPE, stream_id=doc.id, reason="in error"
            ),
        )
    with conn_of(busy) as uow:
        assert reports.overdue_reviews(uow.conn(), SCOPE, on=TODAY) == []


def test_the_transmittal_log_marks_the_issued_ones_that_wait_past_their_date(busy: World) -> None:
    a = busy.revision("ISO-1234", "A")
    doc = busy.document("ISO-1234")
    forge(
        busy,
        "T1",
        "documents.Transmittal",
        "TRN-0001",
        transmittal_events("TRN-0001", a.id, doc.id, due_date="2026-10-10"),
    )
    forge(
        busy,
        "T2",
        "documents.Transmittal",
        "TRN-0002",
        transmittal_events("TRN-0002", a.id, doc.id, due_date="2026-10-30", direction="incoming"),
    )
    forge(
        busy,
        "T3",
        "documents.Transmittal",
        "TRN-0003",
        transmittal_events("TRN-0003", a.id, doc.id, due_date="2026-10-01"),
    )
    # TRN-0001 and TRN-0002 are issued; TRN-0003 is answered
    from tl_core.ledger import NewEvent

    def move(stream: str, events: list[tuple[str, dict]], transitions: list[str]) -> None:
        with open_uow(busy.db) as uow:
            version = (
                uow.conn()
                .exec_driver_sql(f"SELECT version FROM cur_core_record WHERE id = '{stream}'")
                .scalar_one()
            )
            result = uow.append(
                stream_id=stream,
                stream_type="documents.Transmittal",
                scope=SCOPE,
                expected_version=int(version),
                events=[NewEvent(event_type=t, payload=p) for t, p in events],
                actor="user:forge",
                source="test",
                correlation_id="c",
            )
            assert result.new_version
        from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow

        for name in transitions:
            with open_uow(busy.db) as uow:
                now = (
                    uow.conn()
                    .exec_driver_sql(f"SELECT version FROM cur_core_record WHERE id = '{stream}'")
                    .scalar_one()
                )
                handle_transition_workflow(
                    uow,
                    TransitionWorkflow(
                        actor="user:forge",
                        source="test",
                        scope=SCOPE,
                        stream_id=stream,
                        expected_version=int(now),
                        transition=name,
                    ),
                    by_module=True,
                )

    move("T1", [("Transmittal.Issued", {"issued_on": "2026-10-02"})], ["issue"])
    move("T2", [("Transmittal.Issued", {"issued_on": "2026-10-03"})], ["issue"])
    move(
        "T3",
        [
            ("Transmittal.Issued", {"issued_on": "2026-09-20"}),
            (
                "Transmittal.ResponseRecorded",
                {"response_code": "approved", "response_note": None, "responded_on": "2026-09-25"},
            ),
        ],
        ["issue", "acknowledge"],
    )
    with conn_of(busy) as uow:
        log = reports.transmittal_log(uow.conn(), SCOPE, on=TODAY)
        incoming = reports.transmittal_log(uow.conn(), SCOPE, direction="incoming", on=TODAY)
        answered = reports.transmittal_log(uow.conn(), SCOPE, state="Acknowledged", on=TODAY)
    assert [(x.number, x.state, x.overdue) for x in log] == [
        ("TRN-0001", "Issued", True),
        ("TRN-0002", "Issued", False),
        ("TRN-0003", "Acknowledged", False),  # answered, so not waiting
    ]
    assert log[2].response_code == "approved" and log[2].responded_on == "2026-09-25"
    assert log[0].items == 1 and log[0].issued_on == "2026-10-02" and log[0].direction == "outgoing"
    assert [x.number for x in incoming] == ["TRN-0002"]
    assert [x.number for x in answered] == ["TRN-0003"]


def test_stale_pins_name_the_document_the_pin_and_what_replaced_it(busy: World) -> None:
    pinned = busy.link(busy.tag("47-FV-1001"), "ISO-1234", "A")
    busy.link(busy.tag("47-FV-1002"), "ISO-1234", None)  # floating: never stale
    busy.link(busy.tag("47-FV-1003"), "ISO-1234", "B")  # on the current revision
    busy.create_revision("ISO-1234")
    busy.attach("ISO-1234", "C", data=b"%PDF-1.7 c", name="c.pdf")
    busy.issue("ISO-1234", "C", "IFC")
    assert busy.link_status(pinned) == "stale"
    with conn_of(busy) as uow:
        lines = reports.stale_pins(uow.conn(), SCOPE)
        other = reports.stale_pins(uow.conn(), "project:P999")
    assert [(x.linked_key, x.pinned_code) for x in lines] == [
        ("47-FV-1001", "A"),
        ("47-FV-1003", "B"),
    ]
    first = lines[0]
    assert (first.document_number, first.current_code, first.current_status) == (
        "ISO-1234",
        "C",
        "IFC",
    )
    assert first.newer_codes == ["B", "C"] and first.link_status == "stale"
    assert first.linked_type == "core.Record" and first.link_id == pinned
    assert other == []
