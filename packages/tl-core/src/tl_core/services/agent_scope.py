"""What an agent may file (P2-X2). S1: ``check_filing``; S2 adds the queue cap here."""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.auth import module_roles
from tl_core.modules import load_modules
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError


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
