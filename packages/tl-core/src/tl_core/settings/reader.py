"""The settings reader: cached lookups for code that asks often (brief 30.3: live settings).

``SettingsReader.get(key, project=...)`` answers from an in-memory copy of the setting tables, so
a hot path (a webhook delivery, a lake watcher) does not query per call. Three things end the life
of what it holds:

* **A change.** Attach it to the bus (:meth:`SettingsReader.attach`) and every ``Setting.Changed``
  or ``Setting.Locked`` event drops the copy, so a ``live`` setting applies on the next call,
  with no restart. In a process that does not share the writer's bus (a worker beside a server)
  the copy expires on its own after ``max_age_s`` seconds.
* **Time.** A scheduled change takes effect at its ``applies_at`` without any event. Each answer is
  cached only until the next ``applies_at`` of that key (decision D5), so the first call after it
  sees the new value.
* **A race.** A reload that overlaps an invalidation is not kept: the copy is stored only if no
  event arrived while it was being read.

A reader built without a connection factory answers with the platform defaults. Reads happen in a
read-only transaction the factory opens per reload, never while holding the reader's lock.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Connection

from tl_core.bus import Bus, Subscription
from tl_core.ledger import Event
from tl_core.settings.instants import to_us
from tl_core.settings.registry import get_definition
from tl_core.settings.resolver import Snapshot, load_snapshot, resolve_from
from tl_core.settings.types import SETTING_CHANGED, SETTING_LOCKED, EffectiveSetting
from tl_core.util import utcnow

ConnFactory = Callable[[], AbstractContextManager[Connection]]
SETTING_EVENTS: tuple[str, ...] = (SETTING_CHANGED, SETTING_LOCKED)
DEFAULT_MAX_AGE_S = 30.0

_Key = tuple[str, str | None, str | None]


class UowOpener(Protocol):
    """``factory(readonly=...)`` as every server-side unit-of-work factory has it."""

    def __call__(self, readonly: bool = False) -> AbstractContextManager[Any]: ...


def conn_factory_from(factory: UowOpener) -> ConnFactory:
    """A :data:`ConnFactory` that opens a read-only unit of work and yields its connection."""

    @contextmanager
    def open_conn() -> Generator[Connection]:
        with factory(readonly=True) as uow:
            yield uow.conn()

    return open_conn


class SettingsReader:
    def __init__(
        self,
        conn_factory: ConnFactory | None = None,
        *,
        clock: Callable[[], datetime] = utcnow,
        max_age_s: float | None = DEFAULT_MAX_AGE_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = conn_factory
        self._clock = clock
        self._max_age_s = max_age_s
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._generation = 0
        self._snapshot: Snapshot | None = None
        self._loaded_at = 0.0
        self._answers: dict[_Key, tuple[EffectiveSetting, int | None]] = {}
        self.loads = 0  # how many times the tables were read (tests and diagnostics)

    # --- invalidation -------------------------------------------------------------------------

    def invalidate(self) -> None:
        """Drop everything held; the next call reads the tables again."""
        with self._lock:
            self._generation += 1
            self._snapshot = None
            self._answers = {}

    def on_event(self, event: Event) -> None:
        """Bus callback: drop everything when a ``Setting.*`` event arrives."""
        if event.event_type in SETTING_EVENTS:
            self.invalidate()

    def attach(self, bus: Bus) -> Subscription:
        """Subscribe to ``bus`` so a change invalidates this reader; close the result to stop."""
        return bus.subscribe(self.on_event, event_types=SETTING_EVENTS)

    # --- reads --------------------------------------------------------------------------------

    def _fresh(self) -> bool:
        """Whether the copy held is young enough to trust (call with the lock held)."""
        return self._snapshot is not None and (
            self._max_age_s is None or self._monotonic() - self._loaded_at < self._max_age_s
        )

    def _load(self) -> Snapshot:
        if self._factory is None:
            return Snapshot()
        with self._factory() as conn:
            return load_snapshot(conn)

    def _current(self) -> tuple[Snapshot, int]:
        """The snapshot to answer from and the generation it belongs to."""
        with self._lock:
            if self._snapshot is not None and self._fresh():
                return self._snapshot, self._generation
            generation = self._generation
        loaded = self._load()  # outside the lock: a slow database must not block readers
        with self._lock:
            self.loads += 1
            if generation == self._generation:
                self._snapshot = loaded
                self._loaded_at = self._monotonic()
                self._answers = {}
            return loaded, generation

    def effective(
        self, key: str, *, project: str | None = None, user: str | None = None
    ) -> EffectiveSetting:
        """The full :class:`EffectiveSetting` of ``key`` (origin, lock, scheduled, pending effect).

        Raises ``UnknownSettingError``. Cached until the next ``applies_at`` of the key.
        """
        defn = get_definition(key)
        now_us = to_us(self._clock())
        slot: _Key = (key, project, user)
        with self._lock:
            held = self._answers.get(slot)
            if held is not None and self._fresh() and (held[1] is None or now_us < held[1]):
                return held[0].model_copy(deep=True)
        snapshot, generation = self._current()
        answer = resolve_from(defn, snapshot, project=project, user=user, at_us=now_us)
        with self._lock:
            if generation == self._generation:
                self._answers[slot] = (answer, snapshot.next_change_us(key, now_us))
        return answer.model_copy(deep=True)  # the cached answer must not be reachable by callers

    def get(self, key: str, *, project: str | None = None, user: str | None = None) -> Any:
        """The effective value of ``key`` for ``project`` and ``user``."""
        return self.effective(key, project=project, user=user).value


def reader(
    conn_factory: ConnFactory | None = None, *, max_age_s: float | None = DEFAULT_MAX_AGE_S
) -> SettingsReader:
    """A :class:`SettingsReader` over ``conn_factory`` (``None``: platform defaults only)."""
    return SettingsReader(conn_factory, max_age_s=max_age_s)
