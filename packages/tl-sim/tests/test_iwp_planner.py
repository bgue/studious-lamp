"""The IWP planner on an in-memory world, and ``HttpSimClient``'s IWP writes on a recording stub
(P2-I2-T10a)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from suite import Suite, build_suite, close_suite
from test_end_to_end import RUN_ID, SuiteConnector
from tl_core.services.commands import CommandResult
from tl_mod_awp.iwp_views import IwpRow
from tl_sim import groundtruth as gt
from tl_sim.actors.iwp_planner import CATEGORIES, IwpPlanner
from tl_sim.actors.registry import ACTOR_CLASSES, build_actor
from tl_sim.client import HttpSimClient, IwpDesk, Keys
from tl_sim.clock import SimClock
from tl_sim.orchestrator import ORCHESTRATOR, all_identities
from tl_sim.scenario import (
    ACTOR_NAMES,
    ROLE_NAMES,
    ActorsConfig,
    IwpPlannerParams,
    Scenario,
)
from tl_sim.testing import FakeWorld, make_context
from tl_sim.types import GroundTruth

IDENTITY = "user:sim-iwp_planner"
ASSISTANT = "agent:sim-assistant"
PARAMS = {"iwps_per_day": 2, "scope_items": 3, "constraint_rate": 1.0, "clears_per_day": 1}
BASE: dict[str, Any] = {"scenario": "t", "seed": 1, "start": date(2026, 11, 2)}


def step(world: FakeWorld, *, day: int = 0, **params: Any) -> list[GroundTruth]:
    actor = IwpPlanner(IwpPlannerParams(**{**PARAMS, **params}))
    return actor.step(make_context(world, actor.identity, seed=1, day=day))


def intents(truth: list[GroundTruth]) -> list[str]:
    return [t.intent for t in truth]


def test_identity_and_name_follow_the_contract() -> None:
    actor = IwpPlanner(IwpPlannerParams())
    assert (actor.name, actor.identity) == ("iwp_planner", IDENTITY)


def test_a_day_builds_the_packages_and_raises_one_constraint() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    truth = step(world)
    iwps = sorted(world.iwp_rows, key=lambda r: r["number"])
    assert [r["state"] for r in iwps] == ["In development", "In development"]
    assert [r["title"][-1] for r in iwps] == ["1", "2"]
    items = [r for r in world.record_rows if r["type"] == "awp.ScopeItem"]
    assert len(items) == 6
    for iwp in iwps:
        assert sum(1 for s in world.scope_rows if s["iwp_id"] == iwp["id"]) == 3
    # 2 IWPs, 6 scope items, 1 constraint: the three intents the log names
    assert intents(truth) == [gt.RECORD_CREATED] * 9
    assert [t.expect["record_type"] for t in truth] == (
        ["awp.IWP"]
        + ["awp.ScopeItem"] * 3
        + ["awp.IWP"]
        + ["awp.ScopeItem"] * 3
        + ["core.Constraint"]
    )


def test_a_raised_constraint_is_manual_open_and_on_the_newest_iwp() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    step(world)
    (constraint,) = world.constraint_rows
    newest = max(world.iwp_rows, key=lambda r: r["number"])
    assert constraint["subject_id"] == newest["id"]
    assert constraint["category"] in CATEGORIES
    assert constraint["state"] == "Open"
    assert [e["event_type"] for e in world.event_rows if e["stream_id"] == constraint["id"]] == [
        "Record.Created",
        "Constraint.Raised",
    ]


def test_the_day_after_clears_the_constraint_raised_the_day_before() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    step(world, day=0)
    first = world.constraint_rows[0]["id"]
    truth = step(world, day=1)
    assert world.constraint_rows[0]["id"] == first
    assert world.constraint_rows[0]["state"] == "Cleared"
    assert world.constraint_rows[1]["state"] == "Open"
    assert world.record(first)["status"] == "Cleared"
    assert [t.intent for t in truth].count(gt.RECORD_CREATED) == 2 + 6 + 1


def test_a_constraint_raised_today_is_not_cleared_today() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    step(world, clears_per_day=5)
    assert [c["state"] for c in world.constraint_rows] == ["Open"]


def test_the_same_seed_gives_the_same_keys_and_titles() -> None:
    def run() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        world = FakeWorld("r1", "project:sim-r1")
        step(world, day=0)
        step(world, day=1)
        iwps = [(r["key"], r["title"]) for r in world.record_rows if r["type"] == "awp.IWP"]
        cons = [(r["key"], r["title"]) for r in world.record_rows if r["type"] == "core.Constraint"]
        return iwps, cons

    assert run() == run()


def test_off_by_default_and_named_it_follows_the_workface_planner() -> None:
    assert "iwp_planner" not in Scenario.model_validate(BASE).actors.enabled()
    assert ActorsConfig().iwp_planner is None
    on = Scenario.model_validate(
        {**BASE, "actors": {"workface_planner": {}, "iwp_planner": {}, "approver": {}}}
    ).actors.enabled()
    assert [n for n in on if n in ("workface_planner", "iwp_planner")] == [
        "workface_planner",
        "iwp_planner",
    ]


def test_role_names_are_unchanged_and_the_actor_is_in_the_registry() -> None:
    assert "iwp_planner" not in ROLE_NAMES
    assert ACTOR_NAMES.index("iwp_planner") == ACTOR_NAMES.index("workface_planner") + 1
    assert ACTOR_CLASSES["iwp_planner"] is IwpPlanner
    assert isinstance(build_actor("iwp_planner", IwpPlannerParams()), IwpPlanner)


def test_the_planner_is_a_person_in_the_identities_before_the_assistant() -> None:
    assert all_identities()[-2:] == [IDENTITY, ASSISTANT]


def test_the_fake_client_is_an_iwp_desk() -> None:
    world = FakeWorld("r1", "project:sim-r1")
    assert isinstance(world.client(IDENTITY, SimClock(datetime(2026, 11, 2, tzinfo=UTC))), IwpDesk)


# --- HttpSimClient against a recording stub of the API's IWP reads and generic commands -----


class RecordingApi:
    """Records each generic command (name, body) and answers with ids; reads a fixed world."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.titles: dict[str, str] = {}
        self._seq = 0

    def correspondence_command(self, name: str, cmd: Any) -> CommandResult:
        self.commands.append((name, cmd.model_dump()))
        self._seq += 1
        stream = f"id-{self._seq}"
        title = str(getattr(cmd, "title", None) or getattr(cmd, "description", None) or name)
        self.titles[stream] = title
        return CommandResult(stream_id=stream, key=f"K-{self._seq}", version=1, events=[])

    def get_record_by_id(self, record_id: str) -> dict[str, Any] | None:
        return {"id": record_id, "title": self.titles[record_id]}

    def list_iwps(
        self, project: str, *, state: str | None = None, limit: int = 200
    ) -> list[IwpRow]:
        return [
            IwpRow(id="id-b", number="PIP-IWP-0002", title="B", state="Draft"),
            IwpRow(id="id-a", number="PIP-IWP-0001", title="A", state="In development"),
        ]

    def list_constraints(
        self,
        project: str,
        *,
        subject: str | None = None,
        state: str | None = None,
        limit: int = 200,
    ) -> Any:
        rows = [
            SimpleNamespace(id="c2", key="C-0002", subject_id="id-a", state="Assigned"),
            SimpleNamespace(id="c1", key="C-0001", subject_id="id-a", state="Open"),
            SimpleNamespace(id="c0", key="C-0000", subject_id="id-a", state="Cleared"),
        ]
        return SimpleNamespace(rows=rows, total=len(rows))


