"""Intake item commands: accept through the seam, reject (P2-FORMS S7c, D17, D18)."""

from __future__ import annotations

from typing import Any

import pytest
from forms_world import World, answer, intake_body
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.services.errors import InvalidProposalError, ProposalAccessError, RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_forms.commands import AcceptIntakeItem
from tl_mod_forms.errors import (
    MSG_NOT_ACCEPTED_AS,
    MSG_PROJECT,
    MSG_UNKNOWN,
    FormRuleError,
    FormsScopeError,
    FormStateError,
)


def refused(world: World, who: str, name: str, **fields: Any) -> BaseException:
    with pytest.raises(Exception) as caught:
        world.call(who, name, **fields)
    return caught.value


class Staged:
    def __init__(self, world: World, accepts_as: list[str] | None = None) -> None:
        self.world = world
        self.intake = world.intake_template(accepts_as=accepts_as)
        self.general = world.template()
        self.code = world.stage_code(self.intake)
        self.item = world.stage_item(self.code)

    def args(self, **more: Any) -> dict[str, Any]:
        return {"template_id": self.general, "answers": [answer("topic", "Ladders")], **more}

    def accept(self, who: str = "ada", **more: Any) -> Any:
        fields: dict[str, Any] = {
            "item_id": self.item,
            "command_type": "SubmitForm",
            "command_args": self.args(),
        }
        return self.world.call(who, "AcceptIntakeItem", **{**fields, **more})


@pytest.fixture
def staged(world: World) -> Staged:
    return Staged(world)


def received_event(world: World, item: str) -> str:
    return str(
        world.scalar(
            "SELECT event_id FROM events WHERE stream_id = :i "
            "AND event_type = 'IntakeItem.Received'",
            i=item,
        )
    )


# --- accept ------------------------------------------------------------------------------------


def test_accept_as_submit_form_runs_as_the_controller_and_clears_the_body(staged: Staged) -> None:
    w = staged.world
    made = staged.accept("ada")
    assert w.state(staged.item, "Pending") == "Accepted" and made.version == w.version(staged.item)
    (sub,) = w.rows("SELECT id FROM cur_forms_submission")
    (submitted,) = w.events(str(sub["id"]), "Submission.Submitted")
    assert submitted["actor"] == "user:ada"
    assert submitted["source"] == f"intake:{staged.code}"
    assert submitted["causation_id"] == received_event(w, staged.item)
    assert w.submission(str(sub["id"]))["author"] == "user:ada"
    (accepted,) = w.events(staged.item, "IntakeItem.Accepted")
    claim = {"name": "Sam Smith", "company": "Acme Scaffolding"}
    assert accepted["payload"]["accepted_as"] == "SubmitForm"
    assert accepted["payload"]["on_behalf_of_claim"] == claim
    assert "555" not in repr(w.events(staged.item))
    cause = accepted["payload"]["cause_event_id"]
    assert cause in {
        str(r["event_id"])
        for r in w.rows("SELECT event_id FROM events WHERE stream_id = :s", s=sub["id"])
    }
    assert w.body_rows(staged.item) == 0
    assert len(w.events(staged.item, "IntakeItem.Purged")) == 1
    row = w.rows("SELECT * FROM cur_forms_intake_item WHERE id = :i", i=staged.item)[0]
    assert (row["accepted_as"], row["accepted_by"]) == ("SubmitForm", "user:ada")
    assert row["purged_at"] is not None
    # the staged text is not in the typed event: the controller's answers are
    assert "Need a ladder" not in repr(submitted["payload"])


def test_a_body_with_no_claim_gives_a_null_claim(world: World) -> None:
    s = Staged(world)
    world.stage_item(s.code)
    item = world.stage_item(s.code, intake_body(name=None, company=None))
    world.call(
        "ada", "AcceptIntakeItem", item_id=item, command_type="SubmitForm", command_args=s.args()
    )
    assert world.events(item, "IntakeItem.Accepted")[0]["payload"]["on_behalf_of_claim"] is None


