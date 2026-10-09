"""Workflow engine: guards, TransitionWorkflow, status, projection (P0-I3-T09; brief 8)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from tl_adapters.sqlite.uow import create_schema, open_uow, rebuild_projections
from tl_core.ledger import ConcurrencyError, Event
from tl_core.links.expected import ExpectedLink, ExpectedLinkRegistry
from tl_core.services.commands import CreateRecord, VoidRecord
from tl_core.services.errors import (
    GuardFailedError,
    InvalidStateError,
    NoWorkflowError,
    RecordNotFoundError,
    RecordVoidedError,
    UnknownTransitionError,
)
from tl_core.services.psets import SetPsetValues, handle_set_pset_values
from tl_core.services.records import handle_create_record, handle_void_record
from tl_core.services.workflow import (
    TransitionWorkflow,
    WorkflowStatus,
    handle_transition_workflow,
    workflow_status,
)
from tl_core.workflow.definition import WorkflowDefinition
from tl_core.workflow.loader import WorkflowRegistry
from tl_core.workflow.provider import use_expected_links, use_workflows

P1 = "project:P123"
VALVE: dict[str, Any] = {"manufacturer": "Acme", "size_in": 4, "body_material": "CS"}

FLOW: dict[str, Any] = {
    "id": "t.flow",
    "version": 3,
    "record_type": "core.Record",
    "initial_state": "Draft",
    "states": [
        {"name": "Draft", "label": "Draft"},
        {"name": "Design"},
        {"name": "Review"},
        {"name": "Done"},
    ],
    "transitions": [
        {
            "name": "start",
            "from": ["Draft"],
            "to": "Design",
            "label": "Start design",
            "guards": [
                {
                    "kind": "required_psets",
                    "psets": ["valve_data"],
                    "values": ["valve_data.manufacturer"],
                },
                {"kind": "conformance", "max_status": "ok"},
            ],
        },
        {
            "name": "review",
            "from": ["Design"],
            "to": "Review",
            "guards": [
                {"kind": "required_links", "links": [{"relation": "requires", "min_count": 2}]}
            ],
        },
        {
            "name": "finish",
            "from": ["Review"],
            "to": "Done",
            "guards": [
                {"kind": "expected_links"},
                {"kind": "roles", "any_of": ["manager", "admin"]},
            ],
        },
        {"name": "back", "from": ["Design", "Review"], "to": "Draft"},
        {"name": "skip", "from": ["Draft"], "to": "Review", "guards": [{"kind": "conformance"}]},
    ],
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tl.db"
    create_schema(path)
    return path


@pytest.fixture(autouse=True)
def definitions() -> Iterator[None]:
    expected = ExpectedLinkRegistry(
        {
            "core.Record": [
                ExpectedLink(relation="references", by_state="Done", label="evidence"),
                ExpectedLink(relation="blocks", by_state="Review", label="other state"),
            ]
        }
    )
    with (
        use_workflows(WorkflowRegistry([WorkflowDefinition.model_validate(FLOW)])),
        use_expected_links(expected),
    ):
        yield


def new_record(db: Path, key: str, scope: str = P1) -> str:
    with open_uow(db) as uow:
        return handle_create_record(
            uow,
            CreateRecord(
                actor="u", source="t", scope=scope, record_type="core.Record", title=key, key=key
            ),
        ).stream_id


def version(db: Path, record_id: str) -> int:
    with open_uow(db, readonly=True) as uow:
        return int(
            uow.conn()
            .execute(text("SELECT version FROM cur_core_record WHERE id = :i"), {"i": record_id})
            .scalar_one()
        )


def set_psets(db: Path, record_id: str, values: dict[str, Any]) -> None:
    with open_uow(db) as uow:
        handle_set_pset_values(
            uow,
            SetPsetValues(
                actor="u",
                source="t",
                scope=P1,
                stream_id=record_id,
                expected_version=version(db, record_id),
                pset="valve_data",
                layer="standard",
                values=values,
            ),
        )


def add_link(db: Path, link_id: str, from_id: str, to_id: str, relation: str) -> None:
    with open_uow(db) as uow:
        uow.conn().execute(
            text(
                "INSERT INTO cur_links (link_id, scope, from_id, to_id, relation, status, source, "
                "declined, created_by, created_at, updated_at, version, last_seq) VALUES "
                "(:id, :s, :f, :t, :r, 'active', 'manual', 0, 'u', '2026', '2026', 1, 1)"
            ),
            {"id": link_id, "s": P1, "f": from_id, "t": to_id, "r": relation},
        )


def go(db: Path, record_id: str, name: str, *roles: str, scope: str = P1) -> list[Event]:
    with open_uow(db) as uow:
        return handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor="user:u-1",
                source="test",
                scope=scope,
                stream_id=record_id,
                expected_version=version(db, record_id),
                transition=name,
                actor_roles=list(roles),
            ),
        ).events


def status(db: Path, record_id: str, *roles: str) -> WorkflowStatus:
    with open_uow(db, readonly=True) as uow:
        return workflow_status(uow, record_id, roles=roles)


def row(db: Path, record_id: str) -> dict[str, Any]:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT * FROM cur_core_record WHERE id = :i"), {"i": record_id}
        )
        return dict(found.mappings().one())


def state_row(db: Path, record_id: str) -> dict[str, Any] | None:
    with open_uow(db, readonly=True) as uow:
        found = uow.conn().execute(
            text("SELECT * FROM cur_workflow_state WHERE record_id = :i"), {"i": record_id}
        )
        first = found.mappings().first()
        return dict(first) if first is not None else None


# --- a transition without guards ---------------------------------------------------------------


def test_a_guardless_transition_updates_the_status_and_emits_the_event(db: Path) -> None:
    rid = new_record(db, "A")
    (event,) = go(db, rid, "skip")  # conformance (default max warning) passes for an empty record
    assert event.event_type == "Workflow.Transitioned"
    assert event.stream_id == rid
    assert event.payload["workflow"] == "t.flow"
    assert event.payload["workflow_version"] == 3
    assert (event.payload["from_state"], event.payload["to_state"]) == ("Draft", "Review")
    assert event.payload["transition"] == "skip"
    assert event.payload["signature"] is None
    assert [g["kind"] for g in event.payload["guards_evaluated"]] == ["conformance"]
    assert all(g["passed"] for g in event.payload["guards_evaluated"])
    assert event.actor == "user:u-1"
    current = row(db, rid)
    assert current["status"] == "Review"
    assert current["version"] == 2
    assert current["last_seq"] == event.seq
    assert current["conformance"] == "ok"


def test_the_workflow_state_row_records_when_and_by_whom(db: Path) -> None:
    rid = new_record(db, "A")
    assert state_row(db, rid) is None
    (event,) = go(db, rid, "skip")
    state = state_row(db, rid)
    assert state is not None
    assert (state["workflow"], state["workflow_version"], state["state"]) == ("t.flow", 3, "Review")
    assert (state["transition"], state["transitioned_by"]) == ("skip", "user:u-1")
    assert state["last_seq"] == event.seq
    assert state["entered_at"] == row(db, rid)["updated_at"]
    go(db, rid, "back")
    again = state_row(db, rid)
    assert again is not None and again["state"] == "Draft"


def test_a_record_with_no_status_is_in_the_initial_state(db: Path) -> None:
    rid = new_record(db, "A")
    found = status(db, rid)
    assert found.state == "Draft"
    assert found.state_label == "Draft"
    assert found.workflow == "t.flow"
    assert found.workflow_version == 3
    assert found.key == "A"
    assert found.entered_at == row(db, rid)["created_at"]
    assert found.version == 1
    assert [o.transition for o in found.options] == ["start", "skip"]


# --- guards ------------------------------------------------------------------------------------


def test_required_psets_blocks_until_the_pset_and_value_exist(db: Path) -> None:
    rid = new_record(db, "A")
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "start")
    results = caught.value.results
    assert [r.kind for r in results] == ["required_psets", "conformance"]
    assert results[0].passed is False
    assert "pset valve_data has no values" in results[0].message
    assert "valve_data.manufacturer has no value" in results[0].message
    assert row(db, rid)["status"] is None  # nothing written
    assert version(db, rid) == 1


def test_conformance_is_evaluated_in_the_target_state(db: Path) -> None:
    rid = new_record(db, "A")
    set_psets(db, rid, {"manufacturer": "Acme", "body_material": "CS"})
    # Valid in Draft, but size_in is required in state Design, so entering Design is refused.
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "start")
    conformance = caught.value.results[1]
    assert (conformance.kind, conformance.passed) == ("conformance", False)
    assert conformance.details["state"] == "Design"
    assert conformance.details["status"] == "nonconformant"
    assert any("size_in" in issue["path"] for issue in conformance.details["issues"])
    assert "nonconformant in Design" in conformance.message

    set_psets(db, rid, {"size_in": 4})
    (event,) = go(db, rid, "start")
    assert event.payload["to_state"] == "Design"
    current = row(db, rid)
    assert current["status"] == "Design"
    assert current["conformance"] == "ok"
    assert current["effective_schema_hash"] == event.payload["effective_schema_hash"]


def test_conformance_guard_max_status_warning_lets_warnings_through(db: Path) -> None:
    rid = new_record(db, "A")
    set_psets(db, rid, {"manufacturer": "Acme", "tag_no": "bad tag"})  # advisory: a warning
    (event,) = go(db, rid, "skip")
    assert event.payload["conformance"] == "warning"
    assert row(db, rid)["conformance"] == "warning"


def test_required_links_counts_active_links(db: Path) -> None:
    rid = new_record(db, "A")
    one, two = new_record(db, "B"), new_record(db, "C")
    set_psets(db, rid, VALVE)
    go(db, rid, "start")
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "review")
    guard = caught.value.results[0]
    assert guard.kind == "required_links"
    assert "requires (0 of 2)" in guard.message
    add_link(db, "L1", rid, one, "requires")
    with pytest.raises(GuardFailedError, match=r"requires \(1 of 2\)"):
        go(db, rid, "review")
    add_link(db, "L2", rid, two, "requires")
    (event,) = go(db, rid, "review")
    assert event.payload["to_state"] == "Review"


def test_expected_links_guard_uses_expectations_of_the_target_state_only(db: Path) -> None:
    rid, other = new_record(db, "A"), new_record(db, "B")
    set_psets(db, rid, VALVE)
    go(db, rid, "start")
    add_link(db, "L1", rid, other, "requires")
    add_link(db, "L2", rid, new_record(db, "C"), "requires")
    go(db, rid, "review")
    # `finish` leads to Done: "evidence" (by Done) counts, "other state" (by Review) does not.
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "finish", "manager")
    guard = caught.value.results[0]
    assert guard.kind == "expected_links"
    assert "evidence" in guard.message and "other state" not in guard.message
    add_link(db, "L3", rid, other, "references")
    (event,) = go(db, rid, "finish", "manager")
    assert event.payload["to_state"] == "Done"
    assert [g["kind"] for g in event.payload["guards_evaluated"]] == ["expected_links", "roles"]


def test_roles_guard_is_a_stub_list_on_the_command(db: Path) -> None:
    rid, other = new_record(db, "A"), new_record(db, "B")
    set_psets(db, rid, VALVE)
    go(db, rid, "start")
    add_link(db, "L1", rid, other, "requires")
    add_link(db, "L2", rid, new_record(db, "C"), "requires")
    add_link(db, "L3", rid, other, "references")
    go(db, rid, "review")
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "finish")
    roles = caught.value.results[1]
    assert (roles.kind, roles.passed) == ("roles", False)
    assert roles.details["any_of"] == ["manager", "admin"]
    with pytest.raises(GuardFailedError):
        go(db, rid, "finish", "clerk")
    go(db, rid, "finish", "clerk", "admin")
    assert row(db, rid)["status"] == "Done"


def test_every_failed_guard_is_reported_together(db: Path) -> None:
    rid = new_record(db, "A")
    with pytest.raises(GuardFailedError) as caught:
        go(db, rid, "start")
    message = str(caught.value)
    assert "required_psets:" in message
    assert message.startswith("cannot start A:")


# --- refusals ----------------------------------------------------------------------------------


def test_an_unknown_transition_lists_what_is_available(db: Path) -> None:
    rid = new_record(db, "A")
    with pytest.raises(
        UnknownTransitionError, match=r"no transition 'nope' \(from Draft: start, skip\)"
    ):
        go(db, rid, "nope")


def test_a_transition_from_another_state_is_refused(db: Path) -> None:
    rid = new_record(db, "A")
    with pytest.raises(UnknownTransitionError, match="cannot start in state 'Draft'"):
        go(db, rid, "finish")


def test_a_record_without_a_workflow_is_refused(db: Path) -> None:
    rid = new_record(db, "A")
    with use_workflows(WorkflowRegistry()):
        with pytest.raises(NoWorkflowError, match="core.Record"):
            go(db, rid, "start")
        with open_uow(db, readonly=True) as uow, pytest.raises(NoWorkflowError):
            workflow_status(uow, rid)


def test_a_project_definition_overrides_the_company_one(db: Path) -> None:
    rid = new_record(db, "A")
    override = dict(FLOW, id="t.project", scope=P1, transitions=[
        {"name": "only", "from": ["Draft"], "to": "Done"}
    ])  # fmt: skip
    registry = WorkflowRegistry(
        [WorkflowDefinition.model_validate(FLOW), WorkflowDefinition.model_validate(override)]
    )
    with use_workflows(registry):
        assert [o.transition for o in status(db, rid).options] == ["only"]
        go(db, rid, "only")
    assert row(db, rid)["status"] == "Done"


def test_a_status_outside_the_workflow_is_refused(db: Path) -> None:
    rid = new_record(db, "A")
    with open_uow(db) as uow:
        uow.conn().execute(
            text("UPDATE cur_core_record SET status = 'Mystery' WHERE id = :i"), {"i": rid}
        )
    with pytest.raises(InvalidStateError, match="Mystery"):
        go(db, rid, "start")


def test_a_voided_record_cannot_change_state(db: Path) -> None:
    rid = new_record(db, "A")
    with open_uow(db) as uow:
        handle_void_record(
            uow,
            VoidRecord(
                actor="u", source="t", scope=P1, stream_id=rid, expected_version=1, reason="dup"
            ),
        )
    with pytest.raises(RecordVoidedError):
        go(db, rid, "skip")


def test_an_unknown_record_or_wrong_scope_is_refused(db: Path) -> None:
    rid = new_record(db, "A")

    def attempt(record_id: str, scope: str) -> None:
        with open_uow(db) as uow:
            handle_transition_workflow(
                uow,
                TransitionWorkflow(
                    actor="u",
                    source="t",
                    scope=scope,
                    stream_id=record_id,
                    expected_version=1,
                    transition="skip",
                ),
            )

    with pytest.raises(RecordNotFoundError):
        attempt("NOPE", P1)
    with pytest.raises(RecordNotFoundError):
        attempt(rid, "project:OTHER")
    with open_uow(db, readonly=True) as uow, pytest.raises(RecordNotFoundError):
        workflow_status(uow, "NOPE")


def test_a_stale_expected_version_is_a_concurrency_error(db: Path) -> None:
    rid = new_record(db, "A")
    with open_uow(db) as uow, pytest.raises(ConcurrencyError):
        handle_transition_workflow(
            uow,
            TransitionWorkflow(
                actor="u",
                source="t",
                scope=P1,
                stream_id=rid,
                expected_version=5,
                transition="skip",
            ),
        )
    assert row(db, rid)["status"] is None


def test_two_racing_transitions_only_one_wins(db: Path) -> None:
    rid = new_record(db, "A")
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker(name: str) -> None:
        try:
            with open_uow(db) as uow:
                handle_transition_workflow(
                    uow,
                    TransitionWorkflow(
                        actor="u",
                        source="t",
                        scope=P1,
                        stream_id=rid,
                        expected_version=1,
                        transition=name,
                    ),
                )
            result = f"ok:{name}"
        except (ConcurrencyError, UnknownTransitionError) as exc:
            result = type(exc).__name__
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=worker, args=("skip",), daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes).count("ok:skip") == 1
    assert row(db, rid)["version"] == 2


# --- status listing ----------------------------------------------------------------------------


def test_status_shows_each_option_with_its_guard_results(db: Path) -> None:
    rid = new_record(db, "A")
    found = status(db, rid)
    start, skip = found.options
    assert (start.transition, start.label, start.to_state, start.allowed) == (
        "start",
        "Start design",
        "Design",
        False,
    )
    assert [g.passed for g in start.guards] == [False, True]  # no pset: conformance is vacuous
    assert (skip.label, skip.allowed) == ("skip", True)


def test_status_after_a_transition_shows_state_and_time(db: Path) -> None:
    rid = new_record(db, "A")
    go(db, rid, "skip")
    found = status(db, rid)
    assert found.state == "Review"
    assert found.entered_at == row(db, rid)["updated_at"]
    assert found.version == 2
    assert [o.transition for o in found.options] == ["finish", "back"]
    finish = found.options[0]
    assert finish.allowed is False
    assert [g.kind for g in finish.guards if not g.passed] == ["expected_links", "roles"]
    assert status(db, rid, "manager").options[0].guards[1].passed is True


# --- replay ------------------------------------------------------------------------------------


def test_rebuilding_the_projections_restores_status_and_state(db: Path) -> None:
    rid = new_record(db, "A")
    go(db, rid, "skip")
    go(db, rid, "back")
    before = (row(db, rid), state_row(db, rid))
    assert rebuild_projections(db) == 3
    assert (row(db, rid), state_row(db, rid)) == before
    assert before[0]["status"] == "Draft"


def test_the_shipped_sample_workflow_runs_end_to_end(db: Path) -> None:
    from tl_core.links.expected import default_expected_links
    from tl_core.workflow.loader import default_workflows
    from tl_core.workflow.provider import use_expected_links as real_expected  # noqa: F401

    with use_workflows(default_workflows()), use_expected_links(default_expected_links()):
        rid, other = new_record(db, "A"), new_record(db, "B")
        go(db, rid, "submit")
        with pytest.raises(GuardFailedError, match="supporting record"):
            go(db, rid, "approve")
        add_link(db, "L1", rid, other, "references")
        go(db, rid, "approve")
        with pytest.raises(GuardFailedError, match="manager"):
            go(db, rid, "issue")
        go(db, rid, "issue", "manager")
        assert row(db, rid)["status"] == "Issued"
