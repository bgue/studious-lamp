"""labour helper of P200: labour requisitions for the IWPs (P2-I4B T05b, amendment 2).

The readiness check ``labour_requested`` blocks an IWP that has estimated hours (every seed IWP
has) unless an approved labour requisition for it covers its planned dates. The constraints
section calls ``raise_labour`` for its IWPs just before it evaluates readiness, so the IWPs it
means to be ready carry labour:

- each IWP of the plan gets one labour requisition (raised by a foreman or the project engineer)
  whose dates contain the IWP's planned start and finish; the administrator approves it through
  ``ApproveRequisition`` unless the plan leaves it Requested (readiness ``pending``);
- the IWPs left out of the plan get none (``blocked`` NO_REQUISITION stays in the demo, and the
  check raises its constraint on them).

Every command goes through the commands, read through the actor's viewer, on a day before TODAY.
Draws come from a stream of the caller's, so no other section's draws move. No raw SQL writes.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from tl_mod_requisitions.commands import ApproveRequisition, RaiseRequisition
from tl_mod_requisitions.handlers.requisitions import (
    handle_approve_requisition,
    handle_raise_requisition,
)

from dev.seed.demo_project.requisitions import APPROVER, CRAFTS, RAISERS, _run
from dev.seed.demo_project.world import TODAY, World

RAISED_DAYS_AGO = 20
APPROVED_DAYS_AGO = 18


def raise_labour(
    world: World,
    plan: list[tuple[str, date, date, bool]],
    rng: random.Random,
) -> tuple[int, int]:
    """Raise labour for ``plan`` (IWP id, planned start, planned finish, approve), in order.

    Returns ``(approved, requested)``.
    """
    approved = requested = 0
    for n, (iwp, start, finish, approve) in enumerate(plan):
        made = _run(
            world,
            RAISERS[rng.randrange(len(RAISERS))],
            TODAY - timedelta(days=RAISED_DAYS_AGO),
            handle_raise_requisition,
            RaiseRequisition,
            requisition={
                "kind": "labor",
                "subject": f"Crew for interim package {n + 1:02d}",
                "need_by": (start - timedelta(days=2)).isoformat(),
                "priority": "normal",
                "craft": CRAFTS[n % len(CRAFTS)],
                "headcount": rng.randint(2, 12),
                "start_date": (start - timedelta(days=2)).isoformat(),
                "end_date": (finish + timedelta(days=2)).isoformat(),
            },
            for_record_id=iwp,
        )
        if not approve:
            requested += 1
            continue
        rid = str(made.stream_id)
        _run(
            world,
            APPROVER,
            TODAY - timedelta(days=APPROVED_DAYS_AGO),
            handle_approve_requisition,
            ApproveRequisition,
            requisition=rid,
            expected_version=world.version(rid),
        )
        approved += 1
    return approved, requested
