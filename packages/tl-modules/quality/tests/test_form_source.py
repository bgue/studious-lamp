"""The form source of an inspection: what it offers each reader and what it maps."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from insp_world import QUESTIONS, InspWorld, answers
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.forms import rules
from tl_core.forms.registry import load_form_sources
from tl_core.forms.types import FormBinding, FormSource
from tl_mod_quality import insp_rules
from tl_mod_quality.form_source import InspectionFormSource, source

NOW = datetime(2026, 12, 1, tzinfo=UTC)
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def binding_for(world: InspWorld, record: str, viewer: cf.Viewer = cf.LOWEST) -> FormBinding | None:
    with open_uow(world.db, readonly=True) as uow:
        return InspectionFormSource().binding(uow.conn(), record, viewer, NOW)


def test_the_entry_point_names_a_form_source_for_inspections() -> None:
    assert isinstance(source(), FormSource)
    assert "quality.Inspection" in load_form_sources()


def test_a_scheduled_inspection_offers_the_questions_of_its_pinned_checklist(
    insp: InspWorld,
) -> None:
    item = insp.scheduled()
    got = binding_for(insp, item)
    assert got is not None and got.available and got.reason is None
    assert got.command == "RecordInspectionResult" and got.answers_arg == "answers"
    assert got.fixed_args == {"inspection": item}
    ref = got.template
    assert ref is not None and ref.fmt == 1 and ref.version == 1
    assert ref.source_type == "quality.Checklist"
    assert ref.source_id == insp.inspection_row(item)["checklist_id"]
    assert ref.content_hash == rules.content_hash(QUESTIONS, fmt=1)
    assert got.expected_version is not None and got.expected_version >= 1


@pytest.mark.parametrize(
    ("steps", "reason"),
    [("planned", "no_checklist"), ("done", "already_recorded"), ("cancelled", "cancelled")],
)
def test_an_inspection_that_takes_no_form_now_says_why(
    insp: InspWorld, steps: str, reason: str
) -> None:
    if steps == "planned":
        item = insp.plan()
    else:
        item = insp.scheduled()
        if steps == "done":
            insp.recorded(item, answers=answers())
        else:
            insp.call("sue", "CancelInspection", inspection=item, reason="not needed")
    got = binding_for(insp, item)
    assert got is not None and got.available is False and got.reason == reason
    assert got.command is None and got.template is None


def test_a_hidden_inspection_missing_id_and_other_type_answer_none(insp: InspWorld) -> None:
    secret = insp.hidden_record()
    item = insp.scheduled(secret, who="dora")
    assert binding_for(insp, item) is None  # the lowest viewer
    assert binding_for(insp, item, CLEARED) is not None  # the cleared one reads it
    assert binding_for(insp, "01J000000000000000000000") is None
    assert binding_for(insp, secret, CLEARED) is None  # a record that is not an inspection
    assert binding_for(insp, insp.checklist()) is None


def test_the_answers_become_the_commands_arguments_and_follow_insp_rules(
    insp: InspWorld,
) -> None:
    item = insp.scheduled()
    got = binding_for(insp, item)
    assert got is not None
    mine = InspectionFormSource()
    given = answers(q1="no")
    args = mine.arguments(got, given)
    assert args == {
        "inspection": item,
        "answers": given,
        "expected_version": got.expected_version,
    }
    assert mine.problems(QUESTIONS, given) == insp_rules.validate_answers(QUESTIONS, given) == []
    assert mine.problems(QUESTIONS, [{"q": "q1", "value": "maybe", "note": None}])
    assert mine.problems(QUESTIONS, []) == ["q1: answer required"]
