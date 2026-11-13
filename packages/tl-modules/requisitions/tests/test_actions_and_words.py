"""The actions table, the access words and the row-or-exclusion rule (ADR-0027)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from tl_core.auth.module_roles import normalise_word
from tl_mod_requisitions.actions import RULES, level_of, requisitions_actions, states_for
from tl_mod_requisitions.module import PROPOSABLE, REQUISITIONS_COMMANDS, spec
from tl_mod_requisitions.names import REQUISITION_TYPES, WORK_ORDER

EXCLUSIONS = Path(__file__).resolve().parents[4] / "tests" / "tools" / "proposable_exclusions.toml"
ACCESS = {c.model.__name__: c.access for c in REQUISITIONS_COMMANDS}


def test_every_rule_word_is_the_access_of_its_command() -> None:
    assert {r.command for r in RULES} == set(ACCESS) - {"RaiseRequisition"}
    assert all(r.word == ACCESS[r.command] for r in RULES)
    assert spec().command_words == ACCESS


def test_the_levels_follow_the_table_words() -> None:
    levels = {r.command: level_of(r) for r in RULES}
    assert levels["ApproveRequisition"] == levels["ScheduleWorkOrder"] == "controller"
    assert levels["StartWorkOrder"] == levels["EditRequisition"] == "user"
    assert normalise_word(ACCESS["RaiseRequisition"]) == "user"


def test_every_command_is_a_proposable_row_or_an_exclusion() -> None:
    # the exclusion file lists every module's commands (SR3 F4): compare only this module's own
    excluded = set(tomllib.loads(EXCLUSIONS.read_text())["commands"]) & set(ACCESS)
    own = [p for p in PROPOSABLE if p.model.__name__ in ACCESS]
    rows = {p.model.__name__ for p in own}
    assert rows == {"RaiseRequisition"} and [p.tool for p in own] == ["propose_requisition"]
    assert rows | excluded == set(ACCESS) and not rows & excluded
    assert all(reason for reason in tomllib.loads(EXCLUSIONS.read_text())["commands"].values())


def test_states_for_says_which_button_shows_in_which_state() -> None:
    assert states_for("ApproveRequisition", REQUISITION_TYPES[0]) == ("Requested",)
    assert states_for("CancelRequisition", REQUISITION_TYPES[1]) == ("Requested", "Approved")
    assert states_for("StartWorkOrder", WORK_ORDER) == ("Scheduled",)


def test_the_offers_follow_the_state_and_the_level(world) -> None:  # type: ignore[no-untyped-def]
    from tl_adapters.db import open_uow

    rid, wid = world.approved()

    def offered(record: str, *levels: str) -> list[str]:
        with open_uow(world.db, readonly=True) as uow:
            return [
                o.command for o in requisitions_actions(uow.conn(), record, lambda lv: lv in levels)
            ]

    assert offered(rid, "user", "controller") == ["CancelRequisition"]
    assert offered(wid, "user", "controller") == ["ScheduleWorkOrder", "AssignWorkOrder"]
    assert offered(wid, "user") == []
    assert offered(world.raise_labor(), "user") == ["EditRequisition", "CancelRequisition"]
    assert offered(world.raise_labor(), "controller") == ["ApproveRequisition", "RejectRequisition"]
