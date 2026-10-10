"""The scenario model: what a simulated project is and what its team does (brief 29.5).

A scenario is data. ``scenario_loader.load_scenario`` reads it from YAML into these models; the
orchestrator and the actors only ever see the models. Phase 0 is deterministic and has no LLM
agents (FANOUT D6), so there is no ``llm_share`` or budget here.

Counts. Wherever a scenario says "how many per day" it may give an integer (``3``), a range
(``{min: 1, max: 3}``, uniform) or a normal distribution (``{dist: normal, mean: 2.4, sd: 0.6}``,
rounded and never below 0). ``draw`` turns one into a number using the actor's own generator.
"""

from __future__ import annotations

from datetime import date
from random import Random
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
INJECT_EVENTS = ("material_late", "design_revision", "post")
ACTOR_NAMES = ("document_controller", "planner", "crew")  # the order they act in each day


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CountRange(Strict):
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> CountRange:
        if self.max < self.min:
            raise ValueError("max must be at least min")
        return self


class CountNormal(Strict):
    dist: Literal["normal"]
    mean: float = Field(ge=0)
    sd: float = Field(ge=0)


Count = int | CountRange | CountNormal
"""An integer, a uniform range or a normal distribution; see the module docstring."""


def draw(count: Count, rng: Random) -> int:
    """One draw from ``count`` using ``rng``. Never negative."""
    if isinstance(count, bool):
        raise TypeError("a count is a number, not a bool")
    if isinstance(count, int):
        return max(0, count)
    if isinstance(count, CountRange):
        return rng.randint(count.min, count.max)
    return max(0, round(rng.gauss(count.mean, count.sd)))


class DocumentControllerParams(Strict):
    """Registers documents against lines, submits them for review and issues new revisions.

    Revisions run Rev A, Rev B, ... Rev Z. Rev Z is the last: a document at Rev Z is never revised.
    """

    documents_per_day: Count = CountRange(min=1, max=2)
    revision_rate: float = Field(default=0.25, ge=0, le=1)  # chance per day of one new revision
    forced_revisions: int = Field(default=0, ge=0)  # one-off: the `design_revision` injection


class PlannerParams(Strict):
    """Looks at documents in review, approves them, plans activities and writes the look-ahead."""

    approvals_per_day: Count = 2
    activities_per_day: Count = CountRange(min=0, max=2)
    lookahead_day: Weekday | None = "mon"  # the weekday of the look-ahead post; null is never


class CrewParams(Strict):
    """Installs valves on lines, records their data and posts the day's progress."""

    valves_per_day: Count = CountNormal(dist="normal", mean=3, sd=1)
    reject_rate: float = Field(default=0.1, ge=0, le=1)  # chance per day of a quality `#hold` post
    announce: str | None = None  # one-off: the `material_late` injection posts this text


class ActorsConfig(Strict):
    """Per-actor parameters. ``null`` in the YAML switches an actor off."""

    document_controller: DocumentControllerParams | None = DocumentControllerParams()
    planner: PlannerParams | None = PlannerParams()
    crew: CrewParams | None = CrewParams()

    def enabled(self) -> list[str]:
        return [name for name in ACTOR_NAMES if getattr(self, name) is not None]


class InjectSpec(BaseModel):
    """An event to play on a given working day: ``{day: 2, event: material_late, item: ...}``."""

    model_config = ConfigDict(extra="forbid")

    day: int = Field(ge=0)
    event: Literal["material_late", "design_revision", "post"]
    args: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _gather_args(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw: dict[str, Any] = dict(data)  # pyright: ignore[reportUnknownArgumentType]
        args: dict[str, Any] = dict(raw.pop("args", None) or {})
        for key in [k for k in raw if k not in ("day", "event")]:
            args[key] = raw.pop(key)
        raw["args"] = args
        return raw

    @model_validator(mode="after")
    def _check_args(self) -> InjectSpec:
        required = {"material_late": ("item",), "design_revision": (), "post": ("actor", "body")}
        missing = [name for name in required[self.event] if name not in self.args]
        if missing:
            raise ValueError(f"{self.event} needs: {', '.join(missing)}")
        if self.event == "post" and self.args["actor"] not in ACTOR_NAMES:
            raise ValueError(f"post actor must be one of {', '.join(ACTOR_NAMES)}")
        return self


class Scenario(Strict):
    scenario: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$", max_length=64)
    seed: int = Field(ge=0)
    start: date
    duration_days: int = Field(default=5, ge=1)  # working days `tl sim run` and `just seed` play
    working_days: list[Weekday] = ["mon", "tue", "wed", "thu", "fri"]
    template: str = Field(default="small-piping", pattern=r"^[a-z0-9][a-z0-9._-]*$")
    actors: ActorsConfig = ActorsConfig()
    inject: list[InjectSpec] = []

    @field_validator("working_days")
    @classmethod
    def _some_working_days(cls, value: list[Weekday]) -> list[Weekday]:
        if not value:
            raise ValueError("working_days must not be empty")
        return list(dict.fromkeys(value))


# --- the seed template ---------------------------------------------------------------------------


class AreaSpec(Strict):
    name: str = Field(min_length=1, max_length=80)
    lines: list[str] = Field(min_length=1)  # line designations, e.g. "6-CS-1001"


class Template(Strict):
    """The project that exists before day 0: areas and the piping lines in them."""

    template: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    description: str = ""
    areas: Annotated[list[AreaSpec], Field(min_length=1)]
    valve_sizes_in: list[float] = [2, 3, 4, 6, 8]
    manufacturers: list[str] = ["Crane", "Velan", "Emerson"]
    disciplines: list[str] = ["Piping", "Mechanical", "Civil", "Instrumentation"]
