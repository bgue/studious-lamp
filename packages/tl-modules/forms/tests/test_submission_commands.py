"""Submission commands: save, submit, discard, numbering at submit (P2-FORMS S3, D6, D10, D11)."""

from __future__ import annotations

from typing import Any

import pytest
from forms_world import World, answer, field
from pydantic import ValidationError
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_forms.errors import (
    MSG_DRAFT_SAVES,
    MSG_NOT_FILLABLE,
    MSG_NOT_PUBLISHED,
    MSG_PROJECT,
    MSG_UNKNOWN,
    FormAnswersError,
    FormRuleError,
    FormsScopeError,
    FormStateError,
    StaleVersionError,
)


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def allocations(world: World) -> int:
    """Keys taken for submissions (the templates take TPL numbers of their own)."""
    found = world.events(kind="Numbering.Allocated")
    return len([e for e in found if e["payload"].get("record_type") == "forms.Submission"])


def test_save_twice_counts_the_saves_takes_no_number_and_resumes_by_draft_id(world: World) -> None:
    tpl = world.template()
    first = world.save(template=tpl)
    draft = first.stream_id
    assert first.key is None and world.key(draft) is None and world.state(draft) == "Draft"
    second = world.save(draft_id=draft, answers=[answer("topic", "Ladders", "note")])
    assert second.stream_id == draft and second.version > first.version
    row = world.submission(draft)
    assert row["draft_saves"] == 2 and row["author"] == "user:uma" and row["submitted_on"] is None
    assert allocations(world) == 0 and world.key(draft) is None
    assert [e["payload"]["save_no"] for e in world.events(draft, "Submission.DraftSaved")] == [1, 2]
    assert world.events(draft, "Record.Created")[0]["payload"]["key"] is None
    title = world.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=draft)
    assert title == "Toolbox talk"  # the template's title, never an answer
    assert '"Ladders"' in world.scalar("SELECT answers_json FROM cur_forms_submission")


def test_the_draft_pins_the_template_and_copies_the_answer_class_once(world: World) -> None:
    tpl = world.template(answer_class="restricted")
    draft = world.save(template=tpl).stream_id
    row = world.submission(draft)
    assert (row["template_id"], row["template_version"]) == (tpl, 1)
    assert row["template_hash"] == world.template_row(tpl)["content_hash"]
    assert row["answer_class"] == "restricted"


def test_submit_of_a_draft_takes_the_number_and_writes_the_key_event(world: World) -> None:
    tpl = world.template()
    draft = world.save(template=tpl).stream_id
    made = world.submit(draft_id=draft)
    assert made.key == "P123-FRM-0001" and world.key(draft) == "P123-FRM-0001"
    assert world.state(draft) == "Submitted" and allocations(world) == 1
    updated = world.events(draft, "Record.Updated")
    assert [e["payload"]["changes"] for e in updated] == [{"key": [None, "P123-FRM-0001"]}]
    row = world.submission(draft)
    assert row["submitted_on"] and row["draft_saves"] == 1
    kinds = [e["event_type"] for e in world.events(draft)]
    assert kinds == [
        "Record.Created",
        "Submission.DraftSaved",
        "Record.Updated",
        "Submission.Submitted",
        "Workflow.Transitioned",
    ]
    assert len({e["correlation_id"] for e in world.events(draft)[2:]}) == 1


def test_submit_with_no_draft_takes_the_number_at_creation(world: World) -> None:
    made = world.submit(template=world.template())
    assert made.key == "P123-FRM-0001" and world.state(made.stream_id) == "Submitted"
    assert allocations(world) == 1
    assert world.submission(made.stream_id)["draft_saves"] == 0
    assert [e["event_type"] for e in world.events(made.stream_id)] == [
        "Record.Created",
        "Submission.Submitted",
        "Workflow.Transitioned",
    ]


def test_a_discarded_draft_takes_no_number_so_the_sequence_has_no_gap(world: World) -> None:
    tpl = world.template()
    gone = world.save(template=tpl).stream_id
    world.call("uma", "DiscardFormDraft", submission_id=gone)
    assert world.state(gone) == "Discarded" and world.key(gone) is None
    assert world.events(gone, "Submission.DraftDiscarded")
    assert world.submit(template=tpl).key == "P123-FRM-0001"
    assert world.submit(who="rob", template=tpl).key == "P123-FRM-0002"
    assert allocations(world) == 2


