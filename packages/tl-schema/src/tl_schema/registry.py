"""Read package files and select what a scope adopts (brief 27.4).

``PackageRegistry`` holds every known ``PackageDoc`` and answers "which packages does scope X
adopt?". It does no schema resolution: that is ``tl_schema.compose``. It is rebuilt from the
directory when files change; nothing here writes to disk.

STUB: the bodies below are implemented by P0-I2-T01. Signatures and docstrings are the contract.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from tl_schema.packages import PackageDoc

SCHEMA_DIR_ENV = "TL_SCHEMA_DIR"
#: ``schema/fixtures`` at the repository root; the default package directory in development.
DEFAULT_SCHEMA_DIR: Path = Path(__file__).resolve().parents[4] / "schema" / "fixtures"


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
    raise NotImplementedError


def load_package(path: Path) -> PackageDoc:
    """Read and parse one package file.

    The file name must be ``<package>@<version>.yaml``; a mismatch raises ``PackageError``.
    """
    raise NotImplementedError


class PackageRegistry:
    """An in-memory set of package documents, at most one per ``package@version``."""

    def __init__(self, docs: Iterable[PackageDoc] = ()) -> None:
        raise NotImplementedError

    @classmethod
    def from_directory(cls, directory: Path) -> PackageRegistry:
        """Load every ``*.yaml`` file of ``directory`` in sorted order.

        A missing directory raises ``PackageError``. An empty one gives an empty registry.
        """
        raise NotImplementedError

    def add(self, doc: PackageDoc) -> None:
        """Add a document. A second ``package@version`` raises ``PackageError``."""
        raise NotImplementedError

    def names(self) -> list[str]:
        """Sorted package names."""
        raise NotImplementedError

    def versions(self, name: str) -> list[str]:
        """Versions of ``name`` in ascending semantic-version order; ``[]`` when unknown."""
        raise NotImplementedError

    def get(self, name: str, version: str) -> PackageDoc:
        """The document ``name@version``; ``PackageError`` when absent."""
        raise NotImplementedError

    def latest(self, name: str) -> PackageDoc:
        """The highest version of ``name``; ``PackageError`` when the name is unknown."""
        raise NotImplementedError

    def projects(self) -> list[str]:
        """Sorted ids of the projects that have an extension or project package."""
        raise NotImplementedError

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
        raise NotImplementedError

    def check(self) -> None:
        """Cross-document checks; raises one ``PackageError`` listing every problem found.

        Every ``depends`` entry must name a stored ``package@version`` of kind ``company``; every
        ``extends`` reference must name a stored company package that has that pset.
        """
        raise NotImplementedError

    def fingerprint(self) -> str:
        """SHA-256 hex over the sorted ``name@version`` and canonical JSON of every document.

        Changes when any document is added or changed; equal registries give equal fingerprints.
        """
        raise NotImplementedError
