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

import importlib
import logging
import re
import threading
from collections.abc import Callable, Collection, Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import Connection, text

from tl_core.numbering.config import NumberingPattern
from tl_core.projection.types import Projector
from tl_core.services.commands import Command, CommandResult
from tl_core.uow import UnitOfWork

_log = logging.getLogger("tl_core.modules")

if TYPE_CHECKING:
    from tl_core.actions import ActionsHook
    from tl_core.confidentiality import Viewer
    from tl_core.extypes.registry import UowFactory
    from tl_core.schema_provider import RegistrySource

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


#: What the person who accepts a proposal must hold: ``user`` is any signed-in person.
ProposalAccess = Literal["user", "controller", "admin"]
ProposalHandler = Callable[[UnitOfWork, Any], CommandResult]


@dataclass(frozen=True)
class ProposableCommand:
    """A module command an agent may *propose* through an MCP tool (ADR-0014 section 8).

    ``tool`` is the proposal's tool name (it must not collide with a core tool), ``model`` and
    ``handler`` the command and its handler. ``access`` is required and has no default: accepting
    the proposal runs the command as the accepting person, who must hold that access (the role
    check of the API route or the CLI), so a command is never proposable without someone having
    decided who may approve it.
    """

    tool: str
    model: type[Command]
    handler: ProposalHandler
    access: ProposalAccess
    #: ``False`` for a command only a rule proposes (``EscalateTechnical``, ADR-0019): it can be
    #: accepted like any proposal but names no agent tool, so no tool mode is offered for it.
    agent_tool: bool = True


_SQL_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
_TYPE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*")


@dataclass(frozen=True)
class ChildSource:
    """Records whose class is the class of a root record (ADR-0016): a revision takes its
    document's.

    ``record_types`` are the child record types, ``table`` their module table with the
    ``id_column`` and the ``root_column`` that holds the root record's id. When the child hangs on
    the root through another table (a processing job on a derived document on a document), give
    ``hop`` as ``(table, key_column, root_column)``: ``root_column`` of the child then holds the key
    of that table's row and the root id is the hop's ``root_column``. A child is readable only
    when its root is; a child with no row, or no root, is hidden.
    """

    record_types: frozenset[str]
    table: str
    id_column: str
    root_column: str
    hop: tuple[str, str, str] | None = None


@dataclass(frozen=True)
class ConfidentialSource:
    """A module's declaration that some record types carry a confidentiality class (ADR-0016).

    ``table`` holds one row per record (``id_column``) with the class in ``class_column``;
    ``null_class`` is what a NULL class means (``None``: nothing, so NULL is hidden). With a
    ``clearance_table`` (record and account columns) a ``privileged`` record is also readable by
    the accounts named there. A record of ``record_types`` with no row in ``table`` is hidden.
    """

    record_types: frozenset[str]
    table: str
    id_column: str
    class_column: str
    null_class: str | None = None
    clearance_table: str | None = None
    clearance_record_column: str = "record_id"
    clearance_account_column: str = "account"
    children: tuple[ChildSource, ...] = ()

    def __post_init__(self) -> None:
        names = [self.table, self.id_column, self.class_column]
        names += [self.clearance_table] if self.clearance_table else []
        names += [self.clearance_record_column, self.clearance_account_column]
        for child in self.children:
            names += [child.table, child.id_column, child.root_column]
            names += list(child.hop) if child.hop else []
        types = set(self.record_types)
        for child in self.children:
            types |= child.record_types
        if (
            any(_SQL_NAME.fullmatch(n) is None for n in names)
            or any(_TYPE_NAME.fullmatch(t) is None for t in types)
            or self.null_class not in (None, "internal", "restricted")
        ):
            raise ModuleLoadError(f"confidential source {self.table!r} has an unusable name")


class ModuleLoadError(RuntimeError):
    """An installed module could not be loaded, or two modules claim the same name or type."""


class ModuleHookError(ModuleLoadError):
    """A hook reference of an installed module does not resolve (fixed text, no ref echoed)."""


HookKind = Literal["commands", "read_routers", "tools", "cli_groups", "reports"]

_REF = re.compile(r"[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*:[A-Za-z][A-Za-z0-9_]*")