def test_a_returned_form_resubmitted_keeps_its_number(world: World) -> None:
    tpl = world.template()
    first = world.submit(template=tpl)
    world.call("ada", "ReturnFormSubmission", submission_id=first.stream_id, note="Add a count")
    assert world.state(first.stream_id) == "Returned"
    again = world.submit(draft_id=first.stream_id, answers=[answer("topic", "Ladders v2")])
    assert again.key == "P123-FRM-0001" and world.state(first.stream_id) == "Submitted"
    assert allocations(world) == 1
    assert world.submit(template=tpl).key == "P123-FRM-0002"
    # a returned form may be saved again before it is resubmitted
    world.call("ada", "ReturnFormSubmission", submission_id=first.stream_id, note="Again")
    world.save(draft_id=first.stream_id, answers=[answer("topic", "v3")])
    assert (
        world.state(first.stream_id) == "Returned"
        and world.submission(first.stream_id)["draft_saves"] == 1
    )


def test_the_save_bound_refuses_the_save_past_it(world: World) -> None:
    world.setting("forms.draft_saves_max", 2)
    draft = world.save(template=world.template()).stream_id
    world.save(draft_id=draft)
    before = world.count()
    assert (
        raises(FormRuleError, world, "uma", "SaveFormDraft", draft_id=draft, answers=[])
        == MSG_DRAFT_SAVES
    )
    assert world.count() == before
    world.submit(draft_id=draft)  # a submit is not a save: the bound does not stop it
    assert world.state(draft) == "Submitted"


def test_bound_and_public_templates_are_refused_with_the_fixed_text(world: World) -> None:
    bound = world.template(bound_record_type="quality.PunchItem")
    public = world.template(
        fields=[field("a"), field("b")],
        intake="public",
        purpose="request",
        accepts_as=["SubmitForm"],
    )
    for tpl in (bound, public):
        for name in ("SaveFormDraft", "SubmitForm"):
            msg = raises(FormRuleError, world, "uma", name, template_id=tpl, answers=[])
            assert msg == MSG_NOT_FILLABLE


def test_a_draft_template_is_not_published_and_cannot_be_filled(world: World) -> None:
    tpl = world.template(publish=False)
    assert (
        raises(FormRuleError, world, "uma", "SaveFormDraft", template_id=tpl, answers=[])
        == MSG_NOT_PUBLISHED
    )


def test_a_retired_template_takes_no_new_draft_but_an_existing_draft_submits(world: World) -> None:
    tpl = world.template()
    draft = world.save(template=tpl).stream_id
    world.call("ada", "RetireFormTemplate", template_id=tpl)
    for name in ("SaveFormDraft", "SubmitForm"):
        assert (
            raises(
                FormRuleError, world, "uma", name, template_id=tpl, answers=[answer("topic", "x")]
            )
            == MSG_NOT_PUBLISHED
        )
    world.save(draft_id=draft, answers=[answer("topic", "more")])
    made = world.submit(draft_id=draft)
    assert made.key == "P123-FRM-0001" and world.submission(draft)["template_id"] == tpl


def test_company_scope_is_refused(world: World) -> None:
    tpl = world.template()
    for name in ("SaveFormDraft", "SubmitForm"):
        msg = raises(
            FormsScopeError, world, "uma", name, scope="company", template_id=tpl, answers=[]
        )
        assert msg == MSG_PROJECT
    draft = world.save(template=tpl).stream_id
    assert (
        raises(
            FormsScopeError, world, "uma", "DiscardFormDraft", scope="company", submission_id=draft
        )
        == MSG_PROJECT
    )


def test_a_save_may_be_partial_and_a_submit_must_be_complete(world: World) -> None:
    tpl = world.template()
    world.save(template=tpl, answers=[])  # nothing answered yet: a draft
    msg = raises(FormAnswersError, world, "uma", "SubmitForm", template_id=tpl, answers=[])
    assert "topic: answer required" in msg
    before = world.count()
    msg = raises(
        FormAnswersError, world, "uma", "SaveFormDraft", template_id=tpl,
        answers=[answer("count", "abc")],
    )  # fmt: skip
    assert "count:" in msg and "abc" not in msg and world.count() == before


