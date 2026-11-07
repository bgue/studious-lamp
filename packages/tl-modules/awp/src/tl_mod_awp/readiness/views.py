"""The last readiness evaluation of an IWP, read from the projected rows (never from a check)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Connection, text
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
