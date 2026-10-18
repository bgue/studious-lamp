"""What an actor holds, resolved from the ledger's own state (FANOUT D14; coordinator decision).

The command runner enforces each command's access for the command's own actor, so a command run by
a rule, an inbound mapping, an enricher or a person's dispatch never runs with more than that actor
holds. The access is resolved here, in the same unit of work, and never read from a caller:

* ``user:<name>`` and ``agent:<name>``: the account's roles in ``cur_account`` (an admin holds
  ``admin``, a document controller ``controller``, anybody else ``user``; an agent holds ``user``
  at most; a disabled or missing account holds nothing).
* ``svc:rule-*``, ``svc:inbound-*``, ``svc:enricher-*``: the access declared on the rule, endpoint
  or enricher that owns that actor (``user`` or ``controller``, never ``admin``).
* anything else (``svc:action-*``, ``system:*``, an unknown name): nothing. Fail closed.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection, text

from tl_core.auth.queries import find_account
from tl_core.integration.contract import Access, access_covers
from tl_core.integration.errors import CommandAccessError

_SERVICE_TABLES: dict[str, str] = {
    "svc:rule-": "cur_rule",
    "svc:inbound-": "cur_inbound_endpoint",
    "svc:enricher-": "cur_enricher",
}


def held_access(conn: Connection, actor: str) -> Access | None:
    """The highest access ``actor`` holds, or ``None`` when it holds nothing."""
    for prefix, table in _SERVICE_TABLES.items():
        if actor.startswith(prefix):
            found = conn.execute(
                text(f"SELECT access FROM {table} WHERE service_actor = :a"),  # noqa: S608
                {"a": actor},
            ).first()
            level = None if found is None else str(found[0])
            return level if level in ("user", "controller") else None  # type: ignore[return-value]
    if actor.startswith(("user:", "agent:")):
        name = actor.split(":", 1)[1]
        try:
            account = find_account(conn, username=name)
        except Exception:  # an unusable name is no account
            return None
        if account is None or account.status != "active":
            return None
        if actor.startswith("agent:") != (account.kind == "agent"):
            return None
        if account.kind == "agent":
            return "user"
        if "admin" in account.roles:
            return "admin"
        if "document_controller" in account.roles:
            return "controller"
        return "user"
    return None


def require_access(conn: Connection, actor: str, needed: Access | None, what: str) -> Access:
    """The access ``actor`` holds when it covers ``needed``; else :class:`CommandAccessError`."""
    held = held_access(conn, actor)
    if held is None or not access_covers(held, needed):
        raise CommandAccessError(f"{what} needs {needed or 'an access nobody declared'} access")
    return held


def holds_for(held: Access) -> Callable[[Access], bool]:
    """``holds(level)`` for a handler that takes one: true when ``held`` covers ``level``."""

    def holds(level: Access) -> bool:
        return access_covers(held, level)

    return holds


__all__ = ["held_access", "holds_for", "require_access"]
