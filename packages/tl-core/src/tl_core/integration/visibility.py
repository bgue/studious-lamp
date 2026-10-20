"""What automation may see (ADR-0016 through ADR-0017; P1-I7 catch-up D17).

A rule, an inbound mapping and an enricher act as a service actor. The confidentiality filters
(``tl_core.confidentiality``) know a *viewer*; this module gives automation one and answers the
two questions the engines ask: "is the record this event is about hidden from the actor?" and
"read as the actor". An event about a record the actor may not read is passed over without a trace
(no firing row, no proposal, no value): that it happened is itself what the filters hide.
"""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.confidentiality import (
    Viewer,
    hidden_event_streams,
    is_hidden,
)
from tl_core.integration.contract import AutomationAccess
from tl_core.webhooks.rows import OutboxRow


def declared_viewer(actor: str, access: AutomationAccess) -> Viewer:
    """The viewer an automation of this declared access is, whether or not it is switched on (a
    dry run asks what it would have seen): ``restricted`` for ``controller``, else ``internal``;
    named by its own actor, so a clearance row can name it."""
    return Viewer(actor=actor, level=1 if access == "controller" else 0, account=actor)


def event_hidden(conn: Connection, row: OutboxRow, viewer: Viewer) -> bool:
    """Whether the event ``row`` is about a record, or is the stream of a thing (a link, a file, a
    feed item, an enrichment value, an invocation) of a record, that ``viewer`` must not read."""
    if viewer.system:
        return False
    if row.subject_id and is_hidden(conn, row.subject_id, viewer):
        return True
    return row.stream_id in hidden_event_streams(conn, [(row.stream_id, row.stream_type)], viewer)
