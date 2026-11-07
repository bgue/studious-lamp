"""The path of construction (S3, S4 D10): versions, expected_version, reason codes."""

from __future__ import annotations

import pytest
from awp_world import World, refuses
from tl_core.auth.errors import ForbiddenError
from tl_core.services.errors import NoChangesError
from tl_mod_awp.errors import (
    CodeNotFoundError,
    PathRuleError,
    RetiredError,
    StaleVersionError,
    UnknownListCodeError,
)


@pytest.fixture
def path(world: World) -> World:
    world.areas_and_path()
    return world


def _order(w: World, version: int) -> list[str]:
    rows = w.rows(
        "SELECT c.code FROM cur_awp_path_step s JOIN cur_awp_cwa c ON c.id = s.cwa_id "
        "WHERE s.version = :v ORDER BY s.position",
        v=version,
    )
    return [r["code"] for r in rows]


def test_define_makes_version_1_with_the_keyed_record(path: World) -> None:
    assert _order(path, 1) == ["A1", "A2", "A3", "A4"]
    assert path.scalar("SELECT current_version FROM cur_awp_path") == 1
    assert path.scalar("SELECT key FROM cur_core_record WHERE type = 'awp.PathOfConstruction'") == (
        "P123-POC"
    )


def test_a_second_path_is_refused(path: World) -> None:
    refuses(
        PathRuleError,
        lambda: path.call("sue", "DefinePathOfConstruction", steps=[{"cwa_code": "A1"}]),
    )


def test_an_area_twice_an_unknown_area_and_a_retired_area_are_refused(world: World) -> None:
    for code in ("A1", "A2"):
        world.call("sue", "DefineCwa", code=code, title=code)
    world.call("sue", "RetireCwa", cwa=world.id_of("A2", "awp.CWA"), reason="gone")
    refuses(
        PathRuleError,
        lambda: world.call(
            "sue", "DefinePathOfConstruction", steps=[{"cwa_code": "A1"}, {"cwa_code": "A1"}]
        ),
    )
    refuses(
        CodeNotFoundError,
        lambda: world.call("sue", "DefinePathOfConstruction", steps=[{"cwa_code": "ZZ"}]),
    )
    refuses(
        RetiredError,
        lambda: world.call("sue", "DefinePathOfConstruction", steps=[{"cwa_code": "A2"}]),
    )


def test_a_move_makes_the_next_version_and_keeps_the_old_one(path: World) -> None:
    path.call(
        "sue",
        "MoveCwaInPath",
        cwa_code="A4",
        to_position=1,
        reason_code="Access",
        expected_version=1,
    )
    assert _order(path, 2) == ["A4", "A1", "A2", "A3"]
    assert _order(path, 1) == ["A1", "A2", "A3", "A4"]
    assert path.scalar("SELECT current_version FROM cur_awp_path") == 2
    reasons = path.rows(
        "SELECT reason_code FROM cur_awp_path_step WHERE version = 2 AND reason_code IS NOT NULL"
    )
    assert [r["reason_code"] for r in reasons] == ["Access"]


def test_expected_version_must_be_the_current_one(path: World) -> None:
    move = {"cwa_code": "A4", "to_position": 1, "reason_code": "Access"}
    path.call("sue", "MoveCwaInPath", expected_version=1, **move)
    # version 1 is stale, version 3 is ahead: both refuse
    for stale in (1, 3):
        refuses(
            StaleVersionError,
            lambda v=stale: path.call(
                "sue",
                "MoveCwaInPath",
                cwa_code="A3",
                to_position=1,
                reason_code="Access",
                expected_version=v,
            ),
        )
    assert path.scalar("SELECT current_version FROM cur_awp_path") == 2


def test_a_reason_code_outside_pathreason_is_refused_and_not_repeated(path: World) -> None:
    exc = refuses(
        UnknownListCodeError,
        lambda: path.call(
            "sue",
            "MoveCwaInPath",
            cwa_code="A2",
            to_position=1,
            reason_code="Nonsense",
            expected_version=1,
        ),
    )
    assert "Nonsense" not in str(exc)
    assert path.scalar("SELECT current_version FROM cur_awp_path") == 1


def test_define_checks_the_step_reason_codes(world: World) -> None:
    for code in ("A1", "A2"):
        world.call("sue", "DefineCwa", code=code, title=code)
    refuses(
        UnknownListCodeError,
        lambda: world.call(
            "sue",
            "DefinePathOfConstruction",
            steps=[{"cwa_code": "A1", "reason_code": "Nonsense"}, {"cwa_code": "A2"}],
        ),
    )
    world.call(
        "sue",
        "DefinePathOfConstruction",
        steps=[{"cwa_code": "A1", "reason_code": "Access"}, {"cwa_code": "A2"}],
    )


def test_move_refusals_name_the_rule(path: World) -> None:
    base = {"reason_code": "Access", "expected_version": 1}
    refuses(
        PathRuleError,
        lambda: path.call("sue", "MoveCwaInPath", cwa_code="A1", to_position=5, **base),
    )
    refuses(
        NoChangesError,
        lambda: path.call("sue", "MoveCwaInPath", cwa_code="A1", to_position=1, **base),
    )
    path.call("sue", "DefineCwa", code="B1", title="Not in the path")
    refuses(
        PathRuleError,
        lambda: path.call("sue", "MoveCwaInPath", cwa_code="B1", to_position=1, **base),
    )
    refuses(
        CodeNotFoundError,
        lambda: path.call("sue", "MoveCwaInPath", cwa_code="NOPE", to_position=1, **base),
    )


def test_move_without_a_path_is_refused(world: World) -> None:
    world.call("sue", "DefineCwa", code="A1", title="A1")
    refuses(
        PathRuleError,
        lambda: world.call(
            "sue",
            "MoveCwaInPath",
            cwa_code="A1",
            to_position=1,
            reason_code="Access",
            expected_version=1,
        ),
    )


def test_the_move_needs_the_controller_word(path: World) -> None:
    refuses(
        ForbiddenError,
        lambda: path.call(
            "uma",
            "MoveCwaInPath",
            cwa_code="A1",
            to_position=2,
            reason_code="Access",
            expected_version=1,
        ),
    )
