"""The RFI author and the client's representative against the real API app (P1-I6).

The author raises RFIs and sends them to internal review; a document controller (here the module's
test world, which writes as ``user:ctl`` in the run's scope) issues them; the client answers; the
author accepts. The scenario names the controller as an operator, so ``sim_assert`` holds the rest
of the run to the rules.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from suite import SCOPE, Suite, build_suite, close_suite
from tl_adapters.db import as_target
from tl_core import confidentiality as cf
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_correspondence.handlers.technical_flow import IssueTechnical, handle_issue_technical
from tl_mod_correspondence.testing import BASE, CorrWorld
from tl_mod_documents.derivation import store
from tl_sim.client import HttpSimClient, Keys
from tl_sim.clock import SimClock
from tl_sim.orchestrator import ORCHESTRATOR, Simulation
from tl_sim.reader import HttpReader, SimReader
from tl_sim.scenario import AreaSpec, Scenario, Template
from tl_sim.state import RunStore
from tl_sim.types import SimClient

RUN_ID = "rt1"
FIXTURES = Path(__file__).resolve().parents[3] / "schema" / "fixtures"
CONTROLLER = "user:ctl"
TEMPLATE = Template(template="t", areas=[AreaSpec(name="North", lines=["6-CS-1001", "6-CS-1002"])])


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


class Controller:
    """A document controller beside the run: issues the RFIs that are in internal review."""

    def __init__(self, suite: Suite, root: Path) -> None:
        self.suite = suite
        self.world = CorrWorld(as_target(str(suite.db)), root / "controller-objects")

    def issue_all(self) -> list[str]:
        issued: list[str] = []
        with (
            use_provider(DirectorySchemaProvider(Path(os.environ["TL_SCHEMA_DIR"]))),
            store.use_files(self.world.files),
            cf.use_viewer(cf.Viewer(CONTROLLER, 1, CONTROLLER)),
        ):
            for line in self.suite.api("user:sim-rfi_author").list_rfis("sim-rt1").lines:
                if line.state == "Internal review":
                    fields: dict[str, Any] = {
                        **BASE,
                        "actor": CONTROLLER,
                        "source": "cli",
                        "scope": SCOPE,
                    }
                    self.world.run(
                        IssueTechnical, handle_issue_technical, stream_id=line.id, **fields
                    )
                    issued.append(line.number)
        return issued


def schema_with_calendar(root: Path) -> Path:
    """The fixture packages plus the working calendar of the run's project (the clocks of an issued
    RFI count on ``<project>-default``; a project's calendar is a file, so a run needs one)."""
    target = root / "schema"
    shutil.copytree(FIXTURES, target)
    source = (FIXTURES / "calendars" / "P123-default@1.yaml").read_text()
    made = source.replace("P123-default", "sim-rt1-default").replace("project:P123", SCOPE)
    (target / "calendars" / "sim-rt1-default@1.yaml").write_text(made)
    return target


@pytest.fixture
def suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Suite]:
    monkeypatch.setenv("TL_SCHEMA_DIR", str(schema_with_calendar(tmp_path)))
    built = build_suite(tmp_path / "suite", objects=True)
    try:
        yield built
    finally:
        close_suite(built)


def scenario(**actors: Any) -> Scenario:
    return Scenario.model_validate(
        {
            "scenario": "rfis",
            "seed": 5,
            "start": date(2026, 11, 2),
            "operators": [CONTROLLER],
            "actors": {
                "document_controller": None,
                "planner": None,
                "crew": None,
                "rfi_author": {"rfis_per_day": 2},
                "client_rep": {"answers_per_day": 3, "impact_rate": 0.5},
                **actors,
            },
        }
    )


def open_run(suite: Suite, tmp_path: Path, **actors: Any) -> Simulation:
    return Simulation.create(
        scenario(**actors),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=Connector(suite),
        run_id=RUN_ID,
    )


def rfis(suite: Suite) -> dict[str, str]:
    lines = suite.api(ORCHESTRATOR).list_rfis("sim-rt1").lines
    return {x.number: x.state for x in lines}


def test_a_week_of_rfis_passes_sim_assert(suite: Suite, tmp_path: Path) -> None:
    sim = open_run(suite, tmp_path)
    controller = Controller(suite, tmp_path)
    for _ in range(4):  # the controller issues in the evening of every working day
        sim.advance(1)
        controller.issue_all()
    sim.advance(1)
    report = sim.assert_()
    assert report.ok, [f.line() for f in report.failures]
    states = rfis(suite)
    assert len(states) >= 4
    assert {"Accepted", "Internal review"} <= set(states.values())  # answered, and still waiting
    assert report.counts.get("record.created", 0) >= len(states)
    assert report.counts.get("workflow.transitioned", 0) >= 2
    assert report.excused > 0  # the controller's issue, its clocks and its letter


def test_an_rfi_nobody_issues_stays_in_review_and_the_run_still_passes(
    suite: Suite, tmp_path: Path
) -> None:
    sim = open_run(suite, tmp_path)
    sim.advance(2)
    assert set(rfis(suite).values()) == {"Internal review"}
    assert sim.assert_().ok


def test_without_naming_the_controller_the_issue_is_held_against_the_run(
    suite: Suite, tmp_path: Path
) -> None:
    sim = Simulation.create(
        scenario().model_copy(update={"operators": []}),
        TEMPLATE,
        store=RunStore(tmp_path / "runs"),
        connector=Connector(suite),
        run_id=RUN_ID,
    )
    sim.advance(1)
    Controller(suite, tmp_path).issue_all()
    checks = {f.check for f in sim.assert_().failures}
    assert {"event_source", "event_actor"} <= checks


def test_the_same_seed_gives_the_same_ground_truth(suite: Suite, tmp_path: Path) -> None:
    first = open_run(suite, tmp_path / "a")
    first.advance(1)
    other = build_suite(tmp_path / "other", objects=True)
    try:
        again = open_run(other, tmp_path / "b")
        again.advance(1)
        assert again.status().digest == first.status().digest
    finally:
        close_suite(other)
