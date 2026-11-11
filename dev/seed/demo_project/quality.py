"""quality section: the punch list of P200, built through the real punch commands (P2-PUNCH-T07).

29 punch items, one unit of work per command, as the roster people: ``hsato`` (quality inspector)
raises, verifies, reopens and voids; the foremen ``cbrooks`` and ``pnair`` are the assignees and
clear; ``lhartmann`` raises some and ``ipetrov`` raises the two restricted ones. Each command runs
read through its actor's own viewer (ADR-0016).

The final states are fixed by position (``FINAL``): 12 Open (3 overdue, one reopened once), 8
Cleared, 7 Verified, 2 Void (one from Open, one from Cleared). The sources come from the earlier
sections: 14 raised from IWPs, 6 from engineering tags, 2 from CWPs, 2 from restricted
correspondence items (``ipetrov`` restricts two internal letters of the correspondence section and
raises from them; both stay Open, because a restricted source is hidden from the foremen), and 5
free-standing. Without the correspondence section the two are free-standing too, and the section
says so in one line.

Dates are the project calendar: ``due_on`` is ISO, and every event falls on its day through
``world.on(day)``. Draws come from the section's own ``rng``; nothing reads the clock.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_quality.commands import (
    ClearPunchItem,
    RaisePunchItem,
    ReopenPunchItem,
    VerifyPunchItem,
    VoidPunchItem,
)
from tl_mod_quality.handlers.punch import (
    handle_clear_punch_item,
    handle_raise_punch_item,
    handle_reopen_punch_item,
    handle_verify_punch_item,
    handle_void_punch_item,
)

from dev.seed.demo_project.core import AREAS
from dev.seed.demo_project.registry import register
from dev.seed.demo_project.world import PROJECT, TODAY, World, actor_of

FOREMEN = ("cbrooks", "pnair")  # the assignees; each clears what is assigned to them
INSPECTOR = "hsato"  # raises, verifies, reopens and voids
CATEGORY_CYCLE = ("A", "B", "B", "A", "B", "C", "B", "A", "B", "C")  # 3 A : 5 B : 2 C
REOPENED = 4  # Cleared, then Reopened once: Open again, reopen_count 1
VOID_AFTER_CLEAR = 13  # Cleared, then Void; position 12 is voided from Open
RESTRICTED = (22, 23)  # positions of the two correspondence sources
OVERDUE = (0, 1, 2)  # Open, due before TODAY

#: The final state of each item, by position: 0-13 from IWPs, 14-19 from tags, 20-21 from CWPs,
#: 22-23 from restricted correspondence items, 24-28 free-standing.
FINAL: tuple[str, ...] = (
    "Open",
    "Open",
    "Open",
    "Open",
    "Open",
    "Cleared",
    "Cleared",
    "Verified",
    "Verified",
    "Verified",
    "Verified",
    "Verified",
    "Void",
    "Void",
    "Open",
    "Open",
    "Cleared",
    "Cleared",
    "Verified",
    "Verified",
    "Cleared",
    "Cleared",
    "Open",
    "Open",
    "Open",
    "Open",
    "Open",
    "Cleared",
    "Cleared",
)

SUBJECTS: tuple[str, ...] = (
    "Weld undersize at spool joint",
    "Support clip missing",
    "Insulation damaged at flange",
    "Valve tag plate not fitted",
    "Gasket leak at test flange",
    "Hydrotest blind left in line",
    "Paint damage on pipe rack steel",
    "Grout cracked under base plate",
    "Cable tray cover not fixed",
    "Drain plug missing on tank",
    "Earthing bond not made",
    "Label missing on instrument tubing",
)
RESTRICTED_SUBJECT = "Follow-up of a restricted client letter"
NO_SOURCES_NOTE = (
    "quality: no restricted correspondence sources (correspondence not built); "
    "the two items are free-standing"
)


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


def _letters(world: World) -> list[str]:
    """The internal letters of the correspondence section (the ones that can be restricted)."""
    return [
        str(r["id"])
        for r in world.rows(
            "SELECT r.id AS id FROM cur_core_record r "
            "JOIN cur_correspondence_correspondence c ON c.id = r.id "
            "WHERE r.scope = :s AND r.type = 'correspondence.Correspondence' "
            "AND c.confidentiality = 'internal' ORDER BY r.key",
            s=PROJECT,
        )
    ]


def _systems(world: World) -> list[tuple[str, str]]:
    """The awp WBS system level (depth 3) as (area code, system title), in code order."""
    return [
        (str(r["code"]).split(".")[1], str(r["title"]))
        for r in world.rows(
            "SELECT r.title AS title, n.code AS code FROM cur_awp_wbs_node n "
            "JOIN cur_core_record r ON r.id = n.id WHERE n.scope = :s AND n.depth = 3 "
            "ORDER BY n.code",
            s=PROJECT,
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


def _steps(index: int, state: str) -> tuple[str, ...]:
    """The commands after the raise that bring the item at ``index`` to ``state``."""
    if index == REOPENED:
        return ("clear", "reopen")
    if state == "Cleared":
        return ("clear",)
    if state == "Verified":
        return ("clear", "verify")
    if state == "Void":
        return ("clear", "void") if index == VOID_AFTER_CLEAR else ("void",)
    return ()


def build(world: World, rng: random.Random) -> None:
    iwps = _ids(world, "awp.IWP")
    tags = _ids(world, "engineering.Tag")
    cwps = _ids(world, "awp.CWP")
    letters = _letters(world)
    systems = _systems(world)
    if len(letters) < 2:
        print(NO_SOURCES_NOTE)
    sources: list[str | None] = [
        *_pick(rng, iwps, 14),
        *_pick(rng, tags, 6),
        *_pick(rng, cwps, 2),
        *_pick(rng, letters, 2),
        *([None] * 5),
    ]
    for index, state in enumerate(FINAL):
        restricted = index in RESTRICTED
        source = sources[index]
        raiser = "ipetrov" if restricted else ("lhartmann" if index % 5 == 3 else "hsato")
        foreman = rng.choice(FOREMEN)
        if systems:
            area, system = systems[rng.randrange(len(systems))]
        else:
            area = AREAS[rng.randrange(len(AREAS))][0]
            system = f"{rng.randint(40, 59)}-{rng.randint(1, 4):02d}"
        if restricted:
            raised = TODAY - timedelta(days=2)  # after the letters of the correspondence section
            due = TODAY + timedelta(days=rng.randint(3, 30))
        elif index in OVERDUE:
            due = TODAY - timedelta(days=rng.randint(2, 9))
            raised = due - timedelta(days=rng.randint(5, 12))
        else:
            raised = TODAY - timedelta(days=rng.randint(10, 30))
            due = (
                TODAY + timedelta(days=rng.randint(3, 30))
                if state == "Open"
                else raised + timedelta(days=rng.randint(10, 25))
            )
        clear_day = raised + timedelta(days=rng.randint(2, 6))
        verify_day = clear_day + timedelta(days=rng.randint(1, 3))
        subject = RESTRICTED_SUBJECT if restricted else SUBJECTS[index % len(SUBJECTS)]
        description = None if index % 4 else "Found on the walkdown; to be fixed before the test."
        if restricted and source is not None:
            _run(
                world,
                "ipetrov",
                raised,
                handle_set_confidentiality,
                SetCorrespondenceConfidentiality,
                stream_id=source,
                to_class="restricted",
                reason="Client letter restricted to the project team",
            )
        made = _run(
            world,
            raiser,
            raised,
            handle_raise_punch_item,
            RaisePunchItem,
            subject=subject,
            description=description,
            area=area,
            system=system,
            due_on=due.isoformat(),
            assignee=f"user:{foreman}",
            category=CATEGORY_CYCLE[index % len(CATEGORY_CYCLE)],
            from_record_id=source,
        )
        item = str(made.stream_id)
        day = raised
        for step in _steps(index, state):
            if step == "clear":
                day = clear_day
                _run(
                    world,
                    foreman,
                    day,
                    handle_clear_punch_item,
                    ClearPunchItem,
                    punch_item=item,
                    note="Rework done and checked by the foreman",
                )
            elif step == "verify":
                day = verify_day
                _run(
                    world,
                    INSPECTOR,
                    day,
                    handle_verify_punch_item,
                    VerifyPunchItem,
                    punch_item=item,
                )
            elif step == "reopen":
                _run(
                    world,
                    INSPECTOR,
                    clear_day + timedelta(days=1),
                    handle_reopen_punch_item,
                    ReopenPunchItem,
                    punch_item=item,
                    reason="The inspection found the weld undersize",
                )
            elif step == "void":
                _run(
                    world,
                    INSPECTOR,
                    day + timedelta(days=1),
                    handle_void_punch_item,
                    VoidPunchItem,
                    punch_item=item,
                    reason="Duplicate of another item",
                )


register("quality", build, needs=("quality.PunchItem",))
