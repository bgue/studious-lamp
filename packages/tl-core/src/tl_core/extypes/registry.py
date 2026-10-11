"""The type registry: scan, sync, list, deprecate (brief 31.1; FANOUT D8, D9).

``sync`` is the one write path. For each package directory under a root it works out the package's
identity (type ref and content hash) and compares it with the registration row:

======================================  ===================================================
registry state                          what ``sync`` does
======================================  ===================================================
no row                                  validate; ``Registered`` or ``Quarantined``
row quarantined, same hash              nothing (already reported)
row quarantined, new hash               validate again; ``Registered`` or ``Quarantined``
row active or deprecated, same hash     nothing
row active or deprecated, new hash      ``Quarantined`` with a ``conflict`` issue; the
                                        registration stays as it was (versions are immutable)
row active or deprecated, ``conflict``  nothing (the same refused change is already reported)
======================================  ===================================================

So running it twice appends nothing the second time, and editing a registered version's files can
never take the type away. A change ships as a new version directory.

A package is found by a ``type.yaml`` or ``type.lock`` file; hidden and linked directories are not
entered. Reading is by ``list_types``, ``get_type`` and ``list_quarantined``; they take a
connection and so work inside any unit of work.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import Connection, text

from tl_core.extypes import settings_link
from tl_core.extypes.compile import TYPE_FILE
from tl_core.extypes.errors import TypeNotActiveError, UnknownTypeError
from tl_core.extypes.loader import default_loader
from tl_core.extypes.lock import LOCK_NAME
from tl_core.extypes.names import (
    REGISTRY_SCOPE,
    STREAM_TYPE,
    LayoutError,
    parse_type_ref,
    pset_name,
    stream_id,
    version_key,
)
from tl_core.extypes.types import (
    TYPE_DEPRECATED,
    TYPE_QUARANTINED,
    TYPE_REGISTERED,
    StorageMode,
    TypeIssue,
    TypeRegistration,
    TypeStatus,
    TypeView,
)
from tl_core.extypes.validate import Described, describe_package, validate_package
from tl_core.ledger import ConcurrencyError, NewEvent
from tl_core.schema_provider import SchemaProvider, get_provider
from tl_core.services.errors import ServiceError
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

MAX_DEPTH = 6

log = logging.getLogger("tl_core.extypes")
log.addHandler(logging.NullHandler())

_COLUMNS = (
    "type_ref, type_name, namespace, name, version, pset, location_uri, content_hash, owner, "
    "status, storage_mode, index_fields_json, schema_hash, report_json, conflict_hash, reason, "
    "first_seq, last_seq, version_n"
)
_SELECT = f"SELECT {_COLUMNS} FROM cur_core_type_registration"


class UowFactory(Protocol):
    """``factory(readonly=...)`` yields an entered unit of work (every server-side factory)."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[UnitOfWork]: ...


class QuarantineEntry(BaseModel):
    """A package the registry refused: a quarantined version, or a change under a registered one."""

    type_ref: str
    status: TypeStatus
    location_uri: str
    content_hash: str  # of the files as found when quarantined
    registered_hash: str | None  # the active version's hash, when the change was a conflict
    report: list[TypeIssue]
    seq: int


def scan(root: Path) -> list[Path]:
    """Package directories below ``root``, sorted: those holding ``type.yaml`` or ``type.lock``.

    Does not descend into a package, into hidden directories, or through symbolic links, and stops
    ``MAX_DEPTH`` levels down. A missing root gives an empty list.
    """
    if not root.is_dir():
        return []
    found: list[Path] = []
    base = root.resolve()
    for directory, dirnames, filenames in os.walk(base, followlinks=False):
        here = Path(directory)
        depth = len(here.relative_to(base).parts)
        if TYPE_FILE in filenames or LOCK_NAME in filenames:
            found.append(here)
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not name.startswith(".") and not (here / name).is_symlink() and depth < MAX_DEPTH
        )
    return sorted(found)


# --- reading ----------------------------------------------------------------------------------


def _view(row: Any) -> TypeView:
    index_fields: list[str] = json.loads(row.index_fields_json) if row.index_fields_json else []
    mode: StorageMode = row.storage_mode or "managed"
    registration = TypeRegistration(
        namespace=row.namespace,
        name=row.name,
        version=row.version,
        type_ref=row.type_ref,
        location_uri=row.location_uri,
        content_hash=row.content_hash,
        owner=row.owner or "",
        status=row.status,
        storage_mode=mode,
        index_fields=index_fields,
        schema_hash=row.schema_hash or "",
    )
    return TypeView(registration=registration, seq=int(row.last_seq))


def list_types(conn: Connection, *, status: TypeStatus | None = None) -> list[TypeView]:
    """Registrations ordered by type ref, optionally of one status.

    A quarantined row has no owner, storage mode, index fields or schema hash; they read as empty
    (``""``, ``"managed"``, ``[]``, ``""``). ``list_quarantined`` gives its report.
    """
    if status is None:
        rows = conn.execute(text(f"{_SELECT} ORDER BY type_ref")).all()
    else:
        rows = conn.execute(
            text(f"{_SELECT} WHERE status = :status ORDER BY type_ref"), {"status": status}
        ).all()
    return [_view(row) for row in rows]