def test_problems_name_field_ids_and_never_repeat_a_value_or_an_unknown_id(world: World) -> None:
    tpl = world.template()
    marker = "zq-secret-4410"
    hostile = [answer("count", marker), answer(marker, "v"), answer("topic", marker * 200)]
    msg = raises(FormAnswersError, world, "uma", "SaveFormDraft", template_id=tpl, answers=hostile)
    assert marker not in msg and "count: must be a number" in msg and "no such question" in msg


def test_save_and_submit_refuse_the_states_that_do_not_take_them(world: World) -> None:
    tpl = world.template()
    done = world.submit(template=tpl).stream_id
    for name in ("SaveFormDraft", "SubmitForm"):
        assert "Submitted" in raises(FormStateError, world, "uma", name, draft_id=done, answers=[])
    assert "Submitted" in raises(
        FormStateError, world, "uma", "DiscardFormDraft", submission_id=done
    )
    gone = world.save(template=tpl).stream_id
    world.call("uma", "DiscardFormDraft", submission_id=gone)
    assert "Discarded" in raises(
        FormStateError, world, "uma", "SubmitForm", draft_id=gone, answers=[]
    )


def test_expected_version_is_checked_on_save_submit_and_discard(world: World) -> None:
    draft = world.save(template=world.template()).stream_id
    stale = world.version(draft) - 1
    for name, answers in (
        ("SaveFormDraft", []),
        ("SubmitForm", [answer("topic", "x")]),
    ):
        with pytest.raises(StaleVersionError):
            world.call("uma", name, draft_id=draft, expected_version=stale, answers=answers)
    with pytest.raises(StaleVersionError):
        world.call("uma", "DiscardFormDraft", submission_id=draft, expected_version=stale)
    world.save(draft_id=draft, answers=[], expected_version=world.version(draft))


def test_an_unknown_template_draft_or_subject_answers_the_one_text(world: World) -> None:
    for fields in (
        {"template_id": new_ulid(), "answers": []},
        {"draft_id": new_ulid(), "answers": []},
        {"template_id": world.template(), "subject_id": new_ulid(), "answers": []},
    ):
        assert raises(RecordNotFoundError, world, "uma", "SaveFormDraft", **fields) == MSG_UNKNOWN


def test_a_subject_in_the_project_is_kept_and_one_in_another_project_is_refused(
    world: World,
) -> None:
    tpl = world.template()
    here = world.record("awp.IWP", "IWP-1")
    elsewhere = world.record("awp.IWP", "IWP-2", scope="project:P999")
    made = world.save(template=tpl, subject_id=here)
    assert world.submission(made.stream_id)["subject_id"] == here
    assert (
        raises(
            RecordNotFoundError,
            world,
            "uma",
            "SaveFormDraft",
            template_id=tpl,
            subject_id=elsewhere,
            answers=[],
        )
        == MSG_UNKNOWN
    )


def test_a_submit_names_the_template_or_the_draft_not_both_and_not_neither() -> None:
    from tl_mod_forms.commands import SubmitForm

    base: dict[str, Any] = {"actor": "user:a", "source": "t", "scope": "project:P1", "answers": []}
    with pytest.raises(ValidationError):
        SubmitForm(**base)
    with pytest.raises(ValidationError):
        SubmitForm(**base, template_id="a", draft_id="b")
    with pytest.raises(ValidationError):
        SubmitForm(**base, template_id="a", author="user:x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        SubmitForm(**{**base, "answers": [{}] * 121}, template_id="a")


def test_a_format_1_template_takes_complete_answers(world: World) -> None:
    keys = ("id", "text", "kind", "required", "unit", "min", "max", "choices", "fails_when")
    q1 = {k: v for k, v in field("q1", "yes_no_na").items() if k in keys}
    tpl = world.template(fields=[q1], format_version=1)
    msg = raises(
        FormAnswersError,
        world,
        "uma",
        "SaveFormDraft",
        template_id=tpl,
        answers=[{"q": "q1", "value": "yes"}],
    )
    assert "missing key 'note'" in msg
    world.submit(template=tpl, answers=[answer("q1", "yes")])
