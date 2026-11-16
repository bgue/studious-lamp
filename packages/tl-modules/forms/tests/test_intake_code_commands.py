"""Intake code commands: issue and revoke (P2-FORMS S7c, D15, D16)."""

from __future__ import annotations

from typing import Any

import pytest
from forms_world import World
from pydantic import ValidationError
from tl_adapters.db import open_uow
from tl_core.auth.errors import ForbiddenError
from tl_core.auth.module_roles import require_command_access
from tl_core.qr.codes import code_hash, new_code
from tl_core.services.errors import RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_forms.errors import (
    MSG_CODE_TAKEN,
    MSG_EXPIRY,
    MSG_NOT_INTAKE,
    MSG_NOT_PUBLISHED,
    MSG_PROJECT,
    MSG_UNKNOWN,
    FormRuleError,
    FormsScopeError,
    FormStateError,
)

HASH = code_hash(new_code())


def refused(world: World, who: str, name: str, **fields: Any) -> BaseException:
    with pytest.raises(Exception) as caught:
        world.call(who, name, **fields)
    return caught.value


def issue_fields(world: World, template: str, **more: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "code_hash": code_hash(new_code()),
        "template_id": template,
        "heading": "Scaffold request",
        "controller_role": "controller",
        "expires_on": world.days_from_now(30),
    }
    return {**base, **more}


# --- issue -------------------------------------------------------------------------------------


def test_issue_makes_an_active_code_with_the_pinned_template_and_no_code_anywhere(
    world: World,
) -> None:
    tpl = world.intake_template()
    context = world.record("awp.IWP", "IWP-1")
    code, code_id = world.issue(tpl, context_id=context)
    row = world.rows("SELECT * FROM cur_forms_intake_code WHERE id = :i", i=code_id)[0]
    trow = world.template_row(tpl)
    assert row["code_hash"] == code_hash(code)
    assert (row["template_id"], row["template_version"]) == (tpl, trow["template_version"])
    assert row["template_hash"] == trow["content_hash"]
    assert (row["context_id"], row["context_type"]) == (context, "awp.IWP")
    assert (row["heading"], row["controller_role"]) == ("Scaffold request", "controller")
    assert row["issued_by"] == "user:ada" and row["revoked_at"] is None
    assert world.state(code_id, "Active") == "Active"
    assert world.key(code_id) is None
    # no stored field and no event holds the code, plain or grouped
    everything = repr(world.rows("SELECT * FROM events")) + repr(
        world.rows("SELECT * FROM cur_forms_intake_code")
    )
    assert code not in everything and code.lower() not in everything.lower()
    (issued,) = world.events(code_id, "IntakeCode.Issued")
    assert issued["payload"]["code_hash"] == code_hash(code)
    assert not {"code", "token", "url", "body", "salt"} & set(issued["payload"])


def test_a_code_with_no_context_is_allowed(world: World) -> None:
    _, code_id = world.issue(world.intake_template())
    row = world.rows("SELECT * FROM cur_forms_intake_code WHERE id = :i", i=code_id)[0]
    assert row["context_id"] is None and row["context_type"] is None


def test_the_code_hash_must_be_64_lower_case_hex(world: World) -> None:
    tpl = world.intake_template()
    for bad in ("", "ab" * 31, "AB" * 32, "zz" * 32, "ab" * 33):
        with pytest.raises(ValidationError):
            world.command("ada", "IssueIntakeCode", **issue_fields(world, tpl, code_hash=bad))


@pytest.mark.parametrize(
    "heading",
    ["x" * 61, "", "   ", "line\nbreak", "esc\x1b[31m", "nul\x00", "bidi‮abc", "mark‏x"],
)
def test_a_heading_is_one_clean_line_of_one_to_sixty_characters(world: World, heading: str) -> None:
    with pytest.raises(ValidationError):
        world.command(
            "ada",
            "IssueIntakeCode",
            **issue_fields(world, world.intake_template(), heading=heading),
        )


