"""The guard ``no_open_blocking_constraints`` and the keys-only count behind it (ADR-0024).

Nothing here reads a viewer: ``open_blocking`` counts every open blocking constraint of a
subject and a phase and answers only constraint keys, so the engine can refuse a move without
ever reading a class, a description, an owner or a target. The message names the keys and the
phase and nothing else."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import Connection, text

OPEN_STATES = ("Open", "Assigned")
SEVERITY_BLOCKING = "blocking"
GUARD_KIND = "no_open_blocking_constraints"

_OPEN_BLOCKING_SQL = text(
    "SELECT r.key FROM cur_core_constraint c JOIN cur_core_record r ON r.id = c.id "
    "WHERE c.subject_id = :subject AND c.phase = :phase AND c.severity = :blocking "
    "AND r.voided = :voided AND COALESCE(r.status, :open) IN (:open, :assigned) "
    "ORDER BY r.key, r.id"
)


def open_blocking(conn: Connection, subject_id: str, phase: str) -> list[str]:
    """The keys of the open blocking constraints of ``subject_id`` for ``phase`` (no viewer)."""
    rows = conn.execute(
        _OPEN_BLOCKING_SQL,
        {
            "subject": subject_id,
            "phase": phase,
            "blocking": SEVERITY_BLOCKING,
            "voided": False,
            "open": OPEN_STATES[0],
            "assigned": OPEN_STATES[1],
        },
    )
    return [str(row[0]) for row in rows]


def refusal_message(phase: str, keys: Iterable[str]) -> str:
    """Fixed text: the phase and the constraint keys only."""
    return f"open blocking constraints for phase {phase}: {', '.join(keys)}"


def gated_phases(definition: object) -> frozenset[str]:
    """The phases some guard of the workflow ``definition`` names (the transition's own name when
    the guard names none). ``definition`` is a ``WorkflowDefinition``."""
    from tl_core.workflow.definition import NoOpenBlockingConstraintsGuard, WorkflowDefinition

    assert isinstance(definition, WorkflowDefinition)
    phases: set[str] = set()
    for transition in definition.transitions:
        for guard in transition.guards:
            if isinstance(guard, NoOpenBlockingConstraintsGuard):
                phases.add(guard.phase or transition.name)
    return frozenset(phases)
