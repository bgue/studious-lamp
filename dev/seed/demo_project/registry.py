"""The sections of the generator: what each one builds and which record types it needs."""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from tl_core.modules import load_modules
from tl_schema.generated import models

from dev.seed.demo_project.world import World

#: The order sections run in. A later section may read what an earlier one wrote.
ORDER = (
    "core",
    "engineering",
    "documents",
    "correspondence",
    "awp",
    "schedule",
    "constraints",
    "scope",
    "release",
    "materials",
    "quality",
    "requisitions",
    "weekly",
    "progress",
)

Build = Callable[[World, random.Random], None]


@dataclass(frozen=True)
class Section:
    name: str
    build: Build
    needs: tuple[str, ...] = ()  # record types that must be installed, e.g. ``quality.PunchItem``


SECTIONS: dict[str, Section] = {}


def register(name: str, build: Build, needs: tuple[str, ...] = ()) -> None:
    """Add a section. ``name`` must be one of ``ORDER``."""
    if name not in ORDER:
        raise ValueError(f"unknown section {name!r}; sections are {', '.join(ORDER)}")
    SECTIONS[name] = Section(name, build, needs)


def missing_types(section: Section) -> list[str]:
    """The record types ``section`` needs that no installed module provides."""
    installed = {t for spec in load_modules() for t in spec.record_types}
    return [t for t in section.needs if t not in installed and not _core_type(t)]


def _core_type(record_type: str) -> bool:
    """A ``core.<Name>`` record type that the generated schema models carry (no module owns it)."""
    kind, _, name = record_type.partition(".")
    return kind == "core" and hasattr(models, name)
