"""The form source of a permit: the precaution list of its type as a form, the ticks as ids."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from permit_world import ALL_TICKS, World
from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.forms import rules
from tl_core.forms.registry import load_form_sources
from tl_core.forms.types import FormBinding, FormSource
from tl_mod_permits.form_source import PermitFormSource, questions_of, source
from tl_mod_permits.types_table import load_types

NOW = datetime(2026, 12, 1, 7, tzinfo=UTC)
CLEARED = cf.Viewer(actor="user:dora", level=1, account="user:dora")


def binding_for(world: World, record: str, viewer: cf.Viewer = cf.LOWEST) -> FormBinding | None:
    with open_uow(world.db, readonly=True) as uow:
        return PermitFormSource().binding(uow.conn(), record, viewer, NOW)


def test_the_entry_point_names_a_form_source_for_permits() -> None:
    assert isinstance(source(), FormSource)
    assert "permits.Permit" in load_form_sources()


@pytest.mark.parametrize("permit_type", sorted(ALL_TICKS))
def test_an_approved_permit_offers_the_precaution_list_of_its_type(
    world: World, permit_type: str
) -> None:
    permit = world.approved(permit_type)
    got = binding_for(world, permit)
    assert got is not None and got.available
    assert got.command == "IssuePermit" and got.answers_arg == "precautions"
    assert got.fixed_args == {"permit": permit}
    ref = got.template
    assert ref is not None and ref.source_type == "permits.PermitType"
    assert ref.source_id == permit_type and ref.fmt == 2
    fields = questions_of(permit_type)
    assert [f["id"] for f in fields] == ALL_TICKS[permit_type]
    assert ref.content_hash == rules.content_hash(fields, fmt=2)
    assert rules.validate_questions(fields, fmt=2) == []


def test_a_permit_that_is_not_approved_takes_no_form(world: World) -> None:
    requested = world.request()
    active = world.active()
    for permit in (requested, active):
        got = binding_for(world, permit)
        assert got is not None and got.available is False and got.reason == "not_approved"
        assert got.command is None and got.template is None


def test_a_hidden_permit_missing_id_and_other_type_answer_none(world: World) -> None:
    secret = world.hidden_record()
    permit = world.request(who="dora", for_record_id=secret)
    world.person("eve", ("user", "document_controller"), grant="superuser")
    world.call("eve", "ApprovePermit", permit=permit)
    assert binding_for(world, permit) is None
    assert binding_for(world, permit, CLEARED) is not None
    assert binding_for(world, "01J000000000000000000000") is None
    assert binding_for(world, secret, CLEARED) is None


def test_the_ids_answered_yes_are_the_ticks_and_the_rules_are_the_generic_ones(
    world: World,
) -> None:
    permit = world.approved("hot_work")
    got = binding_for(world, permit)
    assert got is not None
    mine = PermitFormSource()
    given = [
        {"q": "fire_watch", "value": "yes", "note": None},
        {"q": "extinguisher", "value": "no", "note": None},
        {"q": "combustibles_cleared", "value": "yes", "note": None},
        {"q": "spark_containment", "value": "na", "note": None},
    ]
    args = mine.arguments(got, given)
    assert args["precautions"] == ["fire_watch", "combustibles_cleared"]
    assert args["permit"] == permit and args["expected_version"] == got.expected_version
    fields = questions_of("hot_work")
    assert mine.problems(fields, given) == []
    assert mine.problems(fields, given[:2]) == [
        "combustibles_cleared: answer required",
        "spark_containment: answer required",
    ]
    assert len(fields) == len(load_types()["hot_work"].precautions)
