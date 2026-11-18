"""The purge of staged intake bodies (P2-FORMS D19, built in V3-F4).

``purge_due`` removes the staged body of every item received longer ago than the retention window
(``forms.intake.retention_days``, per project) and appends ``IntakeItem.Purged`` for it, in the
caller's unit of work. An accepted item has no body already; a rejected or undecided one has
its body removed here. A run is bounded, and a second run finds nothing (the body row is gone).
This function and S7c's accept handler are the only code that deletes ``forms_intake_body`` rows.
Nothing here reads or returns a body, a salt, a code or a hash: the result is a count of items.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import text
from tl_core.confidentiality import Viewer, not_hidden_each
from tl_core.ledger import NewEvent, iso_utc
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

from tl_mod_forms.handlers.common import silent, version_of
from tl_mod_forms.names import (
    INTAKE_BODY_TABLE,
    INTAKE_ITEM,
    INTAKE_ITEM_PURGED,
    INTAKE_ITEM_TABLE,
    INTAKE_RETENTION_DAYS,
)

BATCH: Final = 100

_SCOPES = text(
    f"SELECT DISTINCT i.scope FROM {INTAKE_BODY_TABLE} b JOIN {INTAKE_ITEM_TABLE} i "
    "ON i.id = b.item_id WHERE i.purged_at IS NULL ORDER BY i.scope"
)
_HELD = (
    f"SELECT b.item_id, b.received_at FROM {INTAKE_BODY_TABLE} b JOIN {INTAKE_ITEM_TABLE} i "
    "ON i.id = b.item_id WHERE i.scope = :scope AND i.purged_at IS NULL AND {visible} "
    "ORDER BY b.received_at, b.item_id"
)
_DELETE = text(f"DELETE FROM {INTAKE_BODY_TABLE} WHERE item_id = :id")


def _moment(stored: object) -> datetime:
    """A stored received time as an aware datetime (a naive one is read as UTC)."""
    found = datetime.fromisoformat(str(stored))
    return found if found.tzinfo is not None else found.replace(tzinfo=UTC)


def purge_due(
    uow: UnitOfWork,
    now: datetime,
    *,
    actor: str,
    source: str,
    scope: str | None = None,
    viewer: Viewer | None = None,
    limit: int = BATCH,
) -> int:
    """Purge up to ``limit`` due items (at most ``BATCH``); the number purged.

    ``scope`` limits the run to one project's items. With a ``viewer`` an item that viewer may not
    read is left alone (and not counted), so the count tells nothing about a hidden item; the job
    that runs with no viewer purges them all."""
    conn = uow.conn()
    left = max(0, min(int(limit), BATCH))
    done = 0
    scopes = [scope] if scope is not None else [str(s) for s in conn.execute(_SCOPES).scalars()]
    for scope in scopes:
        if left <= 0:
            break
        days = int(value_of(conn, INTAKE_RETENTION_DAYS, project=project_of_scope(scope)))
        cutoff = now - timedelta(days=days)
        if viewer is None:
            held, extra = text(_HELD.format(visible="1 = 1")), {}
        else:
            visible, extra = not_hidden_each("i.id", viewer)
            held = text(_HELD.format(visible=visible))
        due = [
            str(row.item_id)
            for row in conn.execute(held, {"scope": scope, **extra})
            if _moment(row.received_at) < cutoff
        ][:left]
        for item_id in due:
            conn.execute(_DELETE, {"id": item_id})
            uow.append(
                stream_id=item_id,
                stream_type=INTAKE_ITEM,
                scope=scope,
                expected_version=version_of(uow, item_id),
                events=[
                    NewEvent(
                        event_type=INTAKE_ITEM_PURGED,
                        payload=silent({"purged_at": iso_utc(now)}),
                    )
                ],
                actor=actor,
                source=source,
                correlation_id=new_ulid(),
            )
        left -= len(due)
        done += len(due)
    return done


__all__ = ["BATCH", "purge_due"]
