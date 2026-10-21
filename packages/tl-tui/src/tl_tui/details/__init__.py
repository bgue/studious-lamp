"""The Details tab as rows: one renderer per record type, the generic envelope rows otherwise.

A renderer is a function ``(client, project, record, labels) -> list[DetailRow]`` registered for
one or more record types with ``@register("documents.Document")``. Every module of this package
is imported once, the first time ``details_for`` runs, so a screen ticket adds one module here and
nothing else. ``details_for`` never raises: a renderer that fails gives the generic rows and one
note line. Rows marked ``technical`` are dropped unless the display mode is technical.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tl_tui.client import ClientInterface
from tl_tui.display import DisplayMode, Labels

NOTE_LABEL = "Note"
NOTE_TEXT = "More details could not be loaded"


@dataclass(frozen=True)
class DetailRow:
    label: str
    value: str
    technical: bool = False  # shown only in technical mode


DetailRenderer = Callable[[ClientInterface, str, dict[str, Any], Labels], list[DetailRow]]

_RENDERERS: dict[str, DetailRenderer] = {}
_loaded = False


def register(*record_types: str) -> Callable[[DetailRenderer], DetailRenderer]:
    """Register the decorated renderer for these record types (``module.Type``)."""

    def decorate(renderer: DetailRenderer) -> DetailRenderer:
        for record_type in record_types:
            _RENDERERS[record_type] = renderer
        return renderer

    return decorate


def _load_renderers() -> None:
    """Import every module of this package once."""
    global _loaded  # noqa: PLW0603
    if _loaded:
        return
    _loaded = True
    for info in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{info.name}")


def details_for(
    client: ClientInterface,
    project: str,
    record: dict[str, Any],
    labels: Labels,
    mode: DisplayMode,
) -> list[DetailRow]:
    """The rows for ``record``: its type's renderer, else the generic rows (technical by mode)."""
    from tl_tui.details.generic import generic_rows  # noqa: PLC0415

    _load_renderers()
    renderer = _RENDERERS.get(str(record.get("type")))
    if renderer is None:
        rows = generic_rows(record, labels)
    else:
        try:
            rows = renderer(client, project, record, labels)
        except Exception:  # noqa: BLE001  a renderer must never take the screen down
            rows = [*generic_rows(record, labels), DetailRow(NOTE_LABEL, NOTE_TEXT)]
    return [row for row in rows if mode.technical or not row.technical]
