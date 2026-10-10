"""Rebuild a database from a ledger archive alone (brief 24.4, "rebuild-from-archive").

Verify the archive, create the schema in an empty database, insert the archived events verbatim
through the dialect's ``restore_events``, add the promoted pset columns the schema packages in
force ask for, rebuild the projections, then verify again, this time against the new database.
Works for a SQLite file and for a Postgres URL; everything dialect specific stays in
``tl_adapters.<dialect>.admin``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import Engine, text
from tl_core.archive import (
    ArchiveStore,
    RestoreError,
    VerifyIssue,
    iter_segment_events,
    verify_archive,
)
from tl_core.archive.segments import list_segment_names
from tl_core.projection.promoted import ensure_promoted_columns
from tl_core.projection.types import ProjectorRegistry
from tl_core.schema_provider import SchemaProvider, get_provider

from tl_adapters import postgres, sqlite
from tl_adapters.db import (
    DbTarget,
    create_schema,
    is_postgres,
    make_engine,
    read_tx,
    rebuild_projections,
    write_tx,
)


@dataclass(frozen=True)
class RestoreResult:
    """What a restore did."""

    events: int
    segments: int
    last_seq: int
    verify_seconds: float
    insert_seconds: float
    rebuild_seconds: float
    total_seconds: float


def _fail(issues: list[VerifyIssue], stage: str) -> RestoreError:
    first = issues[0]
    return RestoreError(
        f"{stage}: {first.kind} in segment {first.segment} at seq {first.seq}: {first.detail}",
        first,
    )


def _ensure_promoted(engine: Engine, provider: SchemaProvider) -> None:
    with write_tx(engine) as conn:
        scopes = [str(row[0]) for row in conn.execute(text("SELECT DISTINCT scope FROM events"))]
        for scope in sorted(scopes):
            try:
                schema = provider.effective(scope)
            except Exception as error:
                raise RestoreError(
                    f"cannot load the effective schema of scope {scope!r} to add promoted "
                    f"columns: {error}"
                ) from error
            ensure_promoted_columns(conn, schema)


def restore_from_archive(
    store: ArchiveStore,
    target: DbTarget,
    *,
    public_key: bytes,
    registry: ProjectorRegistry | None = None,
    schema_provider: SchemaProvider | None = None,
) -> RestoreResult:
    """Restore ``target`` (an empty or new SQLite file, or a Postgres URL) from ``store``.

    Refuses an archive that does not verify and a database whose ``events`` table is not empty.
    Raises ``RestoreError`` with the first divergence when verification fails, before or after.

    Promoted pset columns of ``cur_core_record`` are not events: they exist because a schema package
    marks a property ``materialize: true``. They are added from the effective schema of every scope
    in the archive, taken from ``schema_provider`` (default: the process-wide one), so the schema
    packages in force at restore time decide them. Without them a rebuild would silently drop the
    promoted values.
    """
    started = time.perf_counter()
    segments = len(list_segment_names(store))
    if segments == 0:
        raise RestoreError("the archive holds no segments")
    issues = verify_archive(store, public_key=public_key)
    if issues:
        raise _fail(issues, "the archive does not verify")
    verified = time.perf_counter()

    create_schema(target, registry=registry)
    engine = make_engine(target)
    try:
        insert = (
            postgres.admin.restore_events if is_postgres(target) else sqlite.admin.restore_events
        )
        with write_tx(engine) as conn:
            count = insert(conn, iter_segment_events(store))
        inserted = time.perf_counter()

        _ensure_promoted(engine, schema_provider if schema_provider else get_provider())

        rebuild_projections(target, registry=registry)
        rebuilt = time.perf_counter()

        with read_tx(engine) as conn:
            issues = verify_archive(store, public_key=public_key, conn=conn)
        if issues:
            raise _fail(issues, "the restored database does not match the archive")
    finally:
        engine.dispose()
    return RestoreResult(
        events=count,
        segments=segments,
        last_seq=count,  # seq is gap-free from 1, so the count is the last seq
        verify_seconds=verified - started,
        insert_seconds=inserted - verified,
        rebuild_seconds=rebuilt - inserted,
        total_seconds=time.perf_counter() - started,
    )
