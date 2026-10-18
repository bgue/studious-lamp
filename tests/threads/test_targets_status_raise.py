"""The /status and /raise record targets: the commands each verb builds (P1-I7 WS-B, T10b).

Provided; do not edit.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from thread_world import P1, make_record, planning_world, run_target
from tl_adapters.db import DbTarget, open_uow
from tl_core.integration.contract import Problem
from tl_core.services.workflow import TransitionWorkflow, handle_transition_workflow
from tl_core.threads.contract import DispatchTarget
from tl_core.threads.targets.raise_record import MAX_TITLE_CHARS, RaiseRecordTarget
from tl_core.threads.targets.status import StatusTarget
from tl_core.workflow.loader import WorkflowRegistry
from tl_core.workflow.provider import use_workflows


@pytest.fixture(autouse=True)
def world() -> Iterator[None]:
    with planning_world():
        yield


def test_the_targets_are_dispatch_targets_with_their_names() -> None:
    assert isinstance(StatusTarget(), DispatchTarget)
    assert (StatusTarget().verb, StatusTarget().name) == ("status", "*")
    assert isinstance(RaiseRecordTarget(), DispatchTarget)
    assert (RaiseRecordTarget().verb, RaiseRecordTarget().name) == ("raise", "record")


def test_status_finds_the_transition_by_state_name_label_or_transition_name(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    for typed in ("Issued", "issued", '"Issued for use"', "issue"):
        planned = run_target(db, StatusTarget(), rid, f"/status {typed}")
        assert isinstance(planned, list) and len(planned) == 1, typed
        item = planned[0]
        assert item.command_type == "TransitionWorkflow"
        assert item.command == {"stream_id": rid, "expected_version": 1, "transition": "issue"}
        assert item.summary == "Move REC-1 to Issued for use"
        assert item.access is None and not item.permitted and item.problem is None


def test_status_carries_the_reason_and_never_a_role(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    planned = run_target(db, StatusTarget(), rid, "/status Issued all clear to proceed")
    assert isinstance(planned, list)
    assert planned[0].command["reason"] == "all clear to proceed"
    assert "actor_roles" not in planned[0].command


def test_status_starts_from_the_records_current_state_and_its_version(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    with open_uow(db) as uow:
        handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor="user:a",
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=1,
                transition="issue",
            ),
        )
    planned = run_target(db, StatusTarget(), rid, "/status Closed")
    assert isinstance(planned, list)
    assert planned[0].command["transition"] == "close"
    assert planned[0].command["expected_version"] == 2


def test_status_says_where_the_record_can_go_when_the_state_does_not_fit(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    problem = run_target(db, StatusTarget(), rid, "/status Closed")
    assert isinstance(problem, Problem) and problem.code == "unknown_state"
    assert "Issued for use" in problem.message


def test_status_names_the_transitions_when_two_fit(db: DbTarget) -> None:
    flow = {
        "id": "t.two",
        "version": 1,
        "record_type": "core.Record",
        "initial_state": "Draft",
        "states": [{"name": "Draft"}, {"name": "Done"}],
        "transitions": [
            {"name": "finish", "from": ["Draft"], "to": "Done"},
            {"name": "waive", "from": ["Draft"], "to": "Done"},
        ],
    }
    from tl_core.workflow.definition import WorkflowDefinition

    rid = make_record(db, "REC-1")
    with use_workflows(WorkflowRegistry([WorkflowDefinition.model_validate(flow)])):
        problem = run_target(db, StatusTarget(), rid, "/status Done")
        assert isinstance(problem, Problem) and problem.code == "ambiguous_transition"
        assert "finish" in problem.message and "waive" in problem.message
        chosen = run_target(db, StatusTarget(), rid, "/status waive")
        assert isinstance(chosen, list) and chosen[0].command["transition"] == "waive"


def test_status_without_a_workflow_is_a_problem(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    with use_workflows(WorkflowRegistry()):
        problem = run_target(db, StatusTarget(), rid, "/status Issued")
    assert isinstance(problem, Problem) and problem.code == "no_workflow"


def test_raise_builds_a_createrecord_and_one_raised_against_link_per_target(
    db: DbTarget,
) -> None:
    rid = make_record(db, "REC-1")
    a, b = make_record(db, "REC-A"), make_record(db, "REC-B")
    planned = run_target(
        db, RaiseRecordTarget(), rid, "/raise record #REC-A #REC-B Clash at grid C4"
    )
    assert isinstance(planned, list) and len(planned) == 3
    assert planned[0].command_type == "CreateRecord"
    assert planned[0].command == {"record_type": "core.Record", "title": "Clash at grid C4"}
    assert planned[0].summary == "Create record: Clash at grid C4"
    assert [p.command_type for p in planned[1:]] == ["AddLink", "AddLink"]
    assert [p.command for p in planned[1:]] == [
        {"from_id": "$result:0", "to_id": a, "relation": "raised_against"},
        {"from_id": "$result:0", "to_id": b, "relation": "raised_against"},
    ]
    assert planned[1].summary == "Link the new record raised against REC-A"


def test_raise_puts_the_note_in_the_description(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    planned = run_target(db, RaiseRecordTarget(), rid, "/raise record Leak\nseen at 07:30")
    assert isinstance(planned, list) and len(planned) == 1
    assert planned[0].command["description"] == "seen at 07:30"


def test_raise_needs_a_title_and_refuses_a_long_one(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    missing = run_target(db, RaiseRecordTarget(), rid, "/raise record")
    assert isinstance(missing, Problem) and missing.code == "missing_argument"
    only_key = run_target(db, RaiseRecordTarget(), rid, "/raise record #REC-1")
    assert isinstance(only_key, Problem) and only_key.code == "missing_argument"
    long = run_target(db, RaiseRecordTarget(), rid, "/raise record " + "x" * (MAX_TITLE_CHARS + 1))
    assert isinstance(long, Problem) and long.code == "too_long"


def test_raise_answers_a_problem_for_a_target_it_cannot_resolve(db: DbTarget) -> None:
    rid = make_record(db, "REC-1")
    problem = run_target(db, RaiseRecordTarget(), rid, "/raise record #NOPE Leak")
    assert isinstance(problem, Problem) and problem.code == "unknown_key"
