"""The typed command table as a ``CommandRunner``, for the thread dispatch planner (FANOUT D14).

``tl_core`` never imports ``tl_api``, so an entry point builds the runner from
``tl_api.commands.COMMANDS`` and hands it to the planner and to ``DispatchFromThread``. The
access of a command is the one its table row declares; a command the table does not list is
unknown to the planner (it answers ``dispatch_unavailable``).

When the integration layer is merged (P1-I7 WS-A) its ``command_runner()`` is the same thing and
this module delegates to it.
"""

from __future__ import annotations

from tl_core.integration.contract import Access, CommandRunner
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

from tl_api.commands import COMMANDS, CommandSpec

_ACCESS: dict[str, Access] = {
    "user": "user",
    "company": "admin",  # an admin at company scope, anyone at project scope: fail closed
    "controller": "controller",
    "admin": "admin",
}


class TableRunner:
    """A :class:`~tl_core.integration.contract.CommandRunner` over ``COMMANDS``."""

    def __init__(self, table: tuple[CommandSpec, ...] = COMMANDS) -> None:
        self._table = {spec.name: spec for spec in table}

    def model_of(self, command_type: str) -> type[Command] | None:
        spec = self._table.get(command_type)
        return None if spec is None else spec.model

    def access_of(self, command_type: str) -> Access | None:
        spec = self._table.get(command_type)
        return None if spec is None else _ACCESS.get(spec.access)

    def run(self, uow: UnitOfWork, command: Command) -> CommandResult:
        return self._table[type(command).__name__].handler(uow, command)


def thread_runner() -> CommandRunner:
    """The runner entry points pass to thread dispatch."""
    return TableRunner()
