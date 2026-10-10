"""Ordered bus publishing shared by the SQLite and Postgres units of work.

Commits are ordered by one process-wide lock: a writer commits and enqueues its events for the bus
while holding it, so the publish queue is in commit (``seq``) order. Subscribers run after the lock
is released (see ``tl_core.bus.OrderedPublisher``).
"""

from __future__ import annotations

import threading

from tl_core.bus import Bus, OrderedPublisher

COMMIT_LOCK = threading.Lock()
# One publisher per bus, kept for the life of the process (a bus lives that long in Phase 0).
# The publisher holds its bus, so keying by id() is safe: the bus is never collected, so its id
# is never reused.
_publishers: dict[int, OrderedPublisher] = {}
_publishers_lock = threading.Lock()


def publisher_for(bus: Bus) -> OrderedPublisher:
    """The one :class:`OrderedPublisher` that feeds ``bus``."""
    with _publishers_lock:
        publisher = _publishers.get(id(bus))
        if publisher is None:
            publisher = _publishers[id(bus)] = OrderedPublisher(bus)
        return publisher
