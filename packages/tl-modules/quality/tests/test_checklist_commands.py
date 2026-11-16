"""The five checklist commands: effects, state table, words, versions, revision, bounds."""

from __future__ import annotations

from typing import Any

import pytest
from insp_world import QUESTIONS, InspWorld
from pydantic import ValidationError
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import RecordNotFoundError
from tl_mod_quality.commands import CreateChecklist, EditChecklist
from tl_mod_quality.errors import ChecklistRuleError, ChecklistStateError, StaleVersionError
from tl_mod_quality.guards import MSG_RETIRED
from tl_mod_quality.handlers.checklist import MSG_NOT_READY, MSG_NOTHING, MSG_REVISED

SCOPE = "project:P123"


def raises(error: type[BaseException], world: InspWorld, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def test_create_makes_a_draft_version_one_with_the_count(insp: InspWorld) -> None:
    made = insp.call(
        "uma", "CreateChecklist", title="Hydrotest", discipline="Piping", questions=QUESTIONS
    )
    item = str(made.stream_id)
    assert made.key == "P123-CHK-0001"
    assert insp.state_of(item, "Draft") == "Draft"
    row = insp.checklist_row(item)
    assert (row["discipline"], row["checklist_version"], row["question_count"]) == ("Piping", 1, 3)
    assert row["supersedes_id"] is None and row["published_on"] is None
    assert insp.rows("SELECT title FROM cur_core_record WHERE id = :i", i=item) == [
        {"title": "Hydrotest"}
    ]


def test_create_takes_no_actor_field_and_bounds_the_list() -> None:
    base: dict[str, Any] = {"actor": "user:uma", "source": "t", "scope": SCOPE, "title": "x"}
    with pytest.raises(ValidationError):
        CreateChecklist(**base, published_by="user:sue")  # type: ignore[arg-type]
    CreateChecklist(**base, questions=[{"id": f"q{i}"} for i in range(60)])
    with pytest.raises(ValidationError):
        CreateChecklist(**base, questions=[{"id": f"q{i}"} for i in range(61)])
    with pytest.raises(ValidationError):
        CreateChecklist(**{**base, "title": "  "})


def test_a_user_without_the_controller_word_cannot_publish_retire_or_revise(
    insp: InspWorld,
) -> None:
    item = insp.checklist(publish=False)
    for name in ("PublishChecklist", "RetireChecklist", "ReviseChecklist"):
        with pytest.raises(ForbiddenError):
            insp.call("ian", name, checklist=item)
    with pytest.raises(ForbiddenError):
        insp.call("vera", "CreateChecklist", title="x")
    assert insp.state_of(item, "Draft") == "Draft"


def test_edit_changes_a_draft_and_names_only_what_changed(insp: InspWorld) -> None:
    item = insp.checklist(publish=False, discipline="Piping")
    shorter = QUESTIONS[:2]
    insp.call(
        "uma", "EditChecklist", checklist=item, title="Renamed", discipline=None, questions=shorter
    )
    row = insp.checklist_row(item)
    assert (row["discipline"], row["question_count"]) == (None, 2)
    assert insp.rows("SELECT title FROM cur_core_record WHERE id = :i", i=item)[0]["title"] == (
        "Renamed"
    )
    assert raises(
        ChecklistRuleError, insp, "uma", "EditChecklist", checklist=item, title="Renamed"
    ) == (MSG_NOTHING)
    with pytest.raises(ValidationError):
        EditChecklist(actor="user:uma", source="t", scope=SCOPE, checklist=item)
    with pytest.raises(ValidationError):
        EditChecklist(actor="user:uma", source="t", scope=SCOPE, checklist=item, title=None)


def test_a_published_checklist_accepts_no_edit_and_names_its_state(insp: InspWorld) -> None:
    item = insp.checklist()
    message = raises(ChecklistStateError, insp, "uma", "EditChecklist", checklist=item, title="x")
    assert message == ("a checklist that is Published does not take EditChecklist; it needs Draft")
    assert raises(ChecklistStateError, insp, "sue", "PublishChecklist", checklist=item) == (
        "a checklist that is Published does not take PublishChecklist; it needs Draft"
    )


def test_publish_refuses_an_empty_or_malformed_list_as_one_fixed_text(insp: InspWorld) -> None:
    empty = insp.checklist(publish=False, questions=[])
    assert raises(ChecklistRuleError, insp, "sue", "PublishChecklist", checklist=empty) == (
        MSG_NOT_READY + "question list: at least one question is required"
    )
    bad = insp.checklist(publish=False, questions=[{"id": "x", "text": ""}])
    message = raises(ChecklistRuleError, insp, "sue", "PublishChecklist", checklist=bad)
    assert message.startswith(MSG_NOT_READY) and "; " in message
    assert (
        insp.state_of(bad, "Draft") == "Draft" and insp.checklist_row(bad)["published_on"] is None
    )


def test_publish_moves_to_published_and_dates_it(insp: InspWorld) -> None:
    item = insp.checklist(publish=False)
    insp.call("sue", "PublishChecklist", checklist=item)
    row = insp.checklist_row(item)
    assert insp.state_of(item, "Draft") == "Published"
    assert row["published_by"] == "user:sue" and row["published_on"] is not None


def test_retire_takes_a_draft_or_a_published_one_and_retired_accepts_nothing(
    insp: InspWorld,
) -> None:
    draft, published = insp.checklist(publish=False), insp.checklist()
    for item in (draft, published):
        insp.call("sue", "RetireChecklist", checklist=item)
        assert insp.state_of(item, "Draft") == "Retired"
        assert insp.checklist_row(item)["retired_on"] is not None
        for who, name, extra in (
            ("uma", "EditChecklist", {"title": "x"}),
            ("sue", "PublishChecklist", {}),
            ("sue", "RetireChecklist", {}),
            ("sue", "ReviseChecklist", {}),
        ):
            assert raises(ChecklistStateError, insp, who, name, checklist=item, **extra) == (
                MSG_RETIRED
            )


def test_revise_copies_a_published_one_as_version_n_plus_one_in_draft(insp: InspWorld) -> None:
    first = insp.checklist(discipline="Piping")
    made = insp.call("sue", "ReviseChecklist", checklist=first)
    second = str(made.stream_id)
    assert made.key == "P123-CHK-0002"
    row = insp.checklist_row(second)
    assert (row["checklist_version"], row["supersedes_id"], row["discipline"]) == (
        2,
        first,
        "Piping",
    )
    assert row["questions_json"] == insp.checklist_row(first)["questions_json"]
    assert (
        insp.state_of(second, "Draft") == "Draft" and insp.state_of(first, "Draft") == "Published"
    )
    assert (
        raises(ChecklistStateError, insp, "sue", "ReviseChecklist", checklist=first) == MSG_REVISED
    )
    insp.call("uma", "EditChecklist", checklist=second, questions=QUESTIONS[:1])
    assert insp.checklist_row(first)["question_count"] == 3


def test_a_draft_cannot_be_revised(insp: InspWorld) -> None:
    item = insp.checklist(publish=False)
    assert raises(ChecklistStateError, insp, "sue", "ReviseChecklist", checklist=item) == (
        "a checklist that is Draft does not take ReviseChecklist; it needs Published"
    )


def test_publishing_a_revision_retires_the_version_it_supersedes_in_one_step(
    insp: InspWorld,
) -> None:
    first = insp.checklist()
    second = str(insp.call("sue", "ReviseChecklist", checklist=first).stream_id)
    insp.call("sue", "PublishChecklist", checklist=second)
    assert insp.state_of(second, "Draft") == "Published"
    assert insp.state_of(first, "Draft") == "Retired"
    assert insp.checklist_row(first)["retired_on"] is not None
    third = str(insp.call("sue", "ReviseChecklist", checklist=second).stream_id)
    assert insp.checklist_row(third)["checklist_version"] == 3


def test_a_stale_version_and_a_foreign_id_are_refused(insp: InspWorld) -> None:
    item = insp.checklist(publish=False)
    version = insp.version(item)
    insp.call("uma", "EditChecklist", checklist=item, title="Again")
    assert (
        raises(
            StaleVersionError,
            insp,
            "sue",
            "PublishChecklist",
            checklist=item,
            expected_version=version,
        )
        == "the record changed since it was read"
    )
    iwp = insp.record("awp.IWP", "IWP-9")
    wrong = raises(RecordNotFoundError, insp, "sue", "RetireChecklist", checklist=iwp)
    missing = raises(RecordNotFoundError, insp, "sue", "RetireChecklist", checklist="nothing")
    assert wrong == missing == "no record with that id"


def test_a_failed_publish_leaves_nothing_behind(insp: InspWorld) -> None:
    empty = insp.checklist(publish=False, questions=[])
    before = insp.count()
    raises(ChecklistRuleError, insp, "sue", "PublishChecklist", checklist=empty)
    assert insp.count() == before
