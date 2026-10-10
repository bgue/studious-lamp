"""``POST /commands/{CommandName}``: the shared command models over HTTP."""

from __future__ import annotations

from typing import Any

import pytest
from harness import ALICE, SCOPE, Harness
from tl_api.commands import COMMANDS
from tl_core.services.queries import get_record_by_id


def post(h: Harness, name: str, body: dict[str, Any], actor: str = ALICE) -> Any:
    return h.client_for(actor).post(f"/commands/{name}", json=body)


def create(h: Harness, key: str = "REC-1", **extra: Any) -> dict[str, Any]:
    response = post(
        h,
        "CreateRecord",
        {"scope": SCOPE, "record_type": "core.Record", "title": "Valve", "key": key, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_every_command_in_the_table_has_a_route(harness: Harness) -> None:
    paths = harness.app.openapi()["paths"]
    assert {f"/commands/{spec.name}" for spec in COMMANDS} <= set(paths)
    assert len(COMMANDS) == 13


def test_create_record_returns_the_command_result(harness: Harness) -> None:
    result = create(harness)
    assert result["key"] == "REC-1" and result["version"] == 1
    assert result["events"][0]["event_type"] == "Record.Created"
    with harness.backend(True) as uow:
        assert get_record_by_id(uow, result["stream_id"]) is not None


def test_the_actor_comes_from_the_token_and_the_source_defaults_to_api(harness: Harness) -> None:
    result = post(
        harness,
        "CreateRecord",
        {"scope": SCOPE, "record_type": "core.Record", "title": "T", "key": "K-1"},
        actor="user:bob",
    ).json()
    event = result["events"][0]
    assert event["actor"] == "user:bob" and event["source"] == "api"


def test_a_client_may_name_its_source_but_not_its_actor(harness: Harness) -> None:
    ok = create(harness, "K-2", source="tui")
    assert ok["events"][0]["source"] == "tui"
    forged = post(
        harness,
        "CreateRecord",
        {
            "scope": SCOPE,
            "record_type": "core.Record",
            "title": "T",
            "key": "K-3",
            "actor": "user:x",
        },
    )
    assert forged.status_code == 422
    assert forged.json()["error"] == "validation_error"
    bad_source = post(
        harness,
        "CreateRecord",
        {"scope": SCOPE, "record_type": "core.Record", "title": "T", "key": "K-4", "source": "A b"},
    )
    assert bad_source.status_code == 422


def test_update_edit_and_psets_use_the_expected_version(harness: Harness) -> None:
    made = create(harness)
    sid = made["stream_id"]
    updated = post(
        harness,
        "UpdateRecord",
        {"scope": SCOPE, "stream_id": sid, "expected_version": 1, "changes": {"title": "New"}},
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    stale = post(
        harness,
        "UpdateRecord",
        {"scope": SCOPE, "stream_id": sid, "expected_version": 1, "changes": {"title": "Other"}},
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == "concurrency_conflict"
    edited = post(
        harness,
        "EditRecord",
        {
            "scope": SCOPE,
            "stream_id": sid,
            "expected_version": 2,
            "changes": {"description": "d"},
            "pset_edits": [],
        },
    )
    assert edited.status_code == 200 and edited.json()["version"] == 3


def test_service_errors_use_the_table(harness: Harness) -> None:
    create(harness)
    duplicate = post(
        harness,
        "CreateRecord",
        {"scope": SCOPE, "record_type": "core.Record", "title": "T", "key": "REC-1"},
    )
    assert (duplicate.status_code, duplicate.json()["error"]) == (409, "duplicate_key")
    missing = post(
        harness,
        "UpdateRecord",
        {"scope": SCOPE, "stream_id": "nope", "expected_version": 1, "changes": {"title": "x"}},
    )
    assert (missing.status_code, missing.json()["error"]) == (404, "record_not_found")
    unsupported = post(
        harness,
        "CreateRecord",
        {"scope": SCOPE, "record_type": "piping.Weld", "title": "T", "key": "W-1"},
    )
    assert (unsupported.status_code, unsupported.json()["error"]) == (
        422,
        "unsupported_record_type",
    )


def test_command_validators_still_run(harness: Harness) -> None:
    bad_scope = post(
        harness,
        "CreateRecord",
        {"scope": "everywhere", "record_type": "core.Record", "title": "T", "key": "K"},
    )
    assert bad_scope.status_code == 422 and bad_scope.json()["error"] == "validation_error"
    made = create(harness)
    blank = post(
        harness,
        "RetractLink",
        {"scope": SCOPE, "link_id": made["stream_id"], "reason": "  "},
    )
    assert blank.status_code == 422 and "reason" in blank.json()["message"]


def test_a_failed_command_writes_nothing(harness: Harness) -> None:
    made = create(harness)
    before = harness.backend.ledger.head_seq()
    post(
        harness,
        "EditRecord",
        {
            "scope": SCOPE,
            "stream_id": made["stream_id"],
            "expected_version": 1,
            "changes": {"title": "Changed"},
            "pset_edits": [{"pset": "no_such_pset", "layer": "standard", "values": {"a": 1}}],
        },
    )
    assert harness.backend.ledger.head_seq() == before  # atomic: the title change rolled back


def test_links_and_the_workflow_through_commands(harness: Harness) -> None:
    a = create(harness, "A-1")
    b = create(harness, "B-1")
    link = post(
        harness,
        "AddLink",
        {
            "scope": SCOPE,
            "from_id": a["stream_id"],
            "to_id": b["stream_id"],
            "relation": "requires",
        },
    )
    assert link.status_code == 200, link.text
    retract = post(
        harness,
        "RetractLink",
        {"scope": SCOPE, "link_id": link.json()["stream_id"], "reason": "mistake"},
    )
    assert retract.status_code == 200, retract.text
    submitted = post(
        harness,
        "TransitionWorkflow",
        {
            "scope": SCOPE,
            "stream_id": a["stream_id"],
            "expected_version": 1,
            "transition": "submit",
        },
    )
    assert submitted.status_code == 200, submitted.text
    blocked = post(
        harness,
        "TransitionWorkflow",
        {
            "scope": SCOPE,
            "stream_id": a["stream_id"],
            "expected_version": submitted.json()["version"],
            "transition": "approve",
        },
    )
    assert blocked.status_code == 409 and blocked.json()["error"] == "guard_failed"
    assert any(not r["passed"] for r in blocked.json()["results"])


@pytest.mark.parametrize("spec", COMMANDS, ids=lambda s: s.name)
def test_a_command_with_no_body_is_a_422_not_a_500(harness: Harness, spec) -> None:  # type: ignore[no-untyped-def]
    response = harness.client.post(f"/commands/{spec.name}", json={})
    assert response.status_code == 422 and response.json()["error"] == "validation_error"
