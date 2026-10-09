"""The projectors every ledger gets by default."""

from __future__ import annotations

from tl_core.projection.files import FileProjector
from tl_core.projection.links import LinkProjector
from tl_core.projection.numbering import NumberingProjector
from tl_core.projection.pset import PsetProjector
from tl_core.projection.record import RecordProjector
from tl_core.projection.registry import InMemoryRegistry
from tl_core.projection.workflow import WorkflowProjector


def default_registry() -> InMemoryRegistry:
    """A fresh registry holding the built-in projectors. Later tickets register theirs here."""
    registry = InMemoryRegistry()
    registry.register(RecordProjector())
    registry.register(PsetProjector())  # after RecordProjector: it updates the rows that creates
    registry.register(LinkProjector())  # after RecordProjector: counts read the record's scope
    registry.register(NumberingProjector())
    registry.register(WorkflowProjector())  # after RecordProjector: it updates that row
    registry.register(FileProjector())  # independent of the record row: files carry their scope
    return registry
