"""Projector contracts (build spec 03 section 7)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sqlalchemy import Connection

from tl_core.ledger import Event


class Projector(Protocol):
    """Turns events into rows of one current-state table (or a small group of tables).

    ``apply`` runs inside the transaction that appended the event, so it must be deterministic: no
    clock, no generated ids, no outside calls. Given the same events in the same order it must leave
    identical rows. Projectors never delete history; ``reset`` clears only their own tables.
    """

    name: str
    handles: frozenset[str]
    # Optional: set ``handles_all = True`` (class attribute) to receive every event whatever its
    # type; ``handles`` is then ignored for routing. Registries read it with ``getattr``, so
    # projectors that do not define it are unaffected. Used by the outbox (P0-I5).

    def ddl(self, dialect: str) -> list[str]:
        """Idempotent CREATE statements (generated, never hand-written) for ``dialect``."""
        ...

    def apply(self, conn: Connection, event: Event) -> None: ...

    def reset(self, conn: Connection) -> None:
        """Empty every table this projector owns, ready for a replay."""
        ...


class ProjectorRegistry(Protocol):
    def for_event(self, event_type: str) -> Iterable[Projector]: ...

    def all(self) -> Iterable[Projector]: ...
