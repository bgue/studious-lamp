"""The construction work areas (S3, S4)."""

from __future__ import annotations

import pytest
from awp_world import CWA, World, hidden_record, refuses
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import NoChangesError, RecordNotFoundError
from tl_core.util import new_ulid
from tl_mod_awp.errors import DuplicateCodeError, InUseError, RetiredError


@pytest.fixture
def areas(world: World) -> World:
    world.call("sue", "DefineCwa", code="A1", title="Area A1", location_text="North")
    world.call("uma", "DefineCwa", code="A2", title="Area A2")  # awp.cwa.edit is a user word
    return world


def test_define_stores_the_area_and_keys_it_by_code(areas: World) -> None:
    rows = areas.rows("SELECT code, location_text, retired FROM cur_awp_cwa ORDER BY code")
    assert [(r["code"], r["location_text"], bool(r["retired"])) for r in rows] == [
        ("A1", "North", False),
        ("A2", None, False),
    ]
    assert areas.scalar(
        "SELECT key FROM cur_core_record WHERE id = :i", i=areas.id_of("A1", CWA)
    ) == ("awp.cwa@A1")


def test_a_second_area_with_the_code_is_refused(areas: World) -> None:
    refuses(DuplicateCodeError, lambda: areas.call("sue", "DefineCwa", code="A1", title="Again"))


def test_a_viewer_may_not_define_an_area(areas: World) -> None:
    refuses(ForbiddenError, lambda: areas.call("vera", "DefineCwa", code="A5", title="A5"))


def test_revise_renames_and_moves_and_null_clears_the_location(areas: World) -> None:
    cwa = areas.id_of("A1", CWA)
    areas.call("uma", "ReviseCwa", cwa=cwa, title="Renamed")
    assert areas.scalar("SELECT title FROM cur_core_record WHERE id = :i", i=cwa) == "Renamed"
    areas.call("uma", "ReviseCwa", cwa=cwa, location_text="South")
    assert areas.scalar("SELECT location_text FROM cur_awp_cwa WHERE id = :i", i=cwa) == "South"
    areas.call("uma", "ReviseCwa", cwa=cwa, location_text=None)
    assert areas.scalar("SELECT location_text FROM cur_awp_cwa WHERE id = :i", i=cwa) is None


def test_revise_with_no_change_is_refused(areas: World) -> None:
    cwa = areas.id_of("A1", CWA)
    refuses(NoChangesError, lambda: areas.call("uma", "ReviseCwa", cwa=cwa))
    refuses(NoChangesError, lambda: areas.call("uma", "ReviseCwa", cwa=cwa, title="Area A1"))


def test_retire_is_refused_while_a_package_names_the_area(areas: World) -> None:
    cwa = areas.id_of("A1", CWA)
    cwp = areas.new_cwp("PIP", "Rack", "A1")
    refuses(InUseError, lambda: areas.call("sue", "RetireCwa", cwa=cwa, reason="done"))
    areas.call("sue", "VoidCwp", id=cwp, reason="gone")
    areas.call("sue", "RetireCwa", cwa=cwa, reason="done")
    assert bool(areas.scalar("SELECT retired FROM cur_awp_cwa WHERE id = :i", i=cwa))
    refuses(RetiredError, lambda: areas.call("sue", "RetireCwa", cwa=cwa, reason="again"))


def test_a_hidden_area_id_answers_as_a_missing_one(areas: World) -> None:
    hidden, absent = hidden_record(areas), new_ulid()
    a = refuses(RecordNotFoundError, lambda: areas.call("sue", "RetireCwa", cwa=hidden, reason="x"))
    b = refuses(RecordNotFoundError, lambda: areas.call("sue", "RetireCwa", cwa=absent, reason="x"))
    assert str(a).replace(hidden, "ID") == str(b).replace(absent, "ID")
