"""Remote `ClientInterface`: the TUI over the REST API and SSE stream (brief 4, remote mode).

``RemoteClient`` wraps ``tl_api.client.ApiClient``, which already has every ``ClientInterface``
method with the same names, parameters and exceptions (``tests/api/test_client_roundtrip.py`` holds
that line). What this adapter adds:

* ``relations()`` returns the TUI's ``RelationInfo`` (the API's ``RelationOut`` has the same
  fields).
* The connection state. A call that cannot reach the server (``ApiUnavailableError``) tells
  ``connection_listener`` "unreachable"; the next call that succeeds tells it "live". The app turns
  that into a banner. The exception still propagates, and ``CLIENT_ERRORS`` covers it, so a screen
  shows a status line and keeps its state.
* ``own_writes``: the events of this client's commands, to tell them from other writers' (live.py).
* ``change_feed()``: ``RemoteFeed``, the SSE stream with a cursor, resumed after a drop.

Every other call is passed through unchanged by ``__getattr__``; a test fails when a
``ClientInterface`` method is missing or its signature differs from the API client's.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import Any, Literal, cast

import httpx2
from tl_api.client import ApiClient
from tl_core.services.commands import Command, CommandResult
from tl_core.services.errors import ServiceError
from tl_core.services.feed import EditPost, PostToFeed
from tl_core.services.feed_actions import ReactToPost, RetractPost
from tl_core.services.feed_queries import Completion, FeedPage

from tl_tui.client import ClientInterface, RelationInfo
from tl_tui.live import ChangeFeed, FeedSink, OwnWrites
from tl_tui.messages import ConnectionState

#: ``ApiClient`` attributes that are not request/response calls (no connection state to report).
UNTRACKED = frozenset({"stream_events", "close", "base_url"})

#: Seconds a call may take. The screens call the server on the UI thread (the grid load, a record
#: view, a save), so this is how long the interface can freeze; past it the banner says why.
#: Moving those calls to workers is the P0-I8 hardening follow-up.
INTERACTIVE_TIMEOUT_S = 3.0


class FeedOverApiUnavailable(ServiceError):
    """The activity feed has no API routes yet (P0-I6 workstream B): the remote TUI cannot show it.

    A ``ServiceError``, so it is in ``CLIENT_ERRORS``: the feed pane shows the message and keeps
    its state, and the rest of the remote TUI is unaffected.
    """

    def __init__(self) -> None:
        super().__init__("the activity feed over the API arrives with P0-I6 workstream B")


def find_head(api: ApiClient) -> int:
    """The highest ``seq`` in the server's ledger, found with O(log n) one-event page requests.

    ``seq`` is gap-free and ascending, so "is there an event after k?" changes from yes to no at
    exactly the head. Starting a stream *after* this seq gives a feed that is live from now with no
    gap (anything committed since is replayed) and no need to read the whole log.
    """

    def follows(seq: int) -> bool:
        return bool(api.events_after(seq, limit=1).events)

    if not follows(0):
        return 0
    low, high = 0, 1
    while follows(high):  # head > high
        low, high = high, high * 2
    while low + 1 < high:  # head > low, head <= high
        mid = (low + high) // 2
        if follows(mid):
            low = mid
        else:
            high = mid
    return high


class RemoteFeed:
    """The API's SSE stream, resumed by ``seq`` after any drop (each event once, in order).

    ``follow`` finds the server's head first, so the first stream starts at a known cursor; after a
    drop it asks the server whether it is back (a one-event page), reports the state to the sink,
    and resumes from the last ``seq`` delivered, backing off from 0.25 s to 5 s while it is down.
    The stream gets its own connection pool (``make_api``) so ``close`` can abort a blocked read.
    """

    def __init__(
        self,
        make_api: Callable[[], ApiClient],
        *,
        scope: str | None = None,
        first_delay_s: float = 0.25,
        max_delay_s: float = 5.0,
    ) -> None:
        self._make_api = make_api
        self._scope = scope
        self._first = first_delay_s
        self._max = max_delay_s
        self._api: ApiClient | None = None
        self._lock = threading.Lock()
        self.cursor: int | None = None  # seq of the last event delivered (or the head at start)

    def head(self) -> int | None:
        """The server's head now, which becomes the cursor; ``None`` when it cannot be read."""
        api = self._make_api()
        try:
            self.cursor = find_head(api)
        except Exception:  # unreachable: follow() retries and takes the head itself
            return None
        finally:
            api.close()
        return self.cursor

    def follow(self, sink: FeedSink, stop: threading.Event) -> None:
        api = self._make_api()
        with self._lock:
            self._api = api
        delay = self._first
        checked = self.cursor is not None  # a cursor from head() was read a moment ago
        try:
            while not stop.is_set():
                try:
                    if self.cursor is None:
                        self.cursor = find_head(api)
                    elif not checked:
                        # Back after a drop: is it the same ledger? (replaced or restored: lower)
                        head = find_head(api)
                        if head < self.cursor:
                            self.cursor = head
                            sink.reset("server ledger changed; reloaded")
                    checked = False
                except Exception as exc:  # unreachable, refused (401) or a bad answer
                    if stop.is_set():
                        return
                    sink.connection("unreachable", _short(exc))
                    if stop.wait(delay):
                        return
                    delay = min(delay * 2, self._max)
                    continue
                sink.connection("live")
                delay = self._first
                detail = "the event stream closed"
                try:
                    for event in api.stream_events(
                        after=self.cursor, scope=self._scope, reconnect=False
                    ):
                        self.cursor = event.seq
                        sink.events([event])
                        if stop.is_set():
                            return
                except Exception as exc:  # the connection dropped or the server refused
                    detail = _short(exc)
                if stop.is_set():
                    return
                sink.connection("reconnecting", detail)
                if stop.wait(self._first):
                    return
        finally:
            with self._lock:
                self._api = None
            api.close()

    def close(self) -> None:
        """Close the stream's connection pool, which ends a read that is blocked on it."""
        with self._lock:
            api = self._api
        if api is not None:
            api.close()


