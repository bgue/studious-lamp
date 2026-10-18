"""What the `tl thread` commands share: naming a record, and what the actor holds (P1-I7 WS-B)."""

from __future__ import annotations

from collections.abc import Callable

from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import Access
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.queries import get_record, get_record_by_id
from tl_core.threads.holds import account_holds

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

    No account, no access, on a ledger file as on a server: the command runner resolves what the
    actor holds from the same account, so a preview that said "ok" for an actor the runner then
    refuses would mislead. A dev ledger needs an account for ``user:dev``
    (``tl admin user add``).
    """
    with open_uow(db, readonly=True) as uow:
        return account_holds(uow.conn(), actor)