def test_a_refusal_inside_the_nested_command_leaves_the_item_pending_and_untouched(
    staged: Staged,
) -> None:
    w = staged.world
    before = w.count()
    error = refused(
        w, "ada", "AcceptIntakeItem", item_id=staged.item, command_type="SubmitForm",
        command_args=staged.args(answers=[answer("count", "not a number")]),
    )  # fmt: skip
    assert type(error).__name__ == "FormAnswersError"
    assert w.state(staged.item, "Pending") == "Pending"
    assert w.body_rows(staged.item) == 1
    assert w.count() == before and not w.rows("SELECT id FROM cur_forms_submission")


def test_a_failure_after_the_nested_command_rolls_the_nested_events_back(
    staged: Staged, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tl_mod_forms.handlers import intake

    w = staged.world

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("late failure")

    monkeypatch.setattr(intake, "move", boom)
    before = w.count()
    with pytest.raises(RuntimeError):
        staged.accept("ada")
    assert w.count() == before and w.body_rows(staged.item) == 1
    assert not w.rows("SELECT id FROM cur_forms_submission")


def test_command_type_outside_accepts_as_a_core_command_and_an_unknown_name_are_refused(
    world: World,
) -> None:
    s = Staged(
        world, accepts_as=["SaveFormDraft"]
    )  # a proposable? no: module command, not in accepts_as
    texts: set[tuple[type[BaseException], str]] = set()
    for name in ("SubmitForm", "CreateRecord", "TransitionWorkflow", "NoSuchCommand"):
        error = refused(
            world, "ada", "AcceptIntakeItem", item_id=s.item, command_type=name, command_args={}
        )
        texts.add((type(error), str(error)))
    assert texts == {(FormRuleError, MSG_NOT_ACCEPTED_AS)}
    for name in ("CreateRecord", "NoSuchCommand"):
        assert name not in MSG_NOT_ACCEPTED_AS
    assert world.state(s.item, "Pending") == "Pending" and world.body_rows(s.item) == 1


def test_a_name_in_accepts_as_that_the_seam_refuses_is_refused_with_a_fixed_text(
    world: World,
) -> None:
    s = Staged(world, accepts_as=["CreateRecord"])  # in the template, but no module proposable
    error = refused(
        world,
        "ada",
        "AcceptIntakeItem",
        item_id=s.item,
        command_type="CreateRecord",
        command_args={},
    )
    assert type(error) is InvalidProposalError and "CreateRecord" not in str(error)
    assert world.state(s.item, "Pending") == "Pending"


def test_command_args_naming_actor_or_source_cannot_impersonate(staged: Staged) -> None:
    w = staged.world
    staged.accept(
        "ada",
        command_args=staged.args(
            actor="user:bea", source="intake:other", scope="project:P999", actor_roles=["admin"]
        ),
    )
    (sub,) = w.rows("SELECT id FROM cur_forms_submission")
    (submitted,) = w.events(str(sub["id"]), "Submission.Submitted")
    assert (submitted["actor"], submitted["source"]) == ("user:ada", f"intake:{staged.code}")
    assert (
        w.rows("SELECT scope FROM events WHERE stream_id = :s", s=sub["id"])[0]["scope"]
        == "project:P123"
    )


def test_a_controller_without_the_nested_commands_word_is_refused(staged: Staged) -> None:
    """The seam gets the controller's holder: an actor with no word anywhere is refused inside the
    unit and nothing stays (the handler is called directly: the outer check would stop them)."""
    w = staged.world
    cmd = AcceptIntakeItem(
        actor="agent:nobody", source="test", scope="project:P123", item_id=staged.item,
        command_type="SubmitForm", command_args=staged.args(),
    )  # fmt: skip
    from tl_mod_forms.module import FORMS_COMMANDS

    handler = next(c.handler for c in FORMS_COMMANDS if c.model is AcceptIntakeItem)
    before = w.count()
    with (
        pytest.raises(ProposalAccessError),
        open_uow(w.db) as uow,
        cf.use_viewer(cf.viewer_for_actor(uow.conn(), cmd.actor)),
    ):
        handler(uow, cmd)
    assert w.count() == before and w.body_rows(staged.item) == 1
    assert w.state(staged.item, "Pending") == "Pending"


def test_accept_twice_is_refused(staged: Staged) -> None:
    staged.accept()
    before = staged.world.count()
    error = refused(
        staged.world,
        "ada",
        "AcceptIntakeItem",
        item_id=staged.item,
        command_type="SubmitForm",
        command_args=staged.args(),
    )
    assert type(error) is FormStateError and "Accepted" in str(error)
    assert staged.world.count() == before


def test_accept_checks_the_version(staged: Staged) -> None:
    with pytest.raises(Exception, match="changed since"):
        staged.accept(expected_version=99)
    assert staged.world.state(staged.item, "Pending") == "Pending"


def test_accept_in_a_company_scope_is_refused(staged: Staged) -> None:
    error = refused(
        staged.world,
        "ada",
        "AcceptIntakeItem",
        scope="company",
        item_id=staged.item,
        command_type="SubmitForm",
        command_args={},
    )
    assert (type(error), str(error)) == (FormsScopeError, MSG_PROJECT)


def test_oversized_command_args_are_refused_at_the_model(staged: Staged) -> None:
    with pytest.raises(ValidationError):
        staged.world.command(
            "ada", "AcceptIntakeItem", item_id=staged.item, command_type="SubmitForm",
            command_args={"answers": ["x" * 70_000]},
        )  # fmt: skip


# --- reject ------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["spam", "duplicate", "not_ours", "unclear"])
def test_reject_with_each_reason_keeps_the_body(world: World, reason: str) -> None:
    s = Staged(world)
    made = world.call("bea", "RejectIntakeItem", item_id=s.item, reason=reason)
    assert world.state(s.item, "Pending") == "Rejected" and made.version == world.version(s.item)
    row = world.rows("SELECT * FROM cur_forms_intake_item WHERE id = :i", i=s.item)[0]
    assert (row["rejected_reason"], row["rejected_by"]) == (reason, "user:bea")
    assert world.body_rows(s.item) == 1
    assert not world.events(s.item, "IntakeItem.Purged")


def test_reject_with_an_unknown_reason_is_refused(staged: Staged) -> None:
    for reason in ("", "rude", "SPAM"):
        with pytest.raises(ValidationError):
            staged.world.command("ada", "RejectIntakeItem", item_id=staged.item, reason=reason)


def test_a_decided_item_takes_neither_command(staged: Staged) -> None:
    w = staged.world
    w.call("ada", "RejectIntakeItem", item_id=staged.item, reason="spam")
    for name, fields in (
        ("RejectIntakeItem", {"reason": "spam"}),
        ("AcceptIntakeItem", {"command_type": "SubmitForm", "command_args": staged.args()}),
    ):
        error = refused(w, "ada", name, item_id=staged.item, **fields)
        assert type(error) is FormStateError and "Rejected" in str(error)
    assert w.body_rows(staged.item) == 1


# --- hidden looks missing ----------------------------------------------------------------------


def test_an_item_whose_code_context_is_hidden_answers_as_an_absent_id(world: World) -> None:
    s = Staged(world)
    code = world.stage_code(s.intake, context_id=world.hidden_record("privileged"))
    hidden_item = world.stage_item(code)
    other_project = refused(
        world, "ada", "RejectIntakeItem", scope="project:P999", item_id=s.item, reason="spam"
    )
    absent = new_ulid()
    seen: set[tuple[type[BaseException], str]] = set()
    for item in (hidden_item, absent):
        for name, fields in (
            ("AcceptIntakeItem", {"command_type": "SubmitForm", "command_args": s.args()}),
            ("RejectIntakeItem", {"reason": "spam"}),
        ):
            error = refused(world, "ada", name, item_id=item, **fields)
            seen.add((type(error), str(error)))
    seen.add((type(other_project), str(other_project)))
    assert seen == {(RecordNotFoundError, MSG_UNKNOWN)}
    assert world.state(hidden_item, "Pending") == "Pending" and world.body_rows(hidden_item) == 1


def test_a_reader_who_may_see_the_context_decides_its_item(world: World) -> None:
    """A context the controller may read does not hide its item: the check is the viewer's."""
    s = Staged(world)
    visible_context = world.record("awp.IWP", "IWP-2")
    code = world.stage_code(s.intake, context_id=visible_context)
    item = world.stage_item(code)
    world.call("ada", "RejectIntakeItem", item_id=item, reason="unclear")
    assert world.state(item, "Pending") == "Rejected"
