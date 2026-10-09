"""``Schema.EffectiveChanged``: ledger record that a scope's effective schema changed (brief 27.3).

Clients that watch the bus for this event refresh forms and metadata without a restart. The
event lives in one stream per scope (``schema:<scope>``, stream type ``schema``) and carries the new
hash, the previous hash and the adopted package versions. Recording is idempotent: the same hash is
never recorded twice in a row.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from tl_schema.effective import EffectiveSchema

from tl_core.ledger import Event, NewEvent
from tl_core.schema_provider import ReloadableSchemaProvider
from tl_core.uow import UnitOfWork
from tl_core.util import new_ulid

EVENT_TYPE = "Schema.EffectiveChanged"
PUBLISHED_EVENT_TYPE = "SchemaPackage.Published"
STREAM_TYPE = "schema"
ACTOR = "svc:schema"
SOURCE = "schema-reload"


def schema_stream_id(scope: str) -> str:
    """``schema:project:P123`` for scope ``project:P123``."""
    return f"schema:{scope}"


def record_effective_schema(uow: UnitOfWork, schema: EffectiveSchema) -> Event | None:
    """Append ``Schema.EffectiveChanged`` for ``schema.scope`` unless the hash is already recorded.

    Reads the scope's schema stream; the last event's ``effective_schema_hash`` is the recorded
    hash.
    """
    stream_id = schema_stream_id(schema.scope)
    history = uow.ledger.read_stream(stream_id)
    last = history[-1] if history else None
    previous_hash: str | None = last.payload["effective_schema_hash"] if last else None
    if last is not None and previous_hash == schema.hash:
        return None
    result = uow.append(
        stream_id=stream_id,
        stream_type=STREAM_TYPE,
        scope=schema.scope,
        expected_version=last.stream_version if last else 0,
        events=[
            NewEvent(
                event_type=EVENT_TYPE,
                payload={
                    "scope": schema.scope,
                    "effective_schema_hash": schema.hash,
                    "previous_hash": previous_hash,
                    "packages": [f"{p.name}@{p.version}" for p in schema.packages],
                },
            )
        ],
        actor=ACTOR,
        source=SOURCE,
        correlation_id=new_ulid(),
    )
    return result.events[0]


def reload_and_record(uow: UnitOfWork, provider: ReloadableSchemaProvider) -> list[Event]:
    """Reload ``provider``, then record every scope whose hash differs from the last recorded."""
    provider.reload()
    recorded: list[Event] = []
    for scope in provider.scopes():
        event = record_effective_schema(uow, provider.effective(scope))
        if event is not None:
            recorded.append(event)
    return recorded


def schema_reload_subscriber(
    provider: ReloadableSchemaProvider,
    open_uow: Callable[[], AbstractContextManager[UnitOfWork]],
) -> Callable[[Event], None]:
    """Bus callback: on ``SchemaPackage.Published`` reload and record in its own unit of work."""

    def on_event(event: Event) -> None:
        if event.event_type != PUBLISHED_EVENT_TYPE:
            return
        with open_uow() as uow:
            reload_and_record(uow, provider)

    return on_event
