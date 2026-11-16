"""Checklists and inspections: what the module's records and rules show each reader."""

from __future__ import annotations

import pytest
from insp_world import IWP, InspWorld, answers
from sqlalchemy import Connection
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.actions import Level
from tl_core.auth.module_roles import normalise_word
from tl_core.confidentiality import SUBJECT_LINKS
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality.actions import RULES, punch_actions, states_for
from tl_mod_quality.handlers.punch import SOURCE_REFUSED
from tl_mod_quality.module import QUALITY_COMMANDS

CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def hidden(world: InspWorld, record: str, viewer: cf.Viewer = cf.LOWEST) -> bool:
    with open_uow(world.db, readonly=True) as uow:
        conn: Connection = uow.conn()
        return cf.is_hidden(conn, record, viewer)


def test_an_inspection_follows_its_subject_and_a_checklist_is_always_readable(
    insp: InspWorld,
) -> None:
    secret = insp.hidden_record()
    open_iwp = insp.record(IWP, "IWP-1")
    mine, theirs = insp.plan(open_iwp), insp.plan(secret, who="dora")
    checklist = insp.checklist()
    assert not hidden(insp, mine) and not hidden(insp, checklist)
    assert hidden(insp, theirs) and not hidden(insp, theirs, CLEARED)


def test_every_command_on_a_hidden_inspection_answers_as_on_a_missing_one(insp: InspWorld) -> None:
    secret = insp.hidden_record()
    item = insp.scheduled(secret, who="dora")
    checklist = insp.checklist()
    before = insp.count()
    calls = {
        "ScheduleInspection": {
            "checklist": checklist,
            "scheduled_for": "2026-12-01",
            "inspector": "x",
        },
        "RecordInspectionResult": {"answers": answers()},
        "VerifyInspection": {},
        "ReinspectInspection": {},
        "CancelInspection": {"reason": "x"},
    }
    who = {"VerifyInspection": "sue", "CancelInspection": "sue", "RecordInspectionResult": "rob"}
    for name, fields in calls.items():
        texts = set()
        for target in (item, "no-such-id"):
            with pytest.raises(RecordNotFoundError) as caught:
                insp.call(who.get(name, "uma"), name, inspection=target, **fields)
            texts.add(str(caught.value))
        assert texts == {"no record with that id"}, name
    assert insp.count() == before
    assert insp.state_of(item, "Planned") == "Scheduled"
    insp.recorded(item, who="dora", answers=answers(q1="no"))
    assert insp.state_of(item, "Planned") == "Done"


def test_a_punch_item_raised_by_a_failed_answer_has_the_subjects_class(insp: InspWorld) -> None:
    secret = insp.hidden_record()
    item = insp.scheduled(secret, who="dora")
    insp.recorded(item, who="dora", answers=answers(q1="no"))
    (punch,) = insp.raised_by(item)
    assert punch["source_id"] == secret
    assert hidden(insp, punch["id"]) and not hidden(insp, punch["id"], CLEARED)
    with pytest.raises(RecordNotFoundError, match="no record with that id"):
        insp.call("uma", "ClearPunchItem", punch_item=punch["id"], note="n")


def test_the_subject_link_row_is_in_the_table_and_an_inspection_is_not_a_punch_source() -> None:
    assert ("quality.Inspection", "cur_quality_inspection", "id", "subject_id") in SUBJECT_LINKS
    assert "quality.Inspection" in SOURCE_REFUSED


def test_every_rule_level_equals_the_table_word_of_its_command() -> None:
    words = {c.model.__name__: c.access for c in QUALITY_COMMANDS}
    for rule in RULES:
        assert rule.level == normalise_word(words[rule.command]), rule.command
        assert states_for(rule.command, rule.record_types[0]) == rule.states
    assert [r.command for r in RULES][5:] == [
        "EditChecklist",
        "PublishChecklist",
        "RetireChecklist",
        "ReviseChecklist",
        "ScheduleInspection",
        "RecordInspectionResult",
        "VerifyInspection",
        "ReinspectInspection",
        "CancelInspection",
    ]
    assert states_for("ReinspectInspection", "quality.Inspection") == ("Done", "Verified")


def test_the_actions_table_offers_what_the_state_and_level_allow(insp: InspWorld) -> None:
    item = insp.plan()

    def offered(record: str, level: set[str]) -> list[str]:
        def holds(wanted: Level) -> bool:
            return wanted in level

        with open_uow(insp.db, readonly=True) as uow:
            return [o.command for o in punch_actions(uow.conn(), record, holds)]

    assert offered(item, {"user", "controller"}) == ["ScheduleInspection", "CancelInspection"]
    assert offered(item, {"user"}) == ["ScheduleInspection"]
    draft = insp.checklist(publish=False)
    assert offered(draft, {"user", "controller"}) == [
        "EditChecklist",
        "PublishChecklist",
        "RetireChecklist",
    ]


def test_generic_commands_are_refused_on_a_cancelled_inspection_and_a_retired_checklist(
    insp: InspWorld,
) -> None:
    from tl_core.services.errors import UnsupportedRecordTypeError
    from tl_mod_quality.guards import MSG_CANCELLED, MSG_RETIRED, not_cancelled, not_retired

    cancelled, retired = insp.plan(), insp.checklist()
    live_i, live_c = insp.plan(), insp.checklist(publish=False)
    insp.call("sue", "CancelInspection", inspection=cancelled, reason="x")
    insp.call("sue", "RetireChecklist", checklist=retired)
    with open_uow(insp.db, readonly=True) as uow:
        conn = uow.conn()
        not_cancelled(conn, live_i, None)
        not_retired(conn, live_c, None)
        for guard, record, message in (
            (not_cancelled, cancelled, MSG_CANCELLED),
            (not_retired, retired, MSG_RETIRED),
        ):
            with pytest.raises(UnsupportedRecordTypeError, match=message):
                guard(conn, record, None)
