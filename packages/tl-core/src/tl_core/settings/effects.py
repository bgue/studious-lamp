"""Follow-up effects of a setting change: what was carried out and when (P0-I8 decision D6).

A setting whose ``effect`` is ``reindex``, ``rebuild`` or ``restart`` is fully in force only after
that effect. The ledger cannot say whether it happened, so a local, non-ledger table
(``setting_effect_applied``, one row per effect) records the ledger head and the time of the last
one: ``tl projections rebuild`` writes ``rebuild`` and ``reindex``, and the server start writes
``restart``. The resolver derives ``pending_effect`` from these rows and the key's changes, so a
ledger rebuild alone always yields the same ``cur_setting`` rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Connection, text

from tl_core.settings.instants import to_us
from tl_core.util import utcnow

EFFECTS = ("reindex", "rebuild", "restart")

_HEAD_SQL = text("SELECT COALESCE(MAX(seq), 0) FROM events")
_UPDATE_SQL = text(
    "UPDATE setting_effect_applied SET applied_seq = :seq, applied_us = :us, applied_by = :by "
    "WHERE effect = :effect"
)
_INSERT_SQL = text(
    "INSERT INTO setting_effect_applied (effect, applied_seq, applied_us, applied_by) "
    "VALUES (:effect, :seq, :us, :by)"
)


def mark_applied(
    conn: Connection,
    effects: Sequence[str],
    *,
    applied_by: str,
    now: datetime | None = None,
) -> int:
    """Record that ``effects`` were carried out now, at the current ledger head; return the head.

    ``effects`` are names from :data:`EFFECTS`; ``applied_by`` says what did it (``rebuild``,
    ``server``). Raises ``ValueError`` for another name. Write this in the same transaction that
    did the work, or just after it.
    """
    unknown = sorted(set(effects) - set(EFFECTS))
    if unknown:
        raise ValueError(f"unknown effects {unknown}; use {list(EFFECTS)}")
    head = int(conn.execute(_HEAD_SQL).scalar_one())
    moment = to_us(now if now is not None else utcnow())
    for effect in effects:
        params = {"effect": effect, "seq": head, "us": moment, "by": applied_by}
        if conn.execute(_UPDATE_SQL, params).rowcount == 0:
            conn.execute(_INSERT_SQL, params)
    return head
