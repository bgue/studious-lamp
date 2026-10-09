"""``Schema.EffectiveChanged``: ledger record that a scope's effective schema changed (brief 27.3).

Clients that watch the bus for this event refresh forms and metadata without a restart. The
event lives in one stream per scope (``schema:<scope>``, stream type ``schema``) and carries the new
hash, the previous hash and the adopted package versions. Recording is idempotent: the same hash is
never recorded twice in a row.

STUB: the bodies below are implemented by P0-I2-T10. Names, signatures and docstrings are the
contract.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from tl_schema.effective import EffectiveSchema

from tl_core.ledger import Event
from tl_core.schema_provider import ReloadableSchemaProvider
from tl_core.uow import UnitOfWork

EVENT_TYPE = "Schema.EffectiveChanged"
PUBLISHED_EVENT_TYPE = "SchemaPackage.Published"
STREAM_TYPE = "schema"
ACTOR = "svc:schema"
SOURCE = "schema-reload"


def schema_stream_id(scope: str) -> str:
    """``schema:project:P123`` for scope ``project:P123``."""
    raise NotImplementedError


def record_effective_schema(uow: UnitOfWork, schema: EffectiveSchema) -> Event | None:
    """Append ``Schema.EffectiveChanged`` for ``schema.scope`` unless the hash is already recorded.

    Reads the scope's schema stream; the last event's ``effective_schema_hash`` is the recorded
    hash.
    """
    raise NotImplementedError


def reload_and_record(uow: UnitOfWork, provider: ReloadableSchemaProvider) -> list[Event]:
    """Reload ``provider``, then record every scope whose hash differs from the last recorded."""
    raise NotImplementedError


def schema_reload_subscriber(
    provider: ReloadableSchemaProvider,
    open_uow: Callable[[], AbstractContextManager[UnitOfWork]],
) -> Callable[[Event], None]:
    """Bus callback: on ``SchemaPackage.Published`` reload and record in its own unit of work."""
    raise NotImplementedError
