"""Core constraints (ADR-0024): the three frozen functions a module calls.

The signatures are frozen by ADR-0024 decision 6 and change only by orchestrator decision. A
module passes its name as ``by_module``; the call acts as the service ``svc:<module>`` (source
``job:<module>``). The four commands, the projector, the guard and the reads are in the sibling
modules; the handlers load on first call so the workflow engine can import ``guard`` without a
cycle."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection

from tl_core.constraints import guard
from tl_core.constraints.commands import (
    AssignConstraint,
    ClearConstraint,
    RaiseConstraint,
    WithdrawConstraint,
    command_table,
)
from tl_core.constraints.errors import (
    ConstraintError,
    ConstraintRuleError,
    ConstraintSourceError,
    ConstraintStateError,
    PhaseNotGatedError,
)
from tl_core.constraints.review import AGE_BANDS, ConstraintGroup, review_groups

ConstraintAction = Literal["raised", "exists", "suppressed", "cleared"]


class ConstraintOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    constraint_id: str | None
    key: str | None
    action: ConstraintAction


def raise_constraint(
    uow: Any,
    *,
    subject_id: str,
    phase: str,
    severity: Literal["blocking", "advisory"],
    category: str,
    source: str,
    check_name: str | None,
    facts_hash: str | None,
    by_module: str,
    owner: str | None = None,
    description: str | None = None,
    due_at: str | None = None,
    effective_at: str | None = None,
    target_id: str | None = None,
    target_ref_type: str | None = None,
    target_ref_text: str | None = None,
) -> ConstraintOutcome:
    """Raise a constraint on ``subject_id`` as the module ``by_module`` (ADR-0024 decision 6).

    Answers ``raised``, ``exists`` (an open one of the same subject, phase and check name) or
    ``suppressed`` (a person cleared this facts hash)."""
    from tl_core.constraints.handlers import raise_by_module

    constraint_id, key, action = raise_by_module(
        uow,
        subject_id=subject_id,
        phase=phase,
        severity=severity,
        category=category,
        source=source,
        check_name=check_name,
        facts_hash=facts_hash,
        by_module=by_module,
        owner=owner,
        description=description,
        due_at=due_at,
        effective_at=effective_at,
        target_id=target_id,
        target_ref_type=target_ref_type,
        target_ref_text=target_ref_text,
    )
    return ConstraintOutcome(constraint_id=constraint_id, key=key, action=action)


def clear_constraint(
    uow: Any,
    *,
    constraint_id: str,
    reason: str,
    by_module: str,
    cleared_at: str | None = None,
    resolved_by: str | None = None,
) -> ConstraintOutcome:
    """Clear a constraint as a module: only one whose source is not ``manual``."""
    from tl_core.constraints.handlers import clear_by_module

    cleared_id, key = clear_by_module(
        uow,
        constraint_id=constraint_id,
        reason=reason,
        by_module=by_module,
        cleared_at=cleared_at,
        resolved_by=resolved_by,
    )
    return ConstraintOutcome(constraint_id=cleared_id, key=key, action="cleared")


def open_blocking(conn: Connection, subject_id: str, phase: str) -> list[str]:
    """Keys of the open blocking constraints of a subject and phase; no viewer, keys only."""
    return guard.open_blocking(conn, subject_id, phase)


__all__ = [
    "AGE_BANDS",
    "AssignConstraint",
    "ClearConstraint",
    "ConstraintAction",
    "ConstraintError",
    "ConstraintGroup",
    "ConstraintOutcome",
    "ConstraintRuleError",
    "ConstraintSourceError",
    "ConstraintStateError",
    "PhaseNotGatedError",
    "RaiseConstraint",
    "WithdrawConstraint",
    "clear_constraint",
    "command_table",
    "open_blocking",
    "raise_constraint",
    "review_groups",
]
