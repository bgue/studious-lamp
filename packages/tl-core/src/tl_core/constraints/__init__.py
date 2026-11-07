"""Core constraints (ADR-0024): frozen function signatures.

The bodies arrive with piece C2 (``docs/tickets/P2-I2/C2-core-constraint-commands.md``); the
signatures are frozen by ADR-0024 decision 6 and change only by orchestrator decision.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection

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
    raise NotImplementedError("piece C2")


def clear_constraint(
    uow: Any,
    *,
    constraint_id: str,
    reason: str,
    by_module: str,
    cleared_at: str | None = None,
    resolved_by: str | None = None,
) -> ConstraintOutcome:
    raise NotImplementedError("piece C2")


def open_blocking(conn: Connection, subject_id: str, phase: str) -> list[str]:
    raise NotImplementedError("piece C2")
