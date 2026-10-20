"""Where the raw body of a delivery lives (FANOUT D4 step 6).

The body is stored as an object ``inbound/<endpoint id>/<delivery id>`` before the write
transaction; a corrected body (an admin's retry) is stored as ``inbound/<endpoint id>/<delivery
id>.corrected.<sha8>``. An object left behind by a transaction that failed has no delivery row:
:func:`orphans` lists those (a read-only report, like ``files.reconcile``: a key younger than the
transaction that will name it cannot be told from an orphan, so deleting is a human's call).

The store is configured once per process, as the derivation module's file service is
(``configure``); the commands that need it (a retry with a corrected payload) refuse when it is
not.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from sqlalchemy import text

from tl_core.files.types import ObjectNotFound, ObjectStore
from tl_core.integration.errors import IntegrationStateError
from tl_core.uow import UnitOfWork

PREFIX = "inbound/"
CONTENT_TYPE = "application/json"
_store: ObjectStore | None = None


def configure(store: ObjectStore | None) -> None:
    """Set (or clear) the object store this process keeps delivery bodies in."""
    global _store
    _store = store


def configured() -> ObjectStore:
    if _store is None:
        raise IntegrationStateError("no object store is configured for inbound payloads")
    return _store


def body_key(endpoint_id: str, delivery_id: str, *, correction: str | None = None) -> str:
    suffix = "" if correction is None else f".corrected.{correction}"
    return f"{PREFIX}{endpoint_id}/{delivery_id}{suffix}"


def put_body(store: ObjectStore, key: str, body: bytes) -> str:
    """Store ``body`` under ``key``; returns its SHA-256."""
    digest = hashlib.sha256(body).hexdigest()
    store.put(key, io.BytesIO(body), size=len(body), sha256=digest, content_type=CONTENT_TYPE)
    return digest


def read_body(store: ObjectStore, key: str, limit: int) -> bytes:
    """The body at ``key``; ``ObjectNotFound`` when it is gone, ``ValueError`` over ``limit``."""
    stream = store.get(key)
    try:
        data = stream.read(limit + 1)
    finally:
        stream.close()
    if len(data) > limit:
        raise ValueError("the stored body is larger than its limit")
    return data


@runtime_checkable
class _Listing(Protocol):
    def iter_keys(self) -> Iterator[str]: ...


_KNOWN_SQL = text("SELECT object_key FROM int_delivery")


def orphans(uow: UnitOfWork, store: ObjectStore) -> list[str] | None:
    """Keys under ``inbound/`` that no delivery row names; ``None`` when the store cannot list."""
    if not isinstance(store, _Listing):
        return None
    known = {str(row.object_key) for row in uow.conn().execute(_KNOWN_SQL)}

    def named(key: str) -> bool:  # a delivery's body, or a correction an admin stored for it
        base = key.split(".corrected.", 1)[0]
        return base in known

    return sorted(k for k in store.iter_keys() if k.startswith(PREFIX) and not named(k))


__all__ = [
    "CONTENT_TYPE",
    "PREFIX",
    "ObjectNotFound",
    "body_key",
    "configure",
    "configured",
    "orphans",
    "put_body",
    "read_body",
]
