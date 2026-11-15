"""Template commands: draft, edit, publish, revise, retire (P2-FORMS S3, D9)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from forms_world import World, field, two_fields
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.forms import rules
from tl_core.forms.types import KEYS_1
from tl_core.services.errors import (
    RecordNotFoundError,
    UnknownTransitionError,
)
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.util import new_ulid
from tl_mod_forms.commands import DraftFormTemplate
from tl_mod_forms.errors import (
    MSG_INTAKE_FIELDS,
    MSG_NOTHING,
    MSG_ONE_DRAFT,
    MSG_UNKNOWN,
    FormRuleError,
    FormsScopeError,
    FormStateError,
    FormTemplateError,
    StaleVersionError,
)

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = sorted((ROOT / "schema" / "fixtures" / "forms" / "templates").rglob("*.yaml"))


def raises(error: type[BaseException], world: World, who: str, name: str, **fields: Any) -> str:
    with pytest.raises(error) as caught:
        world.call(who, name, **fields)
    return str(caught.value)


def test_draft_makes_a_draft_with_a_company_key_and_the_template_row(world: World) -> None:
    made = world.call(
        "uma",
        "DraftFormTemplate",
        title="Pre-use check",
        fields=two_fields(),
        answer_class="restricted",
    )
    assert made.key == "TPL-0001" and world.state(made.stream_id) == "Draft"
    row = world.template_row(made.stream_id)
    assert (row["template_version"], row["format_version"], row["field_count"]) == (1, 2, 2)
    assert (row["answer_class"], row["content_hash"], row["supersedes_id"]) == (
        "restricted",
        None,
        None,
    )
    assert world.events(made.stream_id, "Template.Created")[0]["payload"]["field_count"] == 2
    second = world.call("uma", "DraftFormTemplate", title="Other", fields=two_fields())
    assert second.key == "TPL-0002"


def test_a_template_is_company_scope_only(world: World) -> None:
    text = raises(
        FormsScopeError, world, "uma", "DraftFormTemplate",
        scope="project:P123", title="x", fields=two_fields(),
    )  # fmt: skip
    assert text == "a form template belongs to the company"


def test_unclean_field_lists_are_refused_at_draft_edit_and_publish(world: World) -> None:
    bad = [field("topic"), field("topic")]  # a duplicate id
    msg = raises(FormTemplateError, world, "uma", "DraftFormTemplate", title="x", fields=bad)
    assert "topic: duplicate id" in msg
    assert "at least one question" in raises(
        FormTemplateError, world, "uma", "DraftFormTemplate", title="x", fields=[]
    )
    tpl = world.template(publish=False)
    before = world.count()
    msg = raises(FormTemplateError, world, "uma", "EditFormTemplate", template_id=tpl, fields=bad)
    assert "duplicate id" in msg and world.count() == before


def test_publish_runs_the_questions_check_again(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    tpl = world.template(publish=False)
    monkeypatch.setattr(
        "tl_mod_forms.handlers.template.validate_questions",
        lambda fields, *, fmt: ["topic: a rule added since the draft"],
    )
    msg = raises(FormTemplateError, world, "ada", "PublishFormTemplate", template_id=tpl)
    assert "a rule added since the draft" in msg and world.state(tpl) == "Draft"


def test_a_format_1_template_takes_format_1_questions_only(world: World) -> None:
    msg = raises(
        FormTemplateError, world, "uma", "DraftFormTemplate",
        title="x", format_version=1, fields=[field("q1")],
    )  # fmt: skip
    assert "unknown key" in msg  # format 2 keys in a format 1 list
    ok = world.call(
        "uma",
        "DraftFormTemplate",
        title="x",
        format_version=1,
        fields=[{k: v for k, v in field("q1").items() if k in KEYS_1}],
    )
    assert world.template_row(ok.stream_id)["format_version"] == 1


def test_purpose_and_accepts_as_belong_to_a_public_template_only(world: World) -> None:
    msg = raises(
        FormTemplateError, world, "uma", "DraftFormTemplate",
        title="x", fields=two_fields(), purpose="request",
    )  # fmt: skip
    assert MSG_INTAKE_FIELDS in msg


def test_edit_changes_a_draft_and_field_count_follows(world: World) -> None:
    tpl = world.template(publish=False)
    made = world.call(
        "uma",
        "EditFormTemplate",
        template_id=tpl,
        title="Renamed",
        fields=[*two_fields(), field("extra")],
        answer_class="privileged",
    )
    row = world.template_row(tpl)
    assert (row["field_count"], row["answer_class"]) == (3, "privileged")
    title = world.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=tpl)
    assert title == "Renamed" and made.version == world.version(tpl)
    changes = world.events(tpl, "Template.Edited")[0]["payload"]["changes"]
    assert changes["field_count"] == [2, 3] and changes["title"] == ["Toolbox talk", "Renamed"]
    assert (
        raises(FormRuleError, world, "uma", "EditFormTemplate", template_id=tpl, title="Renamed")
        == MSG_NOTHING
    )


def test_edit_refuses_a_published_template_and_a_stale_version(world: World) -> None:
    tpl = world.template()
    assert "Published" in raises(
        FormStateError, world, "uma", "EditFormTemplate", template_id=tpl, title="New"
    )
    draft = world.template(publish=False)
    stale = world.version(draft) + 1
    raises(
        StaleVersionError,
        world, "uma", "EditFormTemplate", template_id=draft, title="New", expected_version=stale,
    )  # fmt: skip


def test_edit_must_name_something_and_cannot_clear_the_title() -> None:
    from tl_mod_forms.commands import EditFormTemplate

    with pytest.raises(ValidationError):
        EditFormTemplate(actor="user:a", source="t", scope="company", template_id="x")
    with pytest.raises(ValidationError):
        EditFormTemplate(actor="user:a", source="t", scope="company", template_id="x", title=None)


def test_publish_sets_the_hash_the_day_and_the_state(world: World) -> None:
    tpl = world.template(publish=False)
    made = world.call("ada", "PublishFormTemplate", template_id=tpl)
    row = world.template_row(tpl)
    assert world.state(tpl) == "Published" and made.version == world.version(tpl)
    assert row["content_hash"] == rules.content_hash(two_fields(), fmt=2)
    assert row["published_on"] and world.events(tpl, "Template.Published")


def test_publish_is_the_controllers_and_a_user_is_refused(world: World) -> None:
    tpl = world.template(publish=False)
    with pytest.raises(ForbiddenError):
        world.call("uma", "PublishFormTemplate", template_id=tpl)
    assert world.state(tpl) == "Draft"


def public_fields(count: int = 2) -> list[dict[str, Any]]:
    return [field(f"f{i}", max=None) for i in range(count)]


def test_a_public_template_publishes_when_it_fits_intake(world: World) -> None:
    tpl = world.template(
        publish=False, fields=public_fields(), intake="public", purpose="request",
        accepts_as=["SubmitForm"],
    )  # fmt: skip
    world.call("ada", "PublishFormTemplate", template_id=tpl)
    assert world.state(tpl) == "Published"


def test_a_public_template_with_nine_fields_or_a_visible_when_is_refused_at_publish(
    world: World,
) -> None:
    nine = world.template(
        publish=False, fields=public_fields(9), intake="public", purpose="request",
        accepts_as=["SubmitForm"],
    )  # fmt: skip
    assert "at most 8 fields" in raises(
        FormTemplateError, world, "ada", "PublishFormTemplate", template_id=nine
    )
    cond = [field("a"), field("b", visible_when={"q": "a", "is": "x"})]
    cond_tpl = world.template(
        publish=False, fields=cond, intake="public", purpose="sign_on", accepts_as=["SubmitForm"]
    )
    assert "allows no visible_when" in raises(
        FormTemplateError, world, "ada", "PublishFormTemplate", template_id=cond_tpl
    )
    assert world.state(nine) == world.state(cond_tpl) == "Draft"


def test_a_public_template_needs_purpose_and_accepts_as_at_publish(world: World) -> None:
    tpl = world.template(publish=False, fields=public_fields(), intake="public")
    msg = raises(FormTemplateError, world, "ada", "PublishFormTemplate", template_id=tpl)
    assert "purpose must be one of" in msg and "accepts_as needs" in msg


def test_revise_makes_version_n_plus_1_as_a_draft_and_keeps_one_open_draft(world: World) -> None:
    v1 = world.template()
    made = world.call("uma", "ReviseFormTemplate", template_id=v1)
    v2 = made.stream_id
    row = world.template_row(v2)
    assert (row["template_version"], row["supersedes_id"], row["field_count"]) == (2, v1, 2)
    assert world.state(v2) == "Draft" and world.state(v1) == "Published"
    assert made.key == "TPL-0002"
    assert (
        raises(FormRuleError, world, "uma", "ReviseFormTemplate", template_id=v1) == MSG_ONE_DRAFT
    )
    world.call("ada", "PublishFormTemplate", template_id=v2)
    assert world.state(v1) == "Published"  # publishing does not retire the predecessor
    v3 = world.call("uma", "ReviseFormTemplate", template_id=v2).stream_id
    assert world.template_row(v3)["template_version"] == 3
    assert (
        raises(FormRuleError, world, "uma", "ReviseFormTemplate", template_id=v1) == MSG_ONE_DRAFT
    )
    assert "Draft" in raises(FormStateError, world, "uma", "ReviseFormTemplate", template_id=v3)


def test_revise_takes_a_retired_template_and_copies_the_flags(world: World) -> None:
    v1 = world.template(answer_class="restricted", bound_record_type="quality.PunchItem")
    world.call("ada", "RetireFormTemplate", template_id=v1)
    v2 = world.call("uma", "ReviseFormTemplate", template_id=v1).stream_id
    row = world.template_row(v2)
    assert (row["answer_class"], row["bound_record_type"]) == ("restricted", "quality.PunchItem")


def test_retire_takes_published_or_draft_and_not_retired(world: World) -> None:
    published, draft = world.template(), world.template(publish=False)
    for tpl in (published, draft):
        world.call("ada", "RetireFormTemplate", template_id=tpl)
        assert world.state(tpl) == "Retired"
    assert world.template_row(published)["retired_on"]
    assert "Retired" in raises(
        FormStateError, world, "ada", "RetireFormTemplate", template_id=published
    )
    with pytest.raises(ForbiddenError):
        world.call("uma", "RetireFormTemplate", template_id=world.template())


def test_a_retired_template_cannot_be_published_again(world: World) -> None:
    tpl = world.template()
    world.call("ada", "RetireFormTemplate", template_id=tpl)
    assert "Retired" in raises(FormStateError, world, "ada", "PublishFormTemplate", template_id=tpl)
    with pytest.raises(UnknownTransitionError), open_uow(world.db) as uow:  # nor by the workflow
        handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor="user:ada",
                source="t",
                scope="company",
                stream_id=tpl,
                expected_version=world.version(tpl),
                transition="publish",
                reason=None,
            ),  # fmt: skip
            by_module=True,
        )


def test_an_unknown_template_answers_one_text(world: World) -> None:
    for name in (
        "EditFormTemplate",
        "PublishFormTemplate",
        "ReviseFormTemplate",
        "RetireFormTemplate",
    ):
        extra: dict[str, Any] = {"title": "x"} if name == "EditFormTemplate" else {}
        assert (
            raises(RecordNotFoundError, world, "ada", name, template_id=new_ulid(), **extra)
            == MSG_UNKNOWN
        )
    sub = world.submit(template=world.template())
    assert (
        raises(RecordNotFoundError, world, "ada", "RetireFormTemplate", template_id=sub.stream_id)
        == MSG_UNKNOWN
    )


def test_template_commands_run_in_company_scope_only(world: World) -> None:
    tpl = world.template(publish=False)
    raises(
        FormsScopeError, world, "ada", "PublishFormTemplate", scope="project:P123", template_id=tpl
    )


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_the_fixtures_of_s2_draft_and_publish(world: World, path: Path) -> None:
    body = yaml.safe_load(path.read_text())
    made = world.call("uma", "DraftFormTemplate", **body)
    assert world.state(made.stream_id) == "Draft"
    world.call("ada", "PublishFormTemplate", template_id=made.stream_id)
    row = world.template_row(made.stream_id)
    assert row["content_hash"] == rules.content_hash(body["fields"], fmt=body["format_version"])


def test_bounds_of_the_draft_command() -> None:
    base: dict[str, Any] = {"actor": "user:a", "source": "t", "scope": "company"}
    for bad in (
        {"title": ""},
        {"title": "x" * 201},
        {"title": "bad\nline"},
        {"format_version": 3},
        {"answer_class": "secret"},
        {"intake": "private"},
        {"purpose": "other"},
        {"accepts_as": ["A"] * 6},
        {"fields": [{"id": "a", "text": "bad‮text"}]},
        {"fields": [{}] * 121},
        {"unknown": 1},
    ):
        with pytest.raises(ValidationError):
            DraftFormTemplate(**{"title": "ok", "fields": [], **base, **bad})  # type: ignore[arg-type]
