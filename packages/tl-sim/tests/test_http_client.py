"""``HttpSimClient`` against the real API app (no feed calls: those arrive with workstream B)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from suite import SCOPE, START, Suite, build_suite, close_suite
from tl_core.services.commands import CreateRecord
from tl_core.services.errors import GuardFailedError, UnknownTransitionError
from tl_mod_schedule import testing as schedule_testing
from tl_mod_schedule.testing import ScheduleWorld
from tl_sim.client import ProposeUnavailableError, ScheduleDesk, install_stamp
from tl_sim.clock import SimClock
from tl_xer.synth import make_xer, series

CREW = "user:sim-crew"


def test_a_record_is_created_with_a_client_key_the_actors_token_and_the_run_source(
    suite: Suite,
) -> None:
    client = suite.client(CREW)
    made = client.create_record(record_type="core.Record", title="Valve V001")
    assert made["key"] == "SIMRT1-REC-0001" and made["version"] == 1
    history = suite.api(CREW).history(made["id"])
    (event,) = history
    assert (event.actor, event.source, event.scope) == (CREW, "sim:rt1", SCOPE)
    assert event.payload["title"] == "Valve V001"


def test_keys_run_on_across_records_and_clients(suite: Suite) -> None:
    keys = [
        suite.client(CREW).create_record(record_type="core.Record", title=f"R{n}")["key"]
        for n in range(3)
    ]
    other = suite.client("user:sim-planner").create_record(record_type="core.Record", title="P")
    assert keys + [other["key"]] == [f"SIMRT1-REC-000{n}" for n in range(1, 5)]


def test_every_write_carries_the_simulated_time_and_it_moves_one_step_each_time(
    suite: Suite,
) -> None:
    clock = SimClock(START)
    client = suite.client(CREW, clock)
    first = client.create_record(record_type="core.Record", title="A")
    second = client.create_record(record_type="core.Record", title="B")
    seen = {
        e.stream_id: e.effective_at
        for e in suite.api("user:alice").events_after(0, scope=SCOPE).events
    }
    assert seen[first["id"]] == datetime(2026, 11, 2, 7, 1, tzinfo=UTC)
    assert seen[second["id"]] == datetime(2026, 11, 2, 7, 2, tzinfo=UTC)
    recorded = suite.api("user:alice").history(first["id"])[0].recorded_at
    assert recorded != seen[first["id"]]  # recorded_at is the real clock, stamped by the server


def test_without_the_stamp_nothing_is_simulated(suite: Suite) -> None:
    api = suite.api(CREW)  # no request hook
    result = api.create_record(
        CreateRecord(
            actor="x", source="sim:rt1", scope=SCOPE, record_type="core.Record", title="t", key="K1"
        )
    )
    assert result.events[0].effective_at == result.events[0].recorded_at


def test_psets_are_set_per_pset_and_read_back(suite: Suite) -> None:
    client = suite.client(CREW)
    valve = client.create_record(record_type="core.Record", title="Valve")
    done = client.set_psets(
        valve["id"], {"valve_data": {"size_in": 6, "body_material": "CS", "manufacturer": "Crane"}}
    )
    assert done["version"] == 2
    (found,) = client.query("title~Valve")
    assert found["psets"]["valve_data"] == {
        "size_in": 6,
        "body_material": "CS",
        "manufacturer": "Crane",
    }


def test_links_and_transitions_follow_the_sample_workflow(suite: Suite) -> None:
    client = suite.client(CREW)
    line = client.create_record(record_type="core.Record", title="Line 6-CS-1001")
    doc = client.create_record(record_type="core.Record", title="Doc 001")
    with pytest.raises(UnknownTransitionError):
        client.transition(doc["id"], "approve")  # a draft cannot be approved
    assert client.transition(doc["id"], "submit")["state"] == "Review"
    with pytest.raises(GuardFailedError):
        client.transition(doc["id"], "approve")  # the guard wants a references link
    link = client.link(doc["id"], line["id"], "references")
    assert link["link_id"]
    assert client.transition(doc["id"], "approve")["state"] == "Approved"
    assert [r["status"] for r in client.query("title~Doc")] == ["Approved"]


def test_a_query_is_scoped_to_the_run_and_takes_the_query_language(suite: Suite) -> None:
    client = suite.client(CREW)
    for title in ("Valve A", "Valve B", "Pump"):
        client.create_record(record_type="core.Record", title=title)
    assert [r["title"] for r in client.query("title~valve")] == ["Valve A", "Valve B"]
    assert [r["title"] for r in client.query("", limit=2)] == ["Valve A", "Valve B"]
    assert client.query("status:null")  # records with no workflow state yet


def test_propose_without_an_mcp_caller_says_so(suite: Suite) -> None:
    with pytest.raises(ProposeUnavailableError):
        suite.client(CREW).propose("link_records", {})


def test_propose_goes_to_the_mcp_caller_as_the_actor(suite: Suite) -> None:
    class Caller:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
            self.calls.append((name, arguments))
            return {"proposal_id": "p1"}

    caller = Caller()
    client = suite.client(CREW, mcp=caller)
    assert client.propose("link_records", {"a": 1}) == {"proposal_id": "p1"}
    assert caller.calls == [("link_records", {"a": 1})]


def test_install_stamp_adds_the_header_to_every_request() -> None:
    clock = SimClock(START)
    seen: list[str] = []
    transport = httpx2.MockTransport(
        lambda request: (seen.append(request.headers["X-TL-Effective-At"]), httpx2.Response(200))[1]
    )
    http = httpx2.Client(transport=transport, base_url="http://x")
    install_stamp(http, clock)
    http.get("/a")
    clock.tick()
    http.get("/b")
    assert seen == ["2026-11-02T07:00:00+00:00", "2026-11-02T07:01:00+00:00"]


# --- the schedule desk (P1-I4) --------------------------------------------------------------------


def test_the_schedule_desk_sends_an_update_and_links_a_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    monkeypatch.setattr(schedule_testing, "PROJECT", SCOPE)
    monkeypatch.setitem(schedule_testing.BASE, "scope", SCOPE)
    suite = build_suite(tmp_path, objects=True)
    try:
        controller = ScheduleWorld(suite.db, tmp_path / "objects")
        controller.define(owner="Planning")
        controller.publish(controller.upload(make_xer(series(1, 1)[0])))
        client = suite.client("user:sim-schedule_updater")
        [listed] = client.schedules()
        assert (listed["code"], listed["current_snapshot_number"], listed["snapshot_count"]) == (
            "MAIN",
            1,
            1,
        )
        assert [(s["number"], s["state"]) for s in client.snapshots_of("MAIN")] == [
            (1, "Published")
        ]
        activities = client.current_activities("MAIN", limit=3)
        assert len(activities) == 3 and {"activity_id", "name"} <= set(activities[0])
        opened = client.open_snapshot(listed["id"])
        assert opened["key"] == "MAIN#2"
        attached = client.attach_snapshot_file(
            opened["id"], "update.xer", make_xer(series(1, 2)[1])
        )
        assert attached["size"] > 0
        client.start_snapshot(opened["id"])
        second = client.snapshots_of("MAIN")[0]
        assert (second["key"], second["source_name"], second["requested_by"]) == (
            "MAIN#2",
            "update.xer",
            "user:sim-schedule_updater",
        )
        record = suite.client("user:sim-planner").create_record(
            record_type="core.Record", title="Activity 001 x"
        )
        first = client.link_activity(record["id"], listed["id"], activities[0]["activity_id"])
        assert first["ref_created"] is True
        again = suite.client("user:sim-planner").create_record(
            record_type="core.Record", title="Activity 002 x"
        )
        assert (
            client.link_activity(again["id"], listed["id"], activities[0]["activity_id"])[
                "ref_created"
            ]
            is False
        )
    finally:
        close_suite(suite)


def test_the_schedule_desk_cannot_define_or_publish() -> None:
    forbidden = {"define_schedule", "publish_schedule_snapshot", "void_schedule_snapshot"}
    assert forbidden.isdisjoint(set(dir(ScheduleDesk)))
