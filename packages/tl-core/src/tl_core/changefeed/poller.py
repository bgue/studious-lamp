"""A seq-cursor poller for readers outside the writing process (brief 5.3).

The in-process bus only reaches subscribers in the process that wrote. A process that merely
shares the database (an API worker, the CLI watching a ledger) runs a :class:`ChangePoller`: it
reads ``Ledger.read_after`` from a cursor and hands every page to a :class:`SubscriptionRegistry`,
which filters and delivers it. The cursor only moves forward after a page was dispatched, so a
crash or a failed read repeats events rather than losing them (at-least-once); the registry drops
a repeat for a subscriber that already saw it.
"""

from __future__ import annotations

import logging
import threading
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
        if after_seq is not None and after_seq < 0:
            raise ValueError("after_seq must be >= 0")
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        if page_size < 1:
            raise ValueError("page_size must be >= 1")
        self._ledger = ledger
        self._registry = registry
        self._scope = scope
        self._interval = interval_s
        self._page_size = page_size
        self._cursor = ledger.head_seq() if after_seq is None else after_seq
        self._error: Exception | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def cursor(self) -> int:
        """``seq`` of the last event dispatched (or the start point before any)."""
        return self._cursor

    @property
    def running(self) -> bool:
        """True while the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> Exception | None:
        """The exception from the most recent failed poll; ``None`` after a successful one."""
        return self._error

    def poll_once(self) -> int:
        """Read and dispatch every event after the cursor; return how many were dispatched.

        Reads pages of ``page_size`` until a page comes back short or empty. Exceptions from the
        ledger propagate.
        """
        total = 0
        while True:
            page = self._ledger.read_after(self._cursor, scope=self._scope, limit=self._page_size)
            if not page:
                break
            self._registry.dispatch(page)
            self._cursor = page[-1].seq
            total += len(page)
            if len(page) < self._page_size:
                break
        return total

    def start(self) -> None:
        """Run ``poll_once`` every ``interval_s`` seconds on a daemon thread.

        A poll that raises is logged, kept in ``last_error`` and retried at the next interval.
        Raises ``RuntimeError`` if already running.
        """
        if self.running:
            raise RuntimeError("the poller is already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tl-change-poller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the thread and wait up to ``timeout`` seconds for it. Safe to call twice."""
        thread = self._thread
        if thread is None:
            return
        self._stop.set()
        thread.join(timeout)
        if not thread.is_alive():
            self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
                self._error = None
            except Exception as exc:
                self._error = exc
                log.warning("change-feed poll failed: %s", exc)
            self._stop.wait(self._interval)

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
