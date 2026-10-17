# ruff: noqa: F401, F841
"""PartyProjector: the ``Party.*`` events into the party and contact tables.

``Defined`` inserts the party and its first contacts (positions 1, 2, ... in list order);
``ContactAdded`` inserts one more at the position the event states; ``ContactEnded`` clears the
contact's ``is_active``; ``Retired`` clears the party's. The code, the title and the email domains
come from the event as written. Deterministic. Register it after ``RecordProjector``.

STUB (P1-I5-T03c): the functions with a STEPS comment are for you to write. When they are
written, delete this paragraph, the STEPS comments and the `ruff: noqa` line at the top.
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
        # STEPS
        # 1. `p = event.payload`, `et = event.event_type`. Named parameters; table names from the
        #    constants PARTY_TABLE and CONTACT_TABLE. Booleans are Python bools.
        # 2. PARTY_DEFINED: INSERT into PARTY_TABLE: id (`event.stream_id`), scope (`event.scope`),
        #    code, project_role (required keys), `email_domains_json` =
        #    `json_text(p.get("email_domains") or [])`, is_active True, last_seq. Then, for each
        #    contact of `p.get("contacts") or []` with position 1, 2, ... in list order, call
        #    `self._contact(conn, event, position, contact)`.
        # 3. PARTY_CONTACT_ADDED: `self._contact(conn, event, p["position"], p)` (the event payload
        #    is the contact).
        # 4. PARTY_CONTACT_ENDED: UPDATE CONTACT_TABLE SET is_active False, last_seq WHERE party_id
        #    = `event.stream_id` AND position = `p["position"]`; a row count of 0 raises
        #    `LookupError(f"no contact {p['position']} for party {event.stream_id}")`.
        # 5. PARTY_RETIRED: UPDATE PARTY_TABLE SET is_active False, last_seq WHERE id =
        #    `event.stream_id`; a row count of 0 raises LookupError like the contact case. The
        #    contacts stay.
        # 6. Any other event type: `raise ValueError(f"PartyProjector cannot apply event type:
        #    {et}")`. After the branches call `touch_record(conn, event)`.
        raise NotImplementedError

    @staticmethod
    def _contact(conn: Connection, event: Event, position: int, contact: dict[str, Any]) -> None:
        # STEPS
        # 1. INSERT into CONTACT_TABLE: contact_id = `f"{event.stream_id}:{position:03d}"`, scope
        #    (`event.scope`), party_id (`event.stream_id`), position, name (required:
        #    `contact["name"]`), email, title, domain (`contact.get`), is_authorised =
        #    `bool(contact.get("is_authorised", False))`, is_active True, last_seq (`event.seq`).
        raise NotImplementedError

    def reset(self, conn: Connection) -> None:
        # STEPS
        # 1. `DELETE FROM` CONTACT_TABLE, then PARTY_TABLE.
        raise NotImplementedError
