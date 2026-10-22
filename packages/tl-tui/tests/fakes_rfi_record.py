"""An RFI with a history and clocks, in a `FakeClient` (P1-UX2-S5).

`event` builds a stored ledger event the way the module writes it (the types and payload keys are
the ones `test_technical_flow.py` reads back from a real ledger). `rfi_world` seeds three records
in project P123: an answered RFI (rejected once, re-issued, answered again, accepted) with two
clocks, a Draft RFI, and a received item that has only a body.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fakes import FakeClient
from fakes_correspondence import _item_fields  # pyright: ignore[reportPrivateUsage]
from tl_core.ledger import Event
from tl_mod_correspondence import reports_technical, views, views_domain
from tl_mod_correspondence.names import CORRESPONDENCE, TECHNICAL

PROJECT = "P123"
RFI_ID = "ID-P123-RFI-0001"
DRAFT_ID = "ID-P123-RFI-0003"
ITEM_ID = "ID-P123-COR-0001"
_WORDS = " ".join(f"Does detail {n} clash with the duct run?" for n in range(1, 100))
LONG_QUESTION = _WORDS[:2990] + " END-OF-Q."  # exactly 3000 characters, ends in a marker
_T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)


def event(
    seq: int,
    event_type: str,
    actor: str = "user:amy",
    *,
    day: int = 5,
    hour: int = 9,
    payload: dict[str, Any] | None = None,
    stream_id: str = RFI_ID,
    stream_type: str = TECHNICAL,
) -> Event:
    """A stored event of a record: ``day`` is the day of October 2026, ``seq`` orders ties."""
    at = _T0.replace(day=day, hour=hour) + timedelta(seconds=seq)
    return Event(
        event_type=event_type, payload=payload or {}, seq=seq, event_id=f"E{seq:06d}",
        stream_id=stream_id, stream_type=stream_type, stream_version=seq, scope="project:P123",
        actor=actor, recorded_at=at, effective_at=at, correlation_id="c", causation_id=None,
        source="test", prev_hash=None, hash=f"h{seq}",
    )  # fmt: skip


def transition(
    seq: int, name: str, actor: str = "user:amy", *, reason: str | None = None, day: int = 5
) -> Event:
    payload = {"transition": name, "reason": reason}
    return event(seq, "Workflow.Transitioned", actor, day=day, payload=payload)


def clock(**more: Any) -> views.ClockView:
    fields: dict[str, Any] = {
        "id": "CLK-1", "key": "P123-RFI-0001-C01", "item_id": RFI_ID,
        "item_number": "P123-RFI-0001", "label": "Answer required", "kind": "response_from_them",
        "start_on": "2026-10-06", "duration_days": 14, "day_type": "calendar",
        "calendar": "P123-default@1", "warn_days": [3, 1], "due_on": "2026-10-20",
        "state": "met", "effective_state": "met", "days_left": None, "warned_level": None,
        "paused_on": None, "closed_on": "2026-10-12", "closed_reason": "answered", "owner": None,
        "clause_id": None, "restarts": 0,
    }  # fmt: skip
    return views.ClockView(**{**fields, **more})


def _rfi(number: str, rfi_id: str, state: str, **more: Any) -> views_domain.TechnicalView:
    fields: dict[str, Any] = {
        **_item_fields(number, "Beam B12 clashes with line 47", state, domain="technical",
                       subtype="rfi", id=rfi_id, issued_on="2026-10-06"),
        "question": "Does beam B12 clash with line 47?", "proposed_solution": None,
        "discipline": "structural", "required_by": "2026-11-02",
        "potential_cost_impact": "unknown", "potential_schedule_impact": "unknown",
        "answer": None, "answered_on": None, "answer_cost_impact": None,
        "answer_schedule_impact": None, "answer_item_id": None, "answer_item_number": None,
        "answering_revision_id": None, "review_decision": None, "reviewed_on": None,
        "review_note": None,
    }  # fmt: skip
    return views_domain.TechnicalView(**{**fields, **more})


def _line(view: views_domain.TechnicalView) -> reports_technical.RfiLogLine:
    return reports_technical.RfiLogLine(
        id=view.id, number=view.number, subject=view.subject, subtype="rfi",
        discipline=view.discipline, state=view.state, raised_on="2026-10-05",
        issued_on=view.issued_on, required_by=view.required_by, answered_on=view.answered_on,
        response_days=None, on_time=None, overdue=False, days_overdue=None,
        potential_cost_impact=view.potential_cost_impact,
        potential_schedule_impact=view.potential_schedule_impact, cost_impact=None,
        schedule_impact=None, review_decision=view.review_decision, confidentiality="internal",
    )  # fmt: skip


def answered_history() -> list[Event]:
    """Raise, submit, edit, issue, answer, reject, re-issue, issue, answer, accept."""
    return [
        event(1, "Record.Created", day=5),
        event(2, "Correspondence.Defined", day=5, payload={"direction": "out"}),
        event(3, "Technical.Defined", day=5),
        transition(4, "submit", day=5),
        event(5, "Technical.Updated", day=5, payload={"question": "edited"}),
        event(6, "Correspondence.Issued", "user:ben", day=6),
        transition(7, "issue", "user:ben", day=6),
        transition(8, "await_response", "user:ben", day=6),
        event(9, "Technical.Answered", "user:cy", day=8),
        event(10, "Correspondence.Responded", "user:cy", day=8),
        transition(11, "answer", "user:cy", day=8),
        event(12, "Technical.Reviewed", day=9,
              payload={"decision": "rejected", "note": "does not answer the clash"}),
        transition(13, "reject", day=9, reason="does not answer the clash"),
        event(14, "Technical.Reissued", day=9, payload={"reason": "names both beams", "round": 2}),
        transition(15, "reissue", day=9, reason="names both beams"),
        event(16, "Correspondence.Issued", "user:ben", day=10),
        event(17, "Technical.Answered", "user:cy", day=12),
        event(18, "Technical.Reviewed", day=13, payload={"decision": "accepted", "note": None}),
        transition(19, "accept", day=13),
    ]  # fmt: skip


def rfi_world() -> FakeClient:
    client = FakeClient()
    answered = _rfi(
        "P123-RFI-0001", RFI_ID, "Accepted", question=LONG_QUESTION,
        proposed_solution="Move the beam 200 mm east.", answer="Re-route above the beam.",
        answered_on="2026-10-12", answer_cost_impact="yes", answer_schedule_impact="no",
        review_decision="accepted", reviewed_on="2026-10-13",
    )  # fmt: skip
    draft = _rfi("P123-RFI-0003", DRAFT_ID, "Draft", issued_on=None)
    client.add_rfi(PROJECT, answered, _line(answered))
    client.add_rfi(PROJECT, draft, _line(draft))
    client.add_stored_record(RFI_ID, "P123-RFI-0001", TECHNICAL, answered.subject)
    client.add_stored_record(DRAFT_ID, "P123-RFI-0003", TECHNICAL, draft.subject)
    client._events[RFI_ID] = answered_history()  # pyright: ignore[reportPrivateUsage]
    client._events[DRAFT_ID] = [  # pyright: ignore[reportPrivateUsage]
        event(21, "Record.Created", stream_id=DRAFT_ID),
        event(22, "Correspondence.Defined", stream_id=DRAFT_ID, payload={"direction": "out"}),
        event(23, "Technical.Defined", stream_id=DRAFT_ID),
    ]
    client.add_clock(PROJECT, clock())
    client.add_clock(
        PROJECT,
        clock(id="CLK-2", key="P123-RFI-0001-C02", closed_on="2026-10-12", start_on="2026-10-10"),
    )
    fields = _item_fields(
        "P123-COR-0001", "Revised programme", "Received", id=ITEM_ID, direction="in",
        domain="general", subtype="letter", response_required=False,
        body="Please find the revised programme attached.",
    )  # fmt: skip
    item = views.ItemView(**fields)  # type: ignore[arg-type]
    client.add_correspondence(PROJECT, item)
    client.add_stored_record(ITEM_ID, "P123-COR-0001", CORRESPONDENCE, item.subject)
    client._events[ITEM_ID] = [  # pyright: ignore[reportPrivateUsage]
        event(31, "Record.Created", stream_id=ITEM_ID, stream_type=CORRESPONDENCE),
        event(32, "Correspondence.Defined", stream_id=ITEM_ID, stream_type=CORRESPONDENCE,
              payload={"direction": "in"}),
    ]  # fmt: skip
    return client


__all__ = ["PROJECT", "clock", "event", "rfi_world", "transition"]
