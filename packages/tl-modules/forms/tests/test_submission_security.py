"""Drafts and answers are confidential text: who may reach them, and what never echoes them."""

from __future__ import annotations

from typing import Any

import pytest
from forms_world import MARKER, World, answer, field
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.services.errors import RecordNotFoundError
from tl_core.services.proposals import accept_proposal, propose
from tl_core.util import new_ulid
from tl_mod_forms.commands import SubmitForm
from tl_mod_forms.errors import (
    MSG_UNKNOWN,
    FormAnswersError,
    FormsError,
    FormTemplateError,
)


def refused(world: World, who: str, name: str, **fields: Any) -> Exception:
    with pytest.raises(Exception) as caught:
        world.call(who, name, **fields)
    return caught.value


def test_a_hidden_subject_answers_like_an_absent_one_before_any_answer_is_read(
    world: World,
) -> None:
    tpl = world.template()
    hidden = world.hidden_record()
    failing = [answer("count", "not a number"), answer("nope", "x")]  # would fail validation
    before = world.count()
    seen: list[tuple[type[Exception], str]] = []
    for subject in (hidden, new_ulid()):
        for name in ("SaveFormDraft", "SubmitForm"):
            error = refused(
                world, "uma", name, template_id=tpl, subject_id=subject, answers=failing
            )
            seen.append((type(error), str(error)))
    assert set(seen) == {(RecordNotFoundError, MSG_UNKNOWN)}
    assert world.count() == before
    # the same refusal at a continued draft, and with answers that are fine
    draft = world.save(template=tpl).stream_id
    for subject in (hidden, new_ulid()):
        error = refused(
            world, "uma", "SaveFormDraft", draft_id=draft, subject_id=subject, answers=[]
        )
        assert (type(error), str(error)) == (RecordNotFoundError, MSG_UNKNOWN)


def test_a_reader_who_may_see_the_subject_files_the_form(world: World) -> None:
    tpl = world.template()
    hidden = world.hidden_record()
    # dora reads restricted records (the document controller); she is a user who may fill forms
    made = world.save(who="dora", template=tpl, subject_id=hidden)
    assert world.submission(made.stream_id)["subject_id"] == hidden


def test_another_persons_draft_is_unknown_to_save_discard_submit_and_accept(world: World) -> None:
    draft = world.save(template=world.template()).stream_id  # uma's
    calls = (
        ("rob", "SaveFormDraft", {"draft_id": draft, "answers": []}),
        ("rob", "DiscardFormDraft", {"submission_id": draft}),
        ("rob", "SubmitForm", {"draft_id": draft, "answers": [answer("topic", "x")]}),
        ("bea", "AcceptFormSubmission", {"submission_id": draft}),
        ("bea", "ReturnFormSubmission", {"submission_id": draft, "note": "x"}),
        ("bea", "VoidFormSubmission", {"submission_id": draft, "reason": "x"}),
    )
    absent = new_ulid()
    for who, name, fields in calls:
        error = refused(world, who, name, **fields)
        again = refused(
            world, who, name, **{k: absent if v == draft else v for k, v in fields.items()}
        )
        assert (
            (type(error), str(error))
            == (type(again), str(again))
            == (RecordNotFoundError, MSG_UNKNOWN)
        )
    assert world.state(draft) == "Draft" and world.submission(draft)["draft_saves"] == 1


def test_a_discarded_draft_of_another_author_is_unknown_too(world: World) -> None:
    draft = world.save(template=world.template()).stream_id
    world.call("uma", "DiscardFormDraft", submission_id=draft)
    error = refused(world, "bea", "VoidFormSubmission", submission_id=draft, reason="x")
    assert (type(error), str(error)) == (RecordNotFoundError, MSG_UNKNOWN)


def test_a_submitted_form_is_known_to_a_reviewer_but_not_to_another_author_of_a_save(
    world: World,
) -> None:
    sub = world.submit(template=world.template()).stream_id
    world.call("bea", "AcceptFormSubmission", submission_id=sub)  # a reviewer reads it
    error = refused(world, "rob", "SaveFormDraft", draft_id=sub, answers=[])
    assert (type(error), str(error)) == (RecordNotFoundError, MSG_UNKNOWN)  # not rob's to save


def test_a_form_of_another_project_is_unknown(world: World) -> None:
    sub = world.submit(template=world.template()).stream_id
    error = refused(world, "bea", "AcceptFormSubmission", scope="project:P999", submission_id=sub)
    assert (type(error), str(error)) == (RecordNotFoundError, MSG_UNKNOWN)


def test_no_exception_text_holds_a_marker_placed_in_an_answer(world: World) -> None:
    tpl = world.template(
        fields=[
            field("topic"),
            field("count", "number", required=False),
            field("pick", "choice", required=False, choices=["a", "b"]),
            field("when", "date", required=False),
            field("many", "multi", required=False, choices=["a", "b"]),
        ]
    )
    shapes: list[list[dict[str, Any]]] = [
        [answer("topic", MARKER * 400)],  # too long
        [answer("count", MARKER)],
        [answer("pick", MARKER)],
        [answer("when", MARKER)],
        [answer("many", [MARKER])],
        [answer(MARKER, "x")],  # an unknown id
        [{"q": "topic", "value": "x", MARKER: 1}],  # an unknown key
        [{"q": "topic", "value": "x", "note": MARKER * 400}],
        [answer("topic", "a"), answer("topic", MARKER)],  # twice
        [{"q": ["x", MARKER], "value": 1}],
        [{"value": MARKER}],
    ]
    for answers in shapes:
        for name in ("SaveFormDraft", "SubmitForm"):
            error = refused(world, "uma", name, template_id=tpl, answers=answers)
            assert isinstance(error, FormsError)
            assert MARKER not in str(error) and MARKER not in repr(error)
            assert MARKER not in " ".join(getattr(error, "problems", ()))
    assert world.count("cur_forms_submission") == 0


