"""Where services get the effective schema of a scope (brief 27.3).

The command and query signatures of the pset services carry no registry, so they ask the
process-wide provider. The default provider reads the package directory named by ``TL_SCHEMA_DIR``
(else ``schema/fixtures``) and notices changed files on its own, so a package edit takes effect on
the next call: that is the hot reload of brief 27.3. Tests and embedders install their own
provider with ``use_provider``.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tl_schema.compose import compose
from tl_schema.effective import EffectiveSchema
from tl_schema.registry import PackageRegistry, default_schema_dir


class SchemaProvider(Protocol):
    def effective(self, scope: str) -> EffectiveSchema:
        """The effective schema of ``scope`` (``company`` or ``project:<id>``)."""
        ...

    def scopes(self) -> list[str]:
        """``company`` and every ``project:<id>`` that has packages."""
        ...


@dataclass(frozen=True)
class SchemaChange:
    scope: str
    old_hash: str | None
    new_hash: str


def _signature(directory: Path) -> tuple[tuple[str, int, int], ...]:
    """Name, mtime and size of every package file: cheap to compute, changes on any edit."""
    if not directory.is_dir():
        return ()
    entries: list[tuple[str, int, int]] = []
    for path in sorted(directory.glob("*.yaml")):
        stat = path.stat()
        entries.append((path.name, stat.st_mtime_ns, stat.st_size))
    return tuple(entries)


class DirectorySchemaProvider:
    """Loads packages from a directory and composes effective schemas, cached until files change."""

    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory
        self._lock = threading.Lock()
        self._signature: tuple[tuple[str, int, int], ...] | None = None
        self._registry = PackageRegistry()
        self._cache: dict[str, EffectiveSchema] = {}

    @property
    def directory(self) -> Path:
        return self._directory if self._directory is not None else default_schema_dir()

    def _refresh(self) -> None:
        signature = _signature(self.directory)
        if signature == self._signature:
            return
        registry = PackageRegistry.from_directory(self.directory)
        registry.check()
        self._registry = registry
        self._cache = {}
        self._signature = signature

    def registry(self) -> PackageRegistry:
        with self._lock:
            self._refresh()
            return self._registry

    def effective(self, scope: str) -> EffectiveSchema:
        with self._lock:
            self._refresh()
            cached = self._cache.get(scope)
            if cached is None:
                cached = compose(self._registry.adopted(scope), scope)
                self._cache[scope] = cached
            return cached

    def scopes(self) -> list[str]:
        with self._lock:
            self._refresh()
            return ["company", *(f"project:{p}" for p in self._registry.projects())]

    def reload(self) -> list[SchemaChange]:
        """Re-read the directory now and report scopes whose effective hash differs.

        Compares against the schemas this provider had cached (a scope never asked for before has
        ``old_hash`` ``None``).
        """
        with self._lock:
            before = {scope: schema.hash for scope, schema in self._cache.items()}
            self._signature = None
            self._refresh()
            scopes = ["company", *(f"project:{p}" for p in self._registry.projects())]
            changes: list[SchemaChange] = []
            for scope in scopes:
                schema = compose(self._registry.adopted(scope), scope)
                self._cache[scope] = schema
                if before.get(scope) != schema.hash:
                    changes.append(SchemaChange(scope, before.get(scope), schema.hash))
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
