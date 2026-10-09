"""The projectors every ledger gets by default."""

from __future__ import annotations

from tl_core.projection.registry import InMemoryRegistry


def default_registry() -> InMemoryRegistry:
    """A fresh registry holding the built-in projectors. Later tickets register theirs here."""
    registry = InMemoryRegistry()
    return registry
