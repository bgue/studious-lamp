"""What the `tl thread` commands share: naming a record, and what the actor holds (P1-I7 WS-B)."""

from __future__ import annotations

from collections.abc import Callable

from tl_adapters.db import DbTarget, is_postgres, open_uow
from tl_core.auth.env import dev_tokens_allowed
from tl_core.integration.contract import Access
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record, get_record_by_id
from tl_core.threads.holds import account_holds, has_account

SOURCE = "cli"


def record_of(db: DbTarget, project: str, record: str) -> tuple[str, str]:
    """``(id, scope)`` of the record named by key in the project, or by id."""
    scope = f"project:{project}"
    with open_uow(db, readonly=True) as uow:
        found = get_record(uow, scope, record) or get_record_by_id(uow, record)
    if found is None:
        raise RecordNotFoundError(f"no record {record!r} in {scope}")
    return str(found["id"]), str(found["scope"])


def holds_of(db: DbTarget, actor: str) -> Callable[[Access], bool]:
    """What ``actor`` holds, read from its account.

    A ledger file in a dev, test or ci setup may have no account for ``user:dev``: its owner can
    write the file anyway (ADR-0009 section 7), so there the actor holds everything. A server never
    does that: no account, no access.
    """
    with open_uow(db, readonly=True) as uow:
        if not has_account(uow.conn(), actor) and not is_postgres(db) and dev_tokens_allowed():
            return lambda level: True
        return account_holds(uow.conn(), actor)
