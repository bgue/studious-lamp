"""permits section: permits to work, isolations and gas tests of P200, built through the real
commands (P2-PTW-T03).

20 permits, 8 isolations and 14 gas tests, one unit of work per command, as the roster people:
the foremen ``cbrooks`` and ``pnair`` request, are the holders, apply isolations, link them, record
gas tests, suspend and hand back; ``ipetrov`` approves, rejects, issues, resumes, closes and
verifies the isolations the foremen applied; ``lhartmann`` verifies the one ``ipetrov`` applied. The
verifier is never the applier and the approver never the requester. Each command runs read through
its actor's own viewer (ADR-0016).

The shown state of each permit is fixed by position (``FINAL``): 2 Requested, 3 Approved, 5 Active,
2 Lapsed, 2 Suspended, 1 Handed back, 2 Closed, 2 Rejected, 1 Cancelled. Of the 5 Active, one
(``RESUMED``) was suspended by a person and resumed, so a Resume event exists. Lapsed is derived,
never made: those permits were issued on an earlier day and their ``valid_until`` is before TODAY
(no job run, no clock read). The permit types cycle over the six types by position, the areas over
the six area codes. 12 permits name an IWP of the awp section, 2 a CWP, the rest nothing.

Dates are the project calendar: every event falls on its day through ``world.on(day)`` (noon UTC),
derived from ``TODAY``. A gas test is taken in the minutes before the noon it is recorded at. Draws
come from the section's own ``rng``; nothing reads the clock. With no IWPs (``--sections
core,permits``) the section prints one line, and the permits name no record.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_permits.commands import (
    ApprovePermit,
    CancelPermit,
    ClosePermit,
    HandBackPermit,
    IssuePermit,
    RejectPermit,
    RequestPermit,
    ResumePermit,
    SuspendPermit,
)
from tl_mod_permits.handlers.gas_test import handle_record_gas_test
from tl_mod_permits.handlers.isolation import (
    handle_apply_isolation,
    handle_link_isolation,
    handle_remove_isolation,
    handle_verify_isolation,
)
from tl_mod_permits.handlers.permit import (
    handle_approve_permit,
    handle_cancel_permit,
    handle_close_permit,
    handle_hand_back_permit,
    handle_issue_permit,
    handle_reject_permit,
    handle_request_permit,
    handle_resume_permit,
    handle_suspend_permit,
)
from tl_mod_permits.iso_commands import (
    ApplyIsolation,
    LinkIsolation,
    RecordGasTest,
    RemoveIsolation,
    VerifyIsolation,
)
from tl_mod_permits.names import ENERGY_KINDS, PERMIT_TYPES
from tl_mod_permits.types_table import load_types

from dev.seed.demo_project.core import AREAS, PEOPLE
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, TODAY, World, actor_of

FOREMEN = ("cbrooks", "pnair")  # request, hold, apply, link, test, suspend and hand back
CONTROLLER = "ipetrov"  # approves, rejects, issues, resumes, closes, verifies, removes
SECOND_VERIFIER = "lhartmann"  # verifies the isolation the controller applied
NAMES = {p.username: p.name for p in PEOPLE}
NO_SUBJECTS_NOTE = "permits: no subjects for permits"

#: The final state of each permit, by position (types cycle over ``PERMIT_TYPES`` by position).
FINAL: tuple[str, ...] = (
    "Active",  # 0 hot work
    "Active",  # 1 confined space
    "Requested",  # 2 work at height
    "Approved",  # 3 excavation
    "Active",  # 4 isolation
    "Requested",  # 5 general
    "Active",  # 6 hot work
    "Suspended",  # 7 confined space: a failing gas test stopped it
    "Active",  # 8 work at height: suspended by a person, then resumed
    "Approved",  # 9 excavation
    "Approved",  # 10 isolation: an Applied isolation is linked
    "Suspended",  # 11 general: suspended by a person with a reason
    "Lapsed",  # 12 hot work
    "Closed",  # 13 confined space: its isolation is Removed
    "Rejected",  # 14 excavation
    "Handed back",  # 15 general
    "Closed",  # 16 isolation: its isolation is Removed
    "Lapsed",  # 17 general
    "Rejected",  # 18 hot work
    "Cancelled",  # 19 confined space
)
RESUMED = 8  # Active, after a Suspend and a Resume
GAS_STOPPED = 7  # Suspended by its own failing gas test
#: The record each permit names: an IWP, a CWP or nothing, by position (12, 2 and 6).
SUBJECT_KIND: tuple[str | None, ...] = (
    "iwp",
    "iwp",
    "cwp",
    "iwp",
    "iwp",
    None,
    "iwp",
    "iwp",
    "iwp",
    None,
    "iwp",
    "cwp",
    "iwp",
    "iwp",
    None,
    "iwp",
    "iwp",
    None,
    None,
    None,
)
#: Where each position's isolation is made and how far it goes: (Verified, Applied, Removed).
ISOLATED = {
    1: "Verified",
    4: "Verified",
    7: "Verified",
    10: "Applied",
    13: "Removed",
    16: "Removed",
}
FREE_ISOLATIONS = 2  # Applied, linked to no permit
POINT_AT = 1  # the isolation of this permit names a core record (a tag) as its point

DESCRIPTIONS: tuple[str, ...] = (
    "Cut and weld pipe supports on the rack",
    "Enter the surge drum for the internal inspection",
    "Erect scaffold at the top of the fractionation column",
    "Trench for the new cooling water line",
    "Open and blank the nitrogen header for the tie-in",
    "Move and set the cable drums at the substation",
    "Grind and weld the nozzle repair on the tank shell",
    "Clean the sump vessel before the lining repair",
    "Fit the safety rails on the pipe rack level 2",
    "Excavate for the earthing grid at the control room",
    "Lock out the transfer pump for the seal change",
    "Hoist the strainer to the platform",
    "Weld the support clips on the steam line",
    "Inspect the tank T-301 bottom",
    "Dig the pit for the drain header",
    "Walk and tag the flare line",
    "Isolate the cooling water pump for the coupling alignment",
    "Clear the laydown area at the tank farm",
    "Weld the flange on the reactor feed line",
    "Enter the column for the tray check",
)
LOCATIONS: tuple[str, ...] = (
    "Pipe rack, bay 3",
    "Surge drum V-102",
    "Fractionation column, top platform",
    "Tank farm, north side",
    "Nitrogen header, tie-in point",
    "Substation yard",
)
INSTRUMENTS = ("Gas monitor GM-01", "Gas monitor GM-02", "Gas monitor GM-03")
POINTS: tuple[str, ...] = (
    "Surge drum feed pump motor breaker",
    "Nitrogen header isolation valve",
    "Cooling water pump suction valve",
    "Transfer pump discharge valve",
    "Reactor feed line spade",
    "Drain header isolation valve",
    "Flare line blind",
    "Steam tie-in block valve",
)
METHODS = ("Lock and tag", "Spade and tag", "Double block and bleed", "Breaker locked off")


def _ids(world: World, record_type: str) -> list[str]:
    """The ids of every record of ``record_type`` in the project, in key order."""
    return [
        str(r["id"])
        for r in world.rows(
            "SELECT id FROM cur_core_record WHERE scope = :s AND type = :t ORDER BY key",
            s=PROJECT,
            t=record_type,
        )
    ]


def _pick(rng: random.Random, pool: list[str], count: int) -> list[str | None]:
    """``count`` sources drawn from ``pool``; ``None`` for each one the pool cannot supply."""
    picked: list[str | None] = list(rng.sample(pool, count) if len(pool) >= count else [])
    return picked + [None] * (count - len(picked))


def _run(world: World, who: str, day: date, handler: Any, model: Any, **fields: Any) -> Any:
    """One command as ``who`` on ``day``, read through ``who``'s own viewer (ADR-0016)."""
    with open_uow(world.target, readonly=True) as uow:
        viewer = viewer_for_actor(uow.conn(), actor_of(who))
    with world.on(day), use_viewer(viewer):
        return world.run(handler, model, by=who, **fields)