def get_type(conn: Connection, type_ref: str) -> TypeView | None:
    row = conn.execute(
        text(f"{_SELECT} WHERE type_ref = :type_ref"), {"type_ref": type_ref}
    ).first()
    return None if row is None else _view(row)


def versions_of(conn: Connection, type_name: str) -> list[TypeView]:
    """Every registered version of ``type_name``, oldest first."""
    rows = conn.execute(
        text(f"{_SELECT} WHERE type_name = :type_name"), {"type_name": type_name}
    ).all()
    return sorted(
        (_view(row) for row in rows),
        key=lambda v: version_key(v.registration.version),
    )


def current_type(conn: Connection, type_name: str) -> TypeView | None:
    """The version new instances use: the highest ``active`` or ``deprecated`` version.

    A deprecated newest version means "do not create": the caller checks ``status``.
    """
    usable = [
        v for v in versions_of(conn, type_name) if v.registration.status in ("active", "deprecated")
    ]
    return usable[-1] if usable else None


def usable_types(conn: Connection) -> list[TypeView]:
    """``current_type`` of every type name that has one, sorted by type name."""
    names = sorted(
        {
            str(row.type_name)
            for row in conn.execute(
                text(
                    "SELECT DISTINCT type_name FROM cur_core_type_registration "
                    "WHERE status IN ('active', 'deprecated')"
                )
            )
        }
    )
    found: list[TypeView] = []
    for name in names:
        view = current_type(conn, name)
        if view is not None:
            found.append(view)
    return found


def list_quarantined(conn: Connection) -> list[QuarantineEntry]:
    """Quarantined versions and conflicts refused under registered versions, by type ref."""
    rows = conn.execute(
        text(
            f"{_SELECT} WHERE status = 'quarantined' OR conflict_hash IS NOT NULL ORDER BY type_ref"
        )
    ).all()
    entries: list[QuarantineEntry] = []
    for row in rows:
        conflict = row.conflict_hash is not None
        raw: list[dict[str, Any]] = json.loads(row.report_json) if row.report_json else []
        entries.append(
            QuarantineEntry(
                type_ref=row.type_ref,
                status=row.status,
                location_uri=row.location_uri,
                content_hash=row.conflict_hash if conflict else row.content_hash,
                registered_hash=row.content_hash if conflict else None,
                report=[TypeIssue.model_validate(item) for item in raw],
                seq=int(row.last_seq),
            )
        )
    return entries


# --- writing ----------------------------------------------------------------------------------

_ROW = text(
    "SELECT status, content_hash, conflict_hash, version_n, pset, type_name "
    "FROM cur_core_type_registration WHERE type_ref = :type_ref"
)
_PSET_OWNER = text(
    "SELECT DISTINCT type_name FROM cur_core_type_registration "
    "WHERE pset = :pset AND type_name <> :type_name AND status IN ('active', 'deprecated')"
)

_changes = 0


def changes() -> int:
    """A counter that rises whenever this process appends a registration event.

    The schema provider compares it so a registration made in this process shows at once, without
    waiting for its polling interval.
    """
    return _changes


def _bump() -> None:
    global _changes
    _changes += 1


def _already_known(row: Any, content_hash: str) -> bool:
    """Whether the registry already holds (or has already refused) exactly these files."""
    if row is None:
        return False
    if content_hash == row.content_hash:
        # A version whose earlier conflict is gone is re-registered to clear the note (a deprecated
        # one stays deprecated: the projector keeps its status).
        return not (row.conflict_hash is not None and row.status in ("active", "deprecated"))
    return row.conflict_hash == content_hash and row.status != "quarantined"


def _decide(
    uow: UnitOfWork,
    described: Described,
    registration: TypeRegistration | None,
    issues: Sequence[TypeIssue],
    *,
    actor: str,
) -> tuple[str, dict[str, Any]] | None:
    """The event to append for a package, or ``None`` when the registry already knows it."""
    row = uow.conn().execute(_ROW, {"type_ref": described.type_ref}).first()
    if _already_known(row, described.content_hash):
        return None
    status = None if row is None else str(row.status)
    problems = list(issues)
    if registration is not None and described.coords is not None:
        clash = (
            uow.conn()
            .execute(
                _PSET_OWNER,
                {
                    "pset": pset_name(described.coords.namespace, described.coords.name),
                    "type_name": described.coords.type_name,
                },
            )
            .all()
        )
        for other in clash:
            detail = f"pset name is already used by {other.type_name}"
            problems.append(TypeIssue(kind="conflict", path=TYPE_FILE, detail=detail))
    if (
        row is not None
        and status in ("active", "deprecated")
        and row.content_hash != described.content_hash
    ):
        detail = (
            f"{described.type_ref} is registered with content hash {str(row.content_hash)[:12]}; "
            f"the files now hash to {described.content_hash[:12]}. "
            "A registered version is immutable: publish the change as a new version."
        )
        problems.insert(0, TypeIssue(kind="conflict", path=None, detail=detail))
    if problems or registration is None:
        return TYPE_QUARANTINED, {
            "type_ref": described.type_ref,
            "location_uri": described.location_uri,
            "content_hash": described.content_hash,
            "report": [p.model_dump(mode="json") for p in problems],
        }
    registered = registration.model_copy(update={"owner": actor})
    return TYPE_REGISTERED, registered.model_dump(mode="json")