#: The modules shipped in this repository (ADR-0029, P2-X4 decision Q1). Only these may name a
#: surface package (``tl_api.routes.``, ``tl_mcp.``, ``tl_cli.``) for a hook; any other module may
#: name its own ``tl_mod_<name>`` package and nothing else.
IN_TREE_SURFACES = frozenset(
    {
        "awp",
        "correspondence",
        "cost",
        "documents",
        "engineering",
        "legacy",
        "materials",
        "quality",
        "requisitions",
        "scaffold",
        "schedule",
        "schemareg",
    }
)

_SURFACE_PREFIX: dict[str, str] = {
    "read_routers": "tl_api.routes.",
    "tools": "tl_mcp.",
    "cli_groups": "tl_cli.",
    "reports": "tl_cli.",
}


def _check_ref(name: str, kind: str, ref: str) -> None:
    """Refuse a hook ref of the wrong shape or outside the places ``kind`` may load from.

    The one function that holds the prefix rule: a different rule is a change here only. The
    error names the module and the field, never the ref. An item that is not text is refused the
    same way (it never reaches the pattern, so no ``TypeError`` leaks out).
    """
    if not isinstance(ref, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ModuleLoadError(f"module {name!r}: {kind} must hold text references")
    if _REF.fullmatch(ref) is None:
        raise ModuleLoadError(f"module {name!r}: {kind} has a malformed reference")
    if kind == "cli_groups":  # the group is named by the attribute: ``app`` or ``<x>_app``
        attr = ref.split(":", 1)[1]
        if attr != "app" and not (attr.endswith("_app") and len(attr) > len("_app")):
            raise ModuleLoadError(f"module {name!r}: {kind} names no group attribute")
    package = ref.split(":", 1)[0]
    own = f"tl_mod_{name}"
    if package == own or package.startswith(own + "."):
        return
    surface = _SURFACE_PREFIX.get(kind)
    if surface is not None and name in IN_TREE_SURFACES and package.startswith(surface):
        return
    raise ModuleLoadError(f"module {name!r}: {kind} names a place it may not load from")


def _no_commands() -> dict[str, frozenset[str]]:
    return {}


def _no_guards() -> dict[tuple[str, str], GenericGuard]:
    return {}


def _no_actions() -> dict[str, ActionsHook]:
    return {}


def _no_words() -> dict[str, str]:
    return {}


def _no_meta() -> Mapping[str, str]:
    return {}


@dataclass(frozen=True)
class ModuleCommand:
    """A command a module owns, as the module declares it (ADR-0029).

    ``handler`` keeps its signature ``(UnitOfWork, Any) -> CommandResult``. ``meta`` carries
    ``delegation`` (``eligible`` or ``excluded:<reason>``; missing means excluded).
    """

    module: str
    model: type[Command]
    handler: ProposalHandler
    access: str
    needs_holds: bool = False
    takes_roles: bool = False
    meta: Mapping[str, str] = field(default_factory=_no_meta)

    @property
    def name(self) -> str:
        return self.model.__name__


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
    #: Module commands an agent may propose, each with the access the accepting person needs.
    proposable: Sequence[ProposableCommand] = ()
    #: Record types of this module that carry a confidentiality class (ADR-0016). The core filters
    #: every read by them; a module that declares none has no confidential records.
    confidential: Sequence[ConfidentialSource] = ()
    #: ``(uow_factory)`` to the module's contribution to the effective schema (the schema registry
    #: module: published packages, pins, waivers). A process attaches it to its schema provider
    #: where it opens its ledger (``tl_core.extypes.provider.attach``). Module-less processes and
    #: modules without one are unaffected.
    schema_source: Callable[[UowFactory], RegistrySource] | None = None
    #: Per record type, the hook that says which of the module's commands the viewer may run on a
    #: record now (``tl_core.actions``, P1-UX2). A pure function over the module's own rows and the
    #: ``holds`` the caller passes; the table it reads (command, record types, states, level) is the
    #: one the command handlers read, so the offer and the refusal cannot drift. A type that is not
    #: a key is offered nothing.
    actions: Mapping[str, ActionsHook] = field(default_factory=_no_actions)
    #: Command class name -> access word, for the module's own commands (ADR-0021, module roles).
    #: A word is declared as the module's ``CommandSpec`` has it: a table word, a platform word, or
    #: a fine word (``awp.cwp.release``) that ``command_index()`` reads as its table word, once.
    command_words: Mapping[str, str] = field(default_factory=_no_words)
    #: Whether the module accepts ``company``-scope role grants (answer 14 of the wave-0 spec).
    company_roles: bool = False
    #: Per record type, the ``user`` commands that only draft it offline (offline-classes spec,
    #: section 4). A key is a type of this module whose class is ``draft_only``; every command is a
    #: ``command_words`` entry with the word ``user``. ``check_offline`` validates it at load.
    offline_drafts: Mapping[str, frozenset[str]] = field(default_factory=_no_commands)
    #: Hook references, `"<dotted.module>:<Name>"`, resolved lazily by `resolve_hook` (ADR-0029).
    #: ``commands`` names a tuple of command rows, or a zero-argument callable that returns one.
    commands: str | None = None
    #: Read routers, MCP tool registrars and CLI groups, in registration order.
    read_routers: Sequence[str] = ()
    tools: Sequence[str] = ()
    cli_groups: Sequence[str] = ()
    #: Each names a sequence of ``Report`` rows (``tl report <name>``; V3-P0). A module names its
    #: own ``tl_mod_<name>`` package; an in-tree module may name ``tl_cli.`` for a report that needs
    #: another module's views.
    reports: Sequence[str] = ()

    def __post_init__(self) -> None:
        if self.commands is not None:
            _check_ref(self.name, "commands", self.commands)
        for kind in ("read_routers", "tools", "cli_groups", "reports"):
            refs = getattr(self, kind)
            if isinstance(refs, str):
                raise ModuleLoadError(f"module {self.name!r}: {kind} must be a sequence")
            for ref in refs:
                _check_ref(self.name, kind, ref)
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
        for record_type in self.actions:
            if record_type not in self.record_types:
                raise ModuleLoadError(
                    f"module {self.name!r}: actions names {record_type!r}, "
                    "which is not one of its record types"
                )
        for source in self.confidential:
            claimed = set(source.record_types)
            for child in source.children:
                claimed |= child.record_types
            if not claimed <= self.record_types:
                raise ModuleLoadError(
                    f"module {self.name!r}: a confidential source names record types it does "
                    "not own"
                )
        for record_type in self.record_types:
            if not record_type.startswith(f"{self.name}."):
                raise ModuleLoadError(
                    f"module {self.name!r}: record type {record_type!r} must start with "
                    f"{self.name + '.'!r}"
                )


def check_offline(spec: ModuleSpec) -> None:
    """Refuse a module whose offline behaviour is inconsistent (``ModuleLoadError``).

    Every record type has a class in ``OFFLINE_CLASSES``; an ``offline_drafts`` key is a type the
    module owns whose class is ``draft_only``; every drafting command carries the word ``user``.
    """
    from tl_schema.generated.offline_classes import OFFLINE_CLASSES  # read-only generated data

    for record_type in sorted(spec.record_types):
        if record_type not in OFFLINE_CLASSES:
            raise ModuleLoadError(
                f"module {spec.name!r}: record type {record_type!r} has no offline class "
                "(declare tl:offline in the schema)"
            )
    for record_type, commands in sorted(spec.offline_drafts.items()):
        if record_type not in spec.record_types:
            raise ModuleLoadError(
                f"module {spec.name!r}: offline_drafts names {record_type!r}, "
                "which is not one of its record types"
            )
        if OFFLINE_CLASSES[record_type] != "draft_only":
            raise ModuleLoadError(
                f"module {spec.name!r}: offline_drafts lists commands for {record_type!r}, "
                f"whose offline class is {OFFLINE_CLASSES[record_type]!r}, not 'draft_only'"
            )
        for command in sorted(commands):
            word = spec.command_words.get(command)
            if word is None:
                raise ModuleLoadError(
                    f"module {spec.name!r}: offline_drafts lists {command!r} for {record_type!r}, "
                    "which is not in command_words"
                )
            if _table_word(word) != "user":
                raise ModuleLoadError(
                    f"module {spec.name!r}: offline_drafts lists {command!r} for {record_type!r}, "
                    f"whose access word is {word!r}, not 'user'"
                )


def _table_word(word: str) -> str:
    """A declared access word as the resolver reads it (a fine word becomes its table word)."""
    from tl_core.auth.module_roles import normalise_word  # avoid an import cycle

    return normalise_word(word)


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
        check_offline(produced)
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
    actor: str | None = None,
) -> None:
    """``require_generic_command``, the module role check, and the module's state guard.

    The guard (``ModuleSpec.generic_guards``) sees the record as it is now: the same command may be
    allowed in one state and refused in another. A core or extension type passes.

    When ``actor`` is given and the type is a module's, the actor needs the access word ``user`` for
    that module on the record's scope (``ForbiddenError``; ADR-0021): a generic command on a module
    record is a working act. Every handler passes ``cmd.actor``; a caller with no actor (a read-side
    offer) gets the allow-list and the guard only.
    """
    from tl_core import confidentiality  # avoid an import cycle
    from tl_core.services.errors import RecordNotFoundError

    # A hidden record does not exist (ADR-0016): say so before saying anything about its type
    if confidentiality.is_hidden(conn, record_id):
        raise RecordNotFoundError(f"no record {record_id!r}")
    require_generic_command(record_type, command)
    if actor is not None:
        _require_user_word(conn, record_type, command, record_id, actor)
    for spec in load_modules():
        guard = spec.generic_guards.get((record_type, command))
        if guard is not None:
            guard(conn, record_id, slot)


