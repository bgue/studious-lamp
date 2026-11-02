"""Where a published derived document's rows go: the publish targets found by entry point.

A publish target is a plugin of the group ``throughline.publish_targets``. Each entry point names a
zero-argument callable that returns a :class:`PublishTarget`; the built-ins ``tags`` and
``documents`` are registered by this package's own ``pyproject.toml``, and a module adds its own by
adding a line to its own. A plugin that fails to load, returns something that is not a target,
is named differently from its entry point or outside ``^[a-z][a-z0-9_]*$``, or shares a name with
another raises :class:`PublishTargetLoadError` naming the group and the entry point: never a silent
gap. A name nobody registered is a ``PublishRefusedError`` (422) that lists the known ones.

The publication itself (create-only, one correlation id, exact compensation, ADR-0014) stays in
:mod:`tl_mod_documents.derivation.publish`; a target only plans its rows and creates its records.

A target other than the built-in ``tags`` and ``documents`` may offer these optional parts (a
target without them is as before; documents never imports the module that registers the target):

* ``mapping_fields``: the names a mapping may send a column to (``check_mapping`` reads it).
* ``plan_rows_for(conn, scope, derived, mapped)``: ``plan_rows`` for a target whose keys depend on
  the derived document the rows came from (``derived`` is a ``rows.DerivedRow``).
* ``takes_provenance``: ``False`` when the target cannot write the ``provenance`` property set (its
  records take no ``SetPsetValues``); the publication then does not require the pset to apply.
* ``compensation_item(conn, record_id, scope)`` and ``reverse(uow, base, record_id, reason)``
  (:class:`ReversibleTarget`): whether the record a publication made can be rolled back, and the
  reversing events. Without them a record of the target's type is not reversible.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager
from importlib import metadata
from typing import Any, Protocol, runtime_checkable

from tl_core.modules import ModuleLoadError

from tl_mod_documents.errors import PublishRefusedError

log = logging.getLogger(__name__)

PUBLISH_ENTRY_POINT = "throughline.publish_targets"
_NAME = re.compile(r"[a-z][a-z0-9_]*")


class PublishTargetLoadError(ModuleLoadError):
    """An installed publish target cannot be loaded, is misnamed, or is declared twice."""


@runtime_checkable
class PublishTarget(Protocol):
    """One kind of record a derived document's rows can be published as."""

    #: The registered name (the entry point's name).
    name: str
    #: The module that registers it (listed with the name).
    module: str
    #: The record type the target creates (``engineering.Tag``).
    record_type: str

    def plan_rows(
        self, conn: Any, scope: str, mapped: list[Any]
    ) -> tuple[list[Any], list[Any], dict[str, int]]:
        """``(plan rows, creatable rows, counts)`` for the mapped rows (nothing is written)."""
        ...

    def create(
        self, uow: Any, base: dict[str, Any], built: Any, provenance: dict[str, str]
    ) -> list[str]:
        """Create the creatable rows with the module's own commands; the ids, in row order."""
        ...


@runtime_checkable
class ReversibleTarget(Protocol):
    """The optional reverse hook of a publish target (see the module docstring)."""

    record_type: str

    def compensation_item(self, conn: Any, record_id: str, scope: str) -> tuple[bool, str | None]:
        """``(reversible, problem)`` for a record the publication made; reads only."""
        ...

    def reverse(self, uow: Any, base: dict[str, Any], record_id: str, reason: str) -> None:
        """Append the reversing events of the record (``base`` is the compensation's envelope)."""
        ...


_lock = threading.Lock()
_found: dict[str, PublishTarget] | None = None
_override: dict[str, PublishTarget] | None = None


def load_publish_targets(
    entry_points: Iterable[metadata.EntryPoint] | None = None,
) -> dict[str, PublishTarget]:
    """The publish targets by name, sorted by name.

    ``entry_points`` is an iterable of entry points (a test injects plugins); the default reads
    the group ``throughline.publish_targets``.
    """
    points = (
        metadata.entry_points(group=PUBLISH_ENTRY_POINT) if entry_points is None else entry_points
    )
    found: dict[str, PublishTarget] = {}
    for entry in sorted(points, key=lambda e: (e.name, e.value)):
        where = f"{PUBLISH_ENTRY_POINT} entry point {entry.name!r}"
        if _NAME.fullmatch(entry.name) is None:
            raise PublishTargetLoadError(f"{where}: the name must match ^[a-z][a-z0-9_]*$")
        try:
            produced = entry.load()()
        except Exception as exc:
            log.warning("%s cannot be loaded: %s", where, exc, exc_info=True)
            raise PublishTargetLoadError(f"{where} cannot be loaded: {type(exc).__name__}") from exc
        if not isinstance(produced, PublishTarget) or produced.name != entry.name:
            raise PublishTargetLoadError(f"{where} must return a PublishTarget of the same name")
        if entry.name in found:
            raise PublishTargetLoadError(
                f"{PUBLISH_ENTRY_POINT}: target {entry.name!r} is declared twice"
            )
        found[entry.name] = produced
    return dict(sorted(found.items()))


def publish_targets() -> Mapping[str, PublishTarget]:
    """The installed publish targets by name, found once per process."""
    global _found
    with _lock:
        if _override is not None:
            return _override
        if _found is None:
            _found = load_publish_targets()
        return _found


def publish_target_for(name: str) -> PublishTarget:
    """The target of that name, or ``PublishRefusedError`` naming the known ones."""
    targets = publish_targets()
    found = targets.get(name)
    if found is None:
        known = ", ".join(sorted(targets)) or "none installed"
        raise PublishRefusedError(f"no publish target {name!r} (known: {known})")
    return found


def reversible_target_for(record_type: str) -> ReversibleTarget | None:
    """The registered target that creates ``record_type`` and offers the reverse hook, else None."""
    for target in publish_targets().values():
        if target.record_type == record_type and isinstance(target, ReversibleTarget):
            return target
    return None


@contextmanager
def use_publish_targets(targets: Mapping[str, PublishTarget]) -> Generator[None]:
    """Make ``targets`` the only publish targets for the block (tests)."""
    global _override
    with _lock:
        previous, _override = _override, dict(targets)
    try:
        yield
    finally:
        with _lock:
            _override = previous
