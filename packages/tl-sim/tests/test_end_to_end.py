"""The real actors against the real API app and MCP server: a run passes ``sim_assert``, replays
identically from the same seed, and fails when someone else changes the project.

Records, psets, links, workflow, feed posts, queries, the events and their simulated times go over
HTTP to the real app. The assistant (an agent) proposes through the real MCP server, in memory on
the same ledger, and the approver (a person) accepts or rejects over HTTP. Nothing is stood in.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from suite import Suite, build_suite, close_suite
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_mcp.server import build_server as build_mcp_server
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.mcp_caller import McpClientCaller
from tl_sim.orchestrator import ASSISTANT, ORCHESTRATOR, Simulation, default_run_id
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import AreaSpec, Scenario, Template
from tl_sim.state import RunStore
from tl_sim.types import SimClient

RUN_ID = "rt1"
TEMPLATE = Template(
    template="t",
    areas=[AreaSpec(name="North", lines=["6-CS-1001", "4-CS-1002"])],
)


class SuiteConnector:
    """The orchestrator's connector over the in-process API app and MCP server of a ``Suite``."""

    def __init__(self, suite: Suite, run_id: str = RUN_ID) -> None:
        self.suite, self.run_id = suite, run_id

    def check(self, scenario: Scenario) -> None:
        return None  # the MCP server is in memory on the suite's ledger

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        return {identity: self.suite.tokens[identity] for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        mcp = None
        if identity == ASSISTANT:  # the real MCP server, in memory, on the same ledger
            mcp = McpClientCaller(build_mcp_server(self.suite.backend, actor=identity))
        return HttpSimClient(
            self.suite.api(identity, clock),
            run_id=self.run_id,
            scope=f"project:sim-{self.run_id}",
            clock=clock,
            keys=keys,
            identity=identity,
            mcp=mcp,
        )

    def reader(self, tokens: dict[str, str]) -> SimReader:
        return HttpReader(self.suite.api(ORCHESTRATOR), f"project:sim-{self.run_id}")


def scenario(seed: int = 4711, **extra: object) -> Scenario:
    base: dict[str, Any] = {
        "scenario": "e2e",
        "seed": seed,
        "start": date(2026, 11, 2),
        "actors": {"assistant": {"proposals_per_day": 2}, "approver": {"accept_rate": 0.5}},
        "inject": [
            {"day": 1, "event": "material_late", "item": "6in flange", "days": 21},
            {"day": 2, "event": "design_revision", "count": 1},
        ],
    }
    return Scenario.model_validate({**base, **extra})


def run(
    suite: Suite, tmp_path: Path, days: int = 4, seed: int = 4711
) -> tuple[Simulation, SuiteConnector]:
    connector = SuiteConnector(suite)
    sim = Simulation.create(
        scenario(seed),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=connector,
        run_id=RUN_ID,
    )
    sim.advance(days)
    return sim, connector


def test_a_run_of_the_real_actors_passes_sim_assert(suite: Suite, tmp_path: Path) -> None:
    sim, connector = run(suite, tmp_path)
    report = sim.assert_()
    assert report.counts.get("proposal.created", 0) >= 2, report.counts
    assert report.ok, [f.line() for f in report.failures]
    assert report.counts["record.created"] > 15 and report.counts["post.created"] >= 8
    api = suite.api(ORCHESTRATOR)
    scope = f"project:sim-{RUN_ID}"
    records = api.list_records(scope, limit=5000)
    titles = [r["title"] for r in records]
    assert any(t.startswith("Valve V") for t in titles) and any(
        t.startswith("Doc 001") for t in titles
    )
    states = {r["status"] for r in records if r["title"].startswith("Doc ")}
    assert "Approved" in states, "the planner got a document through the real approve guard"
    assert any(t.endswith("Rev B") for t in titles), "the design_revision injection issued Rev B"
    posts = [p["body"] for p in connector.reader({}).posts()]
    assert any("6in flange is late by 21 days" in body for body in posts)
    assert any(body.startswith("Registered ") for body in posts)


def test_the_valve_data_the_crew_set_is_what_the_suite_stores(suite: Suite, tmp_path: Path) -> None:
    run(suite, tmp_path, days=1)
    valves = [
        r
        for r in suite.api(ORCHESTRATOR).list_records(f"project:sim-{RUN_ID}", limit=5000)
        if r["title"].startswith("Valve V")
    ]
    assert valves
    for valve in valves:
        data = valve["psets"]["valve_data"]
        assert data["body_material"] == "CS" and data["size_in"] in (2, 3, 4, 6, 8)


def test_every_event_is_by_a_simulated_actor_and_the_simulators_own_carry_simulated_time(
    suite: Suite, tmp_path: Path
) -> None:
    run(suite, tmp_path, days=3)
    events = (
        suite.api(ORCHESTRATOR).events_after(0, scope=f"project:sim-{RUN_ID}", limit=500).events
    )
    assert events
    assert all(e.actor.startswith(("user:sim-", "agent:sim-")) for e in events)
    own = [e for e in events if e.source == f"sim:{RUN_ID}"]
    assert own and all(e.actor.startswith("user:sim-") for e in own)
    assert {e.effective_at.date().isoformat() for e in own} == {
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
    }
    assert all(e.effective_at != e.recorded_at for e in own)
    # the agent's proposals come over MCP (real time), and a person's decisions over the API
    other = {(e.event_type, e.source) for e in events if e not in own}
    assert ("Proposal.Created", "mcp:sim-assistant") in other
    assert ("Proposal.Accepted", "api") in other or ("Proposal.Rejected", "api") in other


def test_the_assistant_only_proposes_and_the_approver_decides(suite: Suite, tmp_path: Path) -> None:
    run(suite, tmp_path, days=4)
    api = suite.api(ORCHESTRATOR)
    scope = f"project:sim-{RUN_ID}"
    views = api.list_proposals(scope, status=None)
    assert views and {v.agent for v in views} == {ASSISTANT}
    assert {v.status for v in views} <= {"accepted", "rejected"}  # nothing is left pending
    assert {v.decided_by for v in views} == {"user:sim-approver"}
    accepted = [v for v in views if v.status == "accepted"]
    events = api.events_after(0, scope=scope, limit=500).events
    links = [e for e in events if e.event_type == "Link.Added" and e.source == "mcp:sim-assistant"]
    assert len(links) == len(accepted)
    assert {e.actor for e in links} == {"user:sim-approver"}  # the agent never wrote a record


def test_the_same_seed_on_a_fresh_suite_gives_identical_ground_truth(tmp_path: Path) -> None:
    digests: list[str] = []
    for n in range(2):
        built = build_suite(tmp_path / f"s{n}")
        try:
            sim, _ = run(built, tmp_path / f"r{n}")
            digests.append(sim.status().digest)
        finally:
            close_suite(built)
    assert digests[0] == digests[1]


def test_another_seed_gives_other_ground_truth(suite: Suite, tmp_path: Path) -> None:
    first, _ = run(suite, tmp_path / "a", days=2, seed=1)
    other = build_suite(tmp_path / "other")
    try:
        second, _ = run(other, tmp_path / "b", days=2, seed=2)
        assert first.status().digest != second.status().digest
    finally:
        close_suite(other)


def test_someone_else_editing_a_record_fails_sim_assert(suite: Suite, tmp_path: Path) -> None:
    sim, _ = run(suite, tmp_path, days=2)
    api = suite.api("user:alice")
    scope = f"project:sim-{RUN_ID}"
    valve = next(r for r in api.list_records(scope, limit=5000) if r["title"].startswith("Valve"))
    api.update_record(
        UpdateRecord(
            actor="x",
            source="api",
            scope=scope,
            stream_id=valve["id"],
            expected_version=valve["version"],
            changes={"title": "Renamed by a person"},
        )
    )
    report = sim.assert_()
    assert not report.ok
    checks = {f.check for f in report.failures}
    assert "record.created" in checks and "event_source" in checks and "event_actor" in checks


def test_a_stray_record_fails_sim_assert(suite: Suite, tmp_path: Path) -> None:
    sim, _ = run(suite, tmp_path, days=1)
    suite.api("user:alice").create_record(
        CreateRecord(
            actor="x",
            source="api",
            scope=f"project:sim-{RUN_ID}",
            record_type="core.Record",
            title="Stray",
            key="STRAY-1",
        )
    )
    assert "unexpected_record" in {f.check for f in sim.assert_().failures}


def test_the_default_run_id_is_usable_as_a_key_prefix() -> None:
    sc = scenario()
    run_id = default_run_id(sc)
    assert Keys(run_id, {}).next().startswith(f"SIM{run_id.upper()}-REC-")
