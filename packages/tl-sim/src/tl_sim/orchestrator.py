"""The simulation orchestrator: create a run, play working days, inject events, report, assert.

A run is a scenario played against a running suite through its public interfaces. The loop for one
working day is, in order: for each enabled actor (document controller, planner, crew) build a
``SimContext`` (the simulated time of that actor's slot, a generator seeded from the run seed, the
actor's name and the day, and the actor's own client), call ``actor.step``, append the ground truth
it returns to the log and save the run state. Then the day's injections play, each as a one-off
step. Nothing in the loop reads the wall clock or a global random generator, so one seed gives one
ground-truth log (``status().digest`` is equal across runs) whatever the machine does.

The orchestrator never touches the ledger. It reaches the suite through a ``Connector``: the HTTP
one in ``tl_sim.connector``, a ``FakeWorld`` in tests.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any, Protocol

from tl_sim import groundtruth as gt
from tl_sim.actors.base import Recorder
from tl_sim.actors.registry import actors_of
from tl_sim.assertions import AssertionReport, Expected, run_assertions
from tl_sim.client import Keys
from tl_sim.clock import SimClock, day_start, seed_time, working_date
from tl_sim.injections import injected_actor
from tl_sim.orchestrator_names import ASSISTANT, ORCHESTRATOR
from tl_sim.reader import SimReader
from tl_sim.rng import actor_rng
from tl_sim.scenario import ROLE_NAMES, InjectSpec, Scenario, Template, guaranteed
from tl_sim.state import RunError, RunInterruptedError, RunState, RunStore
from tl_sim.types import Actor, GroundTruth, SimClient, SimContext

MAX_PENDING = 100  # queued injections per run; more would be a runaway, not a scenario


class Connector(Protocol):
    """How the orchestrator reaches the suite. ``HttpConnector`` is the real one."""

    def check(self, scenario: Scenario) -> None:
        """Raise ``RunError`` if ``scenario`` cannot run here (before anything is written)."""
        ...

    def provision(self, identities: Sequence[str]) -> dict[str, str]:
        """Make the actors able to act (dev tokens); returns identity -> token (may be empty)."""
        ...

    def client(
        self, identity: str, clock: SimClock, keys: Keys, tokens: dict[str, str]
    ) -> SimClient:
        """A client for ``identity`` whose writes carry ``clock`` and take keys from ``keys``."""
        ...

    def reader(self, tokens: dict[str, str]) -> SimReader: ...


@dataclass
class AdvanceResult:
    days: list[date] = field(default_factory=list[date])
    truth: int = 0  # ground-truth lines written
    steps: int = 0


@dataclass
class SimStatus:
    run_id: str
    scope: str
    scenario: str
    seed: int
    day: int  # working days played
    next_date: date
    last_date: date | None
    ground_truth: dict[str, int]  # intent -> lines
    digest: str
    pending: list[dict[str, Any]]
    interrupted: bool


def default_run_id(scenario: Scenario) -> str:
    """``r`` and six hex digits of the scenario name and seed: the same scenario, the same run."""
    material = f"{scenario.scenario}\x1f{scenario.seed}".encode()
    return "r" + hashlib.sha256(material).hexdigest()[:6]


def all_identities() -> list[str]:
    people = (*ROLE_NAMES, "approver")
    return [ORCHESTRATOR, *(f"user:sim-{name}" for name in people), ASSISTANT]


class Simulation:
    def __init__(self, state: RunState, store: RunStore, connector: Connector) -> None:
        self.state = state
        self.store = store
        self.connector = connector
        self._log = gt.GroundTruthLog(store.log_path(state.run_id))
        self._keys = Keys(state.run_id, state.key_counters)

    # --- sim_create ----------------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        scenario: Scenario,
        template: Template,
        *,
        store: RunStore,
        connector: Connector,
        run_id: str | None = None,
    ) -> Simulation:
        run_id = run_id or default_run_id(scenario)
        connector.check(scenario)  # a missing ledger for the agent stops here, not after seeding
        if store.exists(run_id):
            raise RunError(f"run {run_id!r} already exists; choose another run id")
        created = datetime.combine(scenario.start, time(0), tzinfo=UTC)  # simulated, not the clock
        state = RunState(run_id=run_id, scenario=scenario, created_at=created)
        state.tokens = connector.provision(all_identities())
        store.save(state)
        sim = cls(state, store, connector)
        sim._seed(template)
        return sim

    @classmethod
    def open(cls, run_id: str, *, store: RunStore, connector: Connector) -> Simulation:
        return cls(store.load(run_id), store, connector)

    # --- internals -----------------------------------------------------------------------------

    def _date(self, day: int) -> date:
        scenario = self.state.scenario
        return working_date(scenario.start, day, tuple(scenario.working_days))

    def _context(self, identity: str, stream: str, day: int, now: datetime) -> SimContext:
        clock = SimClock(now)
        client = self.connector.client(identity, clock, self._keys, self.state.tokens)
        return SimContext(
            run_id=self.state.run_id,
            scope=self.state.scope,
            now=now,
            rng=actor_rng(self.state.scenario.seed, stream, day),
            client=client,
        )

    def _play(self, actor: Actor, ctx: SimContext, day: int) -> int:
        """One actor step: guard it, record its truth, save the state. Returns lines written."""
        self.state.in_progress = f"{day}:{actor.name}"
        self.store.save(self.state)
        truth = actor.step(ctx)
        written = self._log.append(truth)
        self.state.in_progress = None
        self.store.save(self.state)
        return written

    def _refuse_if_interrupted(self) -> None:
        if self.state.in_progress is not None:
            raise RunInterruptedError(
                f"step {self.state.in_progress} of run {self.state.run_id} did not finish, so the "
                "ground-truth log may miss writes the suite has; create a new run"
            )

    def _seed(self, template: Template) -> None:
        """Day 0, before work: the areas and lines of the template, written as the orchestrator."""
        self.state.in_progress = "0:seed"
        self.store.save(self.state)
        ctx = self._context(ORCHESTRATOR, "seed", 0, seed_time(self._date(0)))
        recorder = Recorder(ctx, ORCHESTRATOR)
        for area in template.areas:
            area_rec = recorder.create(f"Area {area.name}")
            for designation in area.lines:
                line = recorder.create(f"Line {designation}")
                recorder.link(line, area_rec, "belongs_to")
        self._log.append(recorder.truth)
        self.state.in_progress = None
        self.state.seeded = True
        self.store.save(self.state)

    # --- sim_advance ---------------------------------------------------------------------------

    def advance(self, days: int = 1) -> AdvanceResult:
        if days < 1:
            raise RunError("days must be at least 1")
        self._refuse_if_interrupted()
        result = AdvanceResult()
        scenario = self.state.scenario
        for _ in range(days):
            day = self.state.day
            played = self._date(day)
            slot = 0
            for actor in actors_of(scenario):
                now = day_start(played, slot)
                ctx = self._context(actor.identity, actor.name, day, now)
                result.truth += self._play(actor, ctx, day)
                result.steps += 1
                slot += 1
            queued = [s for s in scenario.inject if s.day == day] + self.state.pending
            for spec in queued:
                actor = injected_actor(spec, scenario)
                now = day_start(played, slot)
                ctx = self._context(actor.identity, f"{actor.name}+inject", day, now)
                result.truth += self._play(actor, ctx, day)
                result.steps += 1
                slot += 1
            self.state.pending = []
            self.state.day = day + 1
            self.store.save(self.state)
            result.days.append(played)
        return result

    # --- sim_inject ----------------------------------------------------------------------------

    def inject(self, event: str, **args: Any) -> InjectSpec:
        """Queue an event for the next day that is played (``sim_advance``)."""
        if len(self.state.pending) >= MAX_PENDING:
            raise RunError(f"{MAX_PENDING} injections are already queued; advance the run first")
        spec = InjectSpec.model_validate({"day": self.state.day, "event": event, "args": args})
        self.state.pending = [*self.state.pending, spec]
        self.store.save(self.state)
        return spec

    # --- sim_status ----------------------------------------------------------------------------

    def truth(self) -> list[GroundTruth]:
        return self._log.read()

    def played_dates(self) -> list[date]:
        """Every simulated date with events: the seed day and each day played."""
        dates = [self._date(d) for d in range(max(self.state.day, 1))]
        return sorted(set(dates))

    def status(self) -> SimStatus:
        items = self.truth()
        counts: dict[str, int] = {}
        for item in items:
            counts[item.intent] = counts.get(item.intent, 0) + 1
        played = self.state.day
        return SimStatus(
            run_id=self.state.run_id,
            scope=self.state.scope,
            scenario=self.state.scenario.scenario,
            seed=self.state.scenario.seed,
            day=played,
            next_date=self._date(played),
            last_date=self._date(played - 1) if played else None,
            ground_truth=counts,
            digest=gt.digest(items),
            pending=[s.model_dump(mode="json") for s in self.state.pending],
            interrupted=self.state.in_progress is not None,
        )

    # --- sim_assert ----------------------------------------------------------------------------

    def assert_(self) -> AssertionReport:
        actors = self.state.scenario.actors
        return run_assertions(
            self.truth(),
            self.connector.reader(self.state.tokens),
            run_id=self.state.run_id,
            played=self.played_dates(),
            expected=Expected(
                proposals=actors.assistant is not None
                and guaranteed(actors.assistant.proposals_per_day),
                decisions=actors.approver is not None,
                days_played=self.state.day,
            ),
        )


__all__ = [
    "ASSISTANT",
    "ORCHESTRATOR",
    "AdvanceResult",
    "Connector",
    "SimStatus",
    "Simulation",
    "default_run_id",
]
