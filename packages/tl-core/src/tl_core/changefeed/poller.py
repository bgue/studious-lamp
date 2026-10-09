"""A seq-cursor poller for readers outside the writing process (brief 5.3).

The in-process bus only reaches subscribers in the process that wrote. A process that merely
shares the database (an API worker, the CLI watching a ledger) runs a :class:`ChangePoller`: it
reads ``Ledger.read_after`` from a cursor and hands every page to a :class:`SubscriptionRegistry`,
which filters and delivers it. The cursor only moves forward after a page was dispatched, so a
crash or a failed read repeats events rather than losing them (at-least-once); the registry drops
a repeat for a subscriber that already saw it.

STUB (P0-I4-T02): the names, signatures and docstrings are final; the bodies marked
``raise NotImplementedError`` are the ticket. Remove this paragraph when done.
"""

from __future__ import annotations

import logging
from types import TracebackType

from tl_core.changefeed.registry import SubscriptionRegistry
from tl_core.ledger import Ledger

log = logging.getLogger(__name__)


class ChangePoller:
    """Polls ``ledger`` and dispatches new events to ``registry``."""

    def __init__(
        self,
        ledger: Ledger,
        registry: SubscriptionRegistry,
        *,
        after_seq: int | None = None,
        scope: str | None = None,
        interval_s: float = 0.25,
        page_size: int = 500,
    ) -> None:
        """``after_seq=None`` starts at the ledger's current head (only later events are seen);
        ``after_seq=n`` starts after ``n`` (0 replays everything). ``scope`` is passed to
        ``read_after``. Raises ``ValueError`` for ``after_seq`` < 0, ``interval_s`` <= 0 or
        ``page_size`` < 1."""
        raise NotImplementedError

    @property
    def cursor(self) -> int:
        """``seq`` of the last event dispatched (or the start point before any)."""
        raise NotImplementedError

    @property
    def running(self) -> bool:
        """True while the background thread is alive."""
        raise NotImplementedError

    @property
    def last_error(self) -> Exception | None:
        """The exception from the most recent failed poll; ``None`` after a successful one."""
        raise NotImplementedError

    def poll_once(self) -> int:
        """Read and dispatch every event after the cursor; return how many were dispatched.

        Reads pages of ``page_size`` until a page comes back short or empty. Exceptions from the
        ledger propagate.
        """
        raise NotImplementedError

    def start(self) -> None:
        """Run ``poll_once`` every ``interval_s`` seconds on a daemon thread.

        A poll that raises is logged, kept in ``last_error`` and retried at the next interval.
        Raises ``RuntimeError`` if already running.
        """
        raise NotImplementedError

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the thread and wait up to ``timeout`` seconds for it. Safe to call twice."""
        raise NotImplementedError

    def __enter__(self) -> ChangePoller:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