def _short(exc: BaseException) -> str:
    text = str(exc) or exc.__class__.__name__
    return text if len(text) <= 160 else text[:159] + "…"


class RemoteClient:
    """`ClientInterface` over an ``ApiClient``. Use ``RemoteClient.connect(url, token)``."""

    def __init__(
        self,
        api: ApiClient,
        *,
        feed_api: Callable[[], ApiClient] | None = None,
    ) -> None:
        self._api = api
        self._feed_api = feed_api if feed_api is not None else (lambda: api)
        self.own_writes = OwnWrites()
        self._listener: Callable[[ConnectionState, str], None] | None = None
        self._state: ConnectionState = "live"
        self._detail = ""
        self._lock = threading.Lock()

    @classmethod
    def connect(
        cls, base_url: str, token: str, *, timeout: float = INTERACTIVE_TIMEOUT_S
    ) -> RemoteClient:
        """A client for the API at ``base_url`` using the dev token ``token``.

        Nothing is sent yet: an unreachable server shows up on the first call, as a banner.
        """
        return cls(
            ApiClient(base_url, token, timeout=timeout),
            feed_api=lambda: ApiClient(base_url, token, timeout=timeout),
        )

    @property
    def connection_listener(self) -> Callable[[ConnectionState, str], None] | None:
        """Called as ``listener(state, detail)`` when reachability changes (from any thread).

        Setting a listener tells it the current state at once if that is not "live": the first
        failed call (the grid's load) may happen before the app has attached.
        """
        return self._listener

    @connection_listener.setter
    def connection_listener(self, listener: Callable[[ConnectionState, str], None] | None) -> None:
        with self._lock:
            self._listener = listener
            state, detail = self._state, self._detail
        if listener is not None and state != "live":
            listener(state, detail)

    @property
    def base_url(self) -> str:
        return self._api.base_url

    def as_client(self) -> ClientInterface:
        """This adapter typed as the interface (the delegation is dynamic; tests prove it)."""
        return cast(ClientInterface, self)

    def change_feed(self, scope: str | None = None) -> ChangeFeed:
        return RemoteFeed(self._feed_api, scope=scope)

    def close(self) -> None:
        self._api.close()

    # --- the one conversion ----------------------------------------------------------------

    def relations(self) -> list[RelationInfo]:
        found = self._track(self._api.relations)()
        return [RelationInfo.model_validate(r.model_dump()) for r in found]

    # --- the activity feed has no API routes yet (P0-I6 WS-B) -------------------------------

    def feed_page(
        self,
        scope: str,
        *,
        record_id: str | None = None,
        include_linked: bool = False,
        tag: str | None = None,
        item_type: Literal["post", "card"] | None = None,
        limit: int = 50,
        before_seq: int | None = None,
    ) -> FeedPage:
        raise FeedOverApiUnavailable

    def feed_post(self, cmd: PostToFeed) -> CommandResult:
        raise FeedOverApiUnavailable

    def feed_edit(self, cmd: EditPost) -> CommandResult:
        raise FeedOverApiUnavailable

    def feed_retract(self, cmd: RetractPost) -> CommandResult:
        raise FeedOverApiUnavailable

    def feed_react(self, cmd: ReactToPost) -> CommandResult:
        raise FeedOverApiUnavailable

    def feed_complete(
        self, scope: str, sigil: Literal["#", "@"], prefix: str, *, limit: int = 8
    ) -> list[Completion]:
        raise FeedOverApiUnavailable

    # --- everything else is the API client's ----------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):  # private names are never delegated (also guards __init__)
            raise AttributeError(name)
        target = getattr(self._api, name)
        if not callable(target) or name in UNTRACKED:
            return target
        return self._track(target)

    def _track(self, call: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(call)
        def tracked(*args: Any, **kwargs: Any) -> Any:
            command = args[0] if args and isinstance(args[0], Command) else None
            # Events of a command may reach the feed before its response reaches us: until the
            # response has been noted, events on the command's stream are "pending", not foreign.
            flight: AbstractContextManager[None] = (
                self.own_writes.in_flight(getattr(command, "stream_id", None))
                if command is not None
                else nullcontext()
            )
            with flight:
                try:
                    result = call(*args, **kwargs)
                except httpx2.TransportError as exc:  # includes ApiUnavailableError
                    self._report("unreachable", _short(exc))
                    raise
                self._report("live", "")
                if isinstance(result, CommandResult):
                    self.own_writes.note(result)
            return result

        return tracked

    def _report(self, state: ConnectionState, detail: str) -> None:
        with self._lock:
            if state == self._state:
                return
            self._state, self._detail = state, detail
            listener = self._listener
        if listener is not None:
            listener(state, detail)
