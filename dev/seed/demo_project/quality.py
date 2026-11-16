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

After the punch items the section builds the checklists and inspections (P2-INSP-T03): the three
sample checklists of ``schema/fixtures/quality/checklists`` (``lhartmann`` publishes them; the
flange one is revised once) and 18 inspections whose final states are fixed by position
(``FINAL_INSP``). ``hsato`` plans, schedules and records; ``lhartmann`` verifies. A reject or a
conditional result raises its punch items through the handler, not through this section.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml
from tl_adapters.db import open_uow
from tl_core.confidentiality import use_viewer, viewer_for_actor
from tl_mod_correspondence.handlers.confidentiality import (
    SetCorrespondenceConfidentiality,
    handle_set_confidentiality,
)
from tl_mod_quality.commands import (
    CancelInspection,
    ClearPunchItem,
    CreateChecklist,
    EditChecklist,
    PlanInspection,
    PublishChecklist,
    RaisePunchItem,
    RecordInspectionResult,
    ReinspectInspection,
    ReopenPunchItem,
    ReviseChecklist,
    ScheduleInspection,
    VerifyInspection,
    VerifyPunchItem,
    VoidPunchItem,
)
from tl_mod_quality.handlers.checklist import (
    handle_create_checklist,
    handle_edit_checklist,
    handle_publish_checklist,
    handle_revise_checklist,
)
from tl_mod_quality.handlers.inspection import (
    handle_cancel_inspection,
    handle_plan_inspection,
    handle_record_inspection_result,
    handle_reinspect_inspection,
    handle_schedule_inspection,
    handle_verify_inspection,
)
from tl_mod_quality.handlers.punch import (
    handle_clear_punch_item,
    handle_raise_punch_item,
    handle_reopen_punch_item,
    handle_verify_punch_item,
    handle_void_punch_item,
)

from dev.seed.demo_project.core import AREAS
from dev.seed.demo_project.registry import Section, missing_types, register
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


QA_LEAD = "lhartmann"  # publishes the checklists and verifies the inspections
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures" / "quality" / "checklists"
CHECKLISTS = ("flange-makeup", "hydrotest-precheck", "scaffold-handover")
REVISED = "flange-makeup"
NO_INSPECTIONS_NOTE = "quality: inspections skipped (quality.Inspection not installed)"
NO_SUBJECTS_NOTE = "quality: no subjects for inspections"

