"""The command runner entry points hand to thread dispatch (FANOUT D14).

``tl_core`` never imports ``tl_api``, so an entry point builds the runner from the typed command
table and passes it to the planner and to ``DispatchFromThread``. It is the integration layer's
:func:`tl_api.commands.command_runner`: before it runs a command it resolves, from the ledger, what
the command's own actor holds and refuses a command that actor may not run (a dispatch never runs
more than the person who confirmed it may). A command the table does not list is unknown to the
planner (it answers ``dispatch_unavailable``).
"""

from __future__ import annotations

from tl_core.integration.contract import CommandRunner

from tl_api.commands import command_runner


def thread_runner() -> CommandRunner:
    """The runner entry points pass to thread dispatch."""
    return command_runner()
