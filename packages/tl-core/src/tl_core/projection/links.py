"""LinkProjector: link events into ``cur_links`` and ``cur_link_counts`` (brief 7.1, 5.4).

One row per link. Both directions of a link are read from the same row: outbound by ``from_id``,
inbound by ``to_id``. A retracted link keeps its row (links are never deleted). Every event also
refreshes ``cur_link_counts`` for both records of the link.

Deterministic: the new row depends only on the event and on the rows already in the database. The
status that follows an event comes from ``tl_core.links.lifecycle.next_status``. It must be
registered after ``RecordProjector`` (it reads the record's scope for the counts row).

STUB (P0-I3-T03): ``name``, ``handles``, ``ddl`` and ``reset`` are final; ``apply`` is the ticket.
Remove this paragraph when done.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from tl_schema.ddl_loader import statements

from tl_core.ledger import Event
from tl_core.links.lifecycle import LINK_EVENT_TYPES


class LinkProjector:
    name = "links"
    handles = LINK_EVENT_TYPES

    def ddl(self, dialect: str) -> list[str]:
        if dialect == "sqlite" or dialect == "postgres":
            return statements("cur_links", dialect) + statements("cur_link_counts", dialect)
        raise ValueError(f"unsupported dialect: {dialect}")

    def apply(self, conn: Connection, event: Event) -> None:
        raise NotImplementedError

    def reset(self, conn: Connection) -> None:
        conn.execute(text("DELETE FROM cur_links"))
        conn.execute(text("DELETE FROM cur_link_counts"))