def sync(
    uow_factory: UowFactory,
    root: Path,
    *,
    actor: str,
    source: str,
    provider: SchemaProvider | None = None,
) -> list[TypeView]:
    """Register or quarantine every package below ``root``; idempotent (see the module docstring).

    Returns the registry view of each package that produced an event in this call, in scan order.
    Each package is its own unit of work, so one failing package never rolls back the others.
    ``provider`` is the schema the packages are checked against (default: the process provider).
    """
    schema_provider = provider if provider is not None else get_provider()
    changed: list[TypeView] = []
    # the keys the registered types define, so a new package that repeats one is quarantined
    settings_link.refresh_from_ledger(uow_factory, default_loader().verify)
    for package in scan(root):
        try:
            described = describe_package(package, root)
        except Exception as exc:  # a file vanished while it was read: skip, the next run sees it
            log.warning("cannot read package %s: %s", package, exc)
            continue
        view = _register_package(
            uow_factory, package, root, described, schema_provider, actor=actor, source=source
        )
        if view is not None:
            changed.append(view)
            # a type registered in this call defines its keys for the next package of the scan
            settings_link.refresh_from_ledger(uow_factory, default_loader().verify)
    return changed


def _register_package(
    uow_factory: UowFactory,
    package: Path,
    root: Path,
    described: Described,
    provider: SchemaProvider,
    *,
    actor: str,
    source: str,
) -> TypeView | None:
    """One package: skip it, or append its event. A lost race is retried once.

    Two syncs can decide on the same package together; the loser's append fails on the stream
    version. It then reads the row again, which usually shows the winner's event, and skips.
    """
    validated: tuple[TypeRegistration | None, list[TypeIssue]] | None = None
    for _ in range(2):
        with uow_factory(readonly=True) as uow:
            row = uow.conn().execute(_ROW, {"type_ref": described.type_ref}).first()
        if _already_known(row, described.content_hash):
            return None
        if validated is None:
            validated = validate_package(package, provider=provider, root=root, described=described)
        registration, issues = validated
        if registration is not None and described.coords is not None:
            clashes = settings_link.clash_issues(package, described.coords)
            if clashes:
                registration, issues = None, clashes
        try:
            with uow_factory(readonly=False) as uow:
                decision = _decide(uow, described, registration, issues, actor=actor)
                if decision is None:
                    return None
                event_type, payload = decision
                row = uow.conn().execute(_ROW, {"type_ref": described.type_ref}).first()
                uow.append(
                    stream_id=stream_id(described.type_ref),
                    stream_type=STREAM_TYPE,
                    scope=REGISTRY_SCOPE,
                    expected_version=0 if row is None else int(row.version_n),
                    events=[NewEvent(event_type=event_type, payload=payload)],
                    actor=actor,
                    source=source,
                    correlation_id=new_ulid(),
                )
                view = get_type(uow.conn(), described.type_ref)
        except ConcurrencyError:
            continue
        _bump()
        return view
    log.warning("%s: another sync kept winning; left for the next run", described.type_ref)
    return None


def deprecate_type(
    uow: UnitOfWork, *, type_ref: str, reason: str, actor: str, source: str
) -> TypeView:
    """Retire a version: instances stay readable, no new ones. The reason must not be blank."""
    try:
        parse_type_ref(type_ref)
    except LayoutError as exc:
        raise UnknownTypeError(str(exc)) from None
    if not reason.strip():
        raise ServiceError("a reason is required to deprecate a type")
    row = uow.conn().execute(_ROW, {"type_ref": type_ref}).first()
    if row is None:
        raise UnknownTypeError(f"no registration {type_ref!r}")
    if row.status != "active":
        raise TypeNotActiveError(
            f"{type_ref} is {row.status}; only an active version is deprecated"
        )
    uow.append(
        stream_id=stream_id(type_ref),
        stream_type=STREAM_TYPE,
        scope=REGISTRY_SCOPE,
        expected_version=int(row.version_n),
        events=[
            NewEvent(
                event_type=TYPE_DEPRECATED,
                payload={"type_ref": type_ref, "reason": reason.strip()},
            )
        ],
        actor=actor,
        source=source,
        correlation_id=new_ulid(),
    )
    view = get_type(uow.conn(), type_ref)
    assert view is not None
    return view


def deprecate(
    uow_factory: UowFactory, *, type_ref: str, reason: str, actor: str, source: str
) -> TypeView:
    """``deprecate_type`` in its own unit of work; the schema provider hears of it after the commit.

    ``deprecate_type`` itself cannot tell the provider, because the caller still holds the
    transaction: a provider that read the registry in between would cache the old state.
    """
    with uow_factory(readonly=False) as uow:
        view = deprecate_type(uow, type_ref=type_ref, reason=reason, actor=actor, source=source)
    _bump()
    return view