def test_a_heading_of_sixty_characters_and_a_role_of_sixty_four_are_taken(world: World) -> None:
    _, code_id = world.issue(world.intake_template(), heading="h" * 60, controller_role="r" * 64)
    row = world.rows("SELECT * FROM cur_forms_intake_code WHERE id = :i", i=code_id)[0]
    assert (len(row["heading"]), len(row["controller_role"])) == (60, 64)
    with pytest.raises(ValidationError):
        world.command(
            "ada",
            "IssueIntakeCode",
            **issue_fields(world, "x", controller_role="r" * 65),
        )


def test_the_expiry_is_today_to_today_plus_the_setting_and_no_more(world: World) -> None:
    tpl = world.intake_template()
    for days in (-1, 91):
        error = refused(
            world,
            "ada",
            "IssueIntakeCode",
            **issue_fields(world, tpl, expires_on=world.days_from_now(days)),
        )
        assert (type(error), str(error)) == (FormRuleError, MSG_EXPIRY)
    for days in (0, 90):
        world.issue(tpl, expires_on=world.days_from_now(days))
    world.setting("forms.intake.code_max_days", 10)
    world.issue(tpl, expires_on=world.days_from_now(10))
    error = refused(
        world,
        "ada",
        "IssueIntakeCode",
        **issue_fields(world, tpl, expires_on=world.days_from_now(11)),
    )
    assert (type(error), str(error)) == (FormRuleError, MSG_EXPIRY)


def test_the_template_must_be_published_and_public_and_not_bound(world: World) -> None:
    draft = world.intake_template(publish=False)
    retired = world.intake_template()
    world.call("ada", "RetireFormTemplate", template_id=retired)
    for tpl in (draft, retired):
        error = refused(world, "ada", "IssueIntakeCode", **issue_fields(world, tpl))
        assert (type(error), str(error)) == (FormRuleError, MSG_NOT_PUBLISHED)
    general = world.template()
    error = refused(world, "ada", "IssueIntakeCode", **issue_fields(world, general))
    assert (type(error), str(error)) == (FormRuleError, MSG_NOT_INTAKE)
    bound = world.template(bound_record_type="awp.IWP")
    error = refused(world, "ada", "IssueIntakeCode", **issue_fields(world, bound))
    assert (type(error), str(error)) == (FormRuleError, MSG_NOT_INTAKE)
    absent = refused(world, "ada", "IssueIntakeCode", **issue_fields(world, new_ulid()))
    assert (type(absent), str(absent)) == (RecordNotFoundError, MSG_UNKNOWN)
    assert world.count("cur_forms_intake_code") == 0


def test_the_scope_is_a_project(world: World) -> None:
    error = refused(
        world,
        "ada",
        "IssueIntakeCode",
        scope="company",
        **issue_fields(world, world.intake_template()),
    )
    assert (type(error), str(error)) == (FormsScopeError, MSG_PROJECT)


def test_a_context_in_another_project_is_unknown(world: World) -> None:
    tpl = world.intake_template()
    elsewhere = world.record("awp.IWP", "IWP-9", scope="project:P999")
    error = refused(
        world, "ada", "IssueIntakeCode", **issue_fields(world, tpl, context_id=elsewhere)
    )
    assert (type(error), str(error)) == (RecordNotFoundError, MSG_UNKNOWN)


def test_a_hidden_context_answers_as_an_absent_one_before_the_template_is_read(
    world: World,
) -> None:
    hidden = world.hidden_record("privileged")
    seen: set[tuple[type[BaseException], str]] = set()
    for context in (hidden, new_ulid()):
        for tpl in (world.intake_template(), new_ulid(), world.template()):
            error = refused(
                world, "ada", "IssueIntakeCode", **issue_fields(world, tpl, context_id=context)
            )
            seen.add((type(error), str(error)))
    assert seen == {(RecordNotFoundError, MSG_UNKNOWN)}
    assert world.count("cur_forms_intake_code") == 0


