"""Read package files and select what a scope adopts (brief 27.4).

``PackageRegistry`` holds every known ``PackageDoc`` and answers "which packages does scope X
adopt?". It does no schema resolution: that is ``tl_schema.compose``. It is rebuilt from the
directory when files change; nothing here writes to disk.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from tl_schema.effective import canonical_dump
from tl_schema.packages import PackageDoc, version_tuple

SCHEMA_DIR_ENV = "TL_SCHEMA_DIR"
#: ``schema/fixtures`` at the repository root; the default package directory in development.
DEFAULT_SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "fixtures"

_PROJECT_SCOPE = "project:"


class PackageError(ValueError):
    """A package file or package set that cannot be loaded. The message names the source."""


def default_schema_dir() -> Path:
    """The directory in ``TL_SCHEMA_DIR`` when that is set and non-empty, else the default."""
    configured = os.environ.get(SCHEMA_DIR_ENV)
    return Path(configured) if configured else DEFAULT_SCHEMA_DIR


def parse_package(text: str, *, source: str = "<string>") -> PackageDoc:
    """Parse YAML text into a ``PackageDoc``.

    Raises ``PackageError`` whose message starts with ``source`` for: invalid YAML, a document that
    is not a mapping, or a pydantic ``ValidationError`` (one line per error, ``<loc>: <message>``).
    """
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackageError(f"{source}: invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        kind = type(data).__name__
        raise PackageError(f"{source}: a package file must be a YAML mapping, not {kind}")
    try:
        return PackageDoc.model_validate(data)
    except ValidationError as exc:
        problems: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "(document)"
            problems.append(f"{location}: {error['msg']}")
        raise PackageError(f"{source}: " + "; ".join(problems)) from exc


def load_package(path: Path) -> PackageDoc:
    """Read and parse one package file.

    The file name must be ``<package>@<version>.yaml``; a mismatch raises ``PackageError``.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PackageError(f"{path}: cannot read package file: {exc}") from exc
    doc = parse_package(text, source=str(path))
    expected = f"{doc.key()}.yaml"
    if path.name != expected:
        raise PackageError(f"{path}: file name must be {expected}, not {path.name}")
    return doc