def http_client(api: RecordingApi) -> HttpSimClient:
    clock = SimClock(datetime(2026, 11, 2, 7, 0, tzinfo=UTC))
    return HttpSimClient(
        api,  # type: ignore[arg-type]
        run_id="rt1",
        scope="project:sim-rt1",
        clock=clock,
        keys=Keys("rt1", {}),
        identity=IDENTITY,
    )


def test_the_http_client_is_an_iwp_desk_and_pins_the_command_names_and_bodies() -> None:
    api = RecordingApi()
    client = http_client(api)
    assert isinstance(client, IwpDesk)
    iwp = client.create_iwp("PIP", "Spool set 1")
    item = client.create_scope_item("PIPE-SPOOL", "Pipe spool", "1", "EA", "12")
    client.add_scope(iwp["id"], [item["id"]])
    client.start_development(iwp["id"])
    client.raise_constraint(iwp["id"], "materials", "materials needed for PIP-IWP-0001")
    client.clear_constraint("c1", "cleared by planner")
    names = [name for name, _ in api.commands]
    assert names == [
        "CreateIwp",
        "CreateScopeItem",
        "AddIwpScope",
        "StartIwpDevelopment",
        "RaiseConstraint",
        "ClearConstraint",
    ]
    bodies = dict(api.commands)
    assert bodies["CreateIwp"]["discipline"] == "PIP"
    assert bodies["CreateIwp"]["title"] == "Spool set 1"
    assert float(bodies["CreateScopeItem"]["est_hours"]) == 12  # the model reads it as hours
    assert bodies["AddIwpScope"]["items"] == [item["id"]]
    assert bodies["StartIwpDevelopment"]["iwp"] == iwp["id"]
    raised = bodies["RaiseConstraint"]
    assert (raised["phase"], raised["severity"], raised["source_kind"]) == (
        "ready",
        "blocking",
        "manual",
    )
    assert (raised["subject"], raised["category"]) == (iwp["id"], "materials")
    assert (bodies["ClearConstraint"]["constraint"], bodies["ClearConstraint"]["reason"]) == (
        "c1",
        "cleared by planner",
    )
    assert all(
        body["actor"] == IDENTITY and body["scope"] == "project:sim-rt1" for _, body in api.commands
    )


def test_the_http_client_reads_iwps_by_number_and_open_constraints_by_key() -> None:
    client = http_client(RecordingApi())
    assert [r["number"] for r in client.iwps()] == ["PIP-IWP-0001", "PIP-IWP-0002"]
    assert client.open_constraints() == [
        {"id": "c1", "key": "C-0001", "subject_id": "id-a"},
        {"id": "c2", "key": "C-0002", "subject_id": "id-a"},
    ]


def test_the_real_suite_numbers_an_iwp_in_the_sim_scope(tmp_path: Path, monkeypatch: Any) -> None:
    """The numbering allocator keys an IWP in ``project:sim-<run>`` (the hyphen is dropped from the
    project segment), so the desk's key is the pattern's key, not a client counter."""
    monkeypatch.delenv("TL_SCHEMA_DIR", raising=False)
    built: Suite = build_suite(tmp_path / "s", standards=True)
    try:
        clock = SimClock(datetime(2026, 11, 2, 8, tzinfo=UTC))
        desk = SuiteConnector(built).client(IDENTITY, clock, Keys(RUN_ID, {}), {})
        assert isinstance(desk, HttpSimClient)
        made = desk.create_iwp("PIP", "Numbered spool set 1")
        assert re.fullmatch(r"sim[a-z0-9]+-IWP-PIP-0001", made["key"]), made
        rows = built.api(ORCHESTRATOR).list_iwps(f"sim-{RUN_ID}", limit=200)
        assert [(r.id, r.number) for r in rows] == [(made["id"], made["key"])]
    finally:
        close_suite(built)