def _taken(day: date, minutes_before: int) -> datetime:
    """A gas test time: ``minutes_before`` the noon (UTC) of ``day``, when it is entered."""
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=UTC) - timedelta(
        minutes=minutes_before
    )


class _Builder:
    """The state shared by the permit loop: the world, the draws, the counters."""

    def __init__(self, world: World, rng: random.Random) -> None:
        self.world = world
        self.rng = rng
        self.isolations = 0  # made so far; energies, lock and tag numbers follow it
        self.tests = 0
        self.tags = _ids(world, "engineering.Tag")

    # --- isolations ---------------------------------------------------------------------------

    def isolation(self, day: date, applier: str, point_record: str | None = None) -> str:
        """Apply one isolation on ``day`` as ``applier``; returns its id."""
        n = self.isolations
        self.isolations += 1
        made = _run(
            self.world,
            applier,
            day,
            handle_apply_isolation,
            ApplyIsolation,
            point_text=POINTS[n % len(POINTS)],
            energy=ENERGY_KINDS[n % len(ENERGY_KINDS)],
            method=METHODS[n % len(METHODS)],
            lock_number=f"L-{n + 1:02d}",
            tag_number=f"T-{n + 1:02d}",
            point_record_id=point_record,
        )
        return str(made.stream_id)

    def verify(self, day: date, isolation: str, applier: str) -> None:
        """Verify as a person other than the applier."""
        who = SECOND_VERIFIER if applier == CONTROLLER else CONTROLLER
        _run(
            self.world,
            who,
            day,
            handle_verify_isolation,
            VerifyIsolation,
            isolation=isolation,
        )

    # --- gas tests ------------------------------------------------------------------------------

    def gas(self, day: date, who: str, permit: str, minutes_before: int, result: str) -> None:
        """One gas test, entered at noon of ``day`` and taken ``minutes_before`` that."""
        rng = self.rng
        n = self.tests
        self.tests += 1
        if result == "pass":
            readings = {
                "o2_pct": f"{rng.uniform(20.4, 21.0):.1f}",
                "lel_pct": f"{rng.uniform(0.0, 1.5):.1f}",
                "h2s_ppm": f"{rng.uniform(0.0, 2.0):.1f}",
                "co_ppm": f"{rng.uniform(0.0, 10.0):.1f}",
            }
        else:
            readings = {
                "o2_pct": f"{rng.uniform(20.4, 21.0):.1f}",
                "lel_pct": f"{rng.uniform(8.0, 14.0):.1f}",
                "h2s_ppm": f"{rng.uniform(0.0, 2.0):.1f}",
                "co_ppm": None,
            }
        _run(
            self.world,
            who,
            day,
            handle_record_gas_test,
            RecordGasTest,
            permit=permit,
            instrument_text=INSTRUMENTS[n % len(INSTRUMENTS)],
            taken_at=_taken(day, minutes_before),
            note="Failed at the work face; work stopped" if result == "fail" else None,
            **readings,
        )

    # --- one permit -----------------------------------------------------------------------------

    def permit(self, pos: int, state: str, subject: str | None) -> None:
        run, rng = self.world, self.rng
        kind = PERMIT_TYPES[pos % len(PERMIT_TYPES)]
        rule = load_types()[kind]
        holder = rng.choice(FOREMEN)
        area = AREAS[pos % len(AREAS)][0]
        # the day it goes live (issue), is decided (decided) and is asked for (asked)
        if state == "Active":
            issue = TODAY - timedelta(days=1) if pos == RESUMED else TODAY
        elif state == "Suspended":
            issue = TODAY - timedelta(days=rng.randint(1, 2))
        elif state in ("Lapsed", "Handed back"):
            issue = TODAY - timedelta(days=rng.randint(3, 6))  # Lapsed: valid_until before TODAY
        elif state == "Closed":
            issue = TODAY - timedelta(days=rng.randint(8, 14))
        else:  # not issued: Requested, Approved, Rejected, Cancelled
            issue = TODAY + timedelta(days=rng.randint(0, 2))
        if state in ("Requested", "Approved"):
            decided = TODAY - timedelta(days=rng.randint(0, 1))
            asked = (
                TODAY - timedelta(days=rng.randint(0, 2))
                if state == "Requested"
                else (decided - timedelta(days=rng.randint(0, 2)))
            )
        elif state in ("Rejected", "Cancelled"):
            asked = TODAY - timedelta(days=rng.randint(4, 9))
            decided = asked + timedelta(days=1)
        else:
            decided = issue - timedelta(days=1)
            asked = decided - timedelta(days=rng.randint(0, 1))
        made = _run(
            run,
            holder,
            asked,
            handle_request_permit,
            RequestPermit,
            permit_type=kind,
            for_record_id=subject,
            area=area,
            location_text=LOCATIONS[pos % len(LOCATIONS)],
            work_description=DESCRIPTIONS[pos],
            holder=NAMES[holder],
            needed_from=issue.isoformat(),
            needed_until=(issue + timedelta(days=1)).isoformat(),
        )
        permit = str(made.stream_id)
        if state == "Requested":
            return
        if state == "Rejected":
            _run(
                run,
                CONTROLLER,
                decided,
                handle_reject_permit,
                RejectPermit,
                permit=permit,
                reason="The work description does not name the isolation points",
            )
            return
        if state == "Cancelled":
            _run(
                run,
                holder,
                decided,
                handle_cancel_permit,
                CancelPermit,
                permit=permit,
                reason="The job moved to the next shutdown",
            )
            return
        _run(run, CONTROLLER, decided, handle_approve_permit, ApprovePermit, permit=permit)
        iso = None
        if pos in ISOLATED:
            applier = CONTROLLER if pos == 7 else rng.choice(FOREMEN)
            point = self.tags[0] if pos == POINT_AT and self.tags else None
            iso = self.isolation(decided, applier, point)
            if ISOLATED[pos] != "Applied":
                self.verify(decided, iso, applier)
            _run(
                run,
                holder,
                decided,
                handle_link_isolation,
                LinkIsolation,
                permit=permit,
                isolation=iso,
            )
        if state == "Approved":
            return
        self._issued(pos, state, permit, kind, holder, issue, rule.needs_gas_test)
        if iso is not None and ISOLATED[pos] == "Removed":
            _run(
                run,
                CONTROLLER,
                issue + timedelta(days=2),
                handle_remove_isolation,
                RemoveIsolation,
                isolation=iso,
            )

    def _issued(
        self, pos: int, state: str, permit: str, kind: str, holder: str, day: date, gas: bool
    ) -> None:
        """Test, issue and carry the permit from Active to its final state."""
        run, rng = self.world, self.rng
        if gas:
            if pos in (0, 12):  # a failing test on the Approved permit, then a retest
                self.gas(day, holder, permit, rng.randint(90, 150), "fail")
            self.gas(day, holder, permit, rng.randint(10, 60), "pass")
        _run(
            run,
            CONTROLLER,
            day,
            handle_issue_permit,
            IssuePermit,
            permit=permit,
            precautions=[p.id for p in load_types()[kind].precautions],
        )
        if gas and pos in (0, 1, 6, 12, 13):  # a second passing test in the shift
            self.gas(day, holder, permit, rng.randint(1, 8), "pass")
        if pos == GAS_STOPPED:
            self.gas(day, holder, permit, 1, "fail")  # suspends the permit (the S3 rule)
        elif pos == RESUMED or state == "Suspended":
            _run(
                run,
                holder,
                day,
                handle_suspend_permit,
                SuspendPermit,
                permit=permit,
                reason="Wind above the limit for the lift; work stopped",
            )
        if pos == RESUMED:
            _run(
                run,
                CONTROLLER,
                day + timedelta(days=1),
                handle_resume_permit,
                ResumePermit,
                permit=permit,
            )
        if state in ("Handed back", "Closed"):
            _run(
                run,
                holder,
                day,
                handle_hand_back_permit,
                HandBackPermit,
                permit=permit,
                handback_note="Work finished; the area is clear and left safe",
            )
        if state == "Closed":
            _run(
                run,
                CONTROLLER,
                day + timedelta(days=1),
                handle_close_permit,
                ClosePermit,
                permit=permit,
            )


def build(world: World, rng: random.Random) -> None:
    iwps, cwps = _ids(world, "awp.IWP"), _ids(world, "awp.CWP")
    if not iwps:
        print(NO_SUBJECTS_NOTE)
    iwp_pool = iter(_pick(rng, iwps, SUBJECT_KIND.count("iwp")))
    cwp_pool = iter(_pick(rng, cwps, SUBJECT_KIND.count("cwp")))
    builder = _Builder(world, rng)
    for pos, state in enumerate(FINAL):
        kind = SUBJECT_KIND[pos]
        subject = next(iwp_pool) if kind == "iwp" else next(cwp_pool) if kind == "cwp" else None
        builder.permit(pos, state, subject if iwps else None)
    for _ in range(FREE_ISOLATIONS):  # Applied, nobody's permit yet
        day = TODAY - timedelta(days=rng.randint(0, 1))
        builder.isolation(day, rng.choice(FOREMEN))


register("permits", build, needs=("permits.Permit", "awp.IWP"))
