"""Reads of the constraints (ADR-0024 decision 8): every one joins the subject at read time.

A constraint has no class of its own and none is copied onto its row. Each read asks
``tl_core.confidentiality`` whether the viewer may read the **subject** (``subject_id``): a
viewer who may not read it sees no constraint, in no list, count, history or detail, and gets
``None`` for an id. A viewer who reads the subject but not the **target** sees the constraint
with no target at all (the four target fields are ``None``), byte for byte the same row as a
constraint raised without one; the count never depends on the target. The viewer defaults to the
lowest clearance (``current_viewer``); nothing here reads as the system. ``open_blocking``
(``guard.py``) is keys-only and needs no viewer.

Aging: ``constraint_age_days(row, today)`` counts whole days from the day it began to hold
things back (``effective_at``, else the day it was raised) to ``today`` (to ``cleared_at`` once
cleared); the flag ``aging`` is set for an open one past the setting
``awp.constraint.aging_days`` (the one setting that already existed for it). ``phase_ungated``
flags a blocking one whose phase no guard of the subject's workflow names any more (it never
blocks)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from typing import Any, cast

from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.constraints.guard import OPEN_STATES, gated_phases
from tl_core.ledger import Event
from tl_core.settings.layers import project_of_scope
from tl_core.settings.resolver import value_of
from tl_core.util import utcnow
from tl_core.workflow.provider import get_workflows

AGING_SETTING = "awp.constraint.aging_days"
MAX_LIMIT = 500

_COLUMNS = (
    "c.id, r.key, COALESCE(r.status, 'Open') AS state, c.scope, c.subject_id, c.phase, "
    "c.severity, c.category, c.source, c.owner, c.description_text, c.check_name, "
    "c.clear_reason, c.target_kind, c.target_id, c.target_ref_type, c.target_ref_text, "
    "c.effective_at, c.due_at, c.cleared_at, c.cleared_by, r.created_at, "
    "(COALESCE(r.status, 'Open') = 'Cleared' AND c.source = 'check' "
    "AND c.suppress_hash IS NOT NULL) AS waived, "
    "s.type AS subject_type, s.scope AS subject_scope"
)
_FROM = (
    "FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
    "JOIN cur_core_record s ON s.id = c.subject_id"
)


@dataclass(frozen=True)
class ConstraintView:
    """A constraint as a reader sees it (the target fields are ``None`` when it is hidden)."""

    id: str
    key: str
    state: str
    scope: str
    subject_id: str
    phase: str
    severity: str
    category: str
    source: str
    owner: str | None
    description: str | None
    check_name: str | None
    clear_reason: str | None
    target_kind: str | None
    target_id: str | None
    target_ref_type: str | None
    target_ref_text: str | None
    effective_at: str | None
    due_at: str | None
    cleared_at: str | None
    cleared_by: str | None
    raised_on: str
    age_days: int
    aging: bool
    phase_ungated: bool
    waived: bool


def _field(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return cast("Mapping[str, Any]", row).get(name)
    return getattr(row, name)


def constraint_age_days(row: Any, today: date) -> int:
    """Whole days from the day it began (``effective_at``, else ``raised_on``) to ``today``, or to
    ``cleared_at`` once cleared. A pure function of the row; never negative."""
    start = _field(row, "effective_at") or _field(row, "raised_on")
    if start is None:
        return 0
    cleared = _field(row, "cleared_at")
    end = today if cleared is None else date.fromisoformat(str(cleared)[:10])
    return max(0, (end - date.fromisoformat(str(start)[:10])).days)


def is_aging(row: Any, today: date, aging_days: int) -> bool:
    """Open and standing longer than ``aging_days``."""
    if _field(row, "cleared_at") is not None or _field(row, "state") not in OPEN_STATES:
        return False
    return constraint_age_days(row, today) > aging_days


def aging_days_of(conn: Connection, scope: str) -> int:
    return int(value_of(conn, AGING_SETTING, project=project_of_scope(scope)))


def _build(
    conn: Connection,
    rows: list[Any],
    today: date,
    viewer: confidentiality.Viewer | None,
) -> list[ConstraintView]:
    hidden = confidentiality.hidden_among(
        conn, [str(r.target_id) for r in rows if r.target_id is not None], viewer
    )
    limits: dict[str, int] = {}
    gated: dict[tuple[str, str], frozenset[str] | None] = {}
    out: list[ConstraintView] = []
    for r in rows:
        shown = r.target_id is None or str(r.target_id) not in hidden
        base = ConstraintView(
            id=str(r.id),
            key=str(r.key or ""),
            state=str(r.state),
            scope=str(r.scope),
            subject_id=str(r.subject_id),
            phase=str(r.phase),
            severity=str(r.severity),
            category=str(r.category),
            source=str(r.source),
            owner=r.owner,
            description=r.description_text,
            check_name=r.check_name,
            clear_reason=r.clear_reason,
            target_kind=r.target_kind if shown else None,
            target_id=r.target_id if shown else None,
            target_ref_type=r.target_ref_type if shown else None,
            target_ref_text=r.target_ref_text if shown else None,
            effective_at=r.effective_at,
            due_at=r.due_at,
            cleared_at=r.cleared_at,
            cleared_by=r.cleared_by,
            raised_on=str(r.created_at)[:10],
            age_days=0,
            aging=False,
            phase_ungated=False,
            waived=bool(r.waived),
        )
        if base.scope not in limits:
            limits[base.scope] = aging_days_of(conn, base.scope)
        which = (str(r.subject_type), str(r.subject_scope))
        if which not in gated:
            found = get_workflows().find(*which)
            gated[which] = None if found is None else gated_phases(found)
        phases = gated[which]
        is_open = base.state in OPEN_STATES
        out.append(
            replace(
                base,
                age_days=constraint_age_days(base, today),
                aging=is_aging(base, today, limits[base.scope]),
                phase_ungated=is_open
                and base.severity == "blocking"
                and (phases is None or base.phase not in phases),
            )
        )
    return out


def _where(
    scope: str,
    *,
    subject_id: str | None,
    state: str | None,
    category: str | None,
    phase: str | None,
    blocking: bool | None,
    owner: str | None = None,
    viewer: confidentiality.Viewer | None,
) -> tuple[str, dict[str, Any]]:
    """The conditions, and the join to the subject's class: never a column of the constraint."""
    visible, params = confidentiality.not_hidden_each("c.subject_id", viewer)
    parts = ["c.scope = :scope", "r.voided = :voided", visible]
    params = {**params, "scope": scope, "voided": False}
    for column, value, name in (
        ("c.subject_id", subject_id, "subject"),
        ("COALESCE(r.status, 'Open')", state, "state"),
        ("c.category", category, "category"),
        ("c.phase", phase, "phase"),
    ):
        if value is not None:
            parts.append(f"{column} = :{name}")
            params[name] = value
    if blocking is not None:
        parts.append("c.severity = :severity")
        params["severity"] = "blocking" if blocking else "advisory"
    if owner is not None:
        if owner == "":
            raise ValueError("owner must not be empty")
        parts.append("c.owner = :owner")
        params["owner"] = owner
    return " AND ".join(parts), params


