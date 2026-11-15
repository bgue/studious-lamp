"""The permit type table: what each type demands (design section 3), read once.

The table is the file ``schema/fixtures/permits/types.yaml``, read from the repository tree. An
entry missing for a ``PermitType`` value, an unknown key or a repeated precaution id is an error
at load.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from tl_mod_permits.names import PERMIT_TYPES

TYPES_FILE = Path(__file__).resolve().parents[5] / "schema" / "fixtures" / "permits" / "types.yaml"


class TypesTableError(ValueError):
    """The type table is malformed."""


class Precaution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=120)


class TypeRule(BaseModel):
    """What one permit type demands."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_gas_test: bool
    needs_isolation: bool
    max_days: int = Field(ge=1)
    precautions: tuple[Precaution, ...]

    @field_validator("max_days")
    @classmethod
    def _one_or_seven(cls, value: int) -> int:
        if value not in (1, 7):
            raise ValueError("max_days is 1 or 7")
        return value

    @field_validator("precautions")
    @classmethod
    def _unique_ids(cls, value: tuple[Precaution, ...]) -> tuple[Precaution, ...]:
        ids = [p.id for p in value]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate precaution id")
        return value


def parse_types(raw: Any) -> dict[str, TypeRule]:
    """Validate a parsed table: one entry per permit type, no other key."""
    if not isinstance(raw, dict) or set(raw) != {"types"} or not isinstance(raw["types"], dict):
        raise TypesTableError("the type table is one mapping `types:`")
    table: dict[str, Any] = raw["types"]
    unknown = sorted(set(table) - set(PERMIT_TYPES))
    if unknown:
        raise TypesTableError(f"unknown permit type: {', '.join(unknown)}")
    missing = [t for t in PERMIT_TYPES if t not in table]
    if missing:
        raise TypesTableError(f"no entry for permit type: {', '.join(missing)}")
    try:
        return {t: TypeRule.model_validate(table[t]) for t in PERMIT_TYPES}
    except ValidationError as err:
        raise TypesTableError(str(err)) from err


def load_types_from(path: Path) -> dict[str, TypeRule]:
    """Read and validate a table file (the tests' door; the module uses ``load_types``)."""
    return parse_types(yaml.safe_load(path.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def _load() -> tuple[tuple[str, TypeRule], ...]:
    return tuple(load_types_from(TYPES_FILE).items())


def load_types() -> dict[str, TypeRule]:
    """The type table, read once. A fresh dict each call; the rules are frozen."""
    return dict(_load())
