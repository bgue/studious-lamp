"""The scan-card provider registry (ADR-0030; the pattern of ``tl_core.readiness.registry``).

Providers are plugins found through the entry-point group ``throughline.scan_cards``. A plugin
that fails to load, returns something that is not a provider, or shares a record type with another
raises :class:`ScanCardLoadError`: never a silent gap. The message keeps the exception type only;
the full text goes to the server log.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import EntryPoint, entry_points

from tl_core.qr.types import MAX_PROVIDERS, SCAN_CARD_ENTRY_POINT, ScanCardProvider

log = logging.getLogger(__name__)


class ScanCardLoadError(Exception):
    """An installed scan-card provider could not be loaded, or two claim one record type."""


def load_scan_cards(
    entry_points_: Iterable[EntryPoint] | None = None,
) -> dict[str, ScanCardProvider]:
    """The providers by record type, sorted by record type.

    ``entry_points_`` is an iterable of entry points (a test injects plugins); the default reads
    the group ``throughline.scan_cards``. Raises :class:`ScanCardLoadError` for a plugin that does
    not load or does not return a ``ScanCardProvider``, for two providers of one record type, and
    when more than ``MAX_PROVIDERS`` are installed.
    """
    points = entry_points(group=SCAN_CARD_ENTRY_POINT) if entry_points_ is None else entry_points_
    found: dict[str, ScanCardProvider] = {}
    count = 0
    for entry in sorted(points, key=lambda e: e.name):
        count += 1
        try:
            produced = entry.load()()
        except Exception as exc:
            log.warning(
                "scan card provider %r cannot be loaded: %s", entry.name, exc, exc_info=True
            )
            raise ScanCardLoadError(
                f"scan card provider {entry.name!r} cannot be loaded: {type(exc).__name__}"
            ) from exc
        if not isinstance(produced, ScanCardProvider):
            raise ScanCardLoadError(
                f"scan card provider {entry.name!r}: its entry point must return a ScanCardProvider"
            )
        record_type = produced.record_type
        if record_type in found:
            raise ScanCardLoadError(f"scan card provider for {record_type!r} is declared twice")
        found[record_type] = produced
    if count > MAX_PROVIDERS:
        raise ScanCardLoadError(f"more than {MAX_PROVIDERS} scan card providers are installed")
    return dict(sorted(found.items()))