def list_constraints(
    conn: Connection,
    scope: str,
    *,
    subject_id: str | None = None,
    state: str | None = None,
    category: str | None = None,
    phase: str | None = None,
    blocking: bool | None = None,
    owner: str | None = None,
    limit: int = 200,
    today: date | None = None,
    viewer: confidentiality.Viewer | None = None,
) -> list[ConstraintView]:
    """The constraints of a project the viewer may read (by the subject's class), by key."""
    where, params = _where(
        scope,
        subject_id=subject_id,
        state=state,
        category=category,
        phase=phase,
        blocking=blocking,
        owner=owner,
        viewer=viewer,
    )
    statement = text(f"SELECT {_COLUMNS} {_FROM} WHERE {where} ORDER BY r.key, r.id LIMIT :limit")
    rows = conn.execute(statement, {**params, "limit": max(1, min(limit, MAX_LIMIT))}).all()
    return _build(conn, list(rows), today or utcnow().date(), viewer)


def count_constraints(
    conn: Connection,
    scope: str,
    *,
    subject_id: str | None = None,
    state: str | None = None,
    category: str | None = None,
    phase: str | None = None,
    blocking: bool | None = None,
    owner: str | None = None,
    viewer: confidentiality.Viewer | None = None,
) -> int:
    """How many ``list_constraints`` would find (no limit); the target never changes it."""
    where, params = _where(
        scope,
        subject_id=subject_id,
        state=state,
        category=category,
        phase=phase,
        blocking=blocking,
        owner=owner,
        viewer=viewer,
    )
    statement = text(f"SELECT COUNT(*) {_FROM} WHERE {where}")
    return int(conn.execute(statement, params).scalar_one())


def get_constraint(
    conn: Connection,
    constraint_id: str,
    *,
    today: date | None = None,
    viewer: confidentiality.Viewer | None = None,
) -> ConstraintView | None:
    """One constraint, or ``None`` when absent or when its subject is hidden from the viewer."""
    visible, params = confidentiality.not_hidden_each("c.subject_id", viewer)
    statement = text(f"SELECT {_COLUMNS} {_FROM} WHERE c.id = :id AND {visible}")
    rows = conn.execute(statement, {**params, "id": constraint_id}).all()
    built = _build(conn, list(rows), today or utcnow().date(), viewer)
    return built[0] if built else None


def constraint_history(
    conn: Connection,
    events: list[Event],
    *,
    viewer: confidentiality.Viewer | None = None,
) -> list[Event]:
    """``events`` of constraint streams without those of a constraint whose subject is hidden.

    The subject is read from the constraint row, never from a copy."""
    ids = sorted({e.stream_id for e in events})
    if not ids:
        return []
    shown: set[str] = set()
    for constraint_id in ids:
        if get_constraint(conn, constraint_id, viewer=viewer) is not None:
            shown.add(constraint_id)
    return [e for e in events if e.stream_id in shown]
