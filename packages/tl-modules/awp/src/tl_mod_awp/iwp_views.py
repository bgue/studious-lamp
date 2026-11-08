"""Read views of IWPs and their scope (P2-I2 T04a): one layer the API, the CLI, the MCP tools
and the screens share.

Every function takes a connection and a project scope and reads through the viewer's class
filter (ADR-0016): a hidden IWP is absent (``None`` from the single-record reads, left out of
a list), a hidden CWP is not named (``cwp_number`` is ``None``), and no count or total includes
a hidden record. Nothing here writes and nothing checks an access word: the entry points do.
Constraint counts come from ``tl_core.constraints.queries``, which applies the viewer join
itself.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping
from tl_core.confidentiality import not_hidden
from tl_core.constraints.queries import count_constraints

from tl_mod_awp.names import (
    CWP,
    IWP,
    IWP_DRAFT,
    IWP_TABLE,
    SCOPE_ITEM,
    SCOPE_ITEM_TABLE,
    SCOPE_RELATION,
    TAG_TYPE,
)
from tl_mod_awp.projectors.iwp import signoff_rows

#: The constraint states that count as open on an IWP.
OPEN_STATES: Final = ("Open", "Assigned")
#: The most rows one list or scope read returns.
MAX_LIMIT: Final = 500


class IwpRow(BaseModel):
    """One IWP as a list shows it. ``state`` is the workflow state (Draft when none is set)."""

    id: str
    number: str
    title: str
    state: str
    discipline: str | None = None
    planned_start: str | None = None
    planned_finish: str | None = None
    foreman: str | None = None
    estimated_hours: Decimal | None = None
    cwp_number: str | None = None
    scope_count: int = 0


class IwpDetail(IwpRow):
    """One IWP with its crew, sign-offs, pins, open constraints and scope by record type."""

    crew_text: str | None = None
    signoffs: list[dict[str, Any]] = Field(default_factory=list)
    pin_count: int = 0
    open_constraints: int = 0
    scope_by_type: dict[str, int] = Field(default_factory=dict)


class ScopeRow(BaseModel):
    """One scope member of an IWP: a scope item (with its line fields) or a tag (no number)."""

    id: str
    number: str | None = None
    type: str
    commodity: str | None = None
    description: str | None = None
    qty: Decimal | None = None
    uom: str | None = None
    est_hours: Decimal | None = None


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _clamp(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def _base_params(scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "type": IWP,
        "voided": False,
        "draft": IWP_DRAFT,
        "cwp_type": CWP,
        "scope_rel": SCOPE_RELATION,
        "item_type": SCOPE_ITEM,
        "tag_type": TAG_TYPE,
    }


def _iwp_rows(
    conn: Connection, scope: str, where: str, params: dict[str, Any], limit: int
) -> list[RowMapping]:
    """The live IWPs of ``scope`` the viewer may read, one statement, by number. ``where`` is a
    condition written here, never user input. The hidden-record test is in the WHERE, before the
    ORDER BY and LIMIT, and the scope count and the CWP number reuse the same viewer filter."""
    visible_r, extra_r = not_hidden("r.id")
    visible_t, extra_t = not_hidden("t.id")
    visible_cw, extra_cw = not_hidden("cw.id")
    sql = (
        "SELECT r.id, r.key, r.title, COALESCE(s.state, :draft) AS state, i.discipline, "
        "i.planned_start, i.planned_finish, i.foreman, i.estimated_hours, i.crew_text, "
        "i.signoffs_json, cw.key AS cwp_key, "
        "(SELECT COUNT(*) FROM cur_links l JOIN cur_core_record t ON t.id = l.from_id "
        "WHERE l.to_id = r.id AND l.relation = :scope_rel AND l.source = 'rule' "
        "AND l.status = 'active' AND t.type IN (:item_type, :tag_type) AND t.voided = :voided "
        f"AND {visible_t}) AS scope_count "
        f"FROM {IWP_TABLE} i JOIN cur_core_record r ON r.id = i.id "
        "LEFT JOIN cur_workflow_state s ON s.record_id = r.id "
        f"LEFT JOIN cur_core_record cw ON cw.id = i.cwp_id AND cw.type = :cwp_type "
        f"AND {visible_cw} "
        f"WHERE r.scope = :scope AND r.type = :type AND r.voided = :voided AND {visible_r}"
        f"{where} ORDER BY r.key, r.id LIMIT :limit"
    )
    bound = {
        **_base_params(scope),
        **params,
        **extra_r,
        **extra_t,
        **extra_cw,
        "limit": limit,
    }
    return list(conn.execute(text(sql), bound).mappings())


def _iwp_row(raw: RowMapping) -> IwpRow:
    return IwpRow(
        id=str(raw["id"]),
        number=str(raw["key"]),
        title=str(raw["title"]),
        state=str(raw["state"]),
        discipline=_text(raw["discipline"]),
        planned_start=_text(raw["planned_start"]),
        planned_finish=_text(raw["planned_finish"]),
        foreman=_text(raw["foreman"]),
        estimated_hours=_dec(raw["estimated_hours"]),
        cwp_number=_text(raw["cwp_key"]),
        scope_count=int(raw["scope_count"]),
    )


def iwp_list(
    conn: Connection,
    scope: str,
    *,
    state: str | None = None,
    discipline: str | None = None,
    foreman: str | None = None,
    limit: int = 200,
) -> list[IwpRow]:
    """The IWPs of ``scope`` by number, void ones and hidden ones left out. ``state`` compares the
    workflow state (Draft is the default), ``discipline`` the discipline, ``foreman`` the foreman.
    ``limit`` is clamped to 1..500."""
    where = ""
    params: dict[str, Any] = {}
    if state is not None:
        where += " AND COALESCE(s.state, :draft) = :state"
        params["state"] = state
    if discipline is not None:
        where += " AND i.discipline = :discipline"
        params["discipline"] = discipline
    if foreman is not None:
        where += " AND i.foreman = :foreman"
        params["foreman"] = foreman
    return [_iwp_row(raw) for raw in _iwp_rows(conn, scope, where, params, _clamp(limit))]


def iwp_detail(conn: Connection, scope: str, number: str) -> IwpDetail | None:
    """One IWP by number with its crew, sign-offs, pin count, open constraints (Open and Assigned)
    and scope count by record type. ``None`` for a missing, hidden or voided IWP (the same answer
    for each)."""
    rows = _iwp_rows(conn, scope, " AND r.key = :number", {"number": number}, 1)
    if not rows:
        return None
    raw = rows[0]
    base = _iwp_row(raw)
    visible_p, extra_p = not_hidden("l.to_id")
    pins = conn.execute(
        text(
            "SELECT COUNT(*) FROM cur_links l WHERE l.from_id = :id AND l.status = 'active' "
            f"AND l.pin IS NOT NULL AND {visible_p}"
        ),
        {"id": base.id, **extra_p},
    ).scalar_one()
    visible_t, extra_t = not_hidden("t.id")
    by_type = conn.execute(
        text(
            "SELECT t.type, COUNT(*) FROM cur_links l JOIN cur_core_record t ON t.id = l.from_id "
            "WHERE l.to_id = :id AND l.relation = :scope_rel AND l.source = 'rule' "
            "AND l.status = 'active' AND t.type IN (:item_type, :tag_type) "
            f"AND t.voided = :voided AND {visible_t} GROUP BY t.type"
        ),
        {"id": base.id, **_base_params(scope), **extra_t},
    ).all()
    open_count = sum(
        count_constraints(conn, scope, subject_id=base.id, state=state) for state in OPEN_STATES
    )
    return IwpDetail(
        **base.model_dump(),
        crew_text=_text(raw["crew_text"]),
        signoffs=signoff_rows(raw["signoffs_json"]),
        pin_count=int(pins),
        open_constraints=open_count,
        scope_by_type={str(record_type): int(n) for record_type, n in by_type},
    )


def iwp_scope(
    conn: Connection, scope: str, number: str, *, limit: int = 500
) -> list[ScopeRow] | None:
    """The scope of one IWP by number: its scope items and tags, by type then key. ``None`` when
    the IWP is missing or hidden (not ``[]``). ``limit`` is clamped to 1..500."""
    rows = _iwp_rows(conn, scope, " AND r.key = :number", {"number": number}, 1)
    if not rows:
        return None
    visible_t, extra_t = not_hidden("t.id")
    members = conn.execute(
        text(
            "SELECT t.id, t.key, t.type, s.commodity, s.description_text, s.qty, s.uom, "
            "s.est_hours FROM cur_links l JOIN cur_core_record t ON t.id = l.from_id "
            f"LEFT JOIN {SCOPE_ITEM_TABLE} s ON s.id = t.id "
            "WHERE l.to_id = :id AND l.relation = :scope_rel AND l.source = 'rule' "
            "AND l.status = 'active' AND t.type IN (:item_type, :tag_type) "
            f"AND t.voided = :voided AND {visible_t} "
            "ORDER BY t.type, t.key, t.id LIMIT :limit"
        ),
        {
            "id": str(rows[0]["id"]),
            **_base_params(scope),
            **extra_t,
            "limit": _clamp(limit),
        },
    ).mappings()
    return [
        ScopeRow(
            id=str(m["id"]),
            number=None if str(m["type"]) == TAG_TYPE else _text(m["key"]),
            type=str(m["type"]),
            commodity=_text(m["commodity"]),
            description=_text(m["description_text"]),
            qty=_dec(m["qty"]),
            uom=_text(m["uom"]),
            est_hours=_dec(m["est_hours"]),
        )
        for m in members
    ]
