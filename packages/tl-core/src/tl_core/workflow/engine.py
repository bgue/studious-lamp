"""Guard evaluation for workflow transitions (brief 8; Phase 0 scope).

``evaluate_guards`` answers, for one record and one transition, whether each guard passes and why
not. It reads and never writes. ``tl_core.services.workflow`` uses it to refuse a transition
(``TransitionWorkflow``) and to list what a record may do now (``workflow_status``).

Guards (see ``tl_core.workflow.definition``):

* ``required_psets``: each named pset holds at least one value; each listed path has a value.
* ``conformance``: the record's conformance, evaluated against the effective schema *in the target
  state* (so a property that is required in that state counts), is not worse than ``max_status``.
* ``required_links``: explicit link requirements, evaluated like expected links.
* ``expected_links``: the record type's expected links whose ``by_state`` is the target state.
* ``roles``: the caller's roles include one of ``any_of``. Roles are a stub list on the command
  until auth exists (brief 8); nothing here verifies them.

Contractual workflows (clocks, signatures, approvers) are out of scope (brief M10, human gate).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, cast

from pydantic import BaseModel
from tl_schema.conformance import evaluate

from tl_core.links.expected import ExpectedLink, MissingLink, unmet_expectations
from tl_core.schema_provider import get_provider
from tl_core.uow import UnitOfWork
from tl_core.workflow.definition import (
    ConformanceGuard,
    ExpectedLinksGuard,
    Guard,
    RequiredLinksGuard,
    RequiredPsetsGuard,
    RolesGuard,
    TransitionDef,
)
from tl_core.workflow.provider import get_expected_links

_RANK = {"ok": 0, "waived": 0, "warning": 1, "nonconformant": 2}


class GuardResult(BaseModel):
    kind: str
    passed: bool
    message: str
    details: dict[str, Any] = {}


class RecordFacts(BaseModel):
    """The parts of a ``cur_core_record`` row that guards look at."""

    id: str
    key: str | None
    type: str
    scope: str
    psets: dict[str, Any]


def evaluate_guards(
    uow: UnitOfWork,
    record: RecordFacts,
    transition: TransitionDef,
    *,
    roles: Sequence[str],
    today: date,
) -> list[GuardResult]:
    """Every guard of ``transition`` evaluated, in declaration order. Passed guards are included."""
    return [_evaluate(uow, record, transition, guard, roles, today) for guard in transition.guards]


def conformance_in_state(
    record: RecordFacts, state: str, today: date
) -> tuple[str, str, list[dict[str, str]]]:
    """``(status, effective_schema_hash, issues)`` of the record evaluated as if in ``state``."""
    schema = get_provider().effective(record.scope)
    report = evaluate(schema, record.type, record.psets, state=state, on=today)
    issues = [
        {"path": i.path, "level": i.level, "rule": i.rule, "message": i.message}
        for i in report.issues
    ]
    return report.status, schema.hash, issues


def _evaluate(
    uow: UnitOfWork,
    record: RecordFacts,
    transition: TransitionDef,
    guard: Guard,
    roles: Sequence[str],
    today: date,
) -> GuardResult:
    if isinstance(guard, RequiredPsetsGuard):
        return _required_psets(record, guard)
    if isinstance(guard, ConformanceGuard):
        return _conformance(record, transition, guard, today)
    if isinstance(guard, RequiredLinksGuard):
        return _links(uow, record, "required_links", guard.links)
    if isinstance(guard, ExpectedLinksGuard):
        wanted = [
            e for e in get_expected_links().for_type(record.type) if e.by_state == transition.to
        ]
        return _links(uow, record, "expected_links", wanted)
    return _roles(guard, roles)


def _lookup(psets: dict[str, Any], dotted: str) -> Any:
    node: Any = psets
    for segment in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = cast(dict[str, Any], node).get(segment)
    return node


def _required_psets(record: RecordFacts, guard: RequiredPsetsGuard) -> GuardResult:
    missing: list[str] = []
    for name in guard.psets:
        section = _lookup(record.psets, name)
        if section is None or section == {}:
            missing.append(f"pset {name} has no values")
    for path in guard.values:
        if _lookup(record.psets, path) is None:
            missing.append(f"{path} has no value")
    if missing:
        return GuardResult(
            kind="required_psets",
            passed=False,
            message="; ".join(missing),
            details={"missing": missing},
        )
    return GuardResult(kind="required_psets", passed=True, message="required psets are present")


def _conformance(
    record: RecordFacts, transition: TransitionDef, guard: ConformanceGuard, today: date
) -> GuardResult:
    status, _hash, issues = conformance_in_state(record, transition.to, today)
    passed = _RANK[status] <= _RANK[guard.max_status]
    if passed:
        message = f"conformance is {status} in {transition.to}"
    else:
        shown = "; ".join(f"{i['path']}: {i['message']}" for i in issues[:3])
        message = (
            f"conformance is {status} in {transition.to} (allowed: {guard.max_status}): {shown}"
        )
    return GuardResult(
        kind="conformance",
        passed=passed,
        message=message,
        details={"status": status, "state": transition.to, "issues": issues},
    )


def _links(
    uow: UnitOfWork, record: RecordFacts, kind: str, expectations: Sequence[ExpectedLink]
) -> GuardResult:
    unmet: list[MissingLink] = unmet_expectations(uow, record.id, expectations)
    if not unmet:
        return GuardResult(kind=kind, passed=True, message="required links are present")
    parts = [f"{m.expectation.display} ({m.found} of {m.needed})" for m in unmet]
    return GuardResult(
        kind=kind,
        passed=False,
        message="missing links: " + "; ".join(parts),
        details={"missing": [m.model_dump() for m in unmet]},
    )


def _roles(guard: RolesGuard, roles: Sequence[str]) -> GuardResult:
    held = sorted(set(roles) & set(guard.any_of))
    if held:
        return GuardResult(kind="roles", passed=True, message=f"role {held[0]} held")
    return GuardResult(
        kind="roles",
        passed=False,
        message=f"needs one of the roles: {', '.join(guard.any_of)}",
        details={"any_of": list(guard.any_of), "held": sorted(set(roles))},
    )
