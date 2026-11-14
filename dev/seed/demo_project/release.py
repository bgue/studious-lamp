"""release section: the Ready IWPs are signed off by two people, issued to their foreman, and a few
are started (P2-SEED-T09).

The constraints section has already run readiness on every IWP (``evaluate_now`` at the project's
today), so the Ready ones are read from the ledger. If fewer than ``ISSUE_COUNT`` are Ready, the
blocking ``ready`` constraints that the constraints section raised are cleared through the real
command (``ClearConstraint``, by the administrator) on the IWPs in the constraint check, one IWP
at a time, and readiness is evaluated again for each. Then ``ISSUE_COUNT`` Ready IWPs are chosen
with the section's own ``rng``; each gets two sign-offs (``SignOffIwp``, by the project engineer
and the administrator, both awp superusers in the demo roster) and is issued to its foreman
(``IssueIwp``).
``START_COUNT`` of them, with no open blocking ``start`` constraint, are started (``StartIwpWork``).

Every command runs through ``world.on(day)`` before TODAY. The IWPs that are not chosen stay as they
are. No raw SQL writes.
"""

from __future__ import annotations

import random
from datetime import timedelta

from tl_adapters.db import open_uow
from tl_core.constraints.commands import ClearConstraint
from tl_core.constraints.handlers import handle_clear_constraint
from tl_mod_awp.commands import IssueIwp, SignOffIwp, StartIwpWork
from tl_mod_awp.handlers.progress import handle_start_iwp_work
from tl_mod_awp.handlers.signoff import handle_issue_iwp, handle_sign_off_iwp, iwp_record_hash
from tl_mod_awp.readiness import evaluate_now

from dev.seed.demo_project.core import ADMIN
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import TODAY, World

#: the two distinct signers: the project engineer (an awp superuser in the roster) and the admin
SIGNERS = ("lhartmann", ADMIN)
ISSUE_COUNT = 12
START_COUNT = 4
CLEAR_REASON = "Resolved on site and confirmed by the foreman; cleared to release the package"

Pair = tuple[str, str]  # (IWP record id, IWP key)


def _ready(world: World) -> list[Pair]:
    return [
        (str(r["id"]), str(r["key"]))
        for r in world.rows(
            "SELECT r.id AS id, r.key AS key FROM cur_core_record r "
            "WHERE r.type = 'awp.IWP' AND r.status = 'Ready' ORDER BY r.key"
        )
    ]


def _start_blockers(world: World, iwps: list[str]) -> set[str]:
    """The IWPs with an open or assigned blocking ``start`` constraint (the start is refused)."""
    found = world.rows(
        "SELECT DISTINCT c.subject_id AS s FROM cur_core_constraint c "
        "JOIN cur_core_record r ON r.id = c.id "
        "WHERE c.phase = 'start' AND c.severity = 'blocking' "
        "AND coalesce(r.status, 'Open') IN ('Open', 'Assigned')"
    )
    blocked = {str(r["s"]) for r in found}
    return {i for i in iwps if i in blocked}


def _clear_blocking(world: World, ready: list[Pair]) -> list[Pair]:
    """Clear the open blocking ``ready`` constraints of IWPs in the constraint check, one IWP at a
    time, until ``ISSUE_COUNT`` are Ready. Returns the Ready IWPs."""
    candidates = [
        (str(r["id"]), str(r["key"]))
        for r in world.rows(
            "SELECT DISTINCT r.id AS id, r.key AS key FROM cur_core_record r "
            "JOIN cur_core_constraint c ON c.subject_id = r.id "
            "JOIN cur_core_record k ON k.id = c.id "
            "WHERE r.type = 'awp.IWP' AND r.status = 'Constraint check' "
            "AND c.phase = 'ready' AND c.severity = 'blocking' "
            "AND coalesce(k.status, 'Open') IN ('Open', 'Assigned') ORDER BY r.key"
        )
    ]
    for iwp, _key in candidates:
        if len(ready) >= ISSUE_COUNT:
            break
        open_ids = world.rows(
            "SELECT c.id AS id FROM cur_core_constraint c "
            "JOIN cur_core_record k ON k.id = c.id "
            "WHERE c.subject_id = :s AND c.phase = 'ready' AND c.severity = 'blocking' "
            "AND coalesce(k.status, 'Open') IN ('Open', 'Assigned') ORDER BY k.key",
            s=iwp,
        )
        day = TODAY - timedelta(days=5)
        for row in open_ids:
            with world.on(day):
                world.run(
                    handle_clear_constraint,
                    ClearConstraint,
                    by=ADMIN,
                    constraint=str(row["id"]),
                    reason=CLEAR_REASON,
                    cleared_at=day.isoformat(),
                )
        with world.today():
            with open_uow(world.target) as uow:
                evaluate_now(uow, iwp, TODAY)
        ready = _ready(world)
    return ready


def _digest(world: World, iwp: str) -> str:
    with open_uow(world.target, readonly=True) as uow:
        return iwp_record_hash(uow.conn(), iwp)


def _release(world: World, iwp: str, *, started: bool) -> None:
    """Two sign-offs, the issue, and optionally the start, each on its own day before TODAY."""
    for offset, signer in zip((4, 3), SIGNERS, strict=True):
        with world.on(TODAY - timedelta(days=offset)):
            world.run(
                handle_sign_off_iwp,
                SignOffIwp,
                by=signer,
                iwp=iwp,
                record_hash=_digest(world, iwp),
            )
    with world.on(TODAY - timedelta(days=2)):
        world.run(
            handle_issue_iwp,
            IssueIwp,
            by=ADMIN,
            iwp=iwp,
            record_hash=_digest(world, iwp),
        )
    if started:
        with world.on(TODAY - timedelta(days=1)):
            world.run(
                handle_start_iwp_work,
                StartIwpWork,
                by=ADMIN,
                iwp_id=iwp,
                expected_version=world.version(iwp),
            )


def build(world: World, rng: random.Random) -> None:
    ready = _ready(world)
    if len(ready) < ISSUE_COUNT:
        ready = _clear_blocking(world, ready)
    if len(ready) < ISSUE_COUNT:
        raise RuntimeError("too few IWPs are Ready to release, even after clearing constraints")

    chosen = sorted(rng.sample(ready, ISSUE_COUNT), key=lambda pair: pair[1])
    blocked = _start_blockers(world, [iwp for iwp, _key in chosen])
    startable = [iwp for iwp, _key in chosen if iwp not in blocked]
    started = set(rng.sample(startable, min(START_COUNT, len(startable))))

    for iwp, _key in chosen:
        _release(world, iwp, started=iwp in started)


register("release", build, needs=("awp.IWP",))
