"""Read functions of the weekly plan (P2-I5 S4a): one layer the API, the CLI and the screens share.

Every function takes the viewer and reads through the class filter (ADR-0016): a plan the viewer
cannot open answers as one that does not exist, and a commitment of a hidden IWP is left out with a
note. Nothing here writes and nothing checks an access word: the entry points do.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel
from sqlalchemy import Connection, text
from tl_core.confidentiality import Viewer, not_hidden
from tl_core.services.errors import RecordNotFoundError

from tl_mod_awp.handlers.week import miss_reasons as miss_reasons
from tl_mod_awp.names import (
    IWP_DRAFT,
    IWP_TABLE,
    WEEK_COMMITMENT_TABLE,
    WEEK_DRAFT,
    WEEKLY_PLAN,
    WEEKLY_PLAN_TABLE,
)
from tl_mod_awp.progress import engine

#: The most weeks one list returns.
MAX_WEEKS: Final = 520
NOTE_HIDDEN: Final = "some commitments not shown"


class WeekRow(BaseModel):
    """One weekly plan as a list shows it."""

    id: str
    key: str
    week: str
    week_start: str
    state: str
    ppc: str | None = None
    closed_at: str | None = None


class CommitmentRow(BaseModel):
    iwp_id: str
    iwp_key: str
    iwp_state: str
    foreman: str
    committed_hours: str
    outcome: str | None = None
    miss_reason: str | None = None


class WeekDetail(WeekRow):
    """A plan with its commitments (IWP keys and states) and notes."""

    version: int
    commitments: list[CommitmentRow]
    notes: list[str]


def _row(raw: object) -> WeekRow:
    r = raw  # a sqlalchemy Row
    return WeekRow(
        id=str(r.id),  # type: ignore[attr-defined]
        key=str(r.key),  # type: ignore[attr-defined]
        week=str(r.week),  # type: ignore[attr-defined]
        week_start=str(r.week_start),  # type: ignore[attr-defined]
        state=str(r.state),  # type: ignore[attr-defined]
        ppc=None if r.ppc is None else str(r.ppc),  # type: ignore[attr-defined]
        closed_at=None if r.closed_at is None else str(r.closed_at),  # type: ignore[attr-defined]
    )


_SELECT = (
    "SELECT p.id, r.key, p.week, p.week_start, COALESCE(r.status, :draft) AS state, "
    f"p.ppc, p.closed_at, r.version FROM {WEEKLY_PLAN_TABLE} p JOIN cur_core_record r "
    "ON r.id = p.id "
)


def list_weeks(conn: Connection, scope: str, viewer: Viewer, *, limit: int = 60) -> list[WeekRow]:
    """The plans of ``scope``, the latest week first, those the viewer may read."""
    visible, extra = not_hidden("r.id", viewer)
    rows = conn.execute(
        text(
            _SELECT + "WHERE r.scope = :scope AND r.type = :type AND r.voided = :voided "
            f"AND {visible} ORDER BY p.week DESC, p.id LIMIT :limit"
        ),
        {
            "draft": WEEK_DRAFT,
            "scope": scope,
            "type": WEEKLY_PLAN,
            "voided": False,
            "limit": max(1, min(limit, MAX_WEEKS)),
            **extra,
        },
    )
    return [_row(r) for r in rows]


def week_detail(conn: Connection, plan_id: str, viewer: Viewer) -> WeekDetail:
    """One plan with its commitments. ``RecordNotFoundError`` (one answer) for a plan that is
    absent, voided, of another type or hidden from the viewer."""
    visible, extra = not_hidden("r.id", viewer)
    head = conn.execute(
        text(_SELECT + f"WHERE r.id = :id AND r.type = :type AND r.voided = :voided AND {visible}"),
        {"draft": WEEK_DRAFT, "id": plan_id, "type": WEEKLY_PLAN, "voided": False, **extra},
    ).first()
    if head is None:
        raise RecordNotFoundError(f"no record {plan_id!r}")
    seen, extra_i = not_hidden("i.id", viewer)
    held = conn.execute(
        text(
            "SELECT c.iwp_id, ir.key AS iwp_key, COALESCE(ir.status, :iwp_draft) AS iwp_state, "
            "c.foreman, c.committed_hours, c.outcome, c.miss_reason "
            f"FROM {WEEK_COMMITMENT_TABLE} c JOIN {IWP_TABLE} i ON i.id = c.iwp_id "
            f"JOIN cur_core_record ir ON ir.id = i.id WHERE c.plan_id = :plan AND {seen} "
            "ORDER BY ir.key, c.iwp_id"
        ),
        {"iwp_draft": IWP_DRAFT, "plan": plan_id, **extra_i},
    ).all()
    total = conn.execute(
        text(f"SELECT COUNT(*) FROM {WEEK_COMMITMENT_TABLE} WHERE plan_id = :plan"),
        {"plan": plan_id},
    ).scalar_one()
    notes: list[str] = []
    if int(total) == 0:
        notes.append(engine.ppc(0, 0)[1][0])
    if int(total) > len(held):
        notes.append(NOTE_HIDDEN)
    commitments = [
        CommitmentRow(
            iwp_id=str(h.iwp_id),
            iwp_key=str(h.iwp_key),
            iwp_state=str(h.iwp_state),
            foreman=str(h.foreman),
            committed_hours=str(h.committed_hours),
            outcome=None if h.outcome is None else str(h.outcome),
            miss_reason=None if h.miss_reason is None else str(h.miss_reason),
        )
        for h in held
    ]
    return WeekDetail(
        **_row(head).model_dump(),
        version=int(head.version),
        commitments=commitments,
        notes=notes,
    )


__all__ = ["CommitmentRow", "WeekDetail", "WeekRow", "list_weeks", "miss_reasons", "week_detail"]
