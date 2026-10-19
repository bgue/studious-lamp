"""The /link and /dispatch targets: the commands each verb builds (P1-I7 WS-B, T10a).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from thread_world import make_record, planning_world, run_target
from tl_adapters.db import DbTarget
from tl_core.integration.contract import PlannedCommand, Problem
from tl_core.threads.contract import DispatchTarget
from tl_core.threads.targets.dispatch_action import ActionTarget
from tl_core.threads.targets.link import LinkTarget


@pytest.fixture(autouse=True)
def world() -> Iterator[None]:
    with planning_world():
        yield


def test_the_targets_are_dispatch_targets_with_their_verbs() -> None:
    for target, verb in ((LinkTarget(), "link"), (ActionTarget(), "dispatch")):
        assert isinstance(target, DispatchTarget)
        assert (target.verb, target.name) == (verb, "*")


def test_link_builds_one_addlink_per_key_from_the_threads_record(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    a, b = make_record(db, "REC-A"), make_record(db, "REC-B")
    planned = run_target(db, LinkTarget(), rid, "/link #REC-A REC-B")
    assert isinstance(planned, list) and len(planned) == 2
    assert [p.command_type for p in planned] == ["AddLink", "AddLink"]
    assert [p.command for p in planned] == [
        {"from_id": rid, "to_id": a},
        {"from_id": rid, "to_id": b},
    ]
    assert planned[0].summary == "Link REC-1 to REC-A"
    assert all(p.access is None and not p.permitted and p.problem is None for p in planned)


def test_link_carries_the_relation_and_the_note(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    a = make_record(db, "REC-A")
    planned = run_target(db, LinkTarget(), rid, "/link REC-A as requires\nbecause of the bevels")
    assert isinstance(planned, list)
    assert planned[0].command == {
        "from_id": rid,
        "to_id": a,
        "relation": "requires",
        "note": "because of the bevels",
    }
    assert planned[0].summary == "Link REC-1 to REC-A (requires)"


def test_link_names_only_the_commands_fields_never_the_servers(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    planned = run_target(db, LinkTarget(), rid, "/link REC-A")
    assert isinstance(planned, list)
    forbidden = {"actor", "source", "scope", "correlation_id", "causation_id", "link_source"}
    assert forbidden.isdisjoint(planned[0].command)


def test_link_answers_one_problem_for_keys_it_cannot_resolve(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    make_record(db, "REC-A")
    problem = run_target(db, LinkTarget(), rid, "/link REC-A NOPE-1 NOPE-2")
    assert isinstance(problem, Problem)
    assert problem.code == "unknown_key"
    assert "NOPE-1" in problem.message and "NOPE-2" in problem.message


def test_link_finds_a_key_in_the_company_scope_and_prefers_the_threads_scope(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    company = make_record(db, "SHARED", scope="company")
    planned = run_target(db, LinkTarget(), rid, "/link SHARED")
    assert isinstance(planned, list) and planned[0].command["to_id"] == company
    project = make_record(db, "SHARED")  # the same key in the thread's own project
    planned = run_target(db, LinkTarget(), rid, "/link SHARED")
    assert isinstance(planned, list) and planned[0].command["to_id"] == project


def test_dispatch_builds_an_invokeaction_on_the_threads_record(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    planned = run_target(
        db, ActionTarget(), rid, '/dispatch Send_To_NDE qty=2 urgent "6 inch CL300"'
    )
    assert isinstance(planned, list) and len(planned) == 1
    item: PlannedCommand = planned[0]
    assert item.command_type == "InvokeAction"
    assert item.command == {
        "action": "send_to_nde",
        "targets": [rid],
        "parameters": {"qty": "2", "text": "urgent 6 inch CL300"},
    }
    assert item.summary == "Run action send_to_nde on REC-1"


def test_dispatch_without_text_has_no_text_parameter_and_a_named_text_wins(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    plain = run_target(db, ActionTarget(), rid, "/dispatch crane-lift lift=3")
    assert isinstance(plain, list) and plain[0].command["parameters"] == {"lift": "3"}
    named = run_target(db, ActionTarget(), rid, "/dispatch crane-lift text=mine and more")
    assert isinstance(named, list)
    assert named[0].command["parameters"] == {"text": "mine"}
