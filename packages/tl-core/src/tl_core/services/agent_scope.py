"""What an agent may file (P2-X2). S1: ``check_filing``; S2: ``check_queue_cap``."""

from __future__ import annotations

import json

from sqlalchemy import Connection, text

from tl_core import confidentiality
from tl_core.auth import module_roles
from tl_core.modules import load_modules
from tl_core.services.commands import Command
from tl_core.services.errors import QueueFullError, RecordNotFoundError
from tl_core.settings.resolver import value_of


def _refusal(scope: str) -> RecordNotFoundError:
    """The one refusal: the text of a scope that does not exist (140). No module, no word."""
    return RecordNotFoundError(f"no scope {scope!r}")


_EXPLICIT = frozenset({"granted", "granted_all_modules", "admin"})


def _explicit(
    conn: Connection, holder: module_roles.Holder, scope: str, module: str
) -> module_roles.EffectiveRoles | None:
    """The holder's roles on ``scope`` for ``module`` when an explicit grant gave them, else None.

    A role derived from the account role does not count at filing (closed by default, ADR-0009).
    """
    found = module_roles.effective_roles(conn, holder, scope=scope, module=module)
    return found if found.source in _EXPLICIT else None


def _holds_any_role(conn: Connection, holder: module_roles.Holder, scope: str) -> bool:
    """Whether an explicit grant gives the holder any module role (any module) on ``scope``."""
    modules = {spec.name for spec in load_modules()} | {module_roles.ALL_MODULES}
    return any(
        (found := _explicit(conn, holder, scope, m)) is not None and found.roles
        for m in sorted(modules)
    )


def check_filing(conn: Connection, agent: str, command: Command) -> None:
    """Refuse a filing the agent has no explicit module ``user`` grant for (ADR-0027 F1).

    Only an explicit grant counts (``granted``, ``granted_all_modules``, ``admin``); a role derived
    from the account role does not. The command's own word is checked at accept, not here. A core
    command (no module declares it) needs any explicitly granted module role on the scope. A
    refusal reads as a scope that does not exist.
    """
    holder = module_roles.holder_for_actor(conn, agent)
    found = module_roles.command_index().get(type(command).__name__)
    if found is None:
        if not _holds_any_role(conn, holder, command.scope):
            raise _refusal(command.scope)
        return
    module, _word = found
    granted = _explicit(conn, holder, command.scope, module)
    if granted is None or "user" not in granted.words:
        raise _refusal(command.scope)


QUEUE_CAP_SETTING = "ai.agents.max_pending_per_project"
#: The one refusal of a full queue: no number, no scope, no agent.
QUEUE_FULL_TEXT = "this review queue is full; ask a reviewer to clear it, then file again"


def _queue_limit(conn: Connection, scope: str) -> int:
    project = scope.partition(":")[2] if scope.startswith("project:") else None
    return int(value_of(conn, QUEUE_CAP_SETTING, project=project))


def pending_visible_count(conn: Connection, scope: str, viewer: confidentiality.Viewer) -> int:
    """Pending proposals in ``scope`` the viewer may read (one with a hidden record is not counted).

    The filter runs over every pending row first and the count is taken after it; no LIMIT.
    """
    # lazy: proposals imports this module
    from tl_core.services.proposals import _carried_ids  # pyright: ignore[reportPrivateUsage]

    rows = conn.execute(
        text(
            "SELECT proposal_id, command_json FROM cur_proposals "
            "WHERE scope = :s AND status = 'pending'"
        ),
        {"s": scope},
    ).all()
    carried: dict[str, set[str]] = {}
    every: set[str] = set()
    for row in rows:
        ids: set[str] = set()
        command = row.command_json
        if isinstance(command, str):
            command = json.loads(command)
        _carried_ids(command, ids)
        carried[row.proposal_id] = ids
        every |= ids
    hidden = confidentiality.hidden_among(conn, sorted(every), viewer)
    return sum(1 for ids in carried.values() if not (ids & hidden))


def check_queue_cap(conn: Connection, agent: str, command: Command) -> None:
    """Refuse a filing when the queue holds the cap of pending proposals the agent may read.

    The queue is ``command.scope``. Fixed text, no counts (a count can leak a hidden record).
    """
    # lazy: actor_access imports services
    from tl_core.integration.actor_access import viewer_of

    if pending_visible_count(conn, command.scope, viewer_of(conn, agent)) >= _queue_limit(
        conn, command.scope
    ):
        raise QueueFullError(QUEUE_FULL_TEXT)
