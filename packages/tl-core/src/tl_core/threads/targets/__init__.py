"""Dispatch targets: the map from a verb to the commands it runs (FANOUT D10).

A :class:`~tl_core.threads.contract.DispatchTarget` only *builds* commands; the planner validates
them with the runner's models, checks each one's access with ``holds`` and dry-runs them. This
module holds the registry and the core defaults:

====== ======== ==========================================================
verb   name     runs
====== ======== ==========================================================
link   ``*``    ``AddLink`` from the thread's record to each key
status ``*``    ``TransitionWorkflow`` on the thread's record
raise  record   ``CreateRecord`` (``core.Record``) plus ``raised_against`` links
dispatch ``*``  ``InvokeAction``
notify ``*``    nothing: the mentions are recorded in the message
remind ``*``    the ``ThreadReminder`` effect (a ``thread.reminder`` job)
summarise ``*`` the ``ThreadSummary`` effect (a deterministic summary)
====== ======== ==========================================================

``assign``, ``due``, ``hold`` and ``release`` have no target in Phase 1 (there is no assignee,
due-date or constraint model): the planner answers ``dispatch_unavailable`` until a module registers
one under the entry-point group ``throughline.dispatch_targets``. So does ``/raise rfi`` until
P1-I6 registers its ``rfi`` alias.

Lookup: ``raise`` takes the alias exactly (``rfi``, ``record``); ``dispatch`` takes the request type
then ``*``; every other verb takes the thread's record type (``documents.Revision``) then ``*``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import entry_points
from typing import Any

from tl_core.integration.contract import Problem
from tl_core.threads.contract import (
    DISPATCH_TARGET_ENTRY_POINT,
    DispatchTarget,
    DispatchVerb,
    ParsedDispatch,
)

log = logging.getLogger(__name__)


def first_problem(problems: Iterable[Problem]) -> Problem:
    """One problem standing for several: the first code, every message."""
    items = list(problems)
    message = "; ".join(p.message for p in items)[:480]
    return Problem(code=items[0].code, message=message)


class TargetRegistry:
    """Targets by ``(verb, name)``. A second target for a pair is refused, never replaced."""

    def __init__(self) -> None:
        self._targets: dict[tuple[str, str], DispatchTarget] = {}

    def register(self, target: DispatchTarget) -> None:
        key = (target.verb, target.name)
        if key in self._targets:
            raise ValueError(f"two dispatch targets for {key}")
        self._targets[key] = target

    def names(self) -> list[tuple[str, str]]:
        return sorted(self._targets)

    def get(self, verb: DispatchVerb, name: str) -> DispatchTarget | None:
        return self._targets.get((verb, name))

    def find(self, parsed: ParsedDispatch, record_type: str) -> DispatchTarget | None:
        """The most specific target for a parsed command on a record of ``record_type``."""
        args: Any = parsed.args
        verb = parsed.verb
        if verb == "raise":
            return self.get(verb, str(args.record_type).lower())
        if verb == "dispatch":
            return self.get(verb, str(args.request_type)) or self.get(verb, "*")
        return self.get(verb, record_type) or self.get(verb, "*")


def core_targets() -> list[DispatchTarget]:
    from tl_core.threads.targets.dispatch_action import ActionTarget
    from tl_core.threads.targets.link import LinkTarget
    from tl_core.threads.targets.notify import NotifyTarget
    from tl_core.threads.targets.raise_record import RaiseRecordTarget
    from tl_core.threads.targets.remind import RemindTarget
    from tl_core.threads.targets.status import StatusTarget
    from tl_core.threads.targets.summarise import SummariseTarget

    return [
        LinkTarget(),
        StatusTarget(),
        RaiseRecordTarget(),
        ActionTarget(),
        NotifyTarget(),
        RemindTarget(),
        SummariseTarget(),
    ]


def _as_targets(loaded: Any) -> list[DispatchTarget]:
    if isinstance(loaded, DispatchTarget):
        return [loaded]
    if callable(loaded):
        loaded = loaded()
    if isinstance(loaded, DispatchTarget):
        return [loaded]
    return [t for t in loaded if isinstance(t, DispatchTarget)]


def load_targets(*, entry_points_group: str | None = DISPATCH_TARGET_ENTRY_POINT) -> TargetRegistry:
    """The core targets plus those modules register. A target that fails to load or clashes with
    another is logged and skipped: a broken module must not take dispatch down with it."""
    registry = TargetRegistry()
    for target in core_targets():
        registry.register(target)
    if entry_points_group is None:
        return registry
    for point in sorted(entry_points(group=entry_points_group), key=lambda p: p.name):
        try:
            for target in _as_targets(point.load()):
                registry.register(target)
        except Exception:  # noqa: BLE001 - a module's failure is logged, not raised
            log.warning("dispatch target %s could not be loaded", point.name, exc_info=True)
    return registry