#: The final state of each inspection, by position: 0-2 Planned, 3-6 Scheduled (3 is a hold point
#: on an IWP), 7-9 Done (accept, reject, conditional), 10-15 Verified, 16-17 Cancelled (from
#: Planned, from Scheduled).
FINAL_INSP: tuple[str, ...] = (
    "Planned",
    "Planned",
    "Planned",
    "Scheduled",
    "Scheduled",
    "Scheduled",
    "Scheduled",
    "Done",
    "Done",
    "Done",
    "Verified",
    "Verified",
    "Verified",
    "Verified",
    "Verified",
    "Verified",
    "Cancelled",
    "Cancelled",
)
#: The result recorded for each position that is recorded. Positions 14 and 15 are the
#: reinspections of the Verified reject (12) and conditional (13).
RESULTS: dict[int, str] = {
    7: "accept",
    8: "reject",
    9: "conditional",
    10: "accept",
    11: "accept",
    12: "reject",
    13: "conditional",
    14: "accept",
    15: "accept",
}
REINSPECTS: dict[int, int] = {14: 12, 15: 13}  # child position -> parent position
#: 5 hold, 4 witness, 5 review, 4 surveillance. A reinspection repeats its parent's point, so the
#: tuple holds the same word at 12 and 14 and at 13 and 15.
POINTS: tuple[str, ...] = (
    "hold",
    "witness",
    "review",
    "hold",
    "review",
    "surveillance",
    "witness",
    "hold",
    "review",
    "witness",
    "surveillance",
    "surveillance",
    "hold",
    "review",
    "hold",
    "review",
    "surveillance",
    "witness",
)
CWP_AT = (2, 5, 9, 12, 14, 16)  # the other 12 positions have an IWP as subject
INSP_TITLES: tuple[str, ...] = (
    "Flange make-up, pipe rack line 101",
    "Hydrotest pre-check, process unit package 12",
    "Scaffold handover, tank T-301 shell",
    "Flange make-up, reactor feed line",
    "Hydrotest pre-check, cooling water header",
    "Scaffold handover, fractionation column",
    "Flange make-up, steam tie-in",
    "Hydrotest pre-check, nitrogen header",
    "Scaffold handover, substation roof",
    "Flange make-up, tank farm manifold",
    "Hydrotest pre-check, flare line",
    "Scaffold handover, pipe rack level 2",
    "Flange make-up, pump discharge",
    "Hydrotest pre-check, drain header",
    "Scaffold handover, control room annex",
    "Flange make-up, instrument air line",
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


def _punch(world: World, rng: random.Random) -> None:
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


def _checklists(world: World) -> dict[str, str]:
    """Create and publish the three sample checklists as the QA lead; revise the flange one once
    (one question text edited, then published: version 1 Retired, version 2 Published). Returns
    the id of the Published version of each, by file name.

    A conditional result needs an optional question that can fail, and the samples have none, so
    the first optional yes/no question of each is made ``fails_when: no`` here (the fixtures
    stay as they are)."""
    published: dict[str, str] = {}
    for name in CHECKLISTS:
        data = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
        questions: list[dict[str, Any]] = data["questions"]
        optional = next(
            q for q in questions if q["kind"] == "yes_no_na" and q["required"] is not True
        )
        optional["fails_when"] = "no"
        day = TODAY - timedelta(days=45)
        made = _run(
            world,
            QA_LEAD,
            day,
            handle_create_checklist,
            CreateChecklist,
            title=data["title"],
            discipline=data["discipline"],
            questions=questions,
        )
        published[name] = str(made.stream_id)
        _run(
            world,
            QA_LEAD,
            day,
            handle_publish_checklist,
            PublishChecklist,
            checklist=published[name],
        )
        if name == REVISED:
            draft = _run(
                world,
                QA_LEAD,
                day + timedelta(days=1),
                handle_revise_checklist,
                ReviseChecklist,
                checklist=published[name],
            )
            edited = [dict(q) for q in questions]
            edited[0]["text"] = "Flange faces are clean, undamaged and free of scoring"
            _run(
                world,
                QA_LEAD,
                day + timedelta(days=1),
                handle_edit_checklist,
                EditChecklist,
                checklist=str(draft.stream_id),
                questions=edited,
            )
            _run(
                world,
                QA_LEAD,
                day + timedelta(days=1),
                handle_publish_checklist,
                PublishChecklist,
                checklist=str(draft.stream_id),
            )
            published[name] = str(draft.stream_id)
    return published


def _questions_of(world: World, checklist_id: str) -> list[dict[str, Any]]:
    found = world.scalar(
        "SELECT questions_json FROM cur_quality_checklist WHERE id = :i", i=checklist_id
    )
    return list(json.loads(found) if isinstance(found, (str, bytes)) else found)


def _answers(questions: list[dict[str, Any]], rng: random.Random, result: str) -> list[dict]:
    """An answer to every question. ``accept``: all in range. ``reject``: one required yes/no
    answered no and one required number out of range. ``conditional``: one optional yes/no
    answered no. The failures carry a note."""
    fail: set[str] = set()
    if result == "reject":
        yes_no = next(q for q in questions if q["fails_when"] == "no" and q["required"] is True)
        number = next(q for q in questions if q["fails_when"] == "out_of_range")
        fail = {yes_no["id"], number["id"]}
    elif result == "conditional":
        fail = {
            next(q for q in questions if q["fails_when"] == "no" and q["required"] is not True)[
                "id"
            ]
        }
    answers: list[dict] = []
    for q in questions:
        value: Any
        if q["kind"] == "yes_no_na":
            value = "no" if q["id"] in fail else "yes"
        elif q["kind"] == "number":
            low, high = float(q["min"]), float(q["max"])
            value = (
                round(high + (high - low) * 0.2 + 1, 1)
                if q["id"] in fail
                else round(rng.uniform(low + (high - low) * 0.3, low + (high - low) * 0.7), 1)
            )
        elif q["kind"] == "choice":
            value = q["choices"][rng.randrange(len(q["choices"]))]
        else:
            value = "As found"
        note = "Failed at the inspection; to be fixed and shown again" if q["id"] in fail else None
        answers.append({"q": q["id"], "value": value, "note": note})
    return answers


def _subjects(world: World, rng: random.Random) -> tuple[list[str], list[str]]:
    """The IWP and CWP ids, each in a drawn order (the inspections take them in turn)."""
    iwps, cwps = _ids(world, "awp.IWP"), _ids(world, "awp.CWP")
    rng.shuffle(iwps)
    rng.shuffle(cwps)
    return iwps, cwps


def _inspections(world: World, rng: random.Random, published: dict[str, str]) -> None:
    iwps, cwps = _subjects(world, rng)
    if not iwps and not cwps:
        print(NO_SUBJECTS_NOTE)
        return
    chosen: dict[int, tuple[str, bool, str]] = {}  # position -> subject, is an IWP, checklist id
    plans: dict[int, str] = {}  # position -> inspection id
    verify_day: dict[int, date] = {}  # position -> the day it was verified
    taken = {"iwp": 0, "cwp": 0}
    checks = [published[name] for name in CHECKLISTS]
    titles = iter(INSP_TITLES)
    for pos, state in enumerate(FINAL_INSP):
        parent = REINSPECTS.get(pos)
        planned = TODAY - timedelta(days=rng.randint(26, 40))
        scheduled = planned + timedelta(days=rng.randint(1, 3))
        visit = scheduled + timedelta(days=rng.randint(2, 5))
        done = visit + timedelta(days=rng.randint(0, 2))
        verified = done + timedelta(days=rng.randint(1, 3))
        if state == "Planned":
            planned = TODAY - timedelta(days=rng.randint(1, 5))
        elif state in ("Scheduled", "Cancelled"):
            planned = TODAY - timedelta(days=rng.randint(6, 20))
            scheduled = planned + timedelta(days=rng.randint(1, 4))
            visit = TODAY + timedelta(days=rng.randint(1, 14))
        if parent is not None:
            actor = "hsato"
            first = verify_day[parent] + timedelta(days=1)
            planned, scheduled, visit, done = (
                first,
                first + timedelta(days=1),
                first + timedelta(days=2),
                first + timedelta(days=3),
            )
            verified = done + timedelta(days=1)
            made = _run(
                world,
                actor,
                planned,
                handle_reinspect_inspection,
                ReinspectInspection,
                inspection=plans[parent],
                planned_on=planned.isoformat(),
            )
            subject, is_iwp, _ = chosen[parent]
            checklist = checks[parent % 3]
            chosen[pos] = (subject, is_iwp, checklist)
        else:
            want_cwp = pos in CWP_AT
            pool = (cwps, iwps) if want_cwp else (iwps, cwps)
            use = pool[0] if pool[0] else pool[1]
            is_iwp = use is iwps
            kind = "iwp" if is_iwp else "cwp"
            subject = use[taken[kind] % len(use)]
            taken[kind] += 1
            checklist = checks[pos % 3]
            chosen[pos] = (subject, is_iwp, checklist)
            plan_on = (
                (TODAY + timedelta(days=rng.randint(3, 30))) if state == "Planned" else planned
            )
            made = _run(
                world,
                "hsato",
                planned,
                handle_plan_inspection,
                PlanInspection,
                title=next(titles),
                subject_id=subject,
                point=POINTS[pos],
                for_iwp_id=subject if is_iwp else None,
                area=AREAS[rng.randrange(len(AREAS))][0],
                planned_on=plan_on.isoformat(),
            )
        item = str(made.stream_id)
        plans[pos] = item
        if state == "Planned":
            continue
        if state == "Cancelled" and pos == 16:
            _cancel(world, planned + timedelta(days=1), item)
            continue
        _run(
            world,
            "hsato",
            scheduled,
            handle_schedule_inspection,
            ScheduleInspection,
            inspection=item,
            checklist=checklist,
            scheduled_for=visit.isoformat(),
            inspector="user:hsato",
        )
        if state == "Cancelled":
            _cancel(world, scheduled + timedelta(days=1), item)
        elif state != "Scheduled":
            _run(
                world,
                "hsato",
                done,
                handle_record_inspection_result,
                RecordInspectionResult,
                inspection=item,
                answers=_answers(_questions_of(world, checklist), rng, RESULTS[pos]),
                note=None,
            )
            if state == "Verified":
                verify_day[pos] = verified
                _run(
                    world,
                    QA_LEAD,
                    verified,
                    handle_verify_inspection,
                    VerifyInspection,
                    inspection=item,
                )


def _cancel(world: World, day: date, item: str) -> None:
    _run(
        world,
        "hsato",
        day,
        handle_cancel_inspection,
        CancelInspection,
        inspection=item,
        reason="Superseded by the revised work sequence",
    )


def build(world: World, rng: random.Random) -> None:
    _punch(world, rng)
    published = (
        _checklists(world) if not missing_types(Section("c", build, ("quality.Checklist",))) else {}
    )
    if not published:
        return
    if missing_types(Section("i", build, ("quality.Inspection",))):
        print(NO_INSPECTIONS_NOTE)
        return
    _inspections(world, rng, published)


register("quality", build, needs=("quality.PunchItem",))
