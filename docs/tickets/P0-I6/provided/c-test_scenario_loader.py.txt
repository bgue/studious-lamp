"""Scenario and template loading, and the bundled files under dev/seed (supervisor-provided)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from tl_sim.scenario import CountNormal, CountRange, Scenario, Template
from tl_sim.scenario_loader import (
    MAX_BYTES,
    ScenarioError,
    bundled_scenarios,
    load_scenario,
    load_template,
    seed_dir,
)

MINIMAL = "scenario: tiny\nseed: 5\nstart: 2026-11-02\n"


@pytest.fixture
def own_seed_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "templates").mkdir()
    monkeypatch.setenv("TL_SEED_DIR", str(tmp_path))
    return tmp_path


def test_the_default_seed_dir_is_dev_seed_in_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    found = seed_dir()
    assert found.parts[-2:] == ("dev", "seed")
    assert (found / "scenarios").is_dir() and (found / "templates").is_dir()


def test_tl_seed_dir_overrides_it(own_seed_dir: Path) -> None:
    assert seed_dir() == own_seed_dir


def test_the_bundled_scenarios_are_listed_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    names = bundled_scenarios()
    assert names == sorted(names)
    assert {"north-unit-small", "seed-xs", "seed-s", "seed-m"} <= set(names)


def test_no_scenarios_directory_lists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TL_SEED_DIR", str(tmp_path / "missing"))
    assert bundled_scenarios() == []


def test_a_bundled_scenario_loads_by_name_and_by_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    by_name = load_scenario("north-unit-small")
    by_path = load_scenario(seed_dir() / "scenarios" / "north-unit-small.yaml")
    assert by_name == by_path
    assert isinstance(by_name, Scenario)
    assert (by_name.seed, by_name.start, by_name.duration_days) == (4711, date(2026, 11, 2), 5)
    assert by_name.template == "small-piping"


def test_counts_in_a_scenario_become_ranges_and_distributions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    scenario = load_scenario("north-unit-small")
    assert scenario.actors.document_controller is not None
    assert scenario.actors.document_controller.documents_per_day == CountRange(min=1, max=2)
    assert scenario.actors.crew is not None
    assert scenario.actors.crew.valves_per_day == CountNormal(dist="normal", mean=3, sd=1)
    assert scenario.actors.planner is not None
    assert scenario.actors.planner.approvals_per_day == 2


def test_injections_are_loaded_with_their_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    first, second = load_scenario("north-unit-small").inject
    assert (first.day, first.event, first.args["item"], first.args["days"]) == (
        2,
        "material_late",
        "6in CL300 WN flange",
        21,
    )
    assert (second.day, second.event, second.args) == (3, "design_revision", {"count": 2})


def test_a_scenario_with_only_the_required_keys_gets_the_defaults(own_seed_dir: Path) -> None:
    (own_seed_dir / "scenarios" / "tiny.yaml").write_text(MINIMAL)
    scenario = load_scenario("tiny")
    assert scenario.working_days == ["mon", "tue", "wed", "thu", "fri"]
    assert scenario.actors.enabled() == ["document_controller", "planner", "crew"]
    assert scenario.inject == []


def test_null_switches_an_actor_off(own_seed_dir: Path) -> None:
    (own_seed_dir / "scenarios" / "quiet.yaml").write_text(MINIMAL + "actors:\n  planner: null\n")
    assert load_scenario("quiet").actors.enabled() == ["document_controller", "crew"]


def test_a_path_outside_the_seed_dir_loads(tmp_path: Path) -> None:
    path = tmp_path / "mine.yaml"
    path.write_text(MINIMAL)
    assert load_scenario(path).scenario == "tiny"
    assert load_scenario(str(path)).scenario == "tiny"


def test_an_unknown_name_lists_what_is_bundled(own_seed_dir: Path) -> None:
    (own_seed_dir / "scenarios" / "tiny.yaml").write_text(MINIMAL)
    with pytest.raises(ScenarioError) as raised:
        load_scenario("nope")
    assert "nope" in str(raised.value) and "tiny" in str(raised.value)


def test_a_missing_path_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="gone.yaml"):
        load_scenario(tmp_path / "gone.yaml")


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("scenario: [unclosed\n", "not valid YAML"),
        ("- just\n- a list\n", "mapping"),
        (MINIMAL + "colour: red\n", "colour"),
        ("scenario: tiny\nstart: 2026-11-02\n", "seed"),
        ("scenario: tiny\nseed: -1\nstart: 2026-11-02\n", "seed"),
        (MINIMAL + "actors:\n  crew:\n    reject_rate: 7\n", "actors.crew.reject_rate"),
        (MINIMAL + "inject:\n  - {day: 1, event: flood}\n", "inject"),
        (MINIMAL + "working_days: []\n", "working_days"),
    ],
)
def test_an_invalid_scenario_is_a_scenario_error_that_names_the_file_and_the_field(
    tmp_path: Path, text: str, needle: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(ScenarioError) as raised:
        load_scenario(path)
    assert "bad.yaml" in str(raised.value)
    assert needle in str(raised.value)


def test_a_file_over_the_size_limit_is_refused_before_it_is_parsed(tmp_path: Path) -> None:
    path = tmp_path / "huge.yaml"
    path.write_text(MINIMAL + "#" + "x" * MAX_BYTES + "\n")
    with pytest.raises(ScenarioError, match="huge.yaml.*more than"):
        load_scenario(path)


def test_yaml_cannot_construct_python_objects(tmp_path: Path) -> None:
    path = tmp_path / "evil.yaml"
    path.write_text(MINIMAL + "x: !!python/object/apply:os.getcwd []\n")
    with pytest.raises(ScenarioError, match="evil.yaml"):
        load_scenario(path)


def test_a_bundled_template_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    template = load_template("small-piping")
    assert isinstance(template, Template)
    assert [a.name for a in template.areas] == ["Unit 100 North", "Unit 200 Utilities"]
    assert template.areas[0].lines[0] == "6-CS-1001"


def test_every_bundled_scenario_names_a_template_that_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TL_SEED_DIR", raising=False)
    for name in bundled_scenarios():
        scenario = load_scenario(name)
        assert scenario.scenario == name, "the file name is the scenario name"
        assert load_template(scenario.template).areas


def test_template_errors_name_the_template(own_seed_dir: Path) -> None:
    with pytest.raises(ScenarioError, match="ghost"):
        load_template("ghost")
    with pytest.raises(ScenarioError, match="template name"):
        load_template("../scenarios/tiny")
    (own_seed_dir / "templates" / "empty.yaml").write_text("template: empty\nareas: []\n")
    with pytest.raises(ScenarioError, match="empty.yaml.*areas"):
        load_template("empty")
