"""Where services get the effective schema of a scope (brief 27.3).

The command and query signatures of the pset services carry no registry, so they ask the
process-wide provider. The default provider reads the package directory named by ``TL_SCHEMA_DIR``
(else ``schema/fixtures``) and notices changed files on its own, so a package edit takes effect on
the next call: that is the hot reload of brief 27.3. Tests and embedders install their own
provider with ``use_provider``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tl_schema.compile import SchemaCompileError
from tl_schema.compose import compose
from tl_schema.effective import EffectiveSchema
from tl_schema.packages import PackageDoc, WaiverDef, version_tuple
from tl_schema.registry import PackageError, PackageRegistry, default_schema_dir

from tl_core.services.errors import InvalidScopeError

_SCOPE_PATTERN = re.compile(r"company|project:[A-Za-z0-9_.-]+")

log = logging.getLogger("tl_core.schema_provider")
log.addHandler(logging.NullHandler())


class SchemaProvider(Protocol):
    def effective(self, scope: str) -> EffectiveSchema:
        """The effective schema of ``scope`` (``company`` or ``project:<id>``)."""
        ...

    def scopes(self) -> list[str]:
        """``company`` and every ``project:<id>`` that has packages."""
        ...


class ReloadableSchemaProvider(SchemaProvider, Protocol):
    def reload(self) -> list[SchemaChange]:
        """Re-read the packages now; report scopes whose effective hash changed."""
        ...


class ExtensionSource(Protocol):
    """Package documents that do not come from the directory: registered extension types.

    ``token()`` must be cheap and change whenever ``documents()`` would; the provider asks it on
    every call and rebuilds only when it changed (``tl_core.extypes.provider`` implements it).
    """

    def token(self) -> str: ...

    def documents(self) -> list[PackageDoc]: ...


@dataclass(frozen=True)
class RegistryState:
    """What the schema registry holds that the effective schema depends on (P1-I8).

    ``documents`` are the published (and deprecated) packages, parsed; ``pins`` maps a project
    scope to ``{company package name: version}``; ``waivers`` maps a project scope to its approved
    waivers (an expired one may be among them: the evaluator checks the date).
    """

    documents: Sequence[PackageDoc] = ()
    pins: Mapping[str, Mapping[str, str]] = field(default_factory=lambda: {})
    waivers: Mapping[str, Sequence[WaiverDef]] = field(default_factory=lambda: {})

    def projects(self) -> set[str]:
        """Project ids named by a pin, a waiver or a package of the registry."""
        found = {d.project for d in self.documents if d.project is not None}
        for scope in (*self.pins, *self.waivers):
            if scope.startswith("project:"):
                found.add(scope.removeprefix("project:"))
        return found


class RegistrySource(Protocol):
    """The ledgered schema registry as the provider sees it (``tl_mod_schemareg.source``).

    ``token()`` must be cheap and change whenever ``snapshot()`` would; the provider asks it on
    every call and rebuilds only when it changed. A source that cannot answer returns an empty
    state: the registry must never take the directory's packages down with it.
    """

    def token(self) -> str: ...

    def snapshot(self) -> RegistryState: ...


@dataclass(frozen=True)
class SchemaChange:
    scope: str
    old_hash: str | None
    new_hash: str


def _signature(directory: Path) -> tuple[tuple[str, str], ...]:
    """File name and SHA-256 of the bytes of every package file.

    Content, not mtime or size, decides whether anything changed: a same-size edit inside one
    mtime tick is still noticed, and ``touch`` alone is not a change. Package files are small.
    """
    if not directory.is_dir():
        return ()
    entries: list[tuple[str, str]] = []
    for path in sorted(directory.glob("*.yaml")):
        entries.append((path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return tuple(entries)


class DirectorySchemaProvider:
    """Loads packages from a directory and composes effective schemas, cached until files change.

    A project scope that has no project packages gets the company effective schema composed for
    that scope: the same company psets, with the scope in the hash (brief 6.3 adoption: mandatory
    and default psets reach every project).

    ``reload()`` reports changes against what the previous ``reload()`` reported, so an edit that
    ``effective()`` noticed first is still reported once (the ``Schema.EffectiveChanged`` hook
    relies on that). It is all-or-nothing: if any scope fails to compose, the old state stays.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._lock = threading.Lock()
        self._signature: tuple[tuple[str, str], ...] | None = None
        self._extensions: ExtensionSource | None = None
        self._extension_token: str | None = None
        self._extension_docs: list[PackageDoc] = []
        self._registry_source: RegistrySource | None = None
        self._registry_token: str | None = None
        self._registry_state = RegistryState()
        self._registry = PackageRegistry()
        self._cache: dict[str, EffectiveSchema] = {}
        self._reported: dict[
            str, str
        ] = {}  # scope -> hash last returned by reload(); never cleared
        self._by_hash: dict[str, EffectiveSchema] = {}  # every schema composed so far

    @property
    def directory(self) -> Path:
        return self._directory if self._directory is not None else default_schema_dir()

    def _remember(self, schema: EffectiveSchema) -> None:
        self._by_hash[schema.hash] = schema

    def attach_extensions(self, source: ExtensionSource | None) -> None:
        """Include the documents of ``source`` (registered extension types) in every scope."""
        with self._lock:
            self._extensions = source
            self._extension_token = None
            self._extension_docs = []
            self._cache = {}

    def attach_registry(self, source: RegistrySource | None) -> None:
        """Include the published packages, pins and waivers of ``source`` (the schema registry)."""
        with self._lock:
            self._registry_source = source
            self._registry_token = None
            self._registry_state = RegistryState()
            self._signature = None  # the registry is rebuilt on the next call
            self._cache = {}

    def _build_registry(self, state: RegistryState) -> PackageRegistry:
        """The directory's packages plus the registry's published ones.

        A published package that does not fit (a dependency missing, a name taken by a file) is
        left out and logged: a bad registry entry must not take the directory's schema down.
        """
        registry = PackageRegistry.from_directory(self.directory)
        registry.check()
        for doc in sorted(state.documents, key=lambda d: (d.package, version_tuple(d.version))):
            if registry.origin(doc.package, doc.version) is not None:
                log.warning("registry package %s is also a file; the file wins", doc.key())
                continue
            registry.add(doc, origin="ledger")
            try:
                registry.check()
            except PackageError as exc:
                registry.discard(doc.package, doc.version)
                log.warning("registry package %s left out: %s", doc.key(), exc)
        return registry

    def _refresh(self) -> None:
        signature = _signature(self.directory)
        token = self._extensions.token() if self._extensions is not None else None
        registry_token = (
            self._registry_source.token() if self._registry_source is not None else None
        )
        if signature != self._signature or registry_token != self._registry_token:
            if self._registry_source is not None:
                self._registry_state = self._registry_source.snapshot()
            self._registry = self._build_registry(self._registry_state)
            self._cache = {}
            self._signature = signature
            self._registry_token = registry_token
        if self._extensions is not None and token != self._extension_token:
            self._extension_docs = self._extensions.documents()
            self._extension_token = token
            self._cache = {}
        elif self._extensions is None and self._extension_docs:
            self._extension_docs = []
            self._cache = {}

    def _compose(
        self,
        registry: PackageRegistry,
        scope: str,
        state: RegistryState | None = None,
        *,
        strict: bool = False,
    ) -> EffectiveSchema:
        """The scope's schema: directory packages plus the extension documents that compose.

        A type that cannot join (its pset name collides with a package that arrived later) is
        left out rather than taking the whole scope's schema down.
        """
        held = state if state is not None else self._registry_state
        base = self._adopted(registry, scope, held, strict=strict)
        waivers = list(held.waivers.get(scope, ()))
        extra = self._extension_docs
        if not extra:
            return self._compose_waived(base, scope, waivers)
        try:
            return self._compose_waived([*base, *extra], scope, waivers)
        except SchemaCompileError:
            kept: list[PackageDoc] = []
            for doc in extra:
                try:
                    compose([*base, *kept, doc], scope)
                except SchemaCompileError:
                    continue
                kept.append(doc)
            return self._compose_waived([*base, *kept], scope, waivers)

    @staticmethod
    def _adopted(
        registry: PackageRegistry, scope: str, state: RegistryState, *, strict: bool = False
    ) -> list[PackageDoc]:
        """The adopted documents of ``scope``, honouring the pins of the registry.

        A pin that no longer fits (the registry refuses it) is left out and logged, so a scope
        falls back to the directory's versions instead of having no schema.
        """
        pins = dict(state.pins.get(scope, {}))
        try:
            return registry.adopted(scope, pins)
        except PackageError as exc:
            if strict or not pins:
                raise
            log.warning("pins of %s ignored: %s", scope, exc)
            return registry.adopted(scope)

    @staticmethod
    def _compose_waived(
        docs: Sequence[PackageDoc], scope: str, waivers: Sequence[WaiverDef]
    ) -> EffectiveSchema:
        """Compose with the registry's waivers; one that names a missing property is dropped."""
        if not waivers:
            return compose(docs, scope)
        try:
            return compose(docs, scope, extra_waivers=waivers)
        except SchemaCompileError as exc:
            if exc.rule != "unknown_property":
                raise
        kept: list[WaiverDef] = []
        for waiver in waivers:
            try:
                compose(docs, scope, extra_waivers=[*kept, waiver])
            except SchemaCompileError as exc:
                if exc.rule != "unknown_property":
                    raise
                log.warning("waiver for %s left out: %s", waiver.path, exc)
                continue
            kept.append(waiver)
        return compose(docs, scope, extra_waivers=kept)

    def registry(self) -> PackageRegistry:
        with self._lock:
            self._refresh()
            return self._registry

    def effective(self, scope: str) -> EffectiveSchema:
        """The effective schema of ``scope``; raises ``InvalidScopeError`` for a malformed scope."""
        if _SCOPE_PATTERN.fullmatch(scope) is None:
            raise InvalidScopeError(f"scope must be 'company' or 'project:<id>', got {scope!r}")
        with self._lock:
            self._refresh()
            cached = self._cache.get(scope)
            if cached is None:
                cached = self._compose(self._registry, scope)
                self._cache[scope] = cached
                self._remember(cached)
            return cached

    def trial(
        self,
        scope: str,
        add: Sequence[PackageDoc] = (),
        *,
        pins: Mapping[str, str] | None = None,
    ) -> EffectiveSchema:
        """The schema ``scope`` would have with ``add`` published and ``pins`` as its pins.

        Nothing is saved or cached: this answers "what if" for the workbench (impact, the compose
        check before a package is submitted or published). ``pins`` replaces the scope's pins when
        given. Raises ``PackageError`` or ``SchemaCompileError`` when the result does not hold
        together, and ``InvalidScopeError`` for a malformed scope.
        """
        if _SCOPE_PATTERN.fullmatch(scope) is None:
            raise InvalidScopeError(f"scope must be 'company' or 'project:<id>', got {scope!r}")
        with self._lock:
            self._refresh()
            trial = self._registry.copy()
            for doc in add:
                trial.add(doc, origin="ledger")
            trial.check()
            held = self._registry_state
            state = RegistryState(
                documents=held.documents,
                pins={**held.pins, scope: dict(pins)} if pins is not None else held.pins,
                waivers=held.waivers,
            )
            return self._compose(trial, scope, state, strict=True)

    def pins_of(self, scope: str) -> Mapping[str, str]:
        """The pins the registry holds for ``scope`` (package name to version)."""
        with self._lock:
            self._refresh()
            return dict(self._registry_state.pins.get(scope, {}))

    def effective_by_hash(self, schema_hash: str) -> EffectiveSchema | None:
        """A schema this provider composed earlier, by its hash (or ``None``)."""
        with self._lock:
            return self._by_hash.get(schema_hash)

    def scopes(self) -> list[str]:
        with self._lock:
            self._refresh()
            projects = {*self._registry.projects(), *self._registry_state.projects()}
            return ["company", *(f"project:{p}" for p in sorted(projects))]

    def reload(self) -> list[SchemaChange]:
        """Re-read the directory now and report scopes whose hash differs from the last report.

        A scope never reported before has ``old_hash`` ``None``. Every scope is composed before
        anything is replaced; if one raises, the provider keeps its previous state and the error
        propagates.
        """
        with self._lock:
            signature = _signature(self.directory)
            state = self._registry_state
            registry_token = self._registry_token
            if self._registry_source is not None:
                registry_token = self._registry_source.token()
                state = self._registry_source.snapshot()
            registry = self._build_registry(state)
            if self._extensions is not None:
                token = self._extensions.token()
                self._extension_docs = self._extensions.documents()
                self._extension_token = token
            projects = {*registry.projects(), *state.projects()}
            scopes = ["company", *(f"project:{p}" for p in sorted(projects))]
            fresh = {scope: self._compose(registry, scope, state) for scope in scopes}
            self._registry = registry
            self._registry_state = state
            self._registry_token = registry_token
            self._signature = signature
            self._cache = dict(fresh)
            changes: list[SchemaChange] = []
            for scope, schema in fresh.items():
                self._remember(schema)
                if self._reported.get(scope) != schema.hash:
                    changes.append(SchemaChange(scope, self._reported.get(scope), schema.hash))
                self._reported[scope] = schema.hash
            return changes


_provider: SchemaProvider = DirectorySchemaProvider()
_provider_lock = threading.Lock()


def get_provider() -> SchemaProvider:
    with _provider_lock:
        return _provider


def set_provider(provider: SchemaProvider) -> SchemaProvider:
    """Install ``provider`` process-wide; returns the previous one."""
    global _provider
    with _provider_lock:
        previous, _provider = _provider, provider
    return previous


@contextmanager
def use_provider(provider: SchemaProvider) -> Generator[SchemaProvider]:
    """Install ``provider`` for the block, then restore the previous one."""
    previous = set_provider(provider)
    try:
        yield provider
    finally:
        set_provider(previous)
