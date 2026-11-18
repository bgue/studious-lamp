"""Inspection commands: plan, schedule, record the result, verify, reinspect, cancel (P2-INSP S2).

An inspection is one record of ``quality.Inspection``, hidden through its subject (``subject_id``,
``tl_core.confidentiality.SUBJECT_LINKS``). Every id a command is given goes through
``load_record``: a record the actor may not read, one in another project and one that does not
exist answer alike. Every state move is a ``by_module`` workflow transition run in the same unit of
work as the module's own event. The result is computed by ``insp_rules.result_of``; a reject or a
conditional result raises one punch item per failed question in that same unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, text
from tl_core.auth.errors import ForbiddenError
from tl_core.confidentiality import SUBJECT_LINKS
from tl_core.ledger import NewEvent, iso_utc
from tl_core.services.commands import Command, CommandResult
from tl_core.services.records import create_module_record
from tl_core.uow import UnitOfWork
from tl_core.util import utcnow

from tl_mod_quality.actions import states_for
from tl_mod_quality.errors import InspectionRuleError, InspectionStateError
from tl_mod_quality.guards import MSG_CANCELLED
from tl_mod_quality.handlers.checklist import as_list
from tl_mod_quality.handlers.common import (
    SUBMISSION,
    RecordRef,
    append,
    correlated,
    load_record,
    move,
    record_state,
    require_project,
    require_version,
    silent,
)
from tl_mod_quality.handlers.punch import create_punch_item
from tl_mod_quality.insp_rules import failed_questions, result_of, validate_answers
from tl_mod_quality.names import (
    CANCELLED,
    CHECKLIST,
    CHECKLIST_TABLE,
    DRAFT,
    INSPECTION,
    INSPECTION_CANCELLED,
    INSPECTION_PLANNED,
    INSPECTION_RESULT_RECORDED,
    INSPECTION_SCHEDULED,
    INSPECTION_TABLE,
    INSPECTION_VERIFIED,
    PLANNED,
    PUBLISHED,
    T_CANCEL,
    T_RECORD,
    T_SCHEDULE,
    T_VERIFY,
)

if TYPE_CHECKING:
    from tl_mod_quality.commands import (
        CancelInspection,
        PlanInspection,
        RecordInspectionResult,
        ReinspectInspection,
        ScheduleInspection,
        VerifyInspection,
    )

MSG_SELF_VERIFY = "the person who recorded an inspection may not verify it"
MSG_CHAIN = (
    "that record names a subject that itself names a subject; plan the inspection against "
    "the work itself"
)
MSG_ANSWERS = "the answers do not fit the checklist: "
MSG_NOT_REINSPECTABLE = "only a rejected or conditional inspection can be reinspected"
MSG_FUTURE = "the time is in the future"
MSG_BEFORE_PLANNED = "the time is before the day the inspection was planned"
MSG_NO_CHECKLIST = "the inspection has no checklist"
_ROW_SQL = text(f"SELECT * FROM {INSPECTION_TABLE} WHERE id = :id")
_CHECKLIST_SQL = text(f"SELECT questions_json FROM {CHECKLIST_TABLE} WHERE id = :id")
_TYPE_SQL = text("SELECT type FROM cur_core_record WHERE id = :id")
#: Record type -> (table, id column, subject column): the records that name a subject.
_NAMES_SUBJECT = {row[0]: (row[1], row[2], row[3]) for row in SUBJECT_LINKS}


@dataclass(frozen=True)
class Inspection:
    """An inspection as the handlers read it: the envelope, the typed row and the state."""

    ref: RecordRef
    state: str
    row: dict[str, Any]

    @property
    def id(self) -> str:
        return self.ref.id

    @property
    def key(self) -> str:
        return self.ref.key or ""


def load_inspection(uow: UnitOfWork, scope: str, inspection_id: str) -> Inspection:
    """The inspection; ``RecordNotFoundError`` (the same words) when it is hidden (its subject
    is), absent, in another project or not an inspection."""
    ref = load_record(uow, scope, inspection_id, (INSPECTION,))
    row = uow.conn().execute(_ROW_SQL, {"id": ref.id}).mappings().first()
    if row is None:
        raise LookupError(f"no inspection row for {ref.id}")
    return Inspection(ref=ref, state=record_state(uow, ref.id, PLANNED), row=dict(row))


def require_state(item: Inspection, command: str) -> None:
    """The inspection is not cancelled and is in a state ``command`` takes (``actions.RULES``)."""
    if item.state == CANCELLED:
        raise InspectionStateError(MSG_CANCELLED)
    needed = states_for(command, INSPECTION)
    if item.state not in needed:
        raise InspectionStateError(
            f"an inspection that is {item.state} does not take {command}; "
            f"it needs {' or '.join(needed)}"
        )


def _subject_of(conn: Connection, record_id: str, record_type: str) -> str | None:
    """The record ``record_id`` names as its subject, ``None`` when it names none."""
    if record_type == "core.Constraint":
        sql = "SELECT subject_id FROM cur_core_constraint WHERE id = :id"
    elif record_type in _NAMES_SUBJECT:
        table, id_column, subject_column = _NAMES_SUBJECT[record_type]
        sql = f"SELECT {subject_column} FROM {table} WHERE {id_column} = :id"
    else:
        return None
    found = conn.execute(text(sql), {"id": record_id}).scalar_one_or_none()
    return None if found is None else str(found)


def require_short_chain(uow: UnitOfWork, subject: RecordRef) -> None:
    """The subject names no subject, or one that names none: the chain from the inspection stays
    within the two hops of the confidentiality join (design section 8)."""
    conn = uow.conn()
    first = _subject_of(conn, subject.id, subject.record_type)
    if first is None:
        return
    kind = conn.execute(_TYPE_SQL, {"id": first}).scalar_one_or_none()
    if kind is not None and _subject_of(conn, first, str(kind)) is not None:
        raise InspectionRuleError(MSG_CHAIN)


def _plan(
    uow: UnitOfWork,
    cmd: Command,
    *,
    title: str,
    subject_id: str,
    for_iwp_id: str,
    point: str,
    area: str | None,
    planned_on: str | None,
    reinspection_of_id: str | None,
) -> CommandResult:
    return create_module_record(
        uow,
        cmd,
        record_type=INSPECTION,
        title=title,
        key=None,
        extra_events=[
            NewEvent(
                event_type=INSPECTION_PLANNED,
                payload=silent(
                    {
                        "subject_id": subject_id,
                        "for_iwp_id": for_iwp_id,
                        "point": point,
                        "area": area,
                        "planned_on": planned_on,
                        "reinspection_of_id": reinspection_of_id,
                    }
                ),
            )
        ],
    )


def handle_plan_inspection(uow: UnitOfWork, cmd: PlanInspection) -> CommandResult:
    """Plan an inspection in state Planned, numbered per project. The subject (and the work
    package, when named) must be readable by the actor: a hidden, absent or foreign id answers
    ``no record with that id``, as every other read of the module does."""
    require_project(cmd)
    cmd = correlated(cmd)
    subject = load_record(uow, cmd.scope, cmd.subject_id, exclude=(SUBMISSION,))
    require_short_chain(uow, subject)
    iwp = subject if cmd.for_iwp_id is None else load_record(uow, cmd.scope, cmd.for_iwp_id)
    return _plan(
        uow,
        cmd,
        title=cmd.title,
        subject_id=subject.id,
        for_iwp_id=iwp.id,
        point=cmd.point,
        area=cmd.area,
        planned_on=cmd.planned_on,
        reinspection_of_id=None,
    )


def handle_schedule_inspection(uow: UnitOfWork, cmd: ScheduleInspection) -> CommandResult:
    """Planned or Scheduled to Scheduled with a Published checklist; its version is pinned."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_inspection(uow, cmd.scope, cmd.inspection)
    require_state(item, "ScheduleInspection")
    checklist = load_record(uow, cmd.scope, cmd.checklist, (CHECKLIST,))
    state = record_state(uow, checklist.id, DRAFT)
    if state != PUBLISHED:
        raise InspectionStateError(
            f"a checklist that is {state} cannot be scheduled; it needs {PUBLISHED}"
        )
    version = (
        uow.conn()
        .execute(
            text(f"SELECT checklist_version FROM {CHECKLIST_TABLE} WHERE id = :id"),
            {"id": checklist.id},
        )
        .scalar_one()
    )
    require_version(uow, item.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        item.id,
        INSPECTION,
        [
            NewEvent(
                event_type=INSPECTION_SCHEDULED,
                payload=silent(
                    {
                        "checklist_id": checklist.id,
                        "checklist_version": int(version),
                        "scheduled_for": cmd.scheduled_for,
                        "inspector": cmd.inspector,
                    }
                ),
            )
        ],
    )
    moved = move(uow, cmd, item.id, T_SCHEDULE)
    return CommandResult(
        stream_id=item.id,
        key=item.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def _done_at(at: datetime | None, planned_on: str) -> str:
    """``at`` as the event carries it, now when not given; never in the future and never before
    the day the inspection was planned."""
    now = utcnow()
    moment = now if at is None else at
    if moment > now:
        raise InspectionRuleError(MSG_FUTURE)
    if iso_utc(moment)[:10] < planned_on:
        raise InspectionRuleError(MSG_BEFORE_PLANNED)
    return iso_utc(moment)


def _pinned_questions(uow: UnitOfWork, item: Inspection) -> list[dict[str, Any]]:
    """The questions of the checklist the inspection was scheduled with (a Published checklist
    never changes, so its version is the list)."""
    checklist_id = item.row["checklist_id"]
    if checklist_id is None:
        raise InspectionStateError(MSG_NO_CHECKLIST)
    found = uow.conn().execute(_CHECKLIST_SQL, {"id": checklist_id}).scalar_one()
    return as_list(found)


def _raise_punch_items(
    uow: UnitOfWork,
    cmd: RecordInspectionResult,
    item: Inspection,
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    failed: list[str],
) -> list[str]:
    """One punch item per failed question, in this unit of work: category A for a failed required
    question on a hold point, else B. The source is the inspection's subject (so the item is
    visible exactly as the subject is); the ``raised_against`` link points at the inspection."""
    by_question = {question["id"]: question for question in questions}
    by_answer = {answer["q"]: answer for answer in answers}
    ids: list[str] = []
    for qid in failed:
        question = by_question[qid]
        note = by_answer[qid].get("note")
        hold = item.row["point"] == "hold" and question.get("required") is True
        made = create_punch_item(
            uow,
            cmd,
            subject=f"{item.key} {qid}: {question['text']}"[:200],
            description=note if note else None,
            area=item.row["area"],
            system=None,
            due_on=None,
            assignee=None,
            category="A" if hold else "B",
            source_id=item.row["subject_id"],
            link_to=item.id,
        )
        ids.append(made.stream_id)
    return ids


def handle_record_inspection_result(uow: UnitOfWork, cmd: RecordInspectionResult) -> CommandResult:
    """Scheduled to Done. The answers are checked against the pinned checklist, the result is
    computed, and a reject or conditional result raises its punch items in the same unit of work.
    ``recorded_by`` is the actor."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_inspection(uow, cmd.scope, cmd.inspection)
    require_state(item, "RecordInspectionResult")
    questions = _pinned_questions(uow, item)
    problems = validate_answers(questions, cmd.answers)
    if problems:
        raise InspectionRuleError(MSG_ANSWERS + "; ".join(problems))
    require_version(uow, item.id, cmd.expected_version)
    done_at = _done_at(cmd.at, str(item.row["planned_on"] or item.ref.created_on))
    result = result_of(questions, cmd.answers)
    failed = failed_questions(questions, cmd.answers) if result != "accept" else []
    punch_ids = _raise_punch_items(uow, cmd, item, questions, cmd.answers, failed)
    recorded = append(
        uow,
        cmd,
        item.id,
        INSPECTION,
        [
            NewEvent(
                event_type=INSPECTION_RESULT_RECORDED,
                payload=silent(
                    {
                        "answers": cmd.answers,
                        "result": result,
                        "done_at": done_at,
                        "note": cmd.note,
                        "punch_item_ids": punch_ids,
                    }
                ),
            )
        ],
    )
    moved = move(uow, cmd, item.id, T_RECORD)
    return CommandResult(
        stream_id=item.id,
        key=item.key,
        version=moved.version,
        events=[*recorded.events, *moved.events],
    )


def handle_verify_inspection(uow: UnitOfWork, cmd: VerifyInspection) -> CommandResult:
    """Done to Verified, by someone other than the person who recorded it."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_inspection(uow, cmd.scope, cmd.inspection)
    require_state(item, "VerifyInspection")
    if cmd.actor == item.row["recorded_by"]:
        raise ForbiddenError(MSG_SELF_VERIFY)
    require_version(uow, item.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        item.id,
        INSPECTION,
        [
            NewEvent(
                event_type=INSPECTION_VERIFIED,
                payload=silent({"verified_on": utcnow().date().isoformat()}),
            )
        ],
    )
    moved = move(uow, cmd, item.id, T_VERIFY)
    return CommandResult(
        stream_id=item.id,
        key=item.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


def handle_reinspect_inspection(uow: UnitOfWork, cmd: ReinspectInspection) -> CommandResult:
    """Plan a new inspection that repeats a Done or Verified one with a reject or conditional
    result (``reinspection_of_id``). The old inspection is not touched."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_inspection(uow, cmd.scope, cmd.inspection)
    require_state(item, "ReinspectInspection")
    if item.row["result"] not in ("reject", "conditional"):
        raise InspectionStateError(MSG_NOT_REINSPECTABLE)
    require_version(uow, item.id, cmd.expected_version)
    return _plan(
        uow,
        cmd,
        title=item.ref.title,
        subject_id=str(item.row["subject_id"]),
        for_iwp_id=str(item.row["for_iwp_id"] or item.row["subject_id"]),
        point=str(item.row["point"]),
        area=item.row["area"],
        planned_on=cmd.planned_on,
        reinspection_of_id=item.id,
    )


def handle_cancel_inspection(uow: UnitOfWork, cmd: CancelInspection) -> CommandResult:
    """Planned or Scheduled to Cancelled, the final state."""
    require_project(cmd)
    cmd = correlated(cmd)
    item = load_inspection(uow, cmd.scope, cmd.inspection)
    require_state(item, "CancelInspection")
    require_version(uow, item.id, cmd.expected_version)
    done = append(
        uow,
        cmd,
        item.id,
        INSPECTION,
        [NewEvent(event_type=INSPECTION_CANCELLED, payload=silent({"reason": cmd.reason}))],
    )
    moved = move(uow, cmd, item.id, T_CANCEL)
    return CommandResult(
        stream_id=item.id,
        key=item.key,
        version=moved.version,
        events=[*done.events, *moved.events],
    )


__all__ = [
    "Inspection",
    "handle_cancel_inspection",
    "handle_plan_inspection",
    "handle_record_inspection_result",
    "handle_reinspect_inspection",
    "handle_schedule_inspection",
    "handle_verify_inspection",
    "load_inspection",
]
