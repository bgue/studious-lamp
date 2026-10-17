"""PartyProjector: the ``Party.*`` events into the party and contact tables.

``Defined`` inserts the party and its first contacts (positions 1, 2, ... in list order);
``ContactAdded`` inserts one more at the position the event states; ``ContactEnded`` clears the
contact's ``is_active``; ``Retired`` clears the party's. The code, the title and the email domains
come from the event as written. Deterministic. Register it after ``RecordProjector``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text
from tl_core.ledger import Event

from tl_mod_correspondence.names import (
    CONTACT_TABLE,
    PARTY_CONTACT_ADDED,
    PARTY_CONTACT_ENDED,
    PARTY_DEFINED,
    PARTY_RETIRED,
    PARTY_TABLE,
    PARTY_VIEW,
)
from tl_mod_correspondence.projectors._common import ddl_for, json_text, touch_record

_INSERT_SQL = text(
    f"INSERT INTO {PARTY_TABLE} (id, scope, code, project_role, email_domains_json, is_active, "
    "last_seq) VALUES (:id, :scope, :code, :project_role, :domains_json, :active, :last_seq)"
)
_CONTACT_SQL = text(
    f"INSERT INTO {CONTACT_TABLE} (contact_id, scope, party_id, position, name, email, title, "
    "domain, is_authorised, is_active, last_seq) VALUES (:contact_id, :scope, :party_id, "
    ":position, :name, :email, :title, :domain, :authorised, :active, :last_seq)"
)
_END_SQL = text(
    f"UPDATE {CONTACT_TABLE} SET is_active = :active, last_seq = :last_seq "
    "WHERE party_id = :party_id AND position = :position"
)
_RETIRE_SQL = text(
    f"UPDATE {PARTY_TABLE} SET is_active = :active, last_seq = :last_seq WHERE id = :id"
)


class PartyProjector:
    name = "correspondence_party"
    handles = frozenset({PARTY_DEFINED, PARTY_CONTACT_ADDED, PARTY_CONTACT_ENDED, PARTY_RETIRED})

    def ddl(self, dialect: str) -> list[str]:
        return (
            ddl_for(PARTY_TABLE, dialect)
            + ddl_for(CONTACT_TABLE, dialect)
            + ddl_for(PARTY_VIEW, dialect)
        )

    def apply(self, conn: Connection, event: Event) -> None:
        p: dict[str, Any] = event.payload
        et = event.event_type
        if et == PARTY_DEFINED:
            conn.execute(
                _INSERT_SQL,
                {
                    "id": event.stream_id,
                    "scope": event.scope,
                    "code": p["code"],
                    "project_role": p["project_role"],
                    "domains_json": json_text(p.get("email_domains") or []),
                    "active": True,
                    "last_seq": event.seq,
                },
            )
            for position, contact in enumerate(p.get("contacts") or [], start=1):
                self._contact(conn, event, position, contact)
        elif et == PARTY_CONTACT_ADDED:
            self._contact(conn, event, p["position"], p)
        elif et == PARTY_CONTACT_ENDED:
            found = conn.execute(
                _END_SQL,
                {
                    "party_id": event.stream_id,
                    "position": p["position"],
                    "active": False,
                    "last_seq": event.seq,
                },
            ).rowcount
            if found == 0:
                raise LookupError(f"no contact {p['position']} for party {event.stream_id}")
        elif et == PARTY_RETIRED:
            found = conn.execute(
                _RETIRE_SQL, {"id": event.stream_id, "active": False, "last_seq": event.seq}
            ).rowcount
            if found == 0:
                raise LookupError(f"no {PARTY_TABLE} row for stream {event.stream_id}")
        else:
            raise ValueError(f"PartyProjector cannot apply event type: {et}")
        touch_record(conn, event)

    @staticmethod
    def _contact(conn: Connection, event: Event, position: int, contact: dict[str, Any]) -> None:
        conn.execute(
            _CONTACT_SQL,
            {
                "contact_id": f"{event.stream_id}:{position:03d}",
                "scope": event.scope,
                "party_id": event.stream_id,
                "position": position,
                "name": contact["name"],
                "email": contact.get("email"),
                "title": contact.get("title"),
                "domain": contact.get("domain"),
                "authorised": bool(contact.get("is_authorised", False)),
                "active": True,
                "last_seq": event.seq,
            },
        )

    def reset(self, conn: Connection) -> None:
        conn.execute(text(f"DELETE FROM {CONTACT_TABLE}"))
        conn.execute(text(f"DELETE FROM {PARTY_TABLE}"))
