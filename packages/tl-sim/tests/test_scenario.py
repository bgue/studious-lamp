"""The scenario models: counts, injections and defaults."""

from __future__ import annotations

from datetime import date
from random import Random

import pytest
from pydantic import ValidationError
from tl_sim.scenario import (
    CountNormal,
    CountRange,
    CrewParams,
    InjectSpec,
    Scenario,
    Template,
    draw,
)

BASE = {"scenario": "t", "seed": 1, "start": date(2026, 11, 2)}


def test_an_integer_count_uses_no_randomness() -> None:
    rng = Random(1)
    state = rng.getstate()
    assert draw(3, rng) == 3 and draw(-2, rng) == 0
    assert rng.getstate() == state


def test_a_range_is_uniform_and_inclusive() -> None:
    seen = {draw(CountRange(min=1, max=3), Random(n)) for n in range(60)}
    assert seen == {1, 2, 3}


def test_a_normal_count_is_rounded_and_never_negative() -> None:
    rng = Random(3)
    values = [draw(CountNormal(dist="normal", mean=0.2, sd=2), rng) for _ in range(200)]
    assert min(values) == 0 and all(isinstance(v, int) for v in values)
    assert max(values) > 0


def test_a_range_with_max_below_min_is_refused() -> None:
    with pytest.raises(ValidationError, match="max must be at least min"):
        CountRange(min=3, max=1)


def test_defaults_enable_all_three_actors_in_order() -> None:
    scenario = Scenario(**BASE)
    assert scenario.actors.enabled() == ["document_controller", "planner", "crew"]
    assert scenario.working_days == ["mon", "tue", "wed", "thu", "fri"]


def test_an_actor_can_be_switched_off_with_null() -> None:
    scenario = Scenario.model_validate({**BASE, "actors": {"planner": None}})
    assert scenario.actors.enabled() == ["document_controller", "crew"]


def test_unknown_keys_are_refused_everywhere() -> None:
    for bad in (
        {**BASE, "colour": 1},
        {**BASE, "actors": {"crew": {"speed": 9}}},
        {**BASE, "actors": {"welder": {}}},
    ):
        with pytest.raises(ValidationError):
            Scenario.model_validate(bad)
    with pytest.raises(ValidationError):
        CrewParams.model_validate({"valves_per_day": {"dist": "uniform", "mean": 1, "sd": 1}})


def test_injection_arguments_are_gathered_from_the_flat_form() -> None:
    spec = InjectSpec.model_validate(
        {"day": 2, "event": "material_late", "item": "flange", "days": 21}
    )
    assert spec.args == {"item": "flange", "days": 21}
    again = InjectSpec.model_validate(spec.model_dump())
    assert again == spec


@pytest.mark.parametrize(
    "bad",
    [
        {"day": 1, "event": "material_late"},
        {"day": 1, "event": "post", "actor": "crew"},
        {"day": 1, "event": "post", "actor": "welder", "body": "x"},
        {"day": -1, "event": "design_revision"},
        {"day": 1, "event": "flood"},
    ],
)
def test_an_invalid_injection_is_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InjectSpec.model_validate(bad)


def test_a_template_needs_an_area_with_a_line() -> None:
    with pytest.raises(ValidationError):
        Template.model_validate({"template": "t", "areas": []})
    with pytest.raises(ValidationError):
        Template.model_validate({"template": "t", "areas": [{"name": "A", "lines": []}]})
