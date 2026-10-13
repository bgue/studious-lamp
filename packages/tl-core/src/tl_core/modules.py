"""Modules: what a module package adds to the platform (ADR-0010; brief 25.2, 31).

A module (``packages/tl-modules/<name>``, schema in ``schema/modules/<name>``) adds record types
that live in the platform's one record table. ``cur_core_record`` keeps the envelope of every
record, so links, property sets, workflow, the query language and the feed work on module records
at once; the module keeps the typed columns of its own types in its own current-state tables,
joined on ``id``. This file is the only place the core learns what a module provides, and it learns
it through ``ModuleSpec``, never by importing the module.

A module package declares one entry point in the group ``throughline.modules``. Its value is a
function that returns the module's ``ModuleSpec``::

    [project.entry-points."throughline.modules"]
    engineering = "tl_mod_engineering.module:spec"

What the platform does with a spec:

* ``default_registry()`` registers the spec's projectors after the core ones and before the outbox,
  so a ledger made, rebuilt or restored by any entry point has the module's tables.
* ``create_module_record`` (``tl_core.services.records``) creates records of the spec's record
  types; ``CreateRecord`` still refuses them, because a module record needs its typed fields.
* ``bound_psets`` asks the module which property sets a record's class binds to it, for conformance
  and pset writes (``tl_core.services.psets``).
* ``numbering_patterns`` lets the module supply the numbering patterns held in the ledger.

A module that is installed but broken (an entry point that does not import, or returns something
that is not a ``ModuleSpec``) raises ``ModuleLoadError`` at the first use: a silently missing
projector would leave tables empty without a trace.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from sqlalchemy import Connection

from tl_core.numbering.config import NumberingPattern
from tl_core.projection.types import Projector

ENTRY_POINT_GROUP = "throughline.modules"

#: The generic commands that reach a record through ``cur_core_record`` whatever its type. A module
#: record type allows none of them unless its spec lists the command in ``generic_commands``
#: (ADR-0010 addendum): the envelope and the typed fields of a module record change through the
#: module's own commands, which check the module's rules and the caller's role.
GENERIC_COMMANDS = frozenset(
    {
        "UpdateRecord",
        "VoidRecord",
        "SetPsetValues",
        "TransitionWorkflow",
        "AddLink",
        "SuggestLink",
        "AttachFile",
        # The life of a link (ADR-0010 addendum, P1-I2): checked at the end the link starts at.
        "AcceptLink",
        "DeclineLink",
        "RepinLink",
        "VerifyLink",
        "FlagLink",
        "RetractLink",
    }
)

#: ``(conn, record_id, slot)``: raise ``UnsupportedRecordTypeError`` when the record's *state* does
#: not allow the generic command (ADR-0010 addendum, P1-I2). ``slot`` is the file slot of an
#: ``AttachFile`` (``None`` for an unslotted attachment and for every other command).
GenericGuard = Callable[[Connection, str, "str | None"], None]

ProjectorFactory = Callable[[], Sequence[Projector]]
#: ``(conn, record_type, record_id)`` to the names of the psets the record's class binds, in order.
BoundPsetsHook = Callable[[Connection, str, str], tuple[str, ...]]
#: ``(conn)`` to the numbering patterns held in the ledger, in a stable order.
NumberingPatternsHook = Callable[[Connection], Sequence[NumberingPattern]]


class ModuleLoadError(RuntimeError):
    """An installed module could not be loaded, or two modules claim the same name or type."""


def _no_commands() -> dict[str, frozenset[str]]:
    return {}


def _no_guards() -> dict[tuple[str, str], GenericGuard]:
    return {}


@dataclass(frozen=True)
class ModuleSpec:
    name: str  # ``engineering``; equal to the directory under ``schema/modules`` and the tl:module
    record_types: frozenset[str]  # ``engineering.Tag`` ...; each starts with ``<name>.``
    projectors: ProjectorFactory  # fresh projector instances; registered in this order
    bound_psets: BoundPsetsHook | None = None
    numbering_patterns: NumberingPatternsHook | None = None
    #: Per record type, the generic commands (``GENERIC_COMMANDS``) people may run on it. A type
    #: that is not a key allows none. These commands are open to every signed-in person: a change
    #: that needs a role is a command of the module, not an entry here.
    generic_commands: Mapping[str, frozenset[str]] = field(default_factory=_no_commands)
    #: Per ``(record type, generic command)``, a state check run after the allow-list: a command
    #: that is allowed for a type may still be refused by what the record is now (a revision that
    #: was issued takes no new PDF). Called by ``require_generic`` from the same places as the
    #: allow-list, including the file upload path, so every entry point inherits it.
    generic_guards: Mapping[tuple[str, str], GenericGuard] = field(default_factory=_no_guards)

    def __post_init__(self) -> None:
        for record_type, commands in self.generic_commands.items():
            if record_type not in self.record_types:
                raise ModuleLoadError(
                    f"module {self.name!r}: generic_commands names {record_type!r}, "
                    "which is not one of its record types"
                )
            unknown = sorted(commands - GENERIC_COMMANDS)
            if unknown:
                raise ModuleLoadError(
                    f"module {self.name!r}: {', '.join(unknown)} is not a generic command"
                )
        for (record_type, command), _guard in self.generic_guards.items():
            if record_type not in self.record_types or command not in GENERIC_COMMANDS:
                raise ModuleLoadError(
                    f"module {self.name!r}: generic_guards names ({record_type!r}, {command!r}), "
                    "which is not one of its record types and a generic command"
                )
        for record_type in self.record_types:
            if not record_type.startswith(f"{self.name}."):
                raise ModuleLoadError(
                    f"module {self.name!r}: record type {record_type!r} must start with "
                    f"{self.name + '.'!r}"
                )


_lock = threading.Lock()
_override: tuple[ModuleSpec, ...] | None = None
_loaded: tuple[ModuleSpec, ...] | None = None


def _discover() -> tuple[ModuleSpec, ...]:
    found: dict[str, ModuleSpec] = {}
    owner: dict[str, str] = {}
    for entry in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda e: e.name):
        try:
            produced = entry.load()()
        except Exception as exc:
            raise ModuleLoadError(f"module {entry.name!r} cannot be loaded: {exc}") from exc
        if not isinstance(produced, ModuleSpec):
            raise ModuleLoadError(
                f"module {entry.name!r}: its entry point must return a ModuleSpec"
            )
        if produced.name != entry.name:
            raise ModuleLoadError(
                f"module entry point {entry.name!r} returned a spec named {produced.name!r}"
            )
        if produced.name in found:
            raise ModuleLoadError(f"module {produced.name!r} is declared twice")
        for record_type in produced.record_types:
            if record_type in owner:
                raise ModuleLoadError(
                    f"record type {record_type!r} is claimed by {owner[record_type]!r} "
                    f"and {produced.name!r}"
                )
            owner[record_type] = produced.name
        found[produced.name] = produced
    return tuple(found[name] for name in sorted(found))


def load_modules() -> tuple[ModuleSpec, ...]:
    """The installed modules, sorted by name. Discovered once per process."""
    global _loaded
    with _lock:
        if _override is not None:
            return _override
        if _loaded is None:
            _loaded = _discover()
        return _loaded


@contextmanager
def use_modules(specs: Sequence[ModuleSpec]) -> Generator[None]:
    """Install ``specs`` as the only modules for the block (tests and embedders)."""
    global _override
    with _lock:
        previous, _override = _override, tuple(specs)
    try:
        yield
    finally:
        with _lock:
            _override = previous


def module_projectors() -> list[Projector]:
    """Fresh projectors of every module, module by module in name order."""
    projectors: list[Projector] = []
    for spec in load_modules():
        projectors.extend(spec.projectors())
    return projectors


def require_generic_command(record_type: str, command: str) -> None:
    """Refuse ``command`` on a record of a module type that does not allow it.

    A core or extension record type is not a module's and passes. Raises
    ``UnsupportedRecordTypeError`` (422 ``unsupported_record_type``) with a fixed message that
    names the type and the command, so every entry point (API, CLI, MCP, a proposal accepted
    later) answers the same.
    """
    for spec in load_modules():
        if record_type in spec.record_types:
            if command in spec.generic_commands.get(record_type, frozenset()):
                return
            from tl_core.services.errors import UnsupportedRecordTypeError  # avoid an import cycle

            raise UnsupportedRecordTypeError(
                f"{command} cannot change a {record_type} record: it changes through the "
                f"{spec.name} module's own commands"
            )


def require_generic(
    conn: Connection,
    record_type: str,
    command: str,
    record_id: str,
    *,
    slot: str | None = None,
) -> None:
    """``require_generic_command`` and then the module's state guard for ``(type, command)``.

    The guard (``ModuleSpec.generic_guards``) sees the record as it is now: the same command may be
    allowed in one state and refused in another. A core or extension type passes.
    """
    require_generic_command(record_type, command)
    for spec in load_modules():
        guard = spec.generic_guards.get((record_type, command))
        if guard is not None:
            guard(conn, record_id, slot)


def module_record_types() -> frozenset[str]:
    """Every record type some module provides."""
    types: frozenset[str] = frozenset()
    for spec in load_modules():
        types |= spec.record_types
    return types


def is_module_record_type(record_type: str) -> bool:
    return record_type in module_record_types()


def bound_psets(conn: Connection, record_type: str, record_id: str) -> tuple[str, ...]:
    """The psets the record's class binds to it: ``()`` for a record no module binds psets to."""
    for spec in load_modules():
        if record_type in spec.record_types and spec.bound_psets is not None:
            return spec.bound_psets(conn, record_type, record_id)
    return ()


def ledger_numbering_patterns(conn: Connection) -> list[NumberingPattern]:
    """The numbering patterns the modules read from the ledger, module by module."""
    patterns: list[NumberingPattern] = []
    for spec in load_modules():
        if spec.numbering_patterns is not None:
            patterns.extend(spec.numbering_patterns(conn))
    return patterns
