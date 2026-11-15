"""The form-source registry (ADR-0031; the pattern of ``tl_core.qr.registry``).

Sources are plugins found through the entry-point group ``throughline.form_sources``. A plugin that
fails to load, returns something that is not a source, or shares a record type with another raises
:class:`FormSourceLoadError`: never a silent gap. The message keeps the exception type only.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points

from tl_core.forms.types import FORM_SOURCE_ENTRY_POINT, MAX_SOURCES, FormSource

log = logging.getLogger(__name__)


class FormSourceLoadError(Exception):
    """An installed form source could not be loaded, or two claim one record type."""


def load_form_sources(
    entry_points_: Iterable[EntryPoint] | None = None,
) -> dict[str, FormSource]:
    """The sources by record type, sorted by record type.

    ``entry_points_`` lets a test inject plugins; the default reads the group
    ``throughline.form_sources``.
    """
    points = entry_points(group=FORM_SOURCE_ENTRY_POINT) if entry_points_ is None else entry_points_
    found: dict[str, FormSource] = {}
    count = 0
    for entry in sorted(points, key=lambda e: e.name):
        count += 1
        try:
            produced = entry.load()()
        except Exception as exc:
            log.warning("form source %r cannot be loaded: %s", entry.name, exc, exc_info=True)
            raise FormSourceLoadError(
                f"form source {entry.name!r} cannot be loaded: {type(exc).__name__}"
            ) from exc
        if not isinstance(produced, FormSource):
            raise FormSourceLoadError(
                f"form source {entry.name!r}: its entry point must return a FormSource"
            )
        record_type = produced.record_type
        if record_type in found:
            raise FormSourceLoadError(f"form source for {record_type!r} is declared twice")
        found[record_type] = produced
    if count > MAX_SOURCES:
        raise FormSourceLoadError(f"more than {MAX_SOURCES} form sources are installed")
    return dict(sorted(found.items()))