def _require_user_word(
    conn: Connection, record_type: str, command: str, record_id: str, actor: str
) -> None:
    """The module role check of ``require_generic``: the word ``user`` for the type's module."""
    from tl_core.auth.module_roles import holder_for_actor, require_word  # avoid an import cycle

    owner = next((spec.name for spec in load_modules() if record_type in spec.record_types), None)
    if owner is None:  # a core or extension type: no module role
        return
    scope = conn.execute(
        text("SELECT scope FROM cur_core_record WHERE id = :id"), {"id": record_id}
    ).scalar_one_or_none()
    if scope is None:  # no such record: the caller reports that
        return
    require_word(
        conn,
        holder_for_actor(conn, actor),
        scope=str(scope),
        module=owner,
        word="user",
        what=command,
    )


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


def module_proposables() -> dict[str, ProposableCommand]:
    """The modules' proposable commands by tool name; two modules claiming a tool is an error."""
    found: dict[str, ProposableCommand] = {}
    for spec in load_modules():
        for item in spec.proposable:
            if item.tool in found:
                raise ModuleLoadError(f"proposal tool {item.tool!r} is declared twice")
            found[item.tool] = item
    return found


def confidential_stream_types() -> frozenset[str]:
    """The record types of every confidential source and of its children (ADR-0016): the streams
    whose events are about a record a viewer may not be allowed to read."""
    types: set[str] = set()
    for source in confidential_sources():
        types |= source.record_types
        for child in source.children:
            types |= child.record_types
    return frozenset(types)


