"""``GET /events``: the paged pull side of the change feed."""

from __future__ import annotations

from harness import SCOPE, Harness


def test_an_empty_ledger_has_no_events(harness: Harness) -> None:
    page = harness.client.get("/events").json()
    assert page == {"events": [], "next_seq": 0, "has_more": False}


def test_events_come_oldest_first_and_page_by_seq(harness: Harness) -> None:
    for n in range(5):
        harness.create_record(f"K-{n}")
    first = harness.client.get("/events", params={"limit": 2}).json()
    assert [e["seq"] for e in first["events"]] == [1, 2]
    assert first["has_more"] is True and first["next_seq"] == 2
    second = harness.client.get("/events", params={"after": first["next_seq"], "limit": 10}).json()
    assert [e["seq"] for e in second["events"]] == [3, 4, 5]
    assert second["has_more"] is False and second["next_seq"] == 5
    assert second["events"][0]["event_type"] == "Record.Created"
    assert second["events"][0]["payload"]["key"] == "K-2"


def test_filters_by_scope_type_and_record(harness: Harness) -> None:
    a = harness.create_record("A-1")
    harness.create_record("B-1", scope="project:P999")
    only_p123 = harness.client.get("/events", params={"scope": SCOPE}).json()
    assert [e["payload"]["key"] for e in only_p123["events"]] == ["A-1"]
    created = harness.client.get("/events", params={"type": "*.Created"}).json()
    assert len(created["events"]) == 2
    nothing = harness.client.get("/events", params={"type": ["Link.*", "File.*"]}).json()
    assert nothing["events"] == []
    assert nothing["next_seq"] == 2  # moved past the events the filter rejected
    one = harness.client.get("/events", params={"record_id": a.stream_id}).json()
    assert [e["stream_id"] for e in one["events"]] == [a.stream_id]


def test_bad_parameters_are_422(harness: Harness) -> None:
    for params in ({"limit": 0}, {"limit": 5000}, {"after": -1}):
        response = harness.client.get("/events", params=params)
        assert response.status_code == 422, params
        assert response.json()["error"] == "validation_error"
