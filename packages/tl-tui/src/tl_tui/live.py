"""Live updates: a change feed, its thread, and the rules that turn events into UI decisions.

A ``ChangeFeed`` blocks in ``follow(sink, stop)`` on a background thread and hands committed
events to a ``FeedSink`` in ``seq`` order, each event once (brief 5.3, 10.2). Two feeds exist:

* ``EmbeddedFeed`` (here): the in-process bus for this process's own writes plus a ``ChangePoller``
  for writes by other processes on the same SQLite file, joined by one ``SubscriptionRegistry``.
* ``RemoteFeed`` (``tl_tui.remote``): the API's SSE stream, resumed by ``seq`` after a drop.

``LiveUpdates`` runs a feed on a daemon thread and posts ``LiveEvents`` and ``ConnectionChanged``
messages to a widget. ``post_message`` is the one thread-safe way into Textual that never blocks
the feed thread and never waits on a loop that may have stopped; a worker that must apply a result
to a widget uses ``call_from_thread`` instead (see the grid).

The decisions the screens make from events are pure functions here (``touched_record_ids``,
``detect_conflict``), so they are tested without a terminal.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from typing import Literal, Protocol

from textual.message_pump import MessagePump
from tl_core.bus import Bus
from tl_core.changefeed import (
    ChangePoller,
    SubscriptionFilter,
    SubscriptionOverflow,
    SubscriptionRegistry,
)
from tl_core.ledger import Event, Ledger
from tl_core.services.commands import CommandResult

from tl_tui.messages import ConnectionChanged, ConnectionState, LedgerReset, LiveEvents

log = logging.getLogger(__name__)

#: Event types whose stream is a record (the stream id is the record id).
RECORD_PREFIXES = ("Record.", "Pset.", "Workflow.")
#: Link events live on a link stream; the records at its two ends are named in the payload.
LINK_PREFIX = "Link."
LINK_END_KEYS = ("from_ref", "to_ref")


class FeedSink(Protocol):
    """Where a feed delivers: events in ``seq`` order, and its connection state."""

    def events(self, batch: list[Event]) -> None: ...

    def connection(self, state: ConnectionState, detail: str = "") -> None: ...

    def reset(self, detail: str) -> None:
        """The ledger is behind the feed's cursor (replaced or restored): reload everything."""
        ...


class ChangeFeed(Protocol):
    """A source of committed events. ``follow`` blocks until ``stop`` is set."""

    def head(self) -> int | None:
        """The ledger's head ``seq`` now (or ``None`` if it cannot be read), and start there.

        The app calls this once *before* its first read of the rows; ``follow`` then delivers
        everything committed after that seq, so nothing committed between the first read and the
        start of the thread is lost.
        """
        ...

    def follow(self, sink: FeedSink, stop: threading.Event) -> None:
        """Deliver live events (from now on) to ``sink``; report the connection state.

        Each event is delivered once and in ascending ``seq``, also across reconnects.
        """
        ...

    def close(self) -> None:
        """Abort a ``follow`` that is blocked on I/O (called after ``stop`` is set)."""
        ...


Origin = Literal["own", "foreign", "pending"]


class OwnWrites:
    """The ids of events this client's own commands produced (bounded, newest kept).

    A screen skips the "changed by someone else" highlight and banner for these: the user knows
    about their own save. Two TUIs run by the same user are told apart by event id, not by actor.

    A command's events can reach the feed before its response reaches the caller (the SSE stream
    and the HTTP response are separate connections). While a command is in flight
    (``in_flight``), events on its stream are ``pending``, not ``foreign``: the app holds them
    until the response has been noted, but never longer than ``HOLD_CAP_S``.
    """

    HOLD_CAP_S = 2.0

    def __init__(self, capacity: int = 2000) -> None:
        self._ids: set[str] = set()
        self._order: deque[str] = deque()
        self._capacity = capacity
        self._lock = threading.Lock()
        self._flight: dict[int, tuple[str | None, float]] = {}
        self._next = 0

    @contextmanager
    def in_flight(self, stream_id: str | None) -> Generator[None]:
        """Mark a command as sent and not yet answered. ``stream_id`` ``None``: any stream."""
        with self._lock:
            self._next += 1
            key = self._next
            self._flight[key] = (stream_id, time.monotonic())
        try:
            yield
        finally:
            with self._lock:
                self._flight.pop(key, None)

    def classify(self, event: Event) -> Origin:
        """``own`` (noted), ``pending`` (a command that may own it is in flight), or ``foreign``."""
        with self._lock:
            if event.event_id in self._ids:
                return "own"
            now = time.monotonic()
            for stream_id, started in self._flight.values():
                if (stream_id is None or stream_id == event.stream_id) and (
                    now - started < self.HOLD_CAP_S
                ):
                    return "pending"
        return "foreign"

    def note(self, result: CommandResult) -> CommandResult:
        """Remember the events of ``result`` and return it (so a call can wrap its return)."""
        with self._lock:
            for event in result.events:
                if event.event_id in self._ids:
                    continue
                self._ids.add(event.event_id)
                self._order.append(event.event_id)
            while len(self._order) > self._capacity:
                self._ids.discard(self._order.popleft())
        return result

    def __contains__(self, event_id: object) -> bool:
        with self._lock:
            return event_id in self._ids

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)