class PackageRegistry:
    """An in-memory set of package documents, at most one per ``package@version``."""

    def __init__(self, docs: Iterable[PackageDoc] = ()) -> None:
        self._docs: dict[tuple[str, str], PackageDoc] = {}
        for doc in docs:
            self.add(doc)

    @classmethod
    def from_directory(cls, directory: Path) -> PackageRegistry:
        """Load every ``*.yaml`` file of ``directory`` in sorted order.

        A missing directory raises ``PackageError``. An empty one gives an empty registry.
        """
        if not directory.is_dir():
            raise PackageError(f"{directory}: package directory does not exist")
        return cls(load_package(path) for path in sorted(directory.glob("*.yaml")))

    def add(self, doc: PackageDoc) -> None:
        """Add a document. A second ``package@version`` raises ``PackageError``."""
        slot = (doc.package, doc.version)
        if slot in self._docs:
            raise PackageError(f"{doc.key()}: already registered")
        self._docs[slot] = doc

    def names(self) -> list[str]:
        """Sorted package names."""
        return sorted({name for name, _ in self._docs})

    def versions(self, name: str) -> list[str]:
        """Versions of ``name`` in ascending semantic-version order; ``[]`` when unknown."""
        found = [version for doc_name, version in self._docs if doc_name == name]
        return sorted(found, key=version_tuple)

    def get(self, name: str, version: str) -> PackageDoc:
        """The document ``name@version``; ``PackageError`` when absent."""
        try:
            return self._docs[(name, version)]
        except KeyError:
            raise PackageError(f"{name}@{version}: not registered") from None

    def latest(self, name: str) -> PackageDoc:
        """The highest version of ``name``; ``PackageError`` when the name is unknown."""
        versions = self.versions(name)
        if not versions:
            raise PackageError(f"{name}: no package of that name is registered")
        return self.get(name, versions[-1])

    def projects(self) -> list[str]:
        """Sorted ids of the projects that have an extension or project package."""
        return sorted({doc.project for doc in self._docs.values() if doc.project is not None})

    def adopted(self, scope: str) -> list[PackageDoc]:
        """The documents ``scope`` adopts, one version per package. See the ticket for the rules.

        ``company``: the latest version of every company package.
        ``project:<id>``: for each extension or project package of that project the highest
        version; the company versions its ``depends`` pin; and the latest version of every other
        company package. Two pins of one company package at different versions raise
        ``PackageError``. Result order: company, then extension, then project documents, each
        sorted by package name. A scope other than ``company`` or ``project:<id>`` raises
        ``ValueError``.
        """
        if scope == "company":
            company = _highest(doc for doc in self._docs.values() if doc.kind == "company")
            return [company[name] for name in sorted(company)]
        if not scope.startswith(_PROJECT_SCOPE) or scope == _PROJECT_SCOPE:
            raise ValueError(f"unknown scope {scope!r}; use 'company' or 'project:<id>'")
        return self._project_adoption(scope[len(_PROJECT_SCOPE) :])

    def _project_adoption(self, project: str) -> list[PackageDoc]:
        """The adopted documents of ``project:<project>`` (rules in ``adopted``)."""
        own = _highest(doc for doc in self._docs.values() if doc.project == project)
        pins: dict[str, str] = {}
        for name in sorted(own):
            for dep, version in own[name].depends.items():
                stored = self._docs.get((dep, version))
                if stored is not None and stored.kind != "company":
                    continue  # a dependency on a non-company package is reported by check()
                existing = pins.get(dep)
                if existing is not None and existing != version:
                    raise PackageError(
                        f"project:{project}: {dep} is pinned at both {existing} and {version}"
                    )
                pins[dep] = version
        company = _highest(doc for doc in self._docs.values() if doc.kind == "company")
        for dep, version in pins.items():
            company[dep] = self.get(dep, version)
        extensions = [own[name] for name in sorted(own) if own[name].kind == "extension"]
        projects = [own[name] for name in sorted(own) if own[name].kind == "project"]
        return [company[name] for name in sorted(company)] + extensions + projects

    def check(self) -> None:
        """Cross-document checks; raises one ``PackageError`` listing every problem found.

        Every ``depends`` entry must name a stored ``package@version`` of kind ``company``; every
        ``extends`` reference must name a stored company package that has that pset.
        """
        problems: list[str] = []
        for doc in self._sorted_docs():
            for dep, version in doc.depends.items():
                stored = self._docs.get((dep, version))
                if stored is None:
                    problems.append(f"{doc.key()}: depends on {dep}@{version}, not found")
                elif stored.kind != "company":
                    problems.append(
                        f"{doc.key()}: depends on {dep}@{version}, which is not a company package"
                    )
            for extension in doc.extends:
                package, version, pset = extension.target()
                base = self._docs.get((package, version))
                if base is None or base.kind != "company":
                    problems.append(
                        f"{doc.key()}: extends {extension.ref}, but no such company package"
                    )
                elif pset not in base.psets:
                    problems.append(
                        f"{doc.key()}: extends {extension.ref}, but {base.key()} has no pset {pset}"
                    )
        if problems:
            raise PackageError("; ".join(problems))

    def fingerprint(self) -> str:
        """SHA-256 hex over the sorted ``name@version`` and canonical JSON of every document.

        Changes when any document is added or changed; equal registries give equal fingerprints.
        """
        parts = [
            f"{doc.key()}\n{canonical_dump(doc.model_dump(mode='json'))}"
            for doc in self._sorted_docs()
        ]
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def _sorted_docs(self) -> list[PackageDoc]:
        """Every stored document, sorted by ``doc.key()``."""
        return sorted(self._docs.values(), key=lambda doc: doc.key())


def _highest(docs: Iterable[PackageDoc]) -> dict[str, PackageDoc]:
    """The highest version of each package name among ``docs``, by semantic version."""
    best: dict[str, PackageDoc] = {}
    for doc in docs:
        current = best.get(doc.package)
        if current is None or version_tuple(doc.version) > version_tuple(current.version):
            best[doc.package] = doc
    return best
