"""Constraint commands: raise, assign, clear, void. The rules are in ``tl_mod_awp.constraints``.

A person's ``RaiseConstraint`` reaches ``raise_constraint`` with ``by_module=False``, so only the
source ``manual`` is accepted; the clear is a person's (``by_source=None``). Fixed messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tl_core.services.commands import CommandResult
from tl_core.uow import UnitOfWork

from tl_mod_awp.constraints import (
    assign_constraint,
    clear_constraint,
    raise_constraint,
    void_constraint,
)

if TYPE_CHECKING:
    from tl_mod_awp.commands import (
        AssignConstraint,
        ClearConstraint,
        RaiseConstraint,
        VoidConstraint,
    )


def handle_raise_constraint(uow: UnitOfWork, cmd: RaiseConstraint) -> CommandResult:
    """Raise a ``manual`` constraint on an IWP. Raises ``ConstraintSourceError`` for any other
    source, ``ConstraintRuleError`` (owner, type, need-by), ``IwpStateError`` (a finished IWP)."""
    return raise_constraint(
        uow,
        cmd,
        iwp_id=cmd.iwp,
        constraint_type=cmd.constraint_type,
        source=cmd.source_kind,
        owner=cmd.owner,
        description=cmd.description,
        need_by=cmd.need_by,
        check_name=cmd.check_name,
        facts_hash=cmd.facts_hash,
        by_module=False,
    )


def handle_assign_constraint(uow: UnitOfWork, cmd: AssignConstraint) -> CommandResult:
    """Open to Assigned with the new owner."""
    return assign_constraint(uow, cmd, constraint_id=cmd.constraint, owner=cmd.owner)


def handle_clear_constraint(uow: UnitOfWork, cmd: ClearConstraint) -> CommandResult:
    """A person's clear: needs a reason; a hidden ``resolved_by`` answers as missing."""
    return clear_constraint(
        uow,
        cmd,
        constraint_id=cmd.constraint,
        reason=cmd.reason,
        resolved_by=cmd.resolved_by,
        by_source=None,
    )


def handle_void_constraint(uow: UnitOfWork, cmd: VoidConstraint) -> CommandResult:
    """Open or assigned to Void."""
    return void_constraint(uow, cmd, constraint_id=cmd.constraint, reason=cmd.reason)
