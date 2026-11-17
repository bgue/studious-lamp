"""Read views of the intake queue: the codes the controller issued and the items the public intake
received (P2-FORMS I03). Nothing here writes, and no access word is checked (the entry points check
``forms.intake.review`` and ``forms.intake.issue``).

Every function takes ``viewer=`` keyword-only; its default is ``confidentiality.LOWEST``, never the
ambient viewer. An intake item is hidden through its code and a code through its context (the core
``SUBJECT_LINKS``); the hidden filter is inside each statement and before ``LIMIT``, so a hidden row
is absent from a list, from ``total`` and from ``pending``, and its detail is ``None``, as a missing
row is. A code with no context is not hidden by this module. Limits are clamped to 1..``MAX_LIMIT``;
an unknown state is a ``ValueError``.

Secret columns stay out of every row: the columns are named one by one in each statement, and the
stored body is read by ``item_answers`` alone, for one Pending item.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final, cast

from sqlalchemy import Connection, Row, bindparam, text
from tl_core import confidentiality

from tl_mod_forms.names import (
    ACTIVE,
    INTAKE_BODY_TABLE,
    INTAKE_CODE_STATES,
    INTAKE_CODE_VIEW,
    INTAKE_ITEM_STATES,
    INTAKE_ITEM_VIEW,
    PENDING,
)

MAX_LIMIT: Final = 500
MIN_LIMIT: Final = 1
MSG_UNKNOWN_STATE: Final = "unknown state"


@dataclass(frozen=True)
class CodeRow:
    """An intake code as the queue shows it. ``pending`` counts the Pending items of the code that
    the viewer may read."""

    id: str
    state: str
    template_id: str
    template_version: int
    context_id: str | None
    context_type: str | None
    heading: str
    controller_role: str
    expires_on: str | None
    issued_by: str | None
    revoked_by: str | None
    pending: int


@dataclass(frozen=True)
class ItemRow:
    """An intake item as the queue shows it. The claim is the name and company the sender gave,
    once the item is accepted; no phone number is ever read into a row."""

    id: str
    state: str
    code_id: str
    template_id: str
    template_version: int
    received_at: str
    body_bytes: int
    accepted_as: str | None
    accepted_by: str | None
    accepted_on: str | None
    claim_name: str | None
    claim_company: str | None
    rejected_reason: str | None
    rejected_by: str | None
    purged_at: str | None
    version: int


@dataclass(frozen=True)
class Page[T]:
    rows: list[T]
    total: int


#: The code columns a read selects, by name (the view's other columns are left out).
_CODE_COLUMNS: Final = (
    "v.id, COALESCE(v.status, :active) AS state, v.template_id, v.template_version, "
    "v.context_id, v.context_type, v.heading, v.controller_role, v.expires_on, "
    "v.issued_by, v.revoked_by"
)
#: The item columns a read selects, by name (the view's other columns are left out).
_ITEM_COLUMNS: Final = (
    "v.id, COALESCE(v.status, :pending) AS state, v.code_id, v.template_id, "
    "v.template_version, v.received_at, v.body_bytes, v.accepted_as, v.accepted_by, "
    "v.accepted_on, v.on_behalf_of_claim_json, v.rejected_reason, v.rejected_by, "
    "v.purged_at, v.version"
)


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def _clamp(limit: int) -> int:
    return min(max(int(limit), MIN_LIMIT), MAX_LIMIT)


def _skip(offset: int) -> int:
    return max(int(offset), 0)


def _claim(raw: object) -> tuple[str | None, str | None]:
    """``(name, company)`` of an accepted item's claim; ``(None, None)`` when the value is not JSON
    of an object. A key that is missing or not text gives ``None``; no other key is read."""
    if raw is None:
        return None, None
    try:
        data: object = json.loads(str(raw))
    except ValueError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    fields = cast(dict[str, object], data)
    name = fields.get("name")
    company = fields.get("company")
    return (
        name if isinstance(name, str) else None,
        company if isinstance(company, str) else None,
    )


def _code_row(row: Row[Any], pending: int) -> CodeRow:
    return CodeRow(
        id=str(row.id),
        state=str(row.state),
        template_id=str(row.template_id),
        template_version=int(row.template_version),
        context_id=_opt(row.context_id),
        context_type=_opt(row.context_type),
        heading=str(row.heading),
        controller_role=str(row.controller_role),
        expires_on=_opt(row.expires_on),
        issued_by=_opt(row.issued_by),
        revoked_by=_opt(row.revoked_by),
        pending=pending,
    )


def _item_row(row: Row[Any]) -> ItemRow:
    claim_name, claim_company = _claim(row.on_behalf_of_claim_json)
    return ItemRow(
        id=str(row.id),
        state=str(row.state),
        code_id=str(row.code_id),
        template_id=str(row.template_id),
        template_version=int(row.template_version),
        received_at=str(row.received_at),
        body_bytes=int(row.body_bytes),
        accepted_as=_opt(row.accepted_as),
        accepted_by=_opt(row.accepted_by),
        accepted_on=_opt(row.accepted_on),
        claim_name=claim_name,
        claim_company=claim_company,
        rejected_reason=_opt(row.rejected_reason),
        rejected_by=_opt(row.rejected_by),
        purged_at=_opt(row.purged_at),
        version=int(row.version),
    )


def _answers(stored: object) -> list[dict[str, Any]] | None:
    """The answers of a stored body, ``{"answers": [...]}``; ``None`` when it is not that."""
    try:
        data: object = json.loads(str(stored))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    answers = cast(dict[str, object], data).get("answers")
    if not isinstance(answers, list):
        return None
    found: list[dict[str, Any]] = []
    for entry in cast(list[object], answers):
        if not isinstance(entry, dict):
            return None
        found.append(cast(dict[str, Any], entry))
    return found


def _count(conn: Connection, view: str, where: str, params: dict[str, Any]) -> int:
    return int(
        conn.execute(text(f"SELECT COUNT(*) FROM {view} v WHERE {where}"), params).scalar_one()
    )


def _pending_counts(
    conn: Connection, scope: str, code_ids: list[str], viewer: confidentiality.Viewer
) -> dict[str, int]:
    """The Pending items of each of ``code_ids``, one grouped statement for the whole page."""
    visible, extra = confidentiality.not_hidden_each("i.id", viewer)
    statement = text(
        "SELECT i.code_id AS code_id, COUNT(*) AS n FROM " + INTAKE_ITEM_VIEW + " i "
        "WHERE i.scope = :scope AND i.voided = :no AND COALESCE(i.status, :pending) = :pending "
        f"AND i.code_id IN :ids AND {visible} GROUP BY i.code_id"
    ).bindparams(bindparam("ids", expanding=True))
    found = conn.execute(
        statement,
        {"scope": scope, "no": False, "pending": PENDING, "ids": code_ids, **extra},
    )
    return {str(row.code_id): int(row.n) for row in found}


def code_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> Page[CodeRow]:
    """The intake codes of ``scope``, oldest issue first, that match ``state``. Each row counts
    its Pending items. Hidden codes are left out of the rows and the total."""
    if state is not None and state not in INTAKE_CODE_STATES:
        raise ValueError(MSG_UNKNOWN_STATE)
    take, skip = _clamp(limit), _skip(offset)
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    conditions = ["v.scope = :scope", "v.voided = :no", visible]
    params: dict[str, Any] = {
        "scope": scope,
        "no": False,
        "active": ACTIVE,
        "limit": take,
        "offset": skip,
        **extra,
    }
    if state is not None:
        conditions.append("COALESCE(v.status, :active) = :state")
        params["state"] = state
    where = " AND ".join(conditions)
    rows = conn.execute(
        text(
            f"SELECT {_CODE_COLUMNS}, COUNT(*) OVER () AS total FROM {INTAKE_CODE_VIEW} v "
            f"WHERE {where} ORDER BY v.issued_at, v.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).all()
    if rows:
        total = int(rows[0].total)
    elif skip == 0:
        total = 0
    else:
        total = _count(conn, INTAKE_CODE_VIEW, where, params)
    pending = _pending_counts(conn, scope, [str(row.id) for row in rows], viewer) if rows else {}
    return Page(
        rows=[_code_row(row, pending.get(str(row.id), 0)) for row in rows],
        total=total,
    )


def item_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    code_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> Page[ItemRow]:
    """The intake items of ``scope``, oldest first (received, then id), that match ``state`` and
    ``code_id``. Hidden items are left out of the rows and the total."""
    if state is not None and state not in INTAKE_ITEM_STATES:
        raise ValueError(MSG_UNKNOWN_STATE)
    take, skip = _clamp(limit), _skip(offset)
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    conditions = ["v.scope = :scope", "v.voided = :no", visible]
    params: dict[str, Any] = {
        "scope": scope,
        "no": False,
        "pending": PENDING,
        "limit": take,
        "offset": skip,
        **extra,
    }
    if state is not None:
        conditions.append("COALESCE(v.status, :pending) = :state")
        params["state"] = state
    if code_id is not None:
        conditions.append("v.code_id = :code")
        params["code"] = code_id
    where = " AND ".join(conditions)
    rows = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS}, COUNT(*) OVER () AS total FROM {INTAKE_ITEM_VIEW} v "
            f"WHERE {where} ORDER BY v.received_at, v.id LIMIT :limit OFFSET :offset"
        ),
        params,
    ).all()
    if rows:
        total = int(rows[0].total)
    elif skip == 0:
        total = 0
    else:
        total = _count(conn, INTAKE_ITEM_VIEW, where, params)
    return Page(rows=[_item_row(row) for row in rows], total=total)


def item_detail(
    conn: Connection,
    scope: str,
    item_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> ItemRow | None:
    """The intake item of ``scope`` with this id. ``None`` when there is no such item or the
    viewer may not read it (its code's context is hidden)."""
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    row = conn.execute(
        text(
            f"SELECT {_ITEM_COLUMNS} FROM {INTAKE_ITEM_VIEW} v "
            "WHERE v.id = :id AND v.scope = :scope AND v.voided = :no "
            f"AND {visible} LIMIT 1"
        ),
        {"id": item_id, "scope": scope, "no": False, "pending": PENDING, **extra},
    ).first()
    return None if row is None else _item_row(row)


def item_answers(
    conn: Connection,
    scope: str,
    item_id: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> list[dict[str, Any]] | None:
    """The answers of a Pending item the viewer may read, from its staged body. ``None`` for an
    absent, hidden, other-scope, not Pending or purged item, and for a body that is not the
    expected JSON. Only SELECT statements run here."""
    visible, extra = confidentiality.not_hidden_each("v.id", viewer)
    allowed = conn.execute(
        text(
            f"SELECT v.id FROM {INTAKE_ITEM_VIEW} v "
            "WHERE v.id = :id AND v.scope = :scope AND v.voided = :no "
            "AND COALESCE(v.status, :pending) = :pending AND v.purged_at IS NULL "
            f"AND {visible} LIMIT 1"
        ),
        {"id": item_id, "scope": scope, "no": False, "pending": PENDING, **extra},
    ).first()
    if allowed is None:
        return None
    stored = conn.execute(
        text(f"SELECT body FROM {INTAKE_BODY_TABLE} WHERE item_id = :id LIMIT 1"),
        {"id": item_id},
    ).scalar_one_or_none()
    if stored is None:
        return None
    return _answers(stored)


def pending_count(
    conn: Connection,
    scope: str,
    *,
    viewer: confidentiality.Viewer = confidentiality.LOWEST,
) -> int:
    """The Pending items of ``scope`` the viewer may read."""
    visible, extra = confidentiality.not_hidden("i.id", viewer)
    return int(
        conn.execute(
            text(
                f"SELECT COUNT(*) FROM {INTAKE_ITEM_VIEW} i "
                "WHERE i.scope = :scope AND i.voided = :no "
                f"AND COALESCE(i.status, :pending) = :pending AND {visible}"
            ),
            {"scope": scope, "no": False, "pending": PENDING, **extra},
        ).scalar_one()
    )


__all__ = [
    "MAX_LIMIT",
    "CodeRow",
    "ItemRow",
    "Page",
    "code_list",
    "item_answers",
    "item_detail",
    "item_list",
    "pending_count",
]
