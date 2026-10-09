"""The projectors every ledger gets by default."""

from __future__ import annotations

from tl_core.projection.links import LinkProjector
from tl_core.projection.pset import PsetProjector
from tl_core.projection.record import RecordProjector
from tl_core.projection.registry import InMemoryRegistry


def default_registry() -> InMemoryRegistry:
    """A fresh registry holding the built-in projectors. Later tickets register theirs here."""
    registry = InMemoryRegistry()
    registry.register(RecordProjector())
    registry.register(PsetProjector())  # after RecordProjector: it updates the rows that creates
    registry.register(LinkProjector())  # after RecordProjector: counts read the record's scope
    return registry
