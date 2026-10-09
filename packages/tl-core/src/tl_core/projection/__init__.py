"""Projections: disposable read models rebuilt from the ledger (brief 5.4)."""

from tl_core.projection.registry import InMemoryRegistry
from tl_core.projection.types import Projector, ProjectorRegistry

__all__ = ["InMemoryRegistry", "Projector", "ProjectorRegistry"]