def confidential_sources() -> list[ConfidentialSource]:
    """Every module's confidential sources, module by module in name order (ADR-0016)."""
    found: list[ConfidentialSource] = []
    for spec in load_modules():
        found.extend(spec.confidential)
    return found


def schema_sources() -> list[Callable[[UowFactory], RegistrySource]]:
    """The modules' schema source factories, in module name order (P1-I8)."""
    return [spec.schema_source for spec in load_modules() if spec.schema_source is not None]


def _unresolved(spec: ModuleSpec, kind: str) -> ModuleHookError:
    return ModuleHookError(f"module {spec.name!r}: hook {kind!r} cannot be resolved")


def _refs(spec: ModuleSpec, kind: str) -> tuple[str, ...]:
    if kind == "commands":
        return (spec.commands,) if spec.commands else ()
    if kind in _SURFACE_PREFIX:
        return tuple(getattr(spec, kind))
    raise ValueError(f"unknown hook kind {kind!r}")


def _as_command(spec: ModuleSpec, row: Any) -> ModuleCommand:
    meta = getattr(row, "meta", None)
    return ModuleCommand(
        module=spec.name,
        model=row.model,
        handler=row.handler,
        access=row.access,
        needs_holds=bool(getattr(row, "needs_holds", False)),
        takes_roles=bool(getattr(row, "takes_roles", False)),
        meta=MappingProxyType(dict(meta)) if meta else MappingProxyType({}),
    )