def test_a_marker_in_a_pydantic_refusal_is_not_echoed(world: World) -> None:
    for fields in (
        {"template_id": "t", "answers": [MARKER]},
        {"template_id": "t", "answers": MARKER},
        {"template_id": MARKER * 20, "answers": []},
    ):
        with pytest.raises(ValidationError) as caught:
            world.command("uma", "SubmitForm", **fields)
        assert MARKER not in str(caught.value)


def test_hostile_answers_are_refused_or_bounded_without_echo(world: World) -> None:
    sixty = [field(f"f{i}") for i in range(60)]
    tpl = world.template(fields=sixty)
    long_text = MARKER + "x" * 1000  # one over the 1000 character bound
    answers = [answer(f"f{i}", long_text) for i in range(60)]
    error = refused(world, "uma", "SaveFormDraft", template_id=tpl, answers=answers)
    assert isinstance(error, FormAnswersError) and MARKER not in str(error)
    assert len(error.problems) == 60 and len(str(error)) < 2000  # listed up to a bound
    ok = [answer(f"f{i}", "y" * 1000) for i in range(60)]
    assert world.save(template=tpl, answers=ok).version >= 1  # the largest legal draft is stored
    unknown = [answer(f"{MARKER}{i}", "v") for i in range(100)]
    error = refused(world, "uma", "SaveFormDraft", template_id=tpl, answers=unknown)
    assert MARKER not in str(error) and len(str(error)) < 2000


def test_a_deep_visible_when_chain_refuses_answers_for_a_question_not_shown(world: World) -> None:
    chain = [
        field("a", "choice", choices=["x", "y"]),
        field("b", "choice", choices=["x", "y"], visible_when={"q": "a", "is": "x"}),
        field("c", "choice", choices=["x", "y"], visible_when={"q": "b", "is": "x"}),
        field("d", "text", visible_when={"q": "c", "is": "x"}),
    ]
    tpl = world.template(fields=chain)
    error = refused(
        world, "uma", "SaveFormDraft", template_id=tpl,
        answers=[answer("a", "y"), answer("d", MARKER)],
    )  # fmt: skip
    assert isinstance(error, FormAnswersError) and "not shown" in str(error)
    assert MARKER not in str(error)
    world.save(template=tpl, answers=[answer("a", "x"), answer("b", "x"), answer("c", "x")])
    nested = {"not": {"not": {"not": {"not": {"q": "a", "is": "x"}}}}}  # four deep
    deep = [field("a"), field("b", visible_when=nested)]
    with pytest.raises(FormTemplateError, match="nested deeper"):
        world.call("uma", "DraftFormTemplate", title="x", fields=deep)


def test_the_answers_are_in_two_events_only(world: World) -> None:
    sub = world.submit(template=world.template(), answers=[answer("topic", MARKER)]).stream_id
    world.call("bea", "AcceptFormSubmission", submission_id=sub, note="ok")
    holding = {e["event_type"] for e in world.events() if MARKER in str(e["payload"])}
    assert holding == {"Submission.Submitted"}
    cards = world.rows("SELECT * FROM cur_feed_items")
    assert cards and not [c for c in cards if MARKER in str(c)]  # a card says who did what, no text


def test_the_proposal_of_an_agent_accepted_by_a_person_submits_as_that_person(world: World) -> None:
    world.agent("forms-bot")
    tpl = world.template()
    command = SubmitForm(
        actor="agent:forms-bot",
        source="mcp:forms-bot",
        scope="project:P123",
        template_id=tpl,
        answers=[answer("topic", "From the bot")],
    )
    with open_uow(world.db) as uow:
        proposal = propose(
            uow, tool="propose_form_submission", agent="agent:forms-bot", command=command,
            summary="File the toolbox talk",
        )  # fmt: skip
    assert proposal.status == "pending" and world.count("cur_forms_submission") == 0
    with open_uow(world.db) as uow:
        decided = accept_proposal(uow, proposal_id=proposal.proposal_id, by="user:rob")
    assert decided.status == "accepted" and decided.result_stream_id is not None
    sub = decided.result_stream_id
    row = world.submission(sub)
    assert row["author"] == "user:rob" and world.state(sub) == "Submitted"
    assert world.key(sub) == "P123-FRM-0001"
    actors = {(e["actor"], e["source"]) for e in world.events(sub)}
    assert actors == {("user:rob", "mcp:forms-bot")}
    # the author is the accepter: he may not accept it as a reviewer, a controller may
    error = refused(world, "ada", "SaveFormDraft", draft_id=sub, answers=[])
    assert isinstance(error, RecordNotFoundError)
    world.call("ada", "AcceptFormSubmission", submission_id=sub)
