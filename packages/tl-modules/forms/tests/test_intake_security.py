"""What a stranger's text can reach once a controller accepts it (P2-FORMS S7c, D16 to D18)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from forms_world import World, answer, intake_body
from tl_core.text import FORBIDDEN_TEXT

BODY = "zq-body-4410"
CLAIM = "zq-claim-5521"
PHONE = "zq-phone-6632"
ARGS = "zq-args-7743"
NAME = "zq-name-8854"


def refused(world: World, name: str, **fields: Any) -> BaseException:
    with pytest.raises(Exception) as caught:
        world.call("ada", name, **fields)
    return caught.value


def events_holding(world: World, marker: str) -> set[str]:
    return {
        str(r["event_type"])
        for r in world.rows("SELECT event_type, payload FROM events")
        if marker in str(r["payload"])
    }


def staged_item(world: World, **claims: Any) -> tuple[str, str, str]:
    intake = world.intake_template()
    general = world.template()
    code = world.stage_code(intake)
    body = intake_body(topic=BODY, **claims)
    return world.stage_item(code, body), general, code


def test_a_marker_in_the_body_never_reaches_any_event_or_result(world: World) -> None:
    item, general, _ = staged_item(world, name=CLAIM, company="Acme", phone=PHONE)
    made = world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=item,
        command_type="SubmitForm",
        command_args={"template_id": general, "answers": [answer("topic", ARGS)]},
    )
    assert events_holding(world, BODY) == set()
    assert events_holding(world, PHONE) == set()
    assert events_holding(world, CLAIM) == {"IntakeItem.Accepted"}
    assert events_holding(world, ARGS) == {"Submission.Submitted"}
    shown = repr(made) + str(made.model_dump())
    for marker in (BODY, CLAIM, PHONE, ARGS):
        assert marker not in shown
    for table in ("cur_forms_intake_item", "cur_forms_submission", "cur_core_record"):
        rows = repr(world.rows(f"SELECT * FROM {table}"))
        assert BODY not in rows and PHONE not in rows


def test_a_refusal_never_echoes_the_body_a_claim_or_a_command_argument(world: World) -> None:
    item, general, _ = staged_item(world, name=CLAIM, phone=PHONE)
    texts = [
        # an answer the nested rules refuse
        refused(
            world,
            "AcceptIntakeItem",
            item_id=item,
            command_type="SubmitForm",
            command_args={"template_id": general, "answers": [answer("count", ARGS)]},
        ),
        # arguments the model refuses (an extra key, a wrong type)
        refused(
            world,
            "AcceptIntakeItem",
            item_id=item,
            command_type="SubmitForm",
            command_args={"template_id": general, "answers": [], ARGS: ARGS},
        ),
        refused(
            world,
            "AcceptIntakeItem",
            item_id=item,
            command_type="SubmitForm",
            command_args={"template_id": ARGS, "answers": ARGS},
        ),
        # a command type that is not accepted, made of the marker
        refused(
            world,
            "AcceptIntakeItem",
            item_id=item,
            command_type=ARGS,
            command_args={"x": ARGS},
        ),
    ]
    for error in texts:
        shown = f"{error!s} {error!r} {getattr(error, 'args', '')}"
        for marker in (BODY, CLAIM, PHONE, ARGS):
            assert marker not in shown, type(error).__name__
    assert world.state(item, "Pending") == "Pending" and world.body_rows(item) == 1
    assert not events_holding(world, ARGS) and not events_holding(world, BODY)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sam\x1b[31m Smith\x00", "Sam[31m Smith"),
        ("‮Sam‏ Smith⁦", "Sam Smith"),
        ("line\nbreak here", "linebreakhere"),
        ("   ", None),
        ("\x00‮", None),
    ],
)
def test_hostile_claim_values_are_cleaned(world: World, raw: str, expected: str | None) -> None:
    item, general, _ = staged_item(world, name=raw, company=None)
    world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=item,
        command_type="SubmitForm",
        command_args={"template_id": general, "answers": [answer("topic", "x")]},
    )
    claim = world.events(item, "IntakeItem.Accepted")[0]["payload"]["on_behalf_of_claim"]
    assert claim == (None if expected is None else {"name": expected})


def test_a_claim_of_ten_thousand_characters_is_bounded_to_eighty(world: World) -> None:
    item, general, _ = staged_item(world, name="n" * 10_000, company="c" * 81)
    world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=item,
        command_type="SubmitForm",
        command_args={"template_id": general, "answers": [answer("topic", "x")]},
    )
    claim = world.events(item, "IntakeItem.Accepted")[0]["payload"]["on_behalf_of_claim"]
    assert claim == {"name": "n" * 80, "company": "c" * 80}
    assert FORBIDDEN_TEXT.search(json.dumps(claim, ensure_ascii=False)) is None


def test_a_claim_that_is_not_text_or_a_body_that_is_not_json_gives_no_claim(
    world: World,
) -> None:
    intake = world.intake_template()
    general = world.template()
    code = world.stage_code(intake)
    bodies = [
        "not json",
        "[1, 2]",
        '{"answers": "x"}',
        '{"answers": [1, {"q": 5, "value": "x"}, {"q": "claim_name", "value": 7}]}',
        '{"claim_name": "top level is not read"}',
    ]
    for body in bodies:
        item = world.stage_item(code, body)
        world.call(
            "ada",
            "AcceptIntakeItem",
            item_id=item,
            command_type="SubmitForm",
            command_args={"template_id": general, "answers": [answer("topic", "x")]},
        )
        accepted = world.events(item, "IntakeItem.Accepted")[0]
        assert accepted["payload"]["on_behalf_of_claim"] is None


def test_the_claim_phone_is_never_read(world: World) -> None:
    item, general, _ = staged_item(world, name="Sam", company="Acme", phone=PHONE)
    world.call(
        "ada",
        "AcceptIntakeItem",
        item_id=item,
        command_type="SubmitForm",
        command_args={"template_id": general, "answers": [answer("topic", "x")]},
    )
    claim = world.events(item, "IntakeItem.Accepted")[0]["payload"]["on_behalf_of_claim"]
    assert set(claim) == {"name", "company"}
    row = world.rows("SELECT * FROM cur_forms_intake_item WHERE id = :i", i=item)[0]
    assert PHONE not in repr(row)


def test_a_reject_puts_no_text_of_the_body_in_any_event(world: World) -> None:
    item, _, _ = staged_item(world, name=CLAIM, phone=PHONE)
    world.call("ada", "RejectIntakeItem", item_id=item, reason="spam")
    for marker in (BODY, CLAIM, PHONE):
        assert events_holding(world, marker) == set()
