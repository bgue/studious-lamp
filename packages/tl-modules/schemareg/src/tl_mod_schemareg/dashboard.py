"""The conformance dashboard of a project (brief 27.3 and 27.5): how its records stand.

One read: per record type the stored conformance counts and how many records were checked against
an older schema than the one in force (stale), the approved waivers with the days they have left,
and the company packages the project is behind on. Nothing is evaluated here: the ``conformance``
and ``effective_schema_hash`` of each record are read as stored. The counts are taken as the
current viewer (ADR-0016): a record the viewer may not read is not counted and its type does not
show for them. Nothing writes, and nothing checks a role.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, text
from tl_core import confidentiality
from tl_core.util import utcnow

from tl_mod_schemareg import analysis, views
from tl_mod_schemareg.names import WAIVER_APPROVED_STATE


class TypeConformance(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: str
    total: int
    ok: int
    warning: int
    nonconformant: int
    waived: int  # stored status ``waived``: a waiver cleared the only issues
    stale: int  # effective_schema_hash is not the hash in force (NULL counts as stale)


class WaiverLeft(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    path: str
    expires: str
    days_left: int  # expires - today, never negative; expired waivers are not listed here


class ConformanceView(BaseModel):
    model_config = ConfigDict(frozen=True)

    project: str
    schema_hash: str  # EffectiveSchema.hash of scope project:<id>
    total: int
    by_type: list[TypeConformance]  # sorted by type
    waivers: list[WaiverLeft]  # state Approved and not expired, by expires then key
    expired_waivers: int  # approved and past their day
    drift: list[views.DriftView]  # only those with behind=True, by package


def _today() -> date:
    return utcnow().date()


def _counts(conn: Connection, scope: str, schema_hash: str) -> list[TypeConformance]:
    clause, params = confidentiality.not_hidden("id")
    where = f"FROM cur_core_record WHERE NOT voided AND scope = :scope AND {clause}"
    bound = {**params, "scope": scope}
    by_status: dict[str, dict[str, int]] = {}
    for row in conn.execute(
        text(f"SELECT type, conformance, COUNT(*) AS n {where} GROUP BY type, conformance"), bound
    ):
        by_status.setdefault(row.type, {})[row.conformance] = int(row.n)
    stale = {
        row.type: int(row.n)
        for row in conn.execute(
            text(
                f"SELECT type, COUNT(*) AS n {where} "
                "AND (effective_schema_hash IS NULL OR effective_schema_hash <> :hash) "
                "GROUP BY type"
            ),
            {**bound, "hash": schema_hash},
        )
    }
    return [
        TypeConformance(
            type=name,
            total=sum(counts.values()),
            ok=counts.get("ok", 0),
            warning=counts.get("warning", 0),
            nonconformant=counts.get("nonconformant", 0),
            waived=counts.get("waived", 0),
            stale=stale.get(name, 0),
        )
        for name, counts in sorted(by_status.items())
    ]


def _waivers(conn: Connection, project: str) -> tuple[list[WaiverLeft], int]:
    today = _today()
    live: list[WaiverLeft] = []
    expired = 0
    for waiver in views.waiver_views(conn, project, WAIVER_APPROVED_STATE):
        left = (date.fromisoformat(waiver.expires) - today).days
        if left < 0:
            expired += 1
            continue
        live.append(
            WaiverLeft(key=waiver.key, path=waiver.path, expires=waiver.expires, days_left=left)
        )
    return sorted(live, key=lambda w: (w.expires, w.key)), expired


def conformance_dashboard(conn: Connection, project: str) -> ConformanceView:
    """How ``project``'s records stand against the schema in force, as the current viewer."""
    scope = f"project:{project}"
    schema_hash = analysis.provider().effective(scope).hash
    by_type = _counts(conn, scope, schema_hash)
    waivers, expired = _waivers(conn, project)
    return ConformanceView(
        project=project,
        schema_hash=schema_hash,
        total=sum(t.total for t in by_type),
        by_type=by_type,
        waivers=waivers,
        expired_waivers=expired,
        drift=[d for d in views.drift_views(project) if d.behind],
    )


__all__ = [
    "ConformanceView",
    "TypeConformance",
    "WaiverLeft",
    "conformance_dashboard",
]
