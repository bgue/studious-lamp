"""Finding enricher plugins (FANOUT D6; brief §18.9).

An enricher is code shipped in the repository and registered under the entry-point group
``throughline.enrichers`` (``ENRICHER_ENTRY_POINT``). An admin registers one *by name*; nobody
supplies code. Phase 1 refuses a plugin whose ``model_ref`` is set (ADR-0008 decision 8: no model
call, no spend), so a registration that names one cannot be stored and cannot be switched on.

``use_enrichers`` replaces the entry points for the length of a block, so tests run a plugin of
their own (and an engine test does not depend on the shipped classifier).
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from importlib.metadata import entry_points

from tl_core.integration.contract import ENRICHER_ENTRY_POINT, Enricher

EnricherFactory = Callable[[], Enricher]

_overrides: Mapping[str, EnricherFactory] | None = None


@contextmanager
def use_enrichers(plugins: Mapping[str, EnricherFactory]) -> Generator[None]:
    """Make ``plugins`` the only registered enrichers inside the block."""
    global _overrides
    before = _overrides
    _overrides = plugins
    try:
        yield
    finally:
        _overrides = before


def _factory(name: str) -> EnricherFactory | None:
    if _overrides is not None:
        return _overrides.get(name)
    for point in entry_points(group=ENRICHER_ENTRY_POINT):
        if point.name == name:
            return point.load()
    return None


def load_enricher(name: str) -> Enricher | None:
    """A fresh instance of the plugin registered as ``name``, or ``None``.

    A plugin that cannot be loaded or built counts as absent (the registration then cannot be
    stored or switched on); the error is not shown, as it may name a path.
    """
    try:
        factory = _factory(name)
        return None if factory is None else factory()
    except Exception:
        return None


def why_unusable(plugin: Enricher | None, name: str) -> str | None:
    """Why a registration cannot use ``plugin``; ``None`` when it can."""
    if plugin is None:
        return f"no enricher plugin is installed as {name}"
    if plugin.name != name:
        return f"the plugin installed as {name} calls itself {plugin.name}"
    if plugin.model_ref is not None:
        return "Phase 1 runs deterministic enrichers only (no model call, no spend)"
    return None


__all__ = ["EnricherFactory", "load_enricher", "use_enrichers", "why_unusable"]
