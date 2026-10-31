"""The readiness-check registry (phase 2 contracts section 1; ADR-0010 decision 3).

Checks are plugins found through the entry-point group ``throughline.readiness_checks``. Each entry
point names a zero-argument callable that returns an object satisfying ``ReadinessCheck``. A plugin
that fails to load, returns something that is not a check, or shares its name with another raises
:class:`ReadinessLoadError`: never a silent gap. The message keeps the exception type only; the full
text goes to the server log.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points

from tl_core.readiness.types import (
    MAX_CHECKS,
    MAX_NAME_CHARS,
    READINESS_ENTRY_POINT,
    ReadinessCheck,
)

log = logging.getLogger(__name__)

_SNAKE = re.compile(r"[a-z][a-z0-9_]*")


class ReadinessLoadError(Exception):
    """An installed readiness check could not be loaded, or two checks claim one name."""


def load_checks(entry_points_: Iterable[EntryPoint] | None = None) -> dict[str, ReadinessCheck]:
    """The readiness checks by name, sorted by name.

    ``entry_points_`` is an iterable of entry points (a test injects plugins); the default reads
    the group ``throughline.readiness_checks``. Raises :class:`ReadinessLoadError` for a plugin that
    does not load, does not return a ``ReadinessCheck``, is named differently from its entry point,
    or repeats a name, and when more than ``MAX_CHECKS`` checks are installed.
    """
    points = entry_points(group=READINESS_ENTRY_POINT) if entry_points_ is None else entry_points_
    found: dict[str, ReadinessCheck] = {}
    for entry in sorted(points, key=lambda e: e.name):
        try:
            produced = entry.load()()
        except Exception as exc:
            log.warning("readiness check %r cannot be loaded: %s", entry.name, exc, exc_info=True)
            raise ReadinessLoadError(
                f"readiness check {entry.name!r} cannot be loaded: {type(exc).__name__}"
            ) from exc
        if not isinstance(produced, ReadinessCheck):
            raise ReadinessLoadError(
                f"readiness check {entry.name!r}: its entry point must return a ReadinessCheck"
            )
        name = produced.name
        if len(name) > MAX_NAME_CHARS or _SNAKE.fullmatch(name) is None:
            raise ReadinessLoadError(
                f"readiness check {entry.name!r}: the name must be snake case, "
                f"at most {MAX_NAME_CHARS} characters"
            )
        if name in found:
            raise ReadinessLoadError(f"readiness check {name!r} is declared twice")
        found[name] = produced
    if len(found) > MAX_CHECKS:
        raise ReadinessLoadError(f"more than {MAX_CHECKS} readiness checks are installed")
    return dict(sorted(found.items()))
