"""Makes the default ``--actor`` of every command the signed-in user (ADR-0009 sec. 4).

Each command module declares ``--actor`` with the default ``user:dev``. The root callback calls
:func:`install`, which swaps that default for a function that asks
:func:`tl_cli.session.default_actor` when (and only when) the option is left out. An explicit
``--actor`` is untouched.

Typer carries its own copy of click (``typer._click``), so the commands are walked by their
attributes, not by ``isinstance``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tl_cli.session import DEV_ACTOR, default_actor

#: What the help shows instead of the dynamic default.
HELP_DEFAULT = "the signed-in user"


class _ActorDefault:
    """A callable click default whose ledger can be repointed between invocations (tests)."""

    def __init__(self, db: Path) -> None:
        self.db = db

    def __call__(self) -> str:
        return default_actor(self.db)


def install(command: Any, db: Path) -> None:
    """Point every ``--actor`` option under ``command`` that defaults to ``user:dev`` at ``db``."""
    for param in getattr(command, "params", []):
        if getattr(param, "name", None) != "actor" or "--actor" not in getattr(param, "opts", []):
            continue
        if isinstance(param.default, _ActorDefault):
            param.default.db = db
        elif param.default == DEV_ACTOR:
            param.default = _ActorDefault(db)
            param.show_default = HELP_DEFAULT
    for sub in getattr(command, "commands", {}).values():
        install(sub, db)
