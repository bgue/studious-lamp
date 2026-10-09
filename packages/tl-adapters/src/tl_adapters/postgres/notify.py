"""LISTEN/NOTIFY wake-ups for pollers (brief 5.3, 14).

Every ledger append sends ``NOTIFY tl_events`` with the payload ``<schema>:<last seq>``; Postgres
delivers it when the transaction commits. :class:`NotifyListener` holds a connection that
``LISTEN``s and sets a :class:`threading.Event` for each notification that concerns its own schema.
Hand that event to ``tl_core.changefeed.ChangePoller(wake=...)`` and delivery is prompt, while the
poller's ``seq`` cursor reads stay authoritative: a notification can be lost (the listener was
reconnecting) or spurious (another schema) without losing an event, because the poller also polls
on its normal interval.
"""

from __future__ import annotations

import logging
import threading
from types import TracebackType

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from tl_adapters.postgres.engine import NOTIFY_CHANNEL, sqlalchemy_url

log = logging.getLogger(__name__)

_RETRY_S = 1.0
_POLL_S = 0.25


def _libpq_url(url: str) -> str:
    parsed = make_url(sqlalchemy_url(url))
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


class NotifyListener:
    """Sets ``wake`` whenever a commit announces new events in this connection's schema."""

    def __init__(self, url: str, wake: threading.Event, *, channel: str = NOTIFY_CHANNEL) -> None:
        self._url = _libpq_url(url)
        self._wake = wake
        self._channel = channel
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.notifications = 0
        """How many matching notifications arrived (for tests and metrics)."""

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, *, timeout: float = 10.0) -> None:
        """Start listening; returns once ``LISTEN`` is active so no later commit is missed."""
        if self.running:
            raise RuntimeError("the listener is already running")
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="tl-pg-listener", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            self.stop()
            raise TimeoutError("the Postgres listener did not start")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the thread. Safe to call twice."""
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
                self._listen()
            except Exception as exc:
                log.warning("Postgres listener lost its connection: %s", exc)
                self._ready.set()  # do not hold start() hostage to a down server
                self._wake.set()  # events may have been missed while disconnected: poll now
                self._stop.wait(_RETRY_S)

    def _listen(self) -> None:
        with psycopg.connect(self._url, autocommit=True) as conn:
            row = conn.execute("SELECT current_schema()").fetchone()
            schema = row[0] if row else ""
            conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self._channel)))
            self._ready.set()
            self._wake.set()  # anything committed before LISTEN began is found by the first poll
            while not self._stop.is_set():
                for notice in conn.notifies(timeout=_POLL_S):
                    if notice.payload.split(":", 1)[0] == schema:
                        self.notifications += 1
                        self._wake.set()
                    if self._stop.is_set():
                        break

    def __enter__(self) -> NotifyListener:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()


__all__ = ["NotifyListener"]
