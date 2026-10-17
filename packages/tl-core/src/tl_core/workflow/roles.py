"""Where a person's workflow roles come from (ADR-0013, addendum P1-SEC1).

A ``roles`` guard (``any_of: [...]``) asks whether the caller holds one of the named roles. The
caller never says so: the entry point (API route, CLI session, embedded client) derives the roles
from the authenticated account with :func:`workflow_roles` and passes them to
``handle_transition_workflow(..., roles=...)`` or ``workflow_status(..., roles=...)``. They are a
Python argument, never a field of a command, so no request body, proposal or tool call can carry
them.

Today the only source is the account's own roles (``admin``, ``document_controller``, ``user``,
ADR-0013). A guard names one of those. A name nobody holds (a sample workflow that wants
``lifting_supervisor``) fails closed: no account has it. A later source (a project assignment, an
Entra group) adds its names here and nowhere else.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol


class RoleHolder(Protocol):
    """What derivation reads: a ``Principal`` or an ``AccountView`` (both have these)."""

    @property
    def kind(self) -> str: ...

    @property
    def roles(self) -> Iterable[str]: ...


def workflow_roles(who: RoleHolder) -> tuple[str, ...]:
    """The roles ``who`` holds for workflow guards, sorted; none for an agent or no role.

    - An ``agent`` holds none: it proposes, and the person who accepts brings theirs (ADR-0009).
    - A person or sim account holds the roles of its account. An ``admin`` also holds
      ``document_controller`` (ADR-0013: an admin passes every controller check), and any account
      with a role holds ``user`` (the authorizer opens everything outside ``admin.*`` and
      ``control.*`` to any account that has a role).
    """
    if who.kind == "agent":
        return ()
    held = set(who.roles)
    if not held:
        return ()
    held.add("user")
    if "admin" in held:
        held.add("document_controller")
    return tuple(sorted(held))
