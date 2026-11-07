"""The last readiness evaluation of an IWP, read from the projected rows (never from a check)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Connection, bindparam, text
from tl_core import confidentiality
from tl_core.readiness.types import MAX_CHECKS, CheckResult, RecordRef

from tl_mod_awp.names import IWP, READINESS_CHECK_TABLE, READINESS_TABLE

_KEY_SQL = text(
    "SELECT id FROM cur_core_record WHERE scope = :scope AND type = :type AND key = :key"
)
_HEAD_SQL = text(
    "SELECT iwp_id, evaluated_at, today, ready, facts_hash "
    f"FROM {READINESS_TABLE} WHERE iwp_id = :id"
)
_CHECKS_SQL = text(
    "SELECT name, version, state, detail, count_ok, count_total, resolve_via_json "
    f"FROM {READINESS_CHECK_TABLE} WHERE iwp_id = :id ORDER BY name"
)


class ReadinessView(BaseModel):
    """One evaluation: what ``IWP.ReadinessEvaluated`` carried."""

    iwp_id: str
    evaluated_at: str
    today: str
    ready: bool
    facts_hash: str
    checks: list[CheckResult] = Field(default_factory=list[CheckResult], max_length=MAX_CHECKS)


def check_from_json(entry: dict[str, Any]) -> CheckResult:
    return CheckResult.model_validate(entry)


def readiness_of(conn: Connection, iwp_id: str) -> ReadinessView | None:
    """The projected evaluation of the IWP with this id; ``None`` when it was never evaluated."""
    head = conn.execute(_HEAD_SQL, {"id": iwp_id}).first()
    if head is None:
        return None
    checks: list[CheckResult] = []
    for row in conn.execute(_CHECKS_SQL, {"id": iwp_id}):
        raw = row.resolve_via_json
        refs = json.loads(raw) if isinstance(raw, str) else (raw or [])
        checks.append(
            CheckResult(
                name=row.name,
                version=row.version,
                state=row.state,
                detail=row.detail or "",
                resolve_via=[RecordRef.model_validate(r) for r in refs],
                count_ok=row.count_ok,
                count_total=row.count_total,
            )
        )
    return ReadinessView(
        iwp_id=str(head.iwp_id),
        evaluated_at=str(head.evaluated_at),
        today=str(head.today),
        ready=bool(head.ready),
        facts_hash=str(head.facts_hash),
        checks=checks,
    )


def readiness(conn: Connection, scope: str, iwp_key: str) -> ReadinessView | None:
    """The last evaluation of the IWP with key ``iwp_key`` in ``scope``.

    ``None`` when the IWP does not exist, is hidden from the viewer, or was never evaluated (the
    three answer alike).
    """
    found = conn.execute(
        _KEY_SQL, {"scope": scope, "type": IWP, "key": iwp_key}
    ).scalar_one_or_none()
    if found is None or confidentiality.is_hidden(conn, str(found)):
        return None
    return readiness_of(conn, str(found))


def visible_readiness(
    conn: Connection, scope: str, key: str, viewer: confidentiality.Viewer | None = None
) -> ReadinessView | None:
    """``readiness`` for a reader: each ``resolve_via`` drops the records the viewer cannot read
    and shows each kept record by its display key (never the id or key of a hidden one).

    State, ``count_ok`` and ``count_total`` stay as the engine evaluated them (counts, no
    identities). ``None`` as for ``readiness``."""
    view = readiness(conn, scope, key)
    if view is None:
        return None
    ids = sorted({r.record_id for c in view.checks for r in c.resolve_via})
    if not ids:
        return view
    hidden = confidentiality.hidden_among(conn, ids, viewer)
    keys: dict[str, str] = {}
    statement = text("SELECT id, key FROM cur_core_record WHERE id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    for start in range(0, len(ids), 500):
        for row in conn.execute(statement, {"ids": ids[start : start + 500]}):
            keys[str(row.id)] = str(row.key)
    for check in view.checks:
        check.resolve_via = [
            RecordRef(record_id=r.record_id, record_type=r.record_type, key=keys[r.record_id])
            for r in check.resolve_via
            if r.record_id not in hidden and r.record_id in keys
        ]
    return view