def touched_record_ids(events: Iterable[Event]) -> set[str]:
    """Ids of the records these events changed: the record stream, or the ends of a link."""
    ids: set[str] = set()
    for event in events:
        if event.event_type.startswith(RECORD_PREFIXES):
            ids.add(event.stream_id)
        elif event.event_type.startswith(LINK_PREFIX):
            for key in LINK_END_KEYS:
                end = event.payload.get(key)
                if isinstance(end, str):
                    ids.add(end)
    return ids


def record_events(events: Iterable[Event], record_id: str) -> list[Event]:
    """The events on the record's own stream (the ones that move its ``version``), in order."""
    return [
        e for e in events if e.stream_id == record_id and e.event_type.startswith(RECORD_PREFIXES)
    ]


def detect_conflict(record_id: str, opened_version: int, events: Iterable[Event]) -> Event | None:
    """The newest event that moved the record past ``opened_version``, or ``None``.

    This is what an open edit asks of each batch of events: if the record's stream is already at a
    later ``stream_version`` than the form was built from, a save would be refused by the ledger
    (``expected_version``), so the form says so now instead of when the user presses save.
    """
    newer = [e for e in record_events(events, record_id) if e.stream_version > opened_version]
    return max(newer, key=lambda e: e.stream_version) if newer else None


class EmbeddedFeed:
    """Changes of a SQLite ledger this process has open: own writes at once, others' by polling."""

    def __init__(
        self,
        ledger: Ledger,
        bus: Bus,
        *,
        scope: str | None = None,
        interval_s: float = 0.25,
    ) -> None:
        self._ledger = ledger
        self._bus = bus
        self._scope = scope
        self._interval = interval_s
        self._start: int | None = None

    def head(self) -> int | None:
        try:
            self._start = self._ledger.head_seq()
        except Exception:  # an unreadable ledger: follow() will take the head itself
            log.warning("could not read the ledger head", exc_info=True)
            self._start = None
        return self._start

    def follow(self, sink: FeedSink, stop: threading.Event) -> None:
        flt = SubscriptionFilter(scope=self._scope) if self._scope else None
        registry = SubscriptionRegistry(self._ledger)
        attached = registry.attach(self._bus)
        # From the head the app saw before its first read: events committed since are replayed.
        poller = ChangePoller(
            self._ledger,
            registry,
            after_seq=self._start,
            scope=self._scope,
            interval_s=self._interval,
        )
        sub = registry.subscribe_queue(flt, after_seq=self._start)
        poller.start()
        sink.connection("live")
        try:
            while not stop.is_set():
                try:
                    batch = sub.get_many(100, timeout=0.2)
                except SubscriptionOverflow as overflow:
                    sub.close()
                    sub = registry.subscribe_queue(flt, after_seq=overflow.resume_seq)
                    continue
                if batch:
                    sink.events(batch)
        finally:
            sub.close()
            attached.close()
            poller.stop()
            registry.close()

    def close(self) -> None:
        """Nothing to abort: ``follow`` looks at ``stop`` every 0.2 s."""


class _PostingSink:
    """Posts what a feed delivers to a widget as Textual messages."""

    def __init__(self, target: MessagePump) -> None:
        self._target = target

    def events(self, batch: list[Event]) -> None:
        self._target.post_message(LiveEvents(batch))

    def connection(self, state: ConnectionState, detail: str = "") -> None:
        self._target.post_message(ConnectionChanged(state, detail))

    def reset(self, detail: str) -> None:
        self._target.post_message(LedgerReset(detail))


class LiveUpdates:
    """Runs a feed on a daemon thread and posts its output to ``target`` (the app)."""

    def __init__(self, feed: ChangeFeed, target: MessagePump) -> None:
        self._feed = feed
        self._sink = _PostingSink(target)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            raise RuntimeError("live updates are already running")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tl-tui-live", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            self._feed.follow(self._sink, self._stop)
        except Exception as exc:
            if not self._stop.is_set():  # a feed that dies tells the user instead of vanishing
                self._sink.connection("unreachable", f"live updates stopped: {exc}")

    def stop(self, timeout: float = 2.0) -> None:
        """Ask the feed to end, abort a blocked read, and wait up to ``timeout`` seconds."""
        self._stop.set()
        try:
            self._feed.close()
        except Exception:  # closing a feed that already failed must not hide the shutdown
            pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if not thread.is_alive():
                self._thread = None


def latest_by_record(events: Sequence[Event]) -> dict[str, Event]:
    """For each record the batch touched, its newest record-stream event (link events excluded)."""
    newest: dict[str, Event] = {}
    for event in events:
        if event.event_type.startswith(RECORD_PREFIXES):
            held = newest.get(event.stream_id)
            if held is None or event.stream_version >= held.stream_version:
                newest[event.stream_id] = event
    return newest


def describe_changes(events: Sequence[Event]) -> str:
    """A status line for a batch: "Record changed by user:bob", "3 records changed by 2 users"."""
    ids = touched_record_ids(events)
    actors = sorted(
        {e.actor for e in events if e.event_type.startswith(RECORD_PREFIXES + (LINK_PREFIX,))}
    )
    who = actors[0] if len(actors) == 1 else f"{len(actors)} users"
    noun = "Record" if len(ids) == 1 else f"{len(ids)} records"
    return f"{noun} changed by {who}"
