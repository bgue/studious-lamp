"""What an agent may file (P2-X2). S1: ``check_filing``; S2 adds the queue cap here."""

from __future__ import annotations

from sqlalchemy import Connection

from tl_core.auth import module_roles
from tl_core.auth.errors import ForbiddenError
from tl_core.modules import load_modules
from tl_core.services.commands import Command
from tl_core.services.errors import RecordNotFoundError


def _refusal(scope: str) -> RecordNotFoundError:
    """The one refusal: the text of a scope that does not exist (140). No module, no word."""
    return RecordNotFoundError(f"no scope {scope!r}")


def _holds_any_role(conn: Connection, holder: module_roles.Holder, scope: str) -> bool:
    """Whether the holder has at least one module role (any module, any word) on ``scope``."""
    modules = {spec.name for spec in load_modules()} | {module_roles.ALL_MODULES}
    return any(
        module_roles.effective_roles(conn, holder, scope=scope, module=m).roles
        for m in sorted(modules)
    )


def check_filing(conn: Connection, agent: str, command: Command) -> None:
    """Refuse a filing the agent has no module ``user`` word for (ADR-0027 F1).

    The command's own word is checked at accept, not here. A core command (no module declares
    it) needs any module role on the scope. A refusal reads as a scope that does not exist.
    """
    holder = module_roles.holder_for_actor(conn, agent)
    found = module_roles.command_index().get(type(command).__name__)
    if found is None:
        if not _holds_any_role(conn, holder, command.scope):
            raise _refusal(command.scope)
        return
    module, _word = found
    try:
        module_roles.require_word(
            conn, holder, scope=command.scope, module=module, word="user", what="filing"
        )
    except ForbiddenError:
        raise _refusal(command.scope) from None
