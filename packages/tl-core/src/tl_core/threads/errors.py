"""Expected failures of record threads and dispatch (brief 21.5; ADR-0018).

Each is a :class:`~tl_core.services.errors.ServiceError`, so every entry point maps it (the API
error table has a row for each). Messages are words for a person: no paths, no record contents.
"""

from __future__ import annotations

from typing import Any

from tl_core.services.errors import ServiceError


class ThreadError(ServiceError):
    """Base class of the thread failures."""


class ThreadsDisabledError(ThreadError):
    """``threads.enabled`` is off, or the record's type is not in ``threads.enabled_types``."""


class ThreadMessageNotFoundError(ThreadError):
    """The message id is unknown, or it belongs to another record's thread."""


class NotMessageAuthorError(ThreadError):
    """Edit or retract of a message by someone who did not write it."""


class MessageRetractedError(ThreadError):
    """Edit or retract of a message that was retracted."""


class MessageNotEditableError(ThreadError):
    """A dispatch, summary or reminder message belongs to the thread's history: it is not edited."""


class DispatchDisabledError(ThreadError):
    """``threads.dispatch.enabled`` is off, or ``threads.agents.can_dispatch`` is ``none``."""


class DispatchForbiddenError(ThreadError):
    """The caller may not dispatch: the role is not in ``threads.dispatch.roles``, or an agent."""


class DispatchStaleError(ThreadError):
    """The plan differs from the one previewed, or the preview expired. Preview again."""


class DispatchRefusedError(ThreadError):
    """The plan has problems (a command not permitted, invalid or refused). ``problems`` lists them.

    Each problem is a ``{"code": ..., "message": ...}`` dictionary.
    """

    def __init__(self, message: str, problems: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.problems: list[dict[str, Any]] = problems if problems is not None else []


class DispatchSyntaxError(ThreadError):
    """The command line did not parse (``code`` is the parser's problem code)."""
