"""The evidence trail: the chain around an item, as it stood on a date (brief 9, M10).

"For any Commercial or Legal item, one view assembles the full linked chain: correspondence, RFIs,
instructions, photos, daily records, schedule activities, and cost codes, all as of the relevant
dates (time-travel reads)." ``evidence_trail`` is that view. It answers a question a claim turns
on: *what did we know, and what was linked to what, on the day we gave notice?*

**As of a date** means every event recorded up to the end of that day (UTC). The trail is a replay
of the ledger, not a read of today's tables: a record that did not exist yet is absent; its title,
state and void flag are the ones its events had reached; a link is as its own events left it (a link
made later is absent, one retracted later is still there with the status it had); and the figures
of an item are folded from its events. Time is the ledger's ``recorded_at`` (what the system knew),
not a date a person typed.

**Who may see it** is decided by today's class, not by the class on that date (ADR-0016, ADR-0019):
a record the viewer cannot read now is left out, and so is every link that ends at it, and nothing
says how many were left out. The trail starts at an item the viewer can read (a hidden or unknown
number answers exactly as an unused one), and it reads the events of a record only after the record
passed the filter. The walk is bounded: depth, number of records, links looked at and events read
per stream; ``truncated`` says a bound was hit.

Nothing here writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any, Final

from pydantic import BaseModel
from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.links.lifecycle import CREATING_EVENTS, next_status
from tl_core.links.provider import get_vocabulary
from tl_core.services.errors import ServiceError

from tl_mod_correspondence import registry
from tl_mod_correspondence.errors import EvidenceDateError, ItemNotFoundError
from tl_mod_correspondence.handlers.common import today_date
from tl_mod_correspondence.names import (
    COMM_ASSESSED,
    COMM_DEFINED,
    COMM_UPDATED,
    CORR_DEFINED,
    CORR_ISSUED,
    CORR_RESPONDED,
    TECH_ANSWERED,
    TECH_DEFINED,
    TECH_REISSUED,
    TECH_REVIEWED,
    TECH_UPDATED,
)

MAX_DEPTH: Final = 3
MAX_NODES: Final = 200
MAX_LINKS_LOOKED_AT: Final = 1000
MAX_STREAM_EVENTS: Final = 5000
SHOWN_STATUSES: Final = ("active", "stale", "broken")
_DAY: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_LONG: Final = 160

_NEIGHBOURS = (
    "SELECT l.link_id, l.from_id, l.to_id, r.id AS other_id, r.type AS other_type "
    "FROM cur_links l "
    "JOIN cur_core_record r ON r.id = CASE WHEN l.from_id = :id THEN l.to_id ELSE l.from_id END "
    "WHERE (l.from_id = :id OR l.to_id = :id) AND r.scope = :scope AND {visible} "
    "ORDER BY l.created_at, l.link_id"
)
_EVENTS = (
    "SELECT event_type, payload, recorded_at FROM events WHERE stream_id = :id "
    "ORDER BY stream_version LIMIT :cap"
)


class EvidenceLink(BaseModel):
    """How a record was reached from its parent, as the link stood on the date."""

    link_id: str
    relation: str
    label: str  # the relation read from the parent: "derived from", "source of"
    direction: str  # out: the parent is the `from` end
    status: str  # active, stale or broken on the date
    pin: str | None
    note: str | None
    since: str  # the day the link was made


class EvidenceNode(BaseModel):
    record_id: str
    key: str | None
    title: str
    type: str
    depth: int
    parent_id: str | None
    via: EvidenceLink | None
    state: str | None  # the workflow state on the date; None for a record with no workflow
    voided: bool
    created_on: str
    facts: dict[str, str]  # what the record's own events said on the date


class EvidenceTrail(BaseModel):
    scope: str
    as_of: str
    root_id: str
    nodes: list[EvidenceNode]  # the root first, then breadth first
    truncated: bool


@dataclass
class _Event:
    event_type: str
    payload: dict[str, Any]
    recorded_at: datetime


@dataclass
class _Folded:
    created_on: str
    key: str | None
    title: str
    voided: bool = False
    state: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _moment(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _events_upto(conn: Connection, stream_id: str, cutoff: datetime) -> tuple[list[_Event], bool]:
    """The events of one stream recorded at or before ``cutoff``, and whether a bound was hit."""
    rows = conn.execute(text(_EVENTS), {"id": stream_id, "cap": MAX_STREAM_EVENTS + 1}).all()
    events: list[_Event] = []
    for row in rows[:MAX_STREAM_EVENTS]:
        at = _moment(row.recorded_at)
        if at > cutoff:
            break
        raw = row.payload
        payload = json.loads(raw) if isinstance(raw, str) else raw
        events.append(_Event(row.event_type, dict(payload or {}), at))
    return events, len(rows) > MAX_STREAM_EVENTS


def _fold(events: list[_Event]) -> _Folded | None:
    """The record as its events had made it; ``None`` when none of them is its creation."""
    found: _Folded | None = None
    for ev in events:
        p = ev.payload
        if ev.event_type == "Record.Created":
            found = _Folded(ev.recorded_at.date().isoformat(), p.get("key"), str(p.get("title")))
            continue
        if found is None:
            continue
        data = found.data
        if ev.event_type == "Record.Updated":
            title = (p.get("changes") or {}).get("title")
            if title:
                found.title = str(title[1])
        elif ev.event_type == "Record.Voided":
            found.voided = True
        elif ev.event_type == "Workflow.Transitioned":
            found.state = str(p["to_state"])
        elif ev.event_type == CORR_DEFINED:
            data.update(
                direction=p.get("direction"), domain=p.get("domain"), subtype=p.get("subtype")
            )
        elif ev.event_type == CORR_ISSUED:
            data["issued_on"] = p.get("issued_on")
        elif ev.event_type == CORR_RESPONDED:
            data["responded_on"] = p.get("responded_on")
        elif ev.event_type in (TECH_DEFINED, COMM_DEFINED):
            data.update({k: v for k, v in p.items() if k != "cost_code_impacts"})
        elif ev.event_type in (TECH_UPDATED, COMM_UPDATED):
            for name, change in (p.get("changes") or {}).items():
                if name != "cost_code_impacts":
                    data[name] = change[1]
        elif ev.event_type == TECH_ANSWERED:
            data.update(
                answer=p.get("answer"),
                answered_on=p.get("answered_on"),
                cost_impact=p.get("cost_impact"),
                schedule_impact=p.get("schedule_impact"),
            )
        elif ev.event_type == TECH_REVIEWED:
            data["review"] = p.get("decision")
        elif ev.event_type == TECH_REISSUED:
            for name in ("answer", "answered_on", "cost_impact", "schedule_impact", "review"):
                data.pop(name, None)
        elif ev.event_type == COMM_ASSESSED:
            data.update(
                assessment_status=p.get("status"),
                assessed_value=p.get("assessed_value"),
                assessed_on=p.get("assessed_on"),
            )
        elif ev.event_type == "Document.CurrentRevisionChanged":
            data["current_revision"] = p.get("current_revision_code")
            data["current_revision_status"] = p.get("current_revision_status")
    return found


#: The facts shown for a record, in this order, when its events said them.
_SHOWN: Final = (
    "direction",
    "subtype",
    "issued_on",
    "responded_on",
    "required_by",
    "answered_on",
    "cost_impact",
    "schedule_impact",
    "review",
    "aware_on",
    "currency",
    "estimated_value",
    "assessment_status",
    "assessed_value",
    "current_revision",
    "current_revision_status",
)


def _facts(folded: _Folded) -> dict[str, str]:
    shown = {k: str(folded.data[k]) for k in _SHOWN if folded.data.get(k) is not None}
    question = folded.data.get("question")
    if question:
        shown["question"] = str(question)[:_LONG]
    answer = folded.data.get("answer")
    if answer:
        shown["answer"] = str(answer)[:_LONG]
    return shown


def _link_as_of(events: list[_Event]) -> tuple[str, str | None, str | None, str] | None:
    """``(status, pin, note, since)`` of a link on the date, ``None`` when it was not a link to
    show (not made yet, suggested, declined, retracted, or a history the rules refuse)."""
    status: Any = None
    pin: str | None = None
    note: str | None = None
    since = ""
    try:
        for ev in events:
            status = next_status(status, ev.event_type, flag=ev.payload.get("status"))
            if ev.event_type in CREATING_EVENTS:
                pin, note = ev.payload.get("pin"), ev.payload.get("note")
                since = ev.recorded_at.date().isoformat()
            elif ev.event_type == "Link.Repinned":
                pin = ev.payload.get("pin")
    except ServiceError:
        return None
    if status not in SHOWN_STATUSES:
        return None
    return str(status), pin, note, since


def _label(relation: str, direction: str) -> str:
    try:
        return get_vocabulary().label(relation, "out" if direction == "out" else "in")
    except ServiceError:
        return relation.replace("_", " ")


def cutoff_of(as_of: str | None) -> tuple[str, datetime]:
    """The day (ISO) and the instant that ends it. ``as_of`` defaults to today and is never later
    than today; ``EvidenceDateError`` for a text that is not a calendar date or a day to come."""
    today = today_date()
    if as_of is None:
        day = today
    else:
        try:
            day = date.fromisoformat(as_of)
        except ValueError as exc:
            raise EvidenceDateError(
                f"as_of must be a date written YYYY-MM-DD, got {as_of!r}"
            ) from exc
        if len(as_of) != 10:
            raise EvidenceDateError(f"as_of must be a date written YYYY-MM-DD, got {as_of!r}")
        if day > today:
            raise EvidenceDateError(f"as_of {as_of} is after today ({today.isoformat()})")
        if day.year < 2000:
            raise EvidenceDateError(f"as_of {as_of} is before the system existed")
    return day.isoformat(), datetime.combine(day, time.max, tzinfo=UTC)


def _node(
    record_id: str,
    folded: _Folded,
    kind: str,
    depth: int,
    parent: str | None,
    via: EvidenceLink | None,
) -> EvidenceNode:
    return EvidenceNode(
        record_id=record_id,
        key=folded.key,
        title=folded.title,
        type=kind,
        depth=depth,
        parent_id=parent,
        via=via,
        state=folded.state,
        voided=folded.voided,
        created_on=folded.created_on,
        facts=_facts(folded),
    )


def evidence_trail(
    conn: Connection,
    scope: str,
    number: str,
    as_of: str | None = None,
    *,
    depth: int = 2,
    max_nodes: int = 100,
) -> EvidenceTrail:
    """The chain around the item ``number``, as it stood at the end of the day ``as_of``.

    ``depth`` (at most 3) is how many links away the walk goes; ``max_nodes`` (at most 200) bounds
    the records. Raises ``ItemNotFoundError`` for an unknown number and for one the viewer may not
    read (the same message), and ``EvidenceDateError`` for a bad date or one before the item
    existed.
    """
    day, cutoff = cutoff_of(as_of)
    limit_depth, limit_nodes = max(0, min(depth, MAX_DEPTH)), max(1, min(max_nodes, MAX_NODES))
    root = registry.find_item(conn, scope, number)
    if root is None:
        raise ItemNotFoundError(f"no correspondence item {number!r} in scope {scope!r}")
    events, cut = _events_upto(conn, root.id, cutoff)
    folded = _fold(events)
    if folded is None:
        raise EvidenceDateError(f"item {number} did not exist on {day}")
    truncated = cut
    nodes = [_node(root.id, folded, root.record_type, 0, None, None)]
    seen = {root.id}
    frontier = [root.id]
    looked_at = 0
    for level in range(1, limit_depth + 1):
        following: list[str] = []
        for parent_id in frontier:
            visible, params = confidentiality.not_hidden("r.id")
            rows = conn.execute(
                text(_NEIGHBOURS.format(visible=visible)),
                {**params, "id": parent_id, "scope": scope},
            ).all()
            for row in rows:
                looked_at += 1
                if looked_at > MAX_LINKS_LOOKED_AT or len(nodes) >= limit_nodes:
                    truncated = True
                    break
                other = str(row.other_id)
                if other in seen:
                    continue
                link_events, link_cut = _events_upto(conn, str(row.link_id), cutoff)
                shown = _link_as_of(link_events)
                if shown is None:
                    continue
                node_events, node_cut = _events_upto(conn, other, cutoff)
                other_folded = _fold(node_events)
                if other_folded is None:  # the record did not exist yet
                    continue
                truncated = truncated or link_cut or node_cut
                direction = "out" if row.from_id == parent_id else "in"
                status, pin, note, since = shown
                nodes.append(
                    _node(
                        other,
                        other_folded,
                        str(row.other_type),
                        level,
                        parent_id,
                        EvidenceLink(
                            link_id=str(row.link_id),
                            relation=_relation(link_events),
                            label=_label(_relation(link_events), direction),
                            direction=direction,
                            status=status,
                            pin=pin,
                            note=note,
                            since=since,
                        ),
                    )
                )
                seen.add(other)
                following.append(other)
        frontier = following
        if not frontier:
            break
    return EvidenceTrail(scope=scope, as_of=day, root_id=root.id, nodes=nodes, truncated=truncated)


def _relation(events: list[_Event]) -> str:
    """The relation of a link, from its first event."""
    return str(events[0].payload.get("relation", "references")) if events else "references"