def resolve_hook(spec: ModuleSpec, kind: str) -> tuple[object, ...]:
    """Import and return the objects a spec's hook names (lazily; never at ``ModuleSpec`` build).

    For ``commands`` the rows become ``ModuleCommand``. Any failure raises ``ModuleHookError``
    with a fixed text that carries neither the ref nor the exception.
    """
    refs = _refs(spec, kind)
    try:
        found: list[object] = []
        for ref in refs:
            package, attr = ref.split(":", 1)
            found.append(getattr(importlib.import_module(package), attr))
        if kind != "commands":
            return tuple(found)
        if not found:
            return ()
        table = found[0]
        if callable(table):
            table = table()
        return tuple(_as_command(spec, row) for row in table)  # type: ignore[attr-defined]
    except Exception:
        raise _unresolved(spec, kind) from None


@dataclass(frozen=True)
class Report:
    """One line-level report of a module (``tl report <name>``; V3-P0).

    ``rows`` yields one mapping per record the ``viewer`` may read, keyed by ``columns`` (other keys
    are never written, so an internal id stays out); a hidden record is simply not yielded. It runs
    inside the viewer's read scope and pages through the module's own list view.
    """

    name: str  # kebab-case, unique across modules: ``rfis``, ``form-submissions``
    title: str
    columns: Sequence[str]
    rows: Callable[[Connection, str, Viewer], Iterable[Mapping[str, Any]]]


def module_reports() -> dict[str, Report]:
    """Every module's reports by name, in module name order. A module whose ``reports`` hook does
    not resolve is skipped with the fixed warning; a name declared twice raises ``ModuleLoadError``.
    """
    found: dict[str, Report] = {}
    for spec in load_modules():
        try:
            tables = resolve_hook(spec, "reports")
        except ModuleHookError as exc:
            _log.warning("%s", exc)
            continue
        for table in tables:
            for row in table:  # type: ignore[attr-defined]
                if not isinstance(row, Report):
                    continue
                if row.name in found:
                    raise ModuleLoadError(f"report {row.name!r} is declared twice")
                found[row.name] = row
    return found


def core_command_names() -> frozenset[str]:
    """The class names of every ``tl_core`` command imported so far (a module's never count)."""
    names: set[str] = set()
    seen: set[type] = set()
    stack: list[type] = [Command]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
                if sub.__module__.startswith("tl_core."):
                    names.add(sub.__name__)
    return frozenset(names)


def refused_hook(spec: ModuleSpec, kind: str) -> ModuleHookError:
    """The fixed error for a hook a surface refuses (a name that is already a core one)."""
    return _unresolved(spec, kind)


def _collect_commands(
    reserved: Collection[str] = (),
) -> tuple[list[ModuleCommand], dict[str, str], frozenset[str]]:
    """Rows, failures by module, and the modules refused for naming a ``reserved`` command."""
    rows: list[ModuleCommand] = []
    failures: dict[str, str] = {}
    refused: set[str] = set()
    for spec in load_modules():
        try:
            resolved = resolve_hook(spec, "commands")
        except ModuleHookError as exc:
            failures[spec.name] = str(exc)
            continue
        mine = [row for row in resolved if isinstance(row, ModuleCommand)]
        if any(row.name in reserved for row in mine):
            failures[spec.name] = str(refused_hook(spec, "commands"))
            refused.add(spec.name)
            continue
        rows.extend(mine)
    return rows, failures, frozenset(refused)


def module_commands(reserved: Collection[str] = ()) -> tuple[ModuleCommand, ...]:
    """Every module's commands, module by module in name order, rows in declared order.

    A module whose ``commands`` hook fails is skipped (see ``hook_failures``). A module that
    declares a command named in ``reserved`` (the core command names) is skipped whole, with one
    warning of the fixed text; it never replaces a core row. A command name declared twice, by
    two modules or twice in one, raises ``ModuleLoadError``: an ambiguous name stops the process.
    """
    rows, failures, refused = _collect_commands(reserved)
    for module in sorted(refused):
        _log.warning("%s", failures[module])
    owner: dict[str, str] = {}
    for row in rows:
        if row.name in owner:
            first, second = sorted((owner[row.name], row.module))
            raise ModuleLoadError(f"command {row.name!r} is declared by {first!r} and {second!r}")
        owner[row.name] = row.module
    return tuple(rows)


def hook_failures(reserved: Collection[str] = ()) -> dict[str, str]:
    """Module name to the fixed message, for modules whose ``commands`` hook did not resolve
    (or, given ``reserved``, was refused for naming a core command)."""
    return _collect_commands(reserved)[1]
