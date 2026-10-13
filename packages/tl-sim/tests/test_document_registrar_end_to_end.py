"""The document registrar against the real API app: the registry checks every number (P1-I2-T12a).

The company and the document standards are loaded in the suite's ledger first (`tl standards load`
does the same). The run is checked by ``sim_assert`` like any other: every document and revision it
names exists with its title and type, every link exists, and nobody else wrote.
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


def scenario(*, tags: bool = True, **registrar: Any) -> Scenario:
    return Scenario.model_validate(
        {
            "scenario": "documents",
            "seed": 11,
            "start": date(2026, 11, 2),
            "actors": {
                "document_controller": None,
                "planner": None,
                "crew": None,
                "tag_clerk": {"tags_per_day": 1, "rename_rate": 0.0} if tags else None,
                "document_registrar": {
                    "documents_per_day": 2,
                    "revision_rate": 1.0,
                    "link_rate": 1.0,
                    **registrar,
                },
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


def play(
    suite: Suite, tmp_path: Path, days: int = 4, *, tags: bool = True, **registrar: Any
) -> Simulation:
    sim = Simulation.create(
        scenario(tags=tags, **registrar),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=Connector(suite),
        run_id=RUN_ID,
    )
    sim.advance(days)
    return sim


def test_a_run_of_the_registrar_passes_sim_assert(standards_suite: Suite, tmp_path: Path) -> None:
    sim = play(standards_suite, tmp_path)
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    api = standards_suite.api(ORCHESTRATOR)
    documents = api.list_documents(f"sim-{RUN_ID}")
    assert len(documents) == 8 and all(d.state == "Registered" for d in documents)
    assert all(d.pattern_code is not None for d in documents)  # every number fit the pattern
    first = api.get_document(f"sim-{RUN_ID}", documents[0].number)
    assert len(first.revisions) <= 1 and all(r.state == "Draft" for r in first.revisions)
    assert report.counts.get("link.added", 0) >= 1


def test_the_same_seed_gives_the_same_register(standards_suite: Suite, tmp_path: Path) -> None:
    play(standards_suite, tmp_path / "a", days=3)
    numbers = [d.number for d in standards_suite.api(ORCHESTRATOR).list_documents(f"sim-{RUN_ID}")]
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
        assert [
            d.number for d in other.api(ORCHESTRATOR).list_documents(f"sim-{RUN_ID}")
        ] == numbers
    finally:
        close_suite(other)


def test_without_the_standards_the_register_takes_any_number_and_checks_none(
    suite: Suite, tmp_path: Path
) -> None:
    sim = play(suite, tmp_path, tags=False)
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    documents = suite.api(ORCHESTRATOR).list_documents(f"sim-{RUN_ID}")
    assert documents and all(d.pattern_code is None for d in documents)
