"""Run one module command inside the caller's unit of work (P2-FORMS S3, decision D8).

The shape ``accept_proposal`` uses (``services/proposals.py``): look the command type up, build the
model from stored arguments with the caller's actor, scope and source, check the access the person
needs, run the handler. This seam opens no unit of work and commits nothing: a refusal propagates
and the caller's block rolls back every earlier append of the same unit.

The seam is closed. It runs only a module's ``ProposableCommand`` (``module_proposables()``),
never a core command and never ``TransitionWorkflow``, ``DispatchFromThread``, ``InvokeAction`` or
``ChangeSetting``. A stored body never names its actor: ``actor``, ``actor_roles`` and ``source``
keys of ``args`` are ignored.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import Holder, require_command_access
from tl_core.modules import module_proposables
from tl_core.services.commands import CommandResult
from tl_core.services.errors import InvalidProposalError, ProposalAccessError
from tl_core.uow import UnitOfWork

MSG_NOT_NESTABLE = "that command cannot be run from another command"
MSG_ACCESS = "the person lacks the access that command needs"


#: The command type is not a module's proposable command (a fixed text, never the name). It is the
#: existing, already mapped ``InvalidProposalError`` (422): a class of its own would need a row in
#: ``tl_api.errors`` (``test_error_table``), which this piece may not edit.
NestedCommandError = InvalidProposalError


def run_nested_command(
    uow: UnitOfWork,
    *,
    command_type: str,
    args: Mapping[str, Any],
    actor: str,
    scope: str,
    source: str,
    causation_id: str | None = None,
    correlation_id: str | None = None,
    holds: Callable[[str], bool] | None = None,
    holder: Holder | None = None,
) -> CommandResult:
    """Run the module command ``command_type`` with ``args`` as ``actor`` in the caller's ``uow``.

    ``NestedCommandError`` for a type that is not a module proposable command. The caller sets
    ``actor``, ``scope``, ``source``, ``causation_id`` and ``correlation_id``; those keys of
    ``args`` (and ``actor_roles``) are overwritten or dropped. Access as ``accept_proposal``:
    without ``holds`` and ``holder`` only a command open to any signed-in person (``user``) runs;
    ``holds(level)`` answers for ``controller`` or ``admin``; with a ``holder`` the module role
    table is also checked (``require_command_access``). A refusal is ``ProposalAccessError``.
    """
    row = next((p for p in module_proposables().values() if p.model.__name__ == command_type), None)
    if row is None:
        raise NestedCommandError(MSG_NOT_NESTABLE)
    needed = row.access
    if needed != "user" and (holds is None or not holds(needed)):
        raise ProposalAccessError(MSG_ACCESS)
    data = dict(args)
    data.pop("actor_roles", None)
    data.update(
        actor=actor,
        scope=scope,
        source=source,
        causation_id=causation_id,
        correlation_id=correlation_id,
    )
    command = row.model.model_validate(data)
    if holder is not None:
        try:
            require_command_access(uow.conn(), command, holder=holder)
        except ForbiddenError as exc:
            raise ProposalAccessError(str(exc)) from exc
    return row.handler(uow, command)
