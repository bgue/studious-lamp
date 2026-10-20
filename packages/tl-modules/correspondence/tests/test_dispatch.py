"""``/raise rfi`` from a record thread makes a real RFI of the module (P1-I6 T05b).

The target builds one ``RaiseTechnical`` command; the thread planner (core) checks the person's
access and dry-runs it. Keys are read as the person dispatching (ADR-0016).
"""

from __future__ import annotations

from typing import Any

from tl_adapters.db import open_uow
from tl_core import confidentiality as cf
from tl_core.integration.contract import PlannedCommand, Problem, RecordRef
from tl_core.threads.contract import DispatchContext
from tl_core.threads.parser import CommandLineParser
from tl_core.threads.targets import load_targets
from tl_mod_correspondence.dispatch import RaiseRfiTarget, plan_raise_rfi, targets
from tl_mod_correspondence.handlers.technical import RaiseTechnical
from tl_mod_correspondence.limits import MAX_TEXT
from tl_mod_correspondence.testing import CONTROLLER, CorrWorld, frozen_today

SCOPE = "project:P123"
MONDAY = "2026-10-19"


def context(record_id: str) -> DispatchContext:
    return DispatchContext(
        record=RecordRef(
            id=record_id, key="P123-RFI-0001", record_type="correspondence.TechnicalItem"
        ),
        scope=SCOPE,
        actor="user:alice",
        today=MONDAY,
        now=f"{MONDAY}T09:00:00Z",
    )


def plan(world: CorrWorld, line: str, record_id: str = "01J0000000000000000000000A") -> Any:
    parsed = CommandLineParser().parse(line)
    assert parsed is not None and not hasattr(parsed, "code"), parsed
    with open_uow(world.db, readonly=True) as uow:
        return plan_raise_rfi(uow, context(record_id), parsed)  # type: ignore[arg-type]


def test_a_title_makes_one_raise_technical_with_the_title_as_subject_and_question(
    world: CorrWorld,
) -> None:
    [planned] = plan(world, "/raise rfi Clash with line 47")
    assert isinstance(planned, PlannedCommand) and planned.command_type == "RaiseTechnical"
    assert planned.command == {
        "subtype": "rfi",
        "subject": "Clash with line 47",
        "question": "Clash with line 47",
        "references": [],
    }
    assert planned.summary == "Raise RFI: Clash with line 47"
    RaiseTechnical(actor="user:alice", source="test", scope=SCOPE, **planned.command)  # valid


def test_the_lines_after_the_first_are_the_question(world: CorrWorld) -> None:
    [planned] = plan(world, "/raise rfi Clash with line 47\nThe isometric clashes with beam B12.")
    assert planned.command["subject"] == "Clash with line 47"
    assert planned.command["question"] == "The isometric clashes with beam B12."


def test_each_key_the_line_names_becomes_a_reference(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        first = world.raise_technical()
        second = world.raise_technical(subject="Second")
    [planned] = plan(world, f"/raise rfi #{first.key} #{second.key} Clash")
    assert planned.command["references"] == [
        {"record_id": first.stream_id, "note": "raised against"},
        {"record_id": second.stream_id, "note": "raised against"},
    ]


def test_no_title_a_long_title_and_an_unknown_key_are_problems(world: CorrWorld) -> None:
    missing = plan(world, "/raise rfi")
    assert isinstance(missing, Problem) and missing.code == "missing_argument"
    long = plan(world, "/raise rfi " + "x" * (MAX_TEXT + 1))
    assert isinstance(long, Problem) and long.code == "too_long"
    unknown = plan(world, "/raise rfi #P123-RFI-9999 Clash")
    assert isinstance(unknown, Problem) and unknown.code == "unknown_key"


def test_a_key_the_person_may_not_read_is_unknown_like_a_missing_one(world: CorrWorld) -> None:
    with frozen_today(MONDAY):
        made = world.raise_technical()
        world.submit_technical(made.stream_id)
        with cf.use_viewer(CONTROLLER):
            world.set_class(made.stream_id, "restricted")
    hidden = plan(world, f"/raise rfi #{made.key} Clash")
    missing = plan(world, "/raise rfi #P123-RFI-9999 Clash")
    assert isinstance(hidden, Problem) and isinstance(missing, Problem)
    assert hidden.code == missing.code == "unknown_key"
    assert made.key is not None  # the message names the key the person typed, nothing else
    assert hidden.message.replace(made.key, "K") == missing.message.replace("P123-RFI-9999", "K")


def test_the_module_target_replaces_the_core_placeholder_and_nothing_else() -> None:
    registry = load_targets()
    found = registry.get("raise", "rfi")
    assert isinstance(found, RaiseRfiTarget) and found.verb == "raise" and found.name == "rfi"
    assert [(t.verb, t.name) for t in targets()] == [("raise", "rfi")]
    core = registry.get("raise", "record")
    assert core is not None and type(core).__module__.startswith("tl_core.")
