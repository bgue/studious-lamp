"""Run state on disk."""

from __future__ import annotations

import stat
from datetime import date
from pathlib import Path

import pytest
from tl_sim.scenario import Scenario
from tl_sim.state import RunError, RunState, RunStore

SCENARIO = Scenario(scenario="t", seed=1, start=date(2026, 11, 2))


def state(run_id: str = "r1") -> RunState:
    return RunState(run_id=run_id, scenario=SCENARIO, tokens={"user:sim-crew": "secret"})


def test_a_run_saves_and_loads_unchanged(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    original = state()
    original.day, original.key_counters = 3, {"REC": 12}
    store.save(original)
    assert store.load("r1") == original
    assert store.exists("r1") and store.runs() == ["r1"]


def test_the_state_file_is_private_because_it_holds_tokens(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.save(state())
    mode = stat.S_IMODE((tmp_path / "r1" / "run.json").stat().st_mode)
    assert mode == 0o600


def test_saving_again_replaces_it_and_leaves_no_scratch_file(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.save(state())
    changed = state()
    changed.day = 7
    store.save(changed)
    assert store.load("r1").day == 7
    assert sorted(p.name for p in (tmp_path / "r1").iterdir()) == ["run.json"]


def test_the_scope_is_the_simulation_project(tmp_path: Path) -> None:
    assert state("rabc12").scope == "project:sim-rabc12"


@pytest.mark.parametrize("bad", ["", "1abc", "a-b", "a/b", "../x", "a" * 25])
def test_a_run_id_must_be_a_letter_then_letters_and_digits(tmp_path: Path, bad: str) -> None:
    with pytest.raises(RunError, match="run id"):
        RunStore(tmp_path).run_dir(bad)


def test_an_unknown_run_names_the_known_ones(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.save(state("ra"))
    with pytest.raises(RunError, match="ra"):
        store.load("rb")


def test_only_run_needs_exactly_one(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    with pytest.raises(RunError, match="none"):
        store.only_run()
    store.save(state("ra"))
    assert store.only_run() == "ra"
    store.save(state("rb"))
    with pytest.raises(RunError, match="ra, rb"):
        store.only_run()
