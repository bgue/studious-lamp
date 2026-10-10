"""``X-TL-Effective-At`` (FANOUT D5): honoured for simulation scopes, refused everywhere else."""

from __future__ import annotations

from typing import Any

import pytest
from harness import ALICE, SCOPE, Harness
from tl_api.effective import EFFECTIVE_AT_HEADER, resolve_effective_at
from tl_api.errors import ApiError

SIM = "project:sim-r1"
AT = "2026-11-02T08:15:00Z"


def create(
    h: Harness, scope: str, key: str, headers: dict[str, str] | None = None, **extra: Any
) -> Any:
    body = {"scope": scope, "record_type": "core.Record", "title": "T", "key": key, **extra}
    return h.client_for(ALICE).post("/commands/CreateRecord", json=body, headers=headers or {})


def test_a_simulation_scope_gets_the_header_as_effective_at(harness: Harness) -> None:
    response = create(harness, SIM, "S-1", {EFFECTIVE_AT_HEADER: AT}, psets={})
    assert response.status_code == 200, response.text
    event = response.json()["events"][0]
    assert event["effective_at"].startswith("2026-11-02T08:15:00")
    assert event["recorded_at"] != event["effective_at"]  # the real clock still stamps recorded_at
    assert event["source"] == "api" and event["actor"] == ALICE


def test_automatic_numbering_cannot_key_a_simulation_scope(harness: Harness) -> None:
    """`{project}` is letters and digits and `sim-r1` has a dash, so the simulator assigns keys."""
    body = {"scope": SIM, "record_type": "core.Record", "title": "T"}
    response = harness.client_for(ALICE).post(
        "/commands/CreateRecord", json=body, headers={EFFECTIVE_AT_HEADER: AT}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "numbering_value"


def test_without_the_header_effective_at_is_recorded_at(harness: Harness) -> None:
    event = create(harness, SIM, "S-2").json()["events"][0]
    assert event["effective_at"] == event["recorded_at"]


@pytest.mark.parametrize("scope", [SCOPE, "company", "project:simulated-x", "project:sim"])
def test_any_other_scope_is_a_400_and_nothing_is_written(harness: Harness, scope: str) -> None:
    response = create(harness, scope, "N-1", {EFFECTIVE_AT_HEADER: AT})
    assert response.status_code == 400
    assert response.json()["error"] == "effective_time_forbidden"
    assert create(harness, scope, "N-1").status_code == 200  # the key was never taken


@pytest.mark.parametrize("value", ["tomorrow", "2026-11-02T08:15:00", "", "2026-13-40T00:00:00Z"])
def test_a_value_that_is_not_an_offset_instant_is_a_400(harness: Harness, value: str) -> None:
    response = create(harness, SIM, "B-1", {EFFECTIVE_AT_HEADER: value})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_effective_time"


def test_a_failed_command_leaves_the_override_unset_for_the_next_request(
    harness: Harness,
) -> None:
    create(harness, SIM, "D-1", {EFFECTIVE_AT_HEADER: AT})
    duplicate = create(harness, SIM, "D-1", {EFFECTIVE_AT_HEADER: AT})
    assert duplicate.status_code == 409
    event = create(harness, SIM, "D-2").json()["events"][0]
    assert event["effective_at"] == event["recorded_at"]


def test_the_stored_event_carries_it_for_readers(harness: Harness) -> None:
    create(harness, SIM, "E-1", {EFFECTIVE_AT_HEADER: "2026-11-03T09:00:00+02:00"})
    page = harness.client_for(ALICE).get("/events", params={"scope": SIM}).json()
    assert page["events"][0]["effective_at"].startswith("2026-11-03T07:00:00")


def test_resolve_converts_to_utc_and_ignores_an_absent_header() -> None:
    assert resolve_effective_at(None, "project:P123") is None  # absent: nothing to refuse
    got = resolve_effective_at("2026-11-03T09:00:00+02:00", SIM)
    assert got is not None and got.isoformat() == "2026-11-03T07:00:00+00:00"


def test_resolve_names_its_refusals() -> None:
    with pytest.raises(ApiError) as forbidden:
        resolve_effective_at(AT, "project:P123")
    assert (forbidden.value.status, forbidden.value.error) == (400, "effective_time_forbidden")
    with pytest.raises(ApiError) as invalid:
        resolve_effective_at("soon", SIM)
    assert invalid.value.error == "invalid_effective_time"


def test_the_openapi_document_lists_the_header_on_command_routes(harness: Harness) -> None:
    operation = harness.app.openapi()["paths"]["/commands/CreateRecord"]["post"]
    names = [p["name"] for p in operation["parameters"] if p["in"] == "header"]
    assert EFFECTIVE_AT_HEADER.lower() in [n.lower() for n in names]
