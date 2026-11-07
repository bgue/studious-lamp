"""Links the module writes and keeps in step with its typed rows (spec m3-wbs-cwp section 2).

A WBS node ``references`` each cost code of its allocation; a CWP ``belongs_to`` its area and to
each WBS node it is allocated to. The module writes them (``by_module=True``, link source ``rule``)
and a person cannot retract them. ``sync_links`` compares the live links of one relation from one
record with the typed rows both ways, so a link that is missing is added again on the next change
and one that is no longer wanted is retracted.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from sqlalchemy import text
from tl_core.ledger import Event
from tl_core.services.commands import Command
from tl_core.services.links import AddLink, RetractLink, handle_add_link, handle_retract_link
from tl_core.uow import UnitOfWork

from tl_mod_awp.names import RULE_LINK_SOURCE

_LIVE_SQL = text(
    "SELECT link_id, to_id, source FROM cur_links "
    "WHERE from_id = :from_id AND relation = :relation AND status <> 'retracted'"
)


def sync_links(
    uow: UnitOfWork,
    cmd: Command,
    from_id: str,
    relation: str,
    wanted: Collection[str],
    reason: str,
) -> list[Event]:
    """Make the module's links of ``relation`` from ``from_id`` point at exactly ``wanted``.

    A live link of source ``rule`` to a record that is not wanted is retracted; a wanted record
    with no live link of any source gets one. A link a person made to a wanted record stays as it
    is (the link exists), and a person's link to another record is never touched.
    """
    rows = uow.conn().execute(_LIVE_SQL, {"from_id": from_id, "relation": relation}).all()
    held = {str(r.to_id) for r in rows}
    keep = set(wanted)
    events: list[Any] = []
    for row in sorted(rows, key=lambda r: (str(r.to_id), str(r.link_id))):
        if row.source == RULE_LINK_SOURCE and str(row.to_id) not in keep:
            gone = handle_retract_link(
                uow,
                RetractLink(
                    actor=cmd.actor,
                    source=cmd.source,
                    scope=cmd.scope,
                    correlation_id=cmd.correlation_id,
                    causation_id=cmd.causation_id,
                    link_id=str(row.link_id),
                    reason=reason,
                ),
                by_module=True,
            )
            events.extend(gone.events)
    for to_id in sorted(keep - held):
        added = handle_add_link(
            uow,
            AddLink(
                actor=cmd.actor,
                source=cmd.source,
                scope=cmd.scope,
                correlation_id=cmd.correlation_id,
                causation_id=cmd.causation_id,
                from_id=from_id,
                to_id=to_id,
                relation=relation,
                link_source=RULE_LINK_SOURCE,
            ),
            by_module=True,
        )
        events.extend(added.events)
    return events
