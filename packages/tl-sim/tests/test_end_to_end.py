"""The three real actors against the real API app: a run passes ``sim_assert``, replays identically
from the same seed, and fails when someone else changes the project.

Feed posts need ``ApiClient.feed_post`` and ``feed_page`` (workstream B), so here a post is kept
in a list by a stand-in client and read back by a stand-in reader. Everything else (records, psets,
links, workflow, queries, the events and their simulated times) goes over HTTP to the real app.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from suite import Suite, build_suite, close_suite
from tl_core.services.commands import CreateRecord, UpdateRecord
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.orchestrator import ORCHESTRATOR, Simulation, default_run_id
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import AreaSpec, Scenario, Template
from tl_sim.state import RunStore
from tl_sim.types import SimClient

RUN_ID = "rt1"
TEMPLATE = Template(
    template="t",
    areas=[AreaSpec(name="North", lines=["6-CS-1001", "4-CS-1002"])],
)


class PostBook:
    """Where the stand-in clients write their posts."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []


class StandInClient(HttpSimClient):
    book: PostBook

    def post(self, body: str) -> dict[str, Any]:
        self._clock.tick()
        self.book.posts.append({"actor": self._identity, "body": body, "retracted": False})
        return {"post_id": f"p{len(self.book.posts)}", "version": 1}


class StandInReader:
    def __init__(self, real: HttpReader, book: PostBook) -> None:
        self._real, self._book = real, book

    def records(self) -> list[dict[str, Any]]:
        return self._real.records()

    def links(self, record_id: str) -> list[dict[str, Any]]:
        return self._real.links(record_id)

    def events(self) -> list[dict[str, Any]]:
        """The real events plus a ``Feed.Posted`` for each stand-in post (not in the ledger)."""
        real = self._real.events()
        day = real[0]["effective_at"] if real else "2026-11-02T07:00:00+00:00"
        posted = [
            {
                "seq": 10_000 + n,
                "stream_id": f"stand-in-{n}",
                "event_type": "Feed.Posted",
                "actor": p["actor"],
                "source": f"sim:{RUN_ID}",
                "effective_at": day,
                "recorded_at": "2000-01-01T00:00:00+00:00",
                "payload": {"body": p["body"]},
            }
            for n, p in enumerate(self._book.posts)
        ]
        return real + posted

    def proposals(self) -> list[dict[str, Any]]:
        return self._real.proposals()

    def posts(self) -> list[dict[str, Any]]:
        return list(self._book.posts)


class SuiteConnector:
    """The orchestrator's connector over the in-process API app of a ``Suite``."""

    def __init__(self, suite: Suite, run_id: str = RUN_ID) -> None:
        self.suite, self.run_id, self.book = suite, run_id, PostBook()

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        return {identity: self.suite.tokens[identity] for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        client = StandInClient(
            self.suite.api(identity, clock),  # type: ignore[arg-type]
            run_id=self.run_id,
            scope=f"project:sim-{self.run_id}",
            clock=clock,
            keys=keys,
            identity=identity,
        )
        client.book = self.book
        return client

    def reader(self, tokens: dict[str, str]) -> SimReader:
        real = HttpReader(self.suite.api(ORCHESTRATOR), f"project:sim-{self.run_id}")
        return StandInReader(real, self.book)


def scenario(seed: int = 4711, **extra: object) -> Scenario:
    base: dict[str, Any] = {
        "scenario": "e2e",
        "seed": seed,
        "start": date(2026, 11, 2),
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
    assert any("6in flange is late by 21 days" in p["body"] for p in connector.book.posts)


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


def test_every_event_is_simulated_time_by_a_simulated_actor_from_the_run(
    suite: Suite, tmp_path: Path
) -> None:
    run(suite, tmp_path, days=3)
    events = (
        suite.api(ORCHESTRATOR).events_after(0, scope=f"project:sim-{RUN_ID}", limit=500).events
    )
    assert events
    assert {e.source for e in events} == {f"sim:{RUN_ID}"}
    assert all(e.actor.startswith("user:sim-") for e in events)
    assert {e.effective_at.date().isoformat() for e in events} == {
        "2026-11-02",
        "2026-11-03",
        "2026-11-04",
    }
    assert all(e.effective_at != e.recorded_at for e in events)


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
