"""The one error a dev-data guard raises. The message is written for an agent to read."""

from __future__ import annotations


class DevToolFailure(Exception):
    """A tool ran and failed (a statement timed out, a child process died). Not a refusal.

    The text is short and carries no server path; the tool reports it as is.
    """


class DevGuardError(ValueError):
    """A request was refused because it could touch something other than dev data.

    The text says what was refused and why, never a server path outside the repository.
    """
