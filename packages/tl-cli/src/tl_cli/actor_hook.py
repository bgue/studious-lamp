"""Makes the default ``--actor`` of every command the signed-in user, and checks every value of it.

Each command module declares ``--actor`` with the default ``user:dev``. The root callback calls
:func:`install`, which gives the option two things (ADR-0009 sec. 7):

* a default that asks :func:`tl_cli.session.default_actor`, so leaving ``--actor`` out means
  "me" (the session's account, or ``user:dev`` in a dev setup on a ledger file);
* a check, run on the default and on an explicit value alike, that the command may act as that
  actor (:func:`tl_cli.session.check_actor`): the session's own actor, or anyone in a dev, test
  or ci setup on a ledger file. A database server URL never allows more than a session.

Typer carries its own copy of click (``typer._click``), so the commands are walked by their
attributes, not by ``isinstance``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tl_cli.session import DEV_ACTOR, check_actor, default_actor

#: What the help shows instead of the dynamic default.
HELP_DEFAULT = "the signed-in user"


@dataclass
class _Target:
    """The ledger of this invocation; repointed by :func:`install` (one invocation per process)."""

    db: Path
    local: bool


_target = _Target(Path("."), True)


class _ActorDefault:
    """A callable click default: the actor of the session of the current target."""

    def __call__(self) -> str:
        return default_actor(_target.db, local=_target.local)


def _checked(original: Callable[..., Any] | None) -> Callable[..., Any]:
    """A click callback that runs ``original`` (if any), then the actor check."""

    def callback(ctx: Any, param: Any, value: Any) -> Any:
        if original is not None:
            value = original(ctx, param, value)
        return check_actor(_target.db, str(value), local=_target.local)

    callback.tl_checked = True  # type: ignore[attr-defined]
    return callback


def install(command: Any, db: Path, *, local: bool = True) -> None:
    """Hook every ``--actor`` option under ``command`` that defaults to ``user:dev`` for ``db``."""
    _target.db, _target.local = db, local
    _install(command)


def _install(command: Any) -> None:
    for param in getattr(command, "params", []):
        if getattr(param, "name", None) != "actor" or "--actor" not in getattr(param, "opts", []):
            continue
        if isinstance(param.default, _ActorDefault):
            continue  # already hooked in an earlier invocation of this process
        if param.default == DEV_ACTOR:
            param.default = _ActorDefault()
            param.show_default = HELP_DEFAULT
            param.callback = _checked(param.callback)
    for sub in getattr(command, "commands", {}).values():
        _install(sub)
