"""What a person holds, read from their account: the ``holds(level)`` of entry points that have no
request principal (the embedded TUI and the CLI).

The API builds ``holds`` from the principal of the request. A process that acts for one signed-in
person looks the account up instead: the actor must be the account's own, character for character
(``USER:ALICE`` and ``svc:alice`` are not ``user:alice``), the account must be active, and an agent
holds nothing (it proposes). Access never comes from a request field (ADR-0014 section 8).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Connection

from tl_core.auth import queries as account_queries
from tl_core.integration.contract import Access


def account_holds(conn: Connection, actor: str) -> Callable[[Access], bool]:
    """``holds(level)`` for the account named by ``actor``: ``user`` for any active person,
    ``controller`` for an admin or a document controller, ``admin`` for an admin."""
    found = account_queries.find_account(conn, username=actor.partition(":")[2])
    valid = (
        found is not None
        and account_queries.actor_of(found) == actor
        and found.status == "active"
        and found.kind != "agent"
    )
    roles: set[str] = set(found.roles) if found is not None and valid else set()

    def holds(level: Access) -> bool:
        if level == "admin":
            return "admin" in roles
        if level == "controller":
            return bool({"admin", "document_controller"} & roles)
        return valid

    return holds


def has_account(conn: Connection, actor: str) -> bool:
    """Whether ``actor`` names an account at all (a dev ledger file may have none)."""
    return account_queries.find_account(conn, username=actor.partition(":")[2]) is not None
