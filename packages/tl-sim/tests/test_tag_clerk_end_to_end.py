"""The tag clerk against the real API app: the registry checks every number it files (P1-I1-T12).

The company standards are loaded in the suite's ledger first (`tl standards load` does the same).
The run is checked by ``sim_assert`` like any other: every tag it names exists with its title and
type, every rename left a ``supersedes`` link and a Superseded old tag, and nobody else wrote.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from suite import Suite, build_suite, close_suite
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.orchestrator import ORCHESTRATOR, Simulation
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import AreaSpec, Scenario, Template
from tl_sim.state import RunStore
from tl_sim.types import SimClient

RUN_ID = "rt1"
SCOPE = f"project:sim-{RUN_ID}"
TEMPLATE = Template(template="t", areas=[AreaSpec(name="North", lines=["6-CS-1001"])])


class Connector:
    def __init__(self, suite: Suite) -> None:
        self.suite = suite

    def check(self, scenario: Scenario) -> None:
        return None

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        return {identity: self.suite.tokens[identity] for identity in identities}

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        return HttpSimClient(
            self.suite.api(identity, clock),
            run_id=RUN_ID,
            scope=SCOPE,
            clock=clock,
            keys=keys,
            identity=identity,
        )

    def reader(self, tokens: dict[str, str]) -> SimReader:
        return HttpReader(self.suite.api(ORCHESTRATOR), SCOPE)


def scenario(**clerk: Any) -> Scenario:
    return Scenario.model_validate(
        {
            "scenario": "tags",
            "seed": 11,
            "start": date(2026, 11, 2),
            "actors": {
                "document_controller": None,
                "planner": None,
                "crew": None,
                "tag_clerk": {"tags_per_day": 2, "rename_rate": 0.5, **clerk},
            },
        }
    )


@pytest.fixture
def standards_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    built = build_suite(tmp_path / "suite", standards=True)
    try:
        yield built
    finally:
        close_suite(built)


def play(suite: Suite, tmp_path: Path, days: int = 5, **clerk: Any) -> Simulation:
    sim = Simulation.create(
        scenario(**clerk),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=Connector(suite),
        run_id=RUN_ID,
    )
    sim.advance(days)
    return sim


def test_a_run_of_the_tag_clerk_passes_sim_assert(standards_suite: Suite, tmp_path: Path) -> None:
    sim = play(standards_suite, tmp_path)
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    assert report.counts.get("link.added", 0) >= 1, "at least one rename happened in five days"
    api = standards_suite.api(ORCHESTRATOR)
    tags = api.list_tags(f"sim-{RUN_ID}")
    assert len(tags) >= 8 and all(t.number_status == "ok" for t in tags)
    assert all(t.class_code is not None for t in tags)
    ended = api.list_tags(f"sim-{RUN_ID}", include_ended=True)
    superseded = [t for t in ended if t.status == "Superseded"]
    assert len(ended) == len(tags) + len(superseded) and superseded


def test_the_same_seed_gives_the_same_tag_list(standards_suite: Suite, tmp_path: Path) -> None:
    play(standards_suite, tmp_path / "a", days=3)
    numbers = [t.number for t in standards_suite.api(ORCHESTRATOR).list_tags(f"sim-{RUN_ID}")]
    other = build_suite(tmp_path / "again", standards=True)
    try:
        again = Simulation.create(
            scenario(),
            TEMPLATE,
            store=RunStore(tmp_path / "runs2"),
            connector=Connector(other),
            run_id=RUN_ID,
        )
        again.advance(3)
        assert [t.number for t in other.api(ORCHESTRATOR).list_tags(f"sim-{RUN_ID}")] == numbers
    finally:
        close_suite(other)


def test_without_the_standards_the_clerk_stops_with_the_registrys_message(
    suite: Suite, tmp_path: Path
) -> None:
    with pytest.raises(Exception, match="tag class|not a registered|ControlValve|Transmitter|Pump"):
        play(suite, tmp_path)