def test_a_duplicate_hash_gives_the_fixed_text_and_no_detail(world: World) -> None:
    tpl = world.intake_template()
    fields = issue_fields(world, tpl, code_hash=HASH)
    world.call("ada", "IssueIntakeCode", **fields)
    before = world.count()
    error = refused(world, "ada", "IssueIntakeCode", **{**fields, "heading": "Other"})
    assert (type(error), str(error)) == (FormRuleError, MSG_CODE_TAKEN)
    assert HASH not in str(error) and "Scaffold" not in str(error)
    assert world.count() == before


# --- revoke ------------------------------------------------------------------------------------


def test_revoke_an_active_code_once(world: World) -> None:
    _, code_id = world.issue(world.intake_template())
    made = world.call("bea", "RevokeIntakeCode", code_id=code_id, reason="Label lost")
    assert world.state(code_id, "Active") == "Revoked" and made.version == world.version(code_id)
    row = world.rows("SELECT * FROM cur_forms_intake_code WHERE id = :i", i=code_id)[0]
    assert row["revoked_by"] == "user:bea" and row["revoked_at"] is not None
    assert world.events(code_id, "IntakeCode.Revoked")[0]["payload"]["reason"] == "Label lost"
    before = world.count()
    error = refused(world, "ada", "RevokeIntakeCode", code_id=code_id, reason="Again")
    assert type(error) is FormStateError and "Revoked" in str(error)
    assert world.count() == before


def test_revoke_checks_the_version_and_the_reason(world: World) -> None:
    _, code_id = world.issue(world.intake_template())
    with pytest.raises(Exception, match="changed since"):
        world.call("ada", "RevokeIntakeCode", code_id=code_id, reason="x", expected_version=9)
    for reason in ("", "x" * 301, "bad\nreason"):
        with pytest.raises(ValidationError):
            world.command("ada", "RevokeIntakeCode", code_id=code_id, reason=reason)
    assert world.state(code_id, "Active") == "Active"


def test_revoke_of_a_code_whose_context_is_hidden_answers_as_an_absent_id(world: World) -> None:
    staged = world.stage_code(world.intake_template(), context_id=world.hidden_record("privileged"))
    seen = {
        (type(e), str(e))
        for e in (
            refused(world, "ada", "RevokeIntakeCode", code_id=staged, reason="x"),
            refused(world, "ada", "RevokeIntakeCode", code_id=new_ulid(), reason="x"),
        )
    }
    assert seen == {(RecordNotFoundError, MSG_UNKNOWN)}
    assert world.state(staged, "Active") == "Active"


def test_revoke_in_another_project_or_of_another_type_is_unknown(world: World) -> None:
    tpl = world.intake_template()
    _, code_id = world.issue(tpl)
    other = refused(
        world, "ada", "RevokeIntakeCode", scope="project:P999", code_id=code_id, reason="x"
    )
    wrong_type = refused(world, "ada", "RevokeIntakeCode", code_id=tpl, reason="x")
    assert {(type(e), str(e)) for e in (other, wrong_type)} == {(RecordNotFoundError, MSG_UNKNOWN)}


# --- words -------------------------------------------------------------------------------------


@pytest.mark.parametrize("who", ["uma", "rob", "vera", "dora"])
def test_a_plain_user_holds_neither_intake_word(world: World, who: str) -> None:
    tpl = world.intake_template()
    _, code_id = world.issue(tpl)
    item = world.stage_item(world.stage_code(tpl))
    calls = {
        "IssueIntakeCode": issue_fields(world, tpl),
        "RevokeIntakeCode": {"code_id": code_id, "reason": "x"},
        "AcceptIntakeItem": {"item_id": item, "command_type": "SubmitForm", "command_args": {}},
        "RejectIntakeItem": {"item_id": item, "reason": "spam"},
    }
    for name, fields in calls.items():
        cmd = world.command(who, name, **fields)
        with open_uow(world.db, readonly=True) as uow, pytest.raises(ForbiddenError):
            require_command_access(uow.conn(), cmd)
