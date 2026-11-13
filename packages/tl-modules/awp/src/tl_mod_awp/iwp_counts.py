"""The per-IWP counts of the IWP log (P2-I5-T11a1): Ready checks, open blocking constraints and the
state-since date, one page of IWPs at a time.

Reads only, through the viewer's class filter: a hidden IWP is absent from the page (``iwp_list``
leaves it out, and no count includes it). The statements are batched over the page: the list, one
readiness pair, one blocking count per IWP and open state (``look_ahead_view._open_blocking``), and
one ``cur_workflow_state`` read for the state-since dates.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection, bindparam, text

from tl_mod_awp import iwp_views
from tl_mod_awp.look_ahead_view import _open_blocking, _readiness

#: The most IWPs one page returns (the list clamps to the same bound).
COUNTS_LIMIT: Final = 500

_STATE_SINCE_SQL = text(
    "SELECT record_id, entered_at FROM cur_workflow_state WHERE record_id IN :ids"
).bindparams(bindparam("ids", expanding=True))


class IwpCountRow(BaseModel):
    """One IWP's counts as the IWP log shows them. ``state_since`` is the transition date as
    ``YYYY-MM-DD`` (``None`` for a Draft with no workflow row); ``ready_ok`` and ``ready_total``
    count the readiness checks as last evaluated (0 and 0 when ``evaluated`` is False)."""

    number: str
    state_since: str | None
    ready_ok: int
    ready_total: int
    evaluated: bool
    open_blocking: int


def iwp_counts(conn: Connection, scope: str, *, limit: int = COUNTS_LIMIT) -> list[IwpCountRow]:
    """The viewer-visible IWPs of ``scope`` by number, at most ``limit`` (clamped to 1..500), with
    their counts. The same call twice gives the same rows."""
    rows = iwp_views.iwp_list(conn, scope, limit=min(max(1, int(limit)), COUNTS_LIMIT))
    if not rows:
        return []
    ids = [row.id for row in rows]
    ready_by, checks = _readiness(conn, ids)
    blocking = _open_blocking(conn, scope, None, set(ids))
    since = {str(r[0]): str(r[1])[:10] for r in conn.execute(_STATE_SINCE_SQL, {"ids": ids}).all()}
    return [
        IwpCountRow(
            number=row.number,
            state_since=since.get(row.id),
            ready_ok=checks.get(row.id, (0, 0))[0],
            ready_total=checks.get(row.id, (0, 0))[1],
            evaluated=row.id in ready_by,
            open_blocking=blocking.get(row.id, 0),
        )
        for row in rows
    ]
