"""The rows of a cost snapshot file, as the reader returns them and the command takes them."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, field_validator
from tl_core.text import clean_optional_text, clean_text

from tl_mod_cost.limits import MAX_CODE, MAX_FIGURE, MAX_TEXT, MAX_UOM
from tl_mod_cost.names import MEASURE_COLUMNS


class CostRow(BaseModel):
    """One code of a snapshot: what the cost system says about it for the period.

    ``description``, ``parent_code`` and ``uom`` are null when the file does not state them
    (a new code then has the code as its title, no parent and no unit; an existing code keeps what
    it has). ``figures`` holds only the measures the file states, keyed by the fifteen names of
    ``MEASURE_COLUMNS``; a figure the file does not state is absent, never zero.
    """

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=MAX_CODE)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    parent_code: str | None = Field(default=None, max_length=MAX_CODE)
    uom: str | None = Field(default=None, max_length=MAX_UOM)
    figures: dict[str, float] = Field(default_factory=dict[str, float])

    @field_validator("description", "uom")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return clean_optional_text(value)

    @field_validator("code", "parent_code")
    @classmethod
    def _plain_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean_text(value)
        if value != value.strip() or not value:
            raise ValueError("a cost code has no leading or trailing space")
        if "@" in value:
            raise ValueError("a cost code may not hold '@'")
        return value

    @field_validator("figures")
    @classmethod
    def _figures(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(value) - set(MEASURE_COLUMNS))
        if unknown:
            raise ValueError(f"unknown figures: {', '.join(unknown[:5])}")
        for name, figure in value.items():
            if not math.isfinite(figure) or abs(figure) > MAX_FIGURE:
                raise ValueError(f"{name} is not a usable number")
        return value


@dataclass(frozen=True)
class CostFile:
    """What the CSV reader returns."""

    rows: tuple[CostRow, ...]
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
