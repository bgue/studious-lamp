"""Names a scaffolder accepts, and the spellings derived from them.

A module is ``[a-z][a-z0-9_]``; a record type class is CamelCase; a projector name is snake_case.
Validation is strict because every name ends up in a file path, a Python identifier and a LinkML
class name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RESERVED_MODULES = frozenset({"core", "test", "tests", "dev", "tl", "schema", "docs"})
_MODULE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_CLASS = re.compile(r"^[A-Z][a-z0-9]*(?:[A-Z][a-z0-9]*)*$")
_SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_EVENT = re.compile(r"^[A-Z][A-Za-z0-9]*\.[A-Z][A-Za-z0-9]*$")
MAX_CLASS = 30
MAX_PROJECTOR = 40
MAX_MODULE = 20


class NameError_(ValueError):
    """A name was refused; the message says the rule."""


def check_module(name: str) -> str:
    """``name`` as a module name, or :class:`NameError_`."""
    if not _MODULE.fullmatch(name) or not 2 <= len(name) <= MAX_MODULE:
        raise NameError_(
            f"module name {name!r}: use 2 to 20 lower-case letters, digits and single underscores, "
            "starting with a letter"
        )
    if name in RESERVED_MODULES:
        raise NameError_(f"module name {name!r} is reserved")
    return name


def snake(camel: str) -> str:
    """``WeldInspection`` as ``weld_inspection``."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", camel).lower()


def camel(snake_name: str) -> str:
    """``weld_inspection`` as ``WeldInspection``."""
    return "".join(part.capitalize() for part in snake_name.split("_"))


@dataclass(frozen=True)
class ModuleName:
    name: str  # inspection

    @property
    def package(self) -> str:  # tl_mod_inspection
        return f"tl_mod_{self.name}"

    @property
    def distribution(self) -> str:  # tl-mod-inspection
        return f"tl-mod-{self.name.replace('_', '-')}"

    @property
    def directory(self) -> str:  # packages/tl-modules/inspection
        return f"packages/tl-modules/{self.name}"


@dataclass(frozen=True)
class RecordTypeName:
    """``<module>.<Class>``, for example ``inspection.WeldInspection``."""

    module: ModuleName
    cls: str  # WeldInspection

    @property
    def snake(self) -> str:  # weld_inspection
        return snake(self.cls)

    @property
    def qualified(self) -> str:
        return f"{self.module.name}.{self.cls}"

    @property
    def table(self) -> str:  # cur_inspection_weld_inspection
        return f"cur_{self.module.name}_{self.snake}"


@dataclass(frozen=True)
class ProjectorName:
    """``<module>.<name>``, for example ``inspection.weld_counts``."""

    module: ModuleName
    name: str  # weld_counts

    @property
    def cls(self) -> str:  # WeldCountsProjector
        return f"{camel(self.name)}Projector"

    @property
    def table(self) -> str:  # proj_inspection_weld_counts
        return f"proj_{self.module.name}_{self.name}"


def parse_module(text: str) -> ModuleName:
    return ModuleName(check_module(text.strip()))


def parse_record_type(text: str) -> RecordTypeName:
    """``module.Class`` as a :class:`RecordTypeName`, or :class:`NameError_`."""
    module, dot, cls = text.strip().partition(".")
    if not dot:
        raise NameError_(
            f"record type {text!r}: write <module>.<Class>, for example inspection.Weld"
        )
    if not _CLASS.fullmatch(cls) or len(cls) > MAX_CLASS:
        raise NameError_(
            f"class name {cls!r}: use CamelCase letters and digits (at most {MAX_CLASS}), "
            "starting with a capital"
        )
    return RecordTypeName(parse_module(module), cls)


def parse_projector(text: str) -> ProjectorName:
    """``module.name`` as a :class:`ProjectorName`, or :class:`NameError_`."""
    module, dot, name = text.strip().partition(".")
    if not dot:
        raise NameError_(
            f"projector {text!r}: write <module>.<name>, for example inspection.counts"
        )
    if not _SNAKE.fullmatch(name) or not 2 <= len(name) <= MAX_PROJECTOR:
        raise NameError_(
            f"projector name {name!r}: use lower_snake_case letters and digits "
            f"(2 to {MAX_PROJECTOR})"
        )
    return ProjectorName(parse_module(module), name)


def check_event_type(text: str) -> str:
    """``Record.Created`` style event type, or :class:`NameError_`."""
    if not _EVENT.fullmatch(text) or len(text) > 80:
        raise NameError_(f"event type {text!r}: write <Class>.<PastTenseVerb>, e.g. Weld.Created")
    return text
