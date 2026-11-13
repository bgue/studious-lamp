"""constraints section: about 40 constraints on 20 of 24 IWPs and 12 CWPs (ADR-0024).

The IWPs are made here (the awp section builds CWPs only), on Released CWPs, and sent to the
constraint check. People raise ``manual`` constraints through the real commands; one constraint
is raised as the awp readiness check does (``constraints.raise_constraint``, source ``check``) and
cleared by a person, because no waive word exists. After the constraints are in, every IWP in
the constraint check is evaluated through the engine's public path (``evaluate_now``), so the
ledger holds readiness results: an IWP with an open blocking ``ready`` constraint stays in the
constraint check, one without moves to Ready.

Dates come from the project calendar. ``due_at`` and ``cleared_at`` are world time on the
constraint; the envelope time is only ever the section's ``world.on(day)`` (ADR-0024 D19).
Draws come from the section's own ``rng``.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from tl_adapters.db import open_uow
from tl_core import constraints
from tl_core.constraints import (
    AssignConstraint,
    ClearConstraint,
    RaiseConstraint,
    WithdrawConstraint,
)
from tl_core.constraints.handlers import (
    handle_assign_constraint,
    handle_clear_constraint,
    handle_raise_constraint,
    handle_withdraw_constraint,
)
from tl_mod_awp.commands import (
    CreateIwp,
    SendIwpToConstraintCheck,
    StartIwpDevelopment,
)
from tl_mod_awp.handlers.iwp import (
    handle_create_iwp,
    handle_send_iwp_to_constraint_check,
    handle_start_iwp_development,
)
from tl_mod_awp.readiness import evaluate_now

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import TODAY, World

BUILDER = "lhartmann"  # the project engineer plans and raises
FOREMEN = ("cbrooks", "pnair")
OWNERS = ("lhartmann", "treyes", "cbrooks", "pnair", "ipetrov", "odoyle")
IWP_COUNT = 24
CWP_CONSTRAINTS = 12
RELEASED = "Released for IWP development"

#: category -> sample descriptions (every category is one of ``CATEGORIES``)
TEXTS: dict[str, tuple[str, ...]] = {
    "materials": ("Flanges and gaskets not on site", "Spool material short on the take-off"),
    "labour": ("Welders not yet mobilised", "Rigging crew shared with area 200"),
    "scaffold": ("Scaffold not erected at the work face",),
    "equipment": ("Mobile crane booked elsewhere", "Hydrotest pump not available"),
    "permit": ("Hot work permit not issued", "Tie-in permit needs plant sign-off"),
    "engineering": ("Isometric revision not issued for construction",),
    "rfi": ("RFI on support location unanswered",),
    "predecessor": ("Foundation hand-over not signed",),
    "other": ("Laydown area not cleared",),
}
CATEGORY_LIST = tuple(TEXTS)


def _stamp(day: date) -> str:
    return day.isoformat()


def _digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


class _Plan:
    """One constraint to raise and the state it ends in."""

    def __init__(self, subject: str, phase: str, severity: str, final: str, due: date | None):
        self.subject, self.phase, self.severity, self.final, self.due = (
            subject,
            phase,
            severity,
            final,
            due,
        )


def build(world: World, rng: random.Random) -> None:
    cwps = [
        (str(r["id"]), str(r["discipline"]))
        for r in world.rows(
            "SELECT r.id AS id, c.discipline AS discipline FROM cur_core_record r "
            "JOIN cur_awp_cwp c ON c.id = r.id WHERE r.type = 'awp.CWP' AND r.status = :s "
            "ORDER BY r.key",
            s=RELEASED,
        )
    ]
    if len(cwps) < IWP_COUNT // 2 + CWP_CONSTRAINTS:
        raise RuntimeError("the awp section left too few released work packages")

    # --- the IWPs, in the constraint check -----------------------------------------------------
    iwps: list[str] = []
    for i in range(IWP_COUNT):
        cwp, disc = cwps[i % len(cwps)]
        start = TODAY + timedelta(days=rng.randrange(10, 60))
        with world.on(TODAY - timedelta(days=40 - i)):
            made = world.run(
                handle_create_iwp,
                CreateIwp,
                by=BUILDER,
                discipline=disc,
                title=f"Interim package {i + 1:02d} ({disc})",
                cwp_id=cwp,
                planned_start=_stamp(start),
                planned_finish=_stamp(start + timedelta(days=rng.randrange(5, 15))),
                foreman=f"user:{rng.choice(FOREMEN)}",
            )
            iwp = str(made.stream_id)
            world.run(handle_start_iwp_development, StartIwpDevelopment, by=BUILDER, iwp=iwp)
            world.run(
                handle_send_iwp_to_constraint_check,
                SendIwpToConstraintCheck,
                by=BUILDER,
                iwp=iwp,
            )
        iwps.append(iwp)

    past = [TODAY - timedelta(days=d) for d in (3, 8, 15, 22)]
    future = [TODAY + timedelta(days=d) for d in (4, 9, 17, 30)]
    plans: list[_Plan] = []
    # IWPs 0-7: two blocking ``ready`` constraints each, still open or assigned (not ready)
    for n, iwp in enumerate(iwps[:8]):
        for k in range(2):
            late = (n + k) % 3 == 0  # open past the due date: overdue by the 2026-11-06 clock
            final = ("open", "assigned")[(n + k) % 2]
            plans.append(
                _Plan(iwp, "ready", "blocking", final, rng.choice(past if late else future))
            )
    # IWPs 8-11: two blocking ``ready`` constraints each, both closed (ready again)
    for n, iwp in enumerate(iwps[8:12]):
        for final in ("cleared", "withdrawn" if n % 2 else "cleared"):
            plans.append(_Plan(iwp, "ready", "blocking", final, rng.choice(past + future)))
    # IWPs 12-15: one constraint that does not hold back readiness: advisory, or blocking ``start``
    for n, iwp in enumerate(iwps[12:16]):
        blocking = n % 2 == 0
        plans.append(
            _Plan(
                iwp,
                "start" if blocking else "ready",
                "blocking" if blocking else "advisory",
                ("open", "assigned")[n // 2],
                rng.choice(future),
            )
        )
    # IWPs 16-19: one constraint each, closed or advisory
    for n, iwp in enumerate(iwps[16:20]):
        plans.append(
            _Plan(
                iwp,
                "ready",
                "advisory",
                ("open", "cleared", "withdrawn", "assigned")[n],
                rng.choice(past + future),
            )
        )
    # IWPs 20-23 carry none; 12 released CWPs carry one each, gated by ``start_execution``
    cwp_ids = [c for c, _d in rng.sample(cwps, CWP_CONSTRAINTS)]
    finals = ("open",) * 3 + ("assigned",) * 2 + ("cleared",) * 3 + ("withdrawn",) + ("open",) * 3
    for n, cwp in enumerate(cwp_ids):
        overdue = n >= 9  # the last three are open and overdue
        blocking = n % 2 == 0
        plans.append(
            _Plan(
                cwp,
                "start_execution" if blocking else "ready",
                "blocking" if blocking else "advisory",
                finals[n],
                rng.choice(past if overdue else future),
            )
        )
    # a blocking constraint on a CWP phase that is not gated is refused; advisory takes any phase

    # --- raise, assign, clear, withdraw -----------------------------------------------------------
    raised: list[tuple[str, str]] = []  # (constraint id, key) in raise order
    for n, plan in enumerate(plans):
        category = CATEGORY_LIST[(n * 4 + rng.randrange(3)) % len(CATEGORY_LIST)]
        owner = rng.choice(OWNERS)
        day = TODAY - timedelta(days=30 - n % 25)
        with world.on(day):
            made = world.run(
                handle_raise_constraint,
                RaiseConstraint,
                by=BUILDER,
                subject=plan.subject,
                phase=plan.phase,
                severity=plan.severity,
                category=category,
                owner=f"user:{owner}",
                description=rng.choice(TEXTS[category]),
                due_at=None if plan.due is None else _stamp(plan.due),
            )
        cid = str(made.stream_id)
        raised.append((cid, str(made.key)))
        later = day + timedelta(days=rng.randrange(1, 6))
        with world.on(later):
            if plan.final == "assigned":
                world.run(
                    handle_assign_constraint,
                    AssignConstraint,
                    by=BUILDER,
                    constraint=cid,
                    owner=f"user:{rng.choice(OWNERS)}",
                )
            elif plan.final == "cleared":
                world.run(
                    handle_clear_constraint,
                    ClearConstraint,
                    by=owner,
                    constraint=cid,
                    reason="Resolved on site and confirmed by the foreman",
                    cleared_at=_stamp(later),
                )
            elif plan.final == "withdrawn":
                world.run(
                    handle_withdraw_constraint,
                    WithdrawConstraint,
                    by=BUILDER,
                    constraint=cid,
                    reason="Raised in error; the item is not in this package's scope",
                )

    # --- a check-raised one, waived by an admin (core.constraint.waive) ----------------------
    with world.on(TODAY - timedelta(days=12)):
        with open_uow(world.target) as uow:
            outcome = constraints.raise_constraint(
                uow,
                subject_id=iwps[8],
                phase="ready",
                severity="blocking",
                category="materials",
                source="check",
                check_name="materials_reserved",
                facts_hash=_digest("materials_reserved", "blocked", iwps[8]),
                by_module="awp",
                description="readiness check materials_reserved is blocked",
                due_at=_stamp(TODAY - timedelta(days=5)),
            )
        assert outcome.constraint_id is not None
    with world.on(TODAY - timedelta(days=9)):
        world.run(
            handle_clear_constraint,
            ClearConstraint,
            by=ADMIN,
            constraint=outcome.constraint_id,
            reason="Materials coordinator confirmed the reservation by phone",
            cleared_at=_stamp(TODAY - timedelta(days=9)),
        )

    # --- readiness: every IWP in the constraint check, evaluated on the project's today -------
    with world.today():
        for iwp in iwps:
            with open_uow(world.target) as uow:
                evaluate_now(uow, iwp, TODAY)


register("constraints", build, needs=("core.Constraint", "awp.IWP"))
