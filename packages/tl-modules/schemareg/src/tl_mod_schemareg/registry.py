"""Reads of the schema registry module: packages, adoptions, waivers.

Rows are frozen dataclasses joined with ``cur_core_record`` (the workflow state). Nothing here
writes, and nothing here checks a role: the entry points do (reads need ``document.read``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, text
from tl_schema.packages import version_tuple

from tl_mod_schemareg.names import (
    ADOPTION_TABLE,
    DRAFT,
    PACKAGE_TABLE,
    REQUESTED,
    WAIVER_TABLE,
)

_PACKAGE_COLUMNS = (
    "t.id, t.scope, t.package, t.semver, t.kind, t.project, t.package_title, t.content, "
    "t.content_sha256, t.changelog, t.drafted_by, t.base_ref, t.classification, "
    "t.classification_digest, t.worst_class, t.impact, t.impact_sha256, t.analysed_sha256, "
    "t.submitted_by, t.approved_by, t.approved_digest, t.published_at, t.deprecated_at, "
    f"t.retired_at, COALESCE(r.status, '{DRAFT}') AS state, r.created_at, r.updated_at"
)
_PACKAGE_SQL = (
    f"SELECT {_PACKAGE_COLUMNS} FROM {PACKAGE_TABLE} t JOIN cur_core_record r ON r.id = t.id"
)
_ADOPTION_SQL = (
    "SELECT t.id, t.scope, t.project, t.package, t.semver, t.previous_semver, t.worst_class, "
    f"t.impact_sha256, t.adopted_by, t.adopted_at FROM {ADOPTION_TABLE} t"
)
_WAIVER_SQL = (
    "SELECT t.id, t.scope, t.project, t.path, t.number, t.reason, t.expires, t.requested_by, "
    "t.approver, t.approved_at, t.revoked_by, t.revoked_at, "
    f"COALESCE(r.status, '{REQUESTED}') AS state, r.created_at "
    f"FROM {WAIVER_TABLE} t JOIN cur_core_record r ON r.id = t.id"
)

#: A page is never longer than this, whatever the caller asks.
MAX_PAGE = 1000


@dataclass(frozen=True)
class PackageRow:
    id: str
    scope: str
    package: str
    version: str
    kind: str
    project: str | None
    package_title: str | None
    content: str
    content_sha256: str
    changelog: str | None
    drafted_by: str
    base_ref: str | None
    classification: dict[str, Any] | None
    classification_digest: str | None
    worst_class: str | None
    impact: dict[str, Any] | None
    impact_sha256: str | None
    analysed_sha256: str | None
    submitted_by: str | None
    approved_by: str | None
    approved_digest: str | None
    published_at: str | None
    deprecated_at: str | None
    retired_at: str | None
    state: str
    created_at: str
    updated_at: str

    @property
    def key(self) -> str:
        return f"{self.package}@{self.version}"


@dataclass(frozen=True)
class AdoptionRow:
    id: str
    scope: str
    project: str
    package: str
    version: str
    previous_version: str | None
    worst_class: str | None
    impact_sha256: str | None
    adopted_by: str
    adopted_at: str

    @property
    def key(self) -> str:
        return f"{self.project}/{self.package}"


@dataclass(frozen=True)
class WaiverRow:
    id: str
    scope: str
    project: str
    path: str
    number: int
    reason: str
    expires: str
    requested_by: str
    approver: str | None
    approved_at: str | None
    revoked_by: str | None
    revoked_at: str | None
    state: str
    created_at: str

    @property
    def key(self) -> str:
        return f"{self.project}/{self.path}@{self.number}"


def _json(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, dict) else None


def _package(row: Any) -> PackageRow:
    m = row._mapping
    return PackageRow(
        id=m["id"],
        scope=m["scope"],
        package=m["package"],
        version=m["semver"],
        kind=m["kind"],
        project=m["project"],
        package_title=m["package_title"],
        content=m["content"],
        content_sha256=m["content_sha256"],
        changelog=m["changelog"],
        drafted_by=m["drafted_by"],
        base_ref=m["base_ref"],
        classification=_json(m["classification"]),
        classification_digest=m["classification_digest"],
        worst_class=m["worst_class"],
        impact=_json(m["impact"]),
        impact_sha256=m["impact_sha256"],
        analysed_sha256=m["analysed_sha256"],
        submitted_by=m["submitted_by"],
        approved_by=m["approved_by"],
        approved_digest=m["approved_digest"],
        published_at=m["published_at"],
        deprecated_at=m["deprecated_at"],
        retired_at=m["retired_at"],
        state=m["state"],
        created_at=str(m["created_at"]),
        updated_at=str(m["updated_at"]),
    )


def get_package(conn: Connection, package_id: str) -> PackageRow | None:
    row = conn.execute(text(f"{_PACKAGE_SQL} WHERE t.id = :id"), {"id": package_id}).first()
    return _package(row) if row is not None else None


def find_package(conn: Connection, name: str, version: str) -> PackageRow | None:
    row = conn.execute(
        text(f"{_PACKAGE_SQL} WHERE t.package = :p AND t.semver = :v"), {"p": name, "v": version}
    ).first()
    return _package(row) if row is not None else None


def list_packages(
    conn: Connection,
    *,
    scope: str | None = None,
    state: str | None = None,
    package: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[PackageRow]:
    """Packages by name and version (highest first), optionally of one scope, state or name."""
    where, params = _filters(
        ("t.scope", scope), ("COALESCE(r.status, 'Draft')", state), ("t.package", package)
    )
    rows = conn.execute(text(f"{_PACKAGE_SQL}{where}"), params).all()
    found = [_package(row) for row in rows]
    found.sort(key=lambda p: (p.package, version_tuple(p.version)), reverse=True)
    low = max(offset, 0)
    return found[low : low + min(max(limit, 1), MAX_PAGE)]


def versions_in_force(conn: Connection, name: str) -> list[PackageRow]:
    """Published and deprecated versions of ``name``, ascending."""
    rows = conn.execute(
        text(f"{_PACKAGE_SQL} WHERE t.package = :p AND r.status IN ('Published', 'Deprecated')"),
        {"p": name},
    ).all()
    return sorted((_package(r) for r in rows), key=lambda p: version_tuple(p.version))


def _filters(*pairs: tuple[str, str | None]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for index, (column, value) in enumerate(pairs):
        if value is not None:
            clauses.append(f"{column} = :f{index}")
            params[f"f{index}"] = value
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _adoption(row: Any) -> AdoptionRow:
    m = row._mapping
    return AdoptionRow(
        id=m["id"],
        scope=m["scope"],
        project=m["project"],
        package=m["package"],
        version=m["semver"],
        previous_version=m["previous_semver"],
        worst_class=m["worst_class"],
        impact_sha256=m["impact_sha256"],
        adopted_by=m["adopted_by"],
        adopted_at=m["adopted_at"],
    )


def list_adoptions(
    conn: Connection, *, project: str | None = None, package: str | None = None
) -> list[AdoptionRow]:
    where, params = _filters(("t.project", project), ("t.package", package))
    rows = conn.execute(text(f"{_ADOPTION_SQL}{where} ORDER BY t.project, t.package"), params)
    return [_adoption(r) for r in rows]


def get_adoption(conn: Connection, project: str, package: str) -> AdoptionRow | None:
    found = list_adoptions(conn, project=project, package=package)
    return found[0] if found else None


def _waiver(row: Any) -> WaiverRow:
    m = row._mapping
    return WaiverRow(
        id=m["id"],
        scope=m["scope"],
        project=m["project"],
        path=m["path"],
        number=int(m["number"]),
        reason=m["reason"],
        expires=m["expires"],
        requested_by=m["requested_by"],
        approver=m["approver"],
        approved_at=m["approved_at"],
        revoked_by=m["revoked_by"],
        revoked_at=m["revoked_at"],
        state=m["state"],
        created_at=str(m["created_at"]),
    )


def list_waivers(
    conn: Connection,
    *,
    project: str | None = None,
    state: str | None = None,
    path: str | None = None,
) -> list[WaiverRow]:
    where, params = _filters(
        ("t.project", project), ("COALESCE(r.status, 'Requested')", state), ("t.path", path)
    )
    rows = conn.execute(text(f"{_WAIVER_SQL}{where} ORDER BY t.project, t.path, t.number"), params)
    return [_waiver(r) for r in rows]


def get_waiver(conn: Connection, waiver_id: str) -> WaiverRow | None:
    row = conn.execute(text(f"{_WAIVER_SQL} WHERE t.id = :id"), {"id": waiver_id}).first()
    return _waiver(row) if row is not None else None


def find_waiver(conn: Connection, ref: str) -> WaiverRow | None:
    """A waiver by record id or by key (``P123/psets.valve_data.size_in@1``)."""
    found = get_waiver(conn, ref)
    if found is not None or "@" not in ref or "/" not in ref:
        return found
    head, _, number = ref.rpartition("@")
    project, _, path = head.partition("/")
    if not number.isascii() or not number.isdigit():
        return None
    for row in list_waivers(conn, project=project, path=path):
        if row.number == int(number[:9]):
            return row
    return None
