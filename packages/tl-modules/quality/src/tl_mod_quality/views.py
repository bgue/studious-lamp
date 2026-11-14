"""Read views of the punch list (P2-PUNCH T01 fills the bodies; the interface is fixed here).

Every read takes keyword-only ``viewer=`` (default ``confidentiality.LOWEST``). Nothing here
reads the clock: an overdue filter takes ``today``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core import confidentiality

from tl_mod_quality.api import MSG_CATEGORY
from tl_mod_quality.names import (
    CATEGORIES,
    CLEARED,
    OPEN,
    PUNCH_ITEM_TABLE,
    VERIFIED,
    VOID,
)

#: The most rows one list returns.
MAX_LIMIT: Final = 500
MSG_STATE: Final = "unknown punch state"
MSG_OVERDUE: Final = "overdue needs today (YYYY-MM-DD)"
_STATES: Final = (OPEN, CLEARED, VERIFIED, VOID)


@dataclass(frozen=True)
class PunchRow:
    id: str  # the record id, for commands; no screen or line prints it
    key: str
    subject: str
    state: str
    category: str
    area: str | None
    system: str | None
    due_on: str | None
    assignee: str | None
    raised_by: str
    source_key: str | None


@dataclass(frozen=True)
class PunchDetail:
    row: PunchRow
    description: str | None
    cleared_by: str | None
    cleared_on: str | None
    clear_note: str | None
    verified_by: str | None
    verified_on: str | None
    reopen_count: int
    last_reopen_reason: str | None
    void_reason: str | None
    source_type: str | None
    version: int


@dataclass(frozen=True)
class PunchPage:
    rows: list[PunchRow]
    total: int


#: The item join, and its source record (LEFT: a free-standing item has none).
_FROM = (
    f"FROM {PUNCH_ITEM_TABLE} t JOIN cur_core_record r ON r.id = t.id "
    "LEFT JOIN cur_core_record src ON src.id = t.source_id "
)
_STATE = "COALESCE(r.status, :open)"
_ROW_COLUMNS = (
    "r.id, r.key, r.title, "
    f"{_STATE} AS state, t.category, t.area, t.system, t.due_on, t.assignee, t.raised_by, "
    "src.key AS source_key"
)


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _row(raw: RowMapping) -> PunchRow:
    return PunchRow(
        id=str(raw["id"]),
        key=str(raw["key"]),
        subject=str(raw["title"]),
        state=str(raw["state"]),
        category=str(raw["category"]),
        area=_text(raw["area"]),
        system=_text(raw["system"]),
        due_on=_text(raw["due_on"]),
        assignee=_text(raw["assignee"]),
        raised_by=str(raw["raised_by"]),
        source_key=_text(raw["source_key"]),
    )


def punch_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    area: str | None = None,
    system: str | None = None,
    assignee: str | None = None,
    category: str | None = None,
    source_key: str | None = None,
    overdue: bool = False,
    today: str | None = None,
    limit: int = 200,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PunchPage:
    """Visible items of ``scope`` by key; ``total`` counts the matches before ``limit``."""
    if state is not None and state not in _STATES:
        raise ValueError(MSG_STATE)
    if category is not None and category not in CATEGORIES:
        raise ValueError(MSG_CATEGORY)
    if overdue and today is None:
        raise ValueError(MSG_OVERDUE)
    params: dict[str, Any] = {
        "open": OPEN,
        "scope": scope,
        "no": False,
        "limit": max(1, min(int(limit), MAX_LIMIT)),
    }
    conds = ["r.scope = :scope", "r.voided = :no"]
    filters = {
        "area": area,
        "system": system,
        "assignee": assignee,
        "category": category,
        "source_key": source_key,
    }
    columns = {
        "area": "t.area",
        "system": "t.system",
        "assignee": "t.assignee",
        "category": "t.category",
        "source_key": "src.key",
    }
    for name, value in filters.items():
        if value is not None:
            conds.append(f"{columns[name]} = :{name}")
            params[name] = value
    if state is not None:
        conds.append(f"{_STATE} = :state")
        params["state"] = state
    if overdue:
        conds.append(f"{_STATE} = :s_open AND t.due_on < :today")
        params["s_open"] = OPEN
        params["today"] = today
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    conds.append(visible)
    params.update(extra)
    where = " AND ".join(conds)
    total = conn.execute(text(f"SELECT COUNT(*) AS n {_FROM} WHERE {where}"), params).scalar_one()
    raws = conn.execute(
        text(f"SELECT {_ROW_COLUMNS} {_FROM} WHERE {where} ORDER BY r.key, r.id LIMIT :limit"),
        params,
    ).mappings()
    return PunchPage(rows=[_row(raw) for raw in raws], total=int(total))


def punch_detail(
    conn: Connection,
    scope: str,
    key: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> PunchDetail | None:
    """One item; ``None`` when it is absent, in another project or hidden."""
    visible, extra = confidentiality.not_hidden_each("r.id", viewer)
    statement = text(
        f"SELECT {_ROW_COLUMNS}, r.description, r.version, t.cleared_by, t.cleared_on, "
        "t.clear_note, t.verified_by, t.verified_on, t.reopen_count, "
        "t.last_reopen_reason, t.void_reason, src.type AS source_type "
        f"{_FROM} WHERE r.scope = :scope AND r.key = :key AND r.voided = :no "
        f"AND {visible}"
    )
    params = {"open": OPEN, "scope": scope, "key": key, "no": False, **extra}
    raw = conn.execute(statement, params).mappings().first()
    if raw is None:
        return None
    return PunchDetail(
        row=_row(raw),
        description=_text(raw["description"]),
        cleared_by=_text(raw["cleared_by"]),
        cleared_on=_text(raw["cleared_on"]),
        clear_note=_text(raw["clear_note"]),
        verified_by=_text(raw["verified_by"]),
        verified_on=_text(raw["verified_on"]),
        reopen_count=int(raw["reopen_count"] or 0),
        last_reopen_reason=_text(raw["last_reopen_reason"]),
        void_reason=_text(raw["void_reason"]),
        source_type=_text(raw["source_type"]),
        version=int(raw["version"]),
    )


def punch_counts(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> dict[str, int]:
    """Visible items by state: ``Open``, ``Cleared``, ``Verified``, ``Void`` (each present)."""
    visible, extra = confidentiality.not_hidden("r.id", viewer)
    statement = text(
        "SELECT r.status AS status, COUNT(*) AS n "
        f"{_FROM} WHERE r.scope = :scope AND r.voided = :no AND {visible} "
        "GROUP BY r.status"
    )
    params = {"scope": scope, "no": False, **extra}
    counts: dict[str, int] = dict.fromkeys(_STATES, 0)
    for raw in conn.execute(statement, params).mappings():
        name = OPEN if raw["status"] is None else str(raw["status"])
        if name in counts:
            counts[name] += int(raw["n"])
    return counts


__all__ = [
    "PunchDetail",
    "PunchPage",
    "PunchRow",
    "punch_counts",
    "punch_detail",
    "punch_list",
]
