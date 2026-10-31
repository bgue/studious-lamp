"""Reads that one screen refresh asks for more than once, answered once (P2-PERF).

A record screen builds its header, its Details rows and its tabs from the same few reads (the
record's history, its links and files); each part used to read them again. ``Reads`` wraps a client
for the length of one refresh: the calls named in ``SHARED`` are made once per arguments, every
other call goes straight through. Nothing is kept past the refresh, so no screen shows older data
than before; an error is not remembered either.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Read-only calls whose answer does not change within one refresh.
SHARED = frozenset({"history", "links_of", "list_record_files", "workflow_status"})


class Reads:
    """A client for one refresh. Use it where a ``ClientInterface`` is expected."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._answers: dict[tuple[Any, ...], Any] = {}

    def __getattr__(self, name: str) -> Any:
        found = getattr(self._client, name)
        if name not in SHARED or not callable(found):
            return found
        return self._shared(name, found)

    def _shared(self, name: str, call: Callable[..., Any]) -> Callable[..., Any]:
        def once(*args: Any, **kwargs: Any) -> Any:
            key = (name, args, tuple(sorted(kwargs.items())))
            try:
                return self._answers[key]
            except KeyError:
                pass
            except TypeError:  # arguments that cannot be a key: ask every time
                return call(*args, **kwargs)
            answer = self._answers[key] = call(*args, **kwargs)
            return answer

        return once
