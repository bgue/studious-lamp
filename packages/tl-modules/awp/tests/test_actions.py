"""The action table (S4): each row's word equals the command's; offers follow state, level."""

from __future__ import annotations

import pytest
from awp_world import World
from tl_adapters.db import open_uow
from tl_core.actions import allowed_actions
from tl_mod_awp.actions import RULES, level_of, states_for
from tl_mod_awp.commands import AWP_COMMANDS

SPEC = {c.model.__name__: c for c in AWP_COMMANDS}


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.command)
def test_the_word_of_each_rule_equals_the_command_s_word(rule: object) -> None:
    from tl_mod_awp.actions import Rule

    assert isinstance(rule, Rule)
    assert rule.command in SPEC
    assert rule.word == SPEC[rule.command].access


def test_a_state_bound_rule_names_the_states_the_handlers_ask_for() -> None:
    assert states_for("ReleaseCwp", "awp.CWP") == ("In development",)
    assert states_for("StartCwpDevelopment", "awp.CWP") == ("Planned",)
    with pytest.raises(KeyError):
        states_for("DefineCwa", "awp.CWA")


def test_levels_follow_the_word() -> None:
    by_command = {r.command: level_of(r) for r in RULES}
    assert by_command["ReleaseCwp"] == "controller"
    assert by_command["VoidCwp"] == "controller"
    assert by_command["ReviseCwp"] == "user"
    assert by_command["UpdateExternalPackage"] == "user"


LEVEL = {"vera": 0, "uma": 1, "sue": 2}
RANK = {"user": 1, "controller": 2, "admin": 3}


def _names(w: World, who: str, record: str) -> list[str]:
    with open_uow(w.db, readonly=True) as uow:
        found = allowed_actions(
            uow, record, actor=f"user:{who}", holds=lambda want: LEVEL[who] >= RANK[want]
        )
    return [o.command for o in found.actions]


@pytest.fixture
def plant(world: World) -> World:
    world.wbs_tree()
    world.areas_and_path(("A1",))
    return world


def test_offers_follow_the_state_and_the_level(plant: World) -> None:
    cwp = plant.full_cwp("PIP", "Rack", "A1", "1.1.1", "100")
    assert _names(plant, "vera", cwp) == []
    planned = _names(plant, "uma", cwp)
    assert "StartCwpDevelopment" in planned
    assert "ReleaseCwp" not in planned
    plant.call("uma", "StartCwpDevelopment", cwp=cwp)
    user = _names(plant, "uma", cwp)
    assert user == ["ReviseCwp", "AllocateCwpToWbs"]
    ctl = _names(plant, "sue", cwp)
    assert ctl[2:] == ["ReleaseCwp", "VoidCwp"]
    plant.call("sue", "ReleaseCwp", cwp=cwp, expected_version=plant.version(cwp))
    assert _names(plant, "sue", cwp) == ["ReturnCwp", "StartCwpExecution", "VoidCwp"]
    assert _names(plant, "uma", cwp) == ["StartCwpExecution"]


def test_a_void_package_is_offered_nothing(plant: World) -> None:
    cwp = plant.new_cwp("PIP", "Rack", "A1")
    plant.call("sue", "VoidCwp", id=cwp, reason="x")
    assert _names(plant, "sue", cwp) == []


def test_a_retired_node_and_a_parent_are_offered_less(plant: World) -> None:
    leaf, parent = plant.id_of("1.1.1"), plant.id_of("1.1")
    assert _names(plant, "sue", leaf) == ["ReviseWbsNode", "MapWbsToCostCodes", "RetireWbsNode"]
    assert _names(plant, "sue", parent) == ["ReviseWbsNode", "RetireWbsNode"]
    assert _names(plant, "uma", leaf) == []
    plant.call("sue", "RetireWbsNode", node=leaf, reason="done")
    assert _names(plant, "sue", leaf) == []
