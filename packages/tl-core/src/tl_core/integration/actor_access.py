"""What an actor holds, resolved from the ledger's own state (FANOUT D14; coordinator decision).

The command runner enforces each command's access for the command's own actor, so a command run by
a rule, an inbound mapping, an enricher or a person's dispatch never runs with more than that actor
holds. The access is resolved here, in the same unit of work, and never read from a caller:

* ``user:<name>`` and ``agent:<name>``: the account's roles in ``cur_account`` (an admin holds
  ``admin``, a document controller ``controller``, anybody else ``user``; an agent holds ``user``
  at most; a disabled or missing account holds nothing).
* ``svc:rule-*``, ``svc:inbound-*``, ``svc:enricher-*``: the access declared on the rule, endpoint
  or enricher that owns that actor (``user`` or ``controller``, never ``admin``), and only while
  that owner is switched on and its app is on. The actor is unique to its owner (a unique index);
  a name with more than one owner, or none, holds nothing.
* anything else (``svc:action-*``, ``system:*``, an unknown name): nothing. Fail closed.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection, text

from tl_core.auth.names import actor_for
from tl_core.auth.queries import find_account
from tl_core.confidentiality import Viewer, viewer_for_actor
from tl_core.integration.contract import Access, access_covers
from tl_core.integration.errors import CommandAccessError

_APP_ON = "EXISTS (SELECT 1 FROM cur_integration_app a WHERE a.name = {app} AND a.enabled = :on)"
#: kind prefix -> the query of the one live owner. "Live" is the owner's own switch, and its app's
#: when it has one (a rule or an enricher may have none). A retired or disabled owner holds nothing.
_SERVICE_QUERIES: dict[str, str] = {
    "svc:rule-": (
        "SELECT r.access FROM cur_rule r WHERE r.service_actor = :a AND r.enabled = :on "
        f"AND (r.integration_app IS NULL OR {_APP_ON.format(app='r.integration_app')})"
    ),
    "svc:inbound-": (
        "SELECT e.access FROM cur_inbound_endpoint e "
        "WHERE e.service_actor = :a AND e.enabled = :on "
        f"AND {_APP_ON.format(app='e.app')}"
    ),
    "svc:enricher-": (
        "SELECT e.access FROM cur_enricher e WHERE e.service_actor = :a AND e.enabled = :on "
        f"AND (e.integration_app IS NULL OR {_APP_ON.format(app='e.integration_app')})"
    ),
}


def held_access(conn: Connection, actor: str) -> Access | None:
    """The highest access ``actor`` holds, or ``None`` when it holds nothing."""
    for prefix, sql in _SERVICE_QUERIES.items():
        if actor.startswith(prefix):
            found = conn.execute(text(sql), {"a": actor, "on": True}).fetchall()
            if len(found) != 1:  # none, or (never, the index forbids it) more than one: closed
                return None
            level = str(found[0][0])
            return level if level in ("user", "controller") else None  # type: ignore[return-value]
    if actor.startswith(("user:", "agent:")):
        name = actor.split(":", 1)[1]
        try:
            account = find_account(conn, username=name)
        except Exception:  # an unusable name is no account
            return None
        if account is None or account.status != "active" or not account.roles:
            return None
        if actor != actor_for(account.kind, account.username):  # exactly, not a normalised twin
            return None
        if account.kind == "agent":
            return "user"
        if "admin" in account.roles:
            return "admin"
        if "document_controller" in account.roles:
            return "controller"
        return "user"
    return None


def viewer_of(conn: Connection, actor: str) -> Viewer:
    """Who the confidentiality filters (ADR-0016) take ``actor`` to be, for automation.

    A person is the viewer ``viewer_for_actor`` says. A service actor (``svc:``) is always the
    lowest viewer, whatever access it declares or holds: it reads ``internal`` records only and can
    never be named on a privileged one (ADR-0017 section 7e; controller-level automation over
    restricted records is a Phase 2 question). So a rule, a mapping, an enricher or a reminder never
    reads or acts on a record that is not ``internal``.
    """
    if actor.startswith("svc:"):
        return Viewer(actor=actor, level=0, account="")
    return viewer_for_actor(conn, actor)


def workflow_roles_of(conn: Connection, actor: str) -> tuple[str, ...]:
    """The workflow roles ``actor`` holds (ADR-0013, addendum P1-SEC1): those of its account when it
    is a person, none for an agent and none for a service actor, so a rule or a mapping that
    transitions a workflow passes no ``roles`` guard (it fails closed, as intended)."""
    from tl_core.workflow.roles import workflow_roles

    if not actor.startswith("user:"):
        return ()
    try:
        account = find_account(conn, username=actor.split(":", 1)[1])
    except Exception:  # an unusable name is no account
        return ()
    if (
        account is None
        or account.status != "active"
        or actor != actor_for(account.kind, account.username)
    ):
        return ()
    return workflow_roles(account)


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


__all__ = ["held_access", "holds_for", "require_access", "viewer_of", "workflow_roles_of"]
