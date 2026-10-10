"""Rebuild a database from a ledger archive alone (brief 24.4, "rebuild-from-archive").

Verify the archive, check that the schema packages in force can be loaded for every scope in it,
create the schema in an empty database, then in ONE transaction insert the archived events
verbatim through the dialect's ``restore_events``, add the promoted pset columns and replay the
events into the projections. If any of that fails the transaction rolls back, the database is
empty again, and the restore can simply be run again. Last, verify the new database against the
archive. Works for a SQLite file and for a Postgres URL; everything dialect specific stays in
``tl_adapters.<dialect>.admin``.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import cast

from sqlalchemy import Connection, Engine, text
from tl_core.archive import (
    ArchiveStore,
    RestoreError,
    VerifyIssue,
    archive_scopes,
    iter_segment_events,
    read_events,
    verify_archive,
)
from tl_core.archive.segments import list_segment_names
from tl_core.ledger import Event, Ledger
from tl_core.projection.defaults import default_registry
from tl_core.projection.promoted import ensure_promoted_columns
from tl_core.projection.types import ProjectorRegistry
from tl_core.schema_provider import SchemaProvider, get_provider
from tl_core.webhooks.dispatch import CURSOR_NAME
from tl_schema.effective import EffectiveSchema

from tl_adapters import postgres, sqlite
from tl_adapters._unit import replay
from tl_adapters.db import DbTarget, create_schema, is_postgres, make_engine, write_tx


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
    schema_hashes: dict[str, str] = field(default_factory=dict[str, str])
    """Scope to the hash of the effective schema in force at restore time."""
    ledger_schema_hashes: dict[str, str] = field(default_factory=dict[str, str])
    """Scope to the last ``effective_schema_hash`` an archived event recorded."""
    warnings: tuple[str, ...] = ()
    """Differences between the two that may change the promoted columns."""


def _fail(issues: list[VerifyIssue], stage: str) -> RestoreError:
    first = issues[0]
    return RestoreError(
        f"{stage}: {first.kind} in segment {first.segment} at seq {first.seq}: {first.detail}",
        first,
    )


class _ReplayLedger:
    """Just enough of a ``Ledger`` for ``replay``: pages of events read through ``conn``.

    The restore transaction has not committed, so another connection could not see its events.
    """

    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def read_after(self, seq: int, *, scope: str | None = None, limit: int = 1000) -> list[Event]:
        return read_events(self._conn, seq + 1, seq + limit)


def _schemas(store: ArchiveStore, provider: SchemaProvider) -> dict[str, EffectiveSchema]:
    """The effective schema of every scope in the archive, loaded before anything is written."""
    schemas: dict[str, EffectiveSchema] = {}
    for scope in archive_scopes(store):
        try:
            schemas[scope] = provider.effective(scope)
        except Exception as error:
            raise RestoreError(
                f"cannot load the effective schema of scope {scope!r} to add promoted "
                f"columns: {error}; nothing was written"
            ) from error
    return schemas


def _recording(events: Iterator[Event], seen: dict[str, str]) -> Iterator[Event]:
    """Pass events through, noting the last ``effective_schema_hash`` each scope recorded."""
    for event in events:
        recorded = event.payload.get("effective_schema_hash")
        if isinstance(recorded, str):
            seen[event.scope] = recorded
        yield event


def _warnings(schemas: dict[str, EffectiveSchema], recorded: dict[str, str]) -> tuple[str, ...]:
    found: list[str] = []
    for scope in sorted(recorded):
        schema = schemas.get(scope)
        if schema is not None and schema.hash != recorded[scope]:
            found.append(
                f"scope {scope}: the ledger last recorded effective schema "
                f"{recorded[scope][:12]}, the schema packages in force now give "
                f"{schema.hash[:12]}; promoted columns may differ from the original "
                "(restore with the TL_SCHEMA_DIR the ledger used)"
            )
    return tuple(found)


def _rotate_hint(subscription_id: str, scope: str) -> str:
    target = "--company" if scope == "company" else f"--project {scope.removeprefix('project:')}"
    return f"tl webhook rotate-secret {subscription_id} {target}"


def _start_dispatcher_at_head(conn: Connection, head: int) -> None:
    """Set the webhook dispatcher's cursor to the restored head.

    Delivery state (the cursor, deliveries, secrets) is operational and is not in the ledger. With
    the cursor at 0 the dispatcher would queue every event since each subscription was created and
    flood its receiver with history once a secret is issued. Events up to ``head`` are treated as
    already dispatched; ``tl webhook replay`` covers a range a receiver may have missed.
    """
    moved = conn.execute(
        text("UPDATE wh_cursor SET last_seq = :seq WHERE name = :n"),
        {"seq": head, "n": CURSOR_NAME},
    )
    if moved.rowcount == 0:
        conn.execute(
            text("INSERT INTO wh_cursor (name, last_seq) VALUES (:n, :seq)"),
            {"n": CURSOR_NAME, "seq": head},
        )


def _secret_warnings(conn: Connection, head: int) -> tuple[str, ...]:
    """One warning per active webhook subscription, plus one about the dispatcher.

    Signing secrets are never in the ledger, so a restored subscription has none and the delivery
    engine holds its deliveries back (pending) until a secret is issued. The dispatcher cursor
    starts at the restored head (``_start_dispatcher_at_head``).
    """
    rows = conn.execute(
        text(
            "SELECT subscription_id, scope FROM cur_webhook_subscription "
            "WHERE status = 'active' ORDER BY created_at, subscription_id"
        )
    ).all()
    if not rows:
        return ()
    found = [
        f"webhook subscription {row[0]} (scope {row[1]}) has no signing secret after the restore "
        f"and sends nothing until you run: {_rotate_hint(str(row[0]), str(row[1]))}"
        for row in rows
    ]
    found.append(
        f"the webhook dispatcher starts at the restored head (seq {head}): events up to it are not "
        "queued again. A receiver may have missed events between its last delivery and the "
        "restore point; replay them with: tl webhook replay <subscription id> --from-seq N "
        f"--to-seq {head}"
    )
    return tuple(found)


def _restore_in_one_transaction(
    engine: Engine,
    target: DbTarget,
    store: ArchiveStore,
    schemas: dict[str, EffectiveSchema],
    registry: ProjectorRegistry,
    seen: dict[str, str],
    public_key: bytes,
) -> tuple[int, float, float, tuple[str, ...]]:
    """Insert, add promoted columns, replay, verify: all or nothing.

    Returns the event count, the ``perf_counter`` times at which the insert and the replay ended,
    and the webhook warnings.

    The closing verification against the archive runs before the commit, so a mismatch rolls
    everything back and leaves an empty database that the same call can restore into again.
    """
    insert = postgres.admin.restore_events if is_postgres(target) else sqlite.admin.restore_events
    with write_tx(engine) as conn:
        count = insert(conn, _recording(iter_segment_events(store), seen))
        inserted = time.perf_counter()
        for schema in schemas.values():
            ensure_promoted_columns(conn, schema)
        replay(conn, cast(Ledger, _ReplayLedger(conn)), registry, list(registry.all()), None)
        rebuilt_at = time.perf_counter()
        issues = verify_archive(store, public_key=public_key, conn=conn)
        if issues:
            raise _fail(issues, "the restored database does not match the archive")
        _start_dispatcher_at_head(conn, count)
        warnings = _secret_warnings(conn, count)
    return count, inserted, rebuilt_at, warnings


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
    Insert, promoted columns and projections commit together, so a failure leaves the database
    with empty tables and the same call can be repeated.

    Promoted pset columns of ``cur_core_record`` are not events: they exist because a schema package
    marks a property ``materialize: true``. They are added from the effective schema of every scope
    in the archive, taken from ``schema_provider`` (default: the process-wide one), so the schema
    packages in force at restore time decide them. The provider is consulted before anything is
    written. ``RestoreResult.warnings`` says when the schema now in force differs from the one the
    ledger last recorded.
    """
    started = time.perf_counter()
    segments = len(list_segment_names(store))
    if segments == 0:
        raise RestoreError("the archive holds no segments")
    issues = verify_archive(store, public_key=public_key)
    if issues:
        raise _fail(issues, "the archive does not verify")
    schemas = _schemas(store, schema_provider if schema_provider else get_provider())
    verified = time.perf_counter()

    reg = registry if registry is not None else default_registry()
    create_schema(target, registry=reg)
    seen: dict[str, str] = {}
    engine = make_engine(target)
    try:
        count, inserted, rebuilt, webhook_warnings = _restore_in_one_transaction(
            engine, target, store, schemas, reg, seen, public_key
        )
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
        schema_hashes={scope: schema.hash for scope, schema in schemas.items()},
        ledger_schema_hashes=dict(seen),
        warnings=(*_warnings(schemas, seen), *webhook_warnings),
    )
