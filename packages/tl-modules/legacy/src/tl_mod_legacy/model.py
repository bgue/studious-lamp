"""What the stages pass between them: the grid, the loader definition, the loaders found."""

from __future__ import annotations

import csv
import io
import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Literal

LOADER_ENTRY_POINT = "throughline.loaders"
TargetKind = Literal["tags", "documents"]


@dataclass(frozen=True)
class Grid:
    """The rows of a file as read: column names in file order and one list of cells per row."""

    columns: list[str]
    rows: list[list[str | None]]

    def to_csv(self) -> str:
        """The grid as comma-separated text (what the module import readers take)."""
        out = io.StringIO()
        writer = csv.writer(out, delimiter=",", lineterminator="\n")
        writer.writerow(self.columns)
        for row in self.rows:
            writer.writerow(["" if cell is None else cell for cell in row])
        return out.getvalue()


@dataclass(frozen=True)
class LoaderDef:
    """One loader: a legacy file kind, how to read it, where its rows go.

    ``mapping_text`` is a mapping template of the target's import (the YAML form of
    ``tl_mod_engineering.imports.mapping`` or ``tl_mod_documents.imports.mapping``); its
    ``delimiter`` is replaced by a comma, because the stages hand the readers the grid as CSV.
    ``sheet`` and ``header_row`` are options of the tabular extractor.
    """

    name: str
    system: str
    table: str
    target: TargetKind
    description: str
    mapping_text: str
    file_types: tuple[str, ...] = ("csv", "xlsx")
    sheet: str | None = None
    header_row: int = 1
    #: The class documents are registered with (``None``: internal). A register that lists
    #: restricted documents is loaded as ``restricted``, and a controller declassifies afterwards.
    confidentiality: str | None = None


_lock = threading.Lock()
_found: dict[str, LoaderDef] | None = None
_override: dict[str, LoaderDef] | None = None


class LoaderLoadError(RuntimeError):
    """An installed loader cannot be loaded or is declared twice."""


def _discover() -> dict[str, LoaderDef]:
    found: dict[str, LoaderDef] = {}
    for entry in sorted(entry_points(group=LOADER_ENTRY_POINT), key=lambda e: e.name):
        try:
            produced = entry.load()()
        except Exception as exc:
            raise LoaderLoadError(
                f"loader {entry.name!r} cannot be loaded: {type(exc).__name__}"
            ) from exc
        if not isinstance(produced, LoaderDef) or produced.name != entry.name:
            raise LoaderLoadError(f"loader entry point {entry.name!r} must return its LoaderDef")
        found[produced.name] = produced
    return found


def load_loaders() -> Mapping[str, LoaderDef]:
    """The installed loaders by name, found once per process."""
    global _found
    with _lock:
        if _override is not None:
            return _override
        if _found is None:
            _found = _discover()
        return _found


@contextmanager
def use_loaders(loaders: Mapping[str, LoaderDef]) -> Generator[None]:
    """Make ``loaders`` the only loaders for the block (tests)."""
    global _override
    with _lock:
        previous, _override = _override, dict(loaders)
    try:
        yield
    finally:
        with _lock:
            _override = previous
